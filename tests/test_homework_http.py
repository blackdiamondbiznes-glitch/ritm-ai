"""Homework is on the topic, and only an active member sees it."""

import os

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, ACTIVE, PENDING = 9865300001, 9865300002, 9865300003
_IDS = (OWNER, ACTIVE, PENDING)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=OWNER, full_name="Lola", language_code="uz"),
                User(telegram_id=ACTIVE, full_name="Ali", language_code="uz"),
                User(telegram_id=PENDING, full_name="Vali", language_code="uz"),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(telegram, secret, 600)}"}
        for name, telegram in (("owner", OWNER), ("active", ACTIVE), ("pending", PENDING))
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_homework_is_visible_to_active_members_only(client) -> None:
    http, heads, sessions = client
    made = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Ingliz", "weekdays": [1], "start": "18:00", "end": "19:00"},
    )
    group_id = (await made.json())["created_id"]
    first = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali Valiyev", "status": "paid", "group_ids": [group_id]},
    )
    second = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Vali", "status": "paid", "group_ids": [group_id]},
    )
    active_id = (await first.json())["created_id"]
    pending_id = (await second.json())["created_id"]
    async with sessions() as session:
        ali = await session.get(TutorStudent, active_id)
        vali = await session.get(TutorStudent, pending_id)
        assert ali is not None and vali is not None
        ali.telegram_id = ACTIVE
        vali.telegram_id = PENDING
        link = (
            await session.execute(
                select(TutorGroupMember).where(
                    TutorGroupMember.group_id == group_id,
                    TutorGroupMember.student_id == pending_id,
                )
            )
        ).scalar_one()
        link.status = "pending"
        await session.commit()
    topic = await http.post(
        f"/api/tutor/groups/{group_id}/topics",
        headers=heads["owner"],
        json={
            "title": "Unit 1",
            "held_on": "2026-11-20",
            "homework": "Read page 4",
            "homework_due": "2026-11-25",
        },
    )
    sheet = await topic.json()
    assert topic.status == 200
    assert sheet["topic"]["homework"] == "Read page 4"
    assert sheet["topic"]["homework_due"] == "2026-11-25"
    long = await http.put(
        f"/api/tutor/groups/{group_id}/topics/{sheet['topic']['id']}/homework",
        headers=heads["owner"],
        json={"homework": "x" * 1001, "homework_due": "2026-11-25"},
    )
    assert long.status == 400 and (await long.json())["error"] == "long"
    seen = await (await http.get("/api/me/learning", headers=heads["active"])).json()
    assert seen["groups"][0]["homework"] == [
        {"topic": "Unit 1", "text": "Read page 4", "due_on": "2026-11-25"}
    ]
    waiting = await (await http.get("/api/me/learning", headers=heads["pending"])).json()
    assert waiting["groups"] == []
    assert all("homework" not in item for item in waiting["pending"])
    cleared = await http.put(
        f"/api/tutor/groups/{group_id}/topics/{sheet['topic']['id']}/homework",
        headers=heads["owner"],
        json={"homework": "", "homework_due": "2026-11-25"},
    )
    assert cleared.status == 200 and (await cleared.json())["homework"] is None
    again = await (await http.get("/api/me/learning", headers=heads["active"])).json()
    assert again["groups"][0]["homework"] == []
