"""A cabinet is one workspace. One account can teach and study at the same time."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.db.repositories.groups import GroupRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.roles import RoleService
from app.services.workspaces import WorkspaceService
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
TEACH, STUDY = 9890000001, 9890000002
_IDS = (TEACH, STUDY, 9890000003)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
_ROOT = Path(__file__).resolve().parents[1]


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    group_ids = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(
        TutorGroupMember.__table__.delete().where(TutorGroupMember.group_id.in_(group_ids))
    )
    await session.execute(TutorGroup.__table__.delete().where(TutorGroup.owner_id.in_(ids)))
    await session.execute(TutorStudent.__table__.delete().where(TutorStudent.owner_id.in_(ids)))
    await session.execute(Workspace.__table__.delete().where(Workspace.owner_id.in_(ids)))
    await session.execute(User.__table__.delete().where(User.telegram_id.in_(_IDS)))


def _alembic(*args: str) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_ROOT,
        env={**os.environ, "DATABASE_URL": _URL},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=TEACH, full_name="Ali Valiyev", language_code="uz"),
                User(telegram_id=STUDY, full_name="Vali", language_code="uz"),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        "teach": {"Authorization": f"Bearer {issue_session(TEACH, secret, 600)}"},
        "study": {"Authorization": f"Bearer {issue_session(STUDY, secret, 600)}"},
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


def _group(name: str) -> dict:
    return {"name": name, "weekdays": [1], "start": "08:00", "end": "09:00"}


async def test_one_account_teaches_and_studies(client) -> None:
    http, heads, sessions = client
    own = await http.post("/api/tutor/groups", headers=heads["teach"], json=_group("Ingliz"))
    assert own.status == 200
    other = await http.post("/api/tutor/groups", headers=heads["study"], json=_group("Matematika"))
    assert other.status == 200
    other_id = (await other.json())["created_id"]
    hidden = await http.get(f"/api/tutor/groups/{other_id}", headers=heads["teach"])
    assert hidden.status == 404
    async with sessions() as session:
        teacher = (
            await session.execute(select(User).where(User.telegram_id == TEACH))
        ).scalar_one()
        group = await session.get(TutorGroup, other_id)
        assert group is not None
        card = TutorStudent(
            owner_id=group.owner_id,
            workspace_id=group.workspace_id,
            name="Ali Valiyev",
            status="paid",
            amount_uzs=0,
            telegram_id=TEACH,
            join_code="studycode1",
        )
        session.add(card)
        await session.flush()
        session.add(TutorGroupMember(group_id=group.id, student_id=card.id, status="active"))
        waiting = TutorGroup(
            owner_id=group.owner_id,
            workspace_id=group.workspace_id,
            name="Fizika",
            weekdays="2",
            start_min=600,
            end_min=660,
            enroll_code="waitcode01",
        )
        session.add(waiting)
        await session.flush()
        session.add(TutorGroupMember(group_id=waiting.id, student_id=card.id, status="pending"))
        own = (
            await session.execute(select(TutorGroup).where(TutorGroup.owner_id == teacher.id))
        ).scalar_one()
        mine = TutorStudent(
            owner_id=teacher.id,
            workspace_id=own.workspace_id,
            name="Ali Valiyev",
            status="paid",
            amount_uzs=0,
            telegram_id=TEACH,
            join_code="owncode001",
        )
        session.add(mine)
        await session.flush()
        session.add(TutorGroupMember(group_id=own.id, student_id=mine.id, status="active"))
        await session.commit()
        statements: list[str] = []

        def before(_c, _cur, statement, _p, _x, _m) -> None:
            statements.append(statement)

        event.listen(session.bind.sync_engine, "before_cursor_execute", before)
        try:
            await session.connection()
            statements.clear()
            roles = await RoleService(
                WorkspaceRepository(session), GroupRepository(session)
            ).for_user(teacher)
        finally:
            event.remove(session.bind.sync_engine, "before_cursor_execute", before)
    assert len(statements) <= 2
    assert roles["teaching"][0]["name"] == "Ali Valiyev"
    assert roles["teaching"][0]["groups"] == 1
    assert [item["group_name"] for item in roles["learning"]] == ["Matematika"]
    assert [item["group_name"] for item in roles["pending"]] == ["Fizika"]
    assert "Ingliz" not in [item["group_name"] for item in roles["learning"]]
    live = await http.get("/api/me/roles", headers=heads["teach"])
    assert live.status == 200
    assert (await live.json())["learning"][0]["group_name"] == "Matematika"
    stats = await http.get("/api/stats", headers=heads["teach"])
    body = await stats.json()
    assert body["modes"]["teaching"][0]["workspace_id"] == roles["teaching"][0]["workspace_id"]


async def test_ensure_is_idempotent_when_two_calls_race(client) -> None:
    _http, _heads, sessions = client

    async def once() -> int:
        async with sessions() as session:
            owner = (
                await session.execute(select(User).where(User.telegram_id == TEACH))
            ).scalar_one()
            row = await WorkspaceService(
                WorkspaceRepository(session), UserRepository(session)
            ).ensure(owner)
            await session.commit()
            return row.id

    first, second = await asyncio.gather(once(), once())
    assert first == second
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == TEACH))).scalar_one()
        count = (
            await session.execute(
                select(func.count()).select_from(Workspace).where(Workspace.owner_id == owner.id)
            )
        ).scalar_one()
        assert count == 1
        assert owner.cabinet_niche == "tutor"


async def test_upgrade_backfills_one_workspace_per_owner() -> None:
    _alembic("downgrade", "0024_reminder_due_index")
    engine = create_async_engine(_URL)
    try:
        await _seed_before_workspaces(engine)
        _alembic("upgrade", "head")
        await _assert_backfill(engine)
    finally:
        _alembic("upgrade", "head")
        await _wipe_backfill(engine)
        await engine.dispose()


async def _seed_before_workspaces(engine) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(text("DELETE FROM tutor_students WHERE join_code = 'backfill02'"))
        await session.execute(text("DELETE FROM tutor_groups WHERE enroll_code = 'backfill01'"))
        await session.execute(
            text("DELETE FROM users WHERE telegram_id IN (9890000003, 9890000004)")
        )
        await session.execute(
            text(
                "INSERT INTO users (telegram_id, full_name, cabinet_niche) "
                "VALUES (9890000003, 'Nora Karimova', 'tutor')"
            )
        )
        teacher = (
            await session.execute(
                text(
                    "INSERT INTO users (telegram_id, full_name) "
                    "VALUES (9890000004, '  ') RETURNING id"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO tutor_groups "
                "(owner_id, name, weekdays, start_min, end_min, enroll_code) "
                "VALUES (:owner, 'Tarix', '1', 480, 540, 'backfill01')"
            ),
            {"owner": teacher},
        )
        await session.execute(
            text(
                "INSERT INTO tutor_students (owner_id, name, status, join_code) "
                "VALUES (:owner, 'Pupil', 'paid', 'backfill02')"
            ),
            {"owner": teacher},
        )
        await session.commit()


async def _assert_backfill(engine) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT u.telegram_id, w.name, "
                    "(SELECT count(*) FROM tutor_groups g WHERE g.workspace_id = w.id), "
                    "(SELECT count(*) FROM tutor_students s WHERE s.workspace_id = w.id) "
                    "FROM workspaces w JOIN users u ON u.id = w.owner_id "
                    "WHERE u.telegram_id IN (9890000003, 9890000004)"
                )
            )
        ).all()
    found = {telegram: (name, groups, students) for telegram, name, groups, students in rows}
    assert found[9890000003][0] == "Nora Karimova"
    assert found[9890000004][0] == "Kabinet"
    assert found[9890000004][1:] == (1, 1)


async def _wipe_backfill(engine) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(
            text(
                "DELETE FROM tutor_group_members WHERE group_id IN ("
                "SELECT id FROM tutor_groups WHERE enroll_code = 'backfill01')"
            )
        )
        await session.execute(text("DELETE FROM tutor_groups WHERE enroll_code = 'backfill01'"))
        await session.execute(text("DELETE FROM tutor_students WHERE join_code = 'backfill02'"))
        await session.execute(
            text(
                "DELETE FROM workspaces WHERE owner_id IN ("
                "SELECT id FROM users WHERE telegram_id IN (9890000003, 9890000004))"
            )
        )
        await session.execute(
            text("DELETE FROM users WHERE telegram_id IN (9890000003, 9890000004)")
        )
        await session.commit()
