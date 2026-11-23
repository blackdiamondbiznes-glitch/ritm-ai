"""Tutor group HTTP API: one student can sit in two of the owner's groups."""

import os

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, OTHER = 9840000001, 9840000002
_IDS = (OWNER, OTHER)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    await session.execute(
        delete(TutorGroupMember).where(
            TutorGroupMember.group_id.in_(select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids)))
        )
    )
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=OWNER, full_name="Owner", language_code="uz"),
                User(telegram_id=OTHER, full_name="Other", language_code="uz"),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        "owner": {"Authorization": f"Bearer {issue_session(OWNER, secret, 600)}"},
        "other": {"Authorization": f"Bearer {issue_session(OTHER, secret, 600)}"},
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_student_joins_two_groups_and_stays_hidden(client) -> None:
    http, heads = client
    student = await http.post(
        "/api/tutor/students", headers=heads["owner"], json={"name": "Ali", "status": "paid"}
    )
    student_id = (await student.json())["created_id"]
    morning = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={
            "name": "Ingliz",
            "level": "A1",
            "weekdays": [1, 3, 5],
            "start": "08:00",
            "end": "10:00",
        },
    )
    assert morning.status == 200
    first = (await morning.json())["created_id"]
    evening = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Matematika", "weekdays": [2, 4], "start": "10:30", "end": "12:30"},
    )
    second = (await evening.json())["created_id"]
    joined = await http.post(
        f"/api/tutor/groups/{first}/students",
        headers=heads["owner"],
        json={"student_id": student_id},
    )
    assert [item["name"] for item in (await joined.json())["members"]] == ["Ali"]
    await http.post(
        f"/api/tutor/groups/{second}/students",
        headers=heads["owner"],
        json={"student_id": student_id},
    )
    hidden = await http.get(f"/api/tutor/groups/{first}", headers=heads["other"])
    assert hidden.status == 404
    bad = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "X", "weekdays": [1], "start": "12:00", "end": "12:00"},
    )
    assert (await bad.json())["error"] == "time"
