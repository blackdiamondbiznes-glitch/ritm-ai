"""Tutor lesson HTTP API: the signed-in owner sees only their own rows."""

import os

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, OTHER = 9850000001, 9850000002
_IDS = (OWNER, OTHER)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
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


async def test_lesson_follows_the_owner_student(client) -> None:
    http, heads = client
    student = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali", "status": "paid"},
    )
    student_id = (await student.json())["students"][0]["id"]
    created = await http.post(
        "/api/tutor/lessons",
        headers=heads["owner"],
        json={
            "title": "Algebra",
            "student_id": student_id,
            "starts_at": "2026-11-21T15:30",
            "status": "scheduled",
        },
    )
    assert created.status == 200
    body = await created.json()
    assert body["lessons"][0]["student_name"] == "Ali"
    assert body["lessons"][0]["starts_at"].startswith("2026-11-21T10:30:00")
    lesson_id = body["lessons"][0]["id"]
    other = await http.get("/api/tutor/lessons", headers=heads["other"])
    assert (await other.json())["lessons"] == []
    stolen = await http.patch(
        f"/api/tutor/lessons/{lesson_id}",
        headers=heads["other"],
        json={"status": "done"},
    )
    assert stolen.status == 404
    done = await http.patch(
        f"/api/tutor/lessons/{lesson_id}",
        headers=heads["owner"],
        json={"status": "done"},
    )
    assert (await done.json())["counts"]["done"] == 1
    blank = await http.post("/api/tutor/lessons", headers=heads["owner"], json={"title": " "})
    assert (await blank.json())["error"] == "empty"


async def test_summary_counts_debt_and_hides_the_other_owner(client) -> None:
    http, heads = client
    assert (await http.get("/api/tutor/summary")).status == 401
    await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali", "status": "debtor", "amount_uzs": 150000},
    )
    await http.post(
        "/api/tutor/lessons",
        headers=heads["owner"],
        json={"title": "Algebra", "status": "scheduled"},
    )
    summary = await http.get("/api/tutor/summary", headers=heads["owner"])
    body = await summary.json()
    assert body["students"]["debtor"] == 1
    assert body["students"]["debt_uzs"] == 150000
    assert body["lessons"]["scheduled"] == 1
    other = await (await http.get("/api/tutor/summary", headers=heads["other"])).json()
    assert other["students"]["debt_uzs"] == 0
    assert other["lessons"]["scheduled"] == 0
    me = await (await http.get("/api/me", headers=heads["owner"])).json()
    assert me["user"]["cabinet_niche"] == "tutor"
    enabled = await http.post("/api/tutor/enable", headers=heads["owner"], json={})
    assert enabled.status == 200
    assert (await enabled.json())["cabinet_niche"] == "tutor"
    again = await (await http.get("/api/me", headers=heads["owner"])).json()
    assert again["user"]["cabinet_niche"] == "tutor"
    kept = await http.get("/api/tutor/summary", headers=heads["owner"])
    assert (await kept.json())["students"]["debtor"] == 1
