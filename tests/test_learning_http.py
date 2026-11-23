"""GET /api/me/learning shows only the signed-in student's groups."""

import os
from datetime import datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.services.clock import TASHKENT
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
TEACH, PUPIL, OTHER = 9864900001, 9864900002, 9864900003
_IDS = (TEACH, PUPIL, OTHER)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    owners = select(User.id).where(User.telegram_id.in_(_IDS))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(owners))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(owners)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(owners)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(owners)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(telegram, secret, 600)}"}
        for name, telegram in (("teach", TEACH), ("pupil", PUPIL), ("other", OTHER))
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_learning_is_scoped_to_the_signed_in_student(client) -> None:
    http, heads, sessions = client
    async with sessions() as session:
        teach = User(telegram_id=TEACH, full_name="Lola Karimova", language_code="uz")
        pupil = User(telegram_id=PUPIL, full_name="Ali Valiyev", language_code="uz")
        other = User(telegram_id=OTHER, full_name="Begona", language_code="uz")
        session.add_all([teach, pupil, other])
        await session.flush()
        space = Workspace(owner_id=teach.id, vertical="tutor", name="Kabinet")
        own = Workspace(owner_id=pupil.id, vertical="tutor", name="O‘zim")
        session.add_all([space, own])
        await session.flush()
        english = TutorGroup(
            owner_id=teach.id,
            workspace_id=space.id,
            name="Ingliz tili",
            level="B1",
            weekdays="1",
            start_min=18 * 60,
            end_min=19 * 60,
            enroll_code="httpeng6",
        )
        waiting = TutorGroup(
            owner_id=teach.id,
            workspace_id=space.id,
            name="Fizika",
            weekdays="3",
            start_min=10 * 60,
            end_min=11 * 60,
            enroll_code="httpfiz6",
        )
        mine = TutorGroup(
            owner_id=pupil.id,
            workspace_id=own.id,
            name="Mening",
            weekdays="5",
            start_min=9 * 60,
            end_min=10 * 60,
            enroll_code="httpown6",
        )
        session.add_all([english, waiting, mine])
        await session.flush()
        card = TutorStudent(
            owner_id=teach.id,
            workspace_id=space.id,
            name="Ali Valiyev",
            status="paid",
            amount_uzs=0,
            telegram_id=PUPIL,
            join_code="http-ali",
        )
        self_card = TutorStudent(
            owner_id=pupil.id,
            workspace_id=own.id,
            name="Ali Valiyev",
            status="paid",
            amount_uzs=0,
            telegram_id=PUPIL,
            join_code="http-own",
        )
        session.add_all([card, self_card])
        await session.flush()
        now = datetime.now(TASHKENT)
        session.add_all(
            [
                TutorGroupMember(group_id=english.id, student_id=card.id, status="active"),
                TutorGroupMember(
                    group_id=waiting.id,
                    student_id=card.id,
                    status="pending",
                    created_at=now - timedelta(days=1),
                ),
                TutorGroupMember(group_id=mine.id, student_id=self_card.id, status="active"),
            ]
        )
        await session.commit()
    pupil_body = await http.get("/api/me/learning", headers=heads["pupil"])
    teacher_body = await http.get("/api/me/learning", headers=heads["teach"])
    other_body = await http.get("/api/me/learning", headers=heads["other"])
    assert pupil_body.status == 200
    payload = await pupil_body.json()
    assert [item["group"]["name"] for item in payload["groups"]] == ["Ingliz tili"]
    assert payload["groups"][0]["group"]["teacher_name"] == "Lola Karimova"
    assert [item["group_name"] for item in payload["pending"]] == ["Fizika"]
    assert "Mening" not in [item["group"]["name"] for item in payload["groups"]]
    assert await teacher_body.json() == {"groups": [], "pending": []}
    assert await other_body.json() == {"groups": [], "pending": []}
