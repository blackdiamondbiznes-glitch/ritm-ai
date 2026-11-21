"""Tutor student HTTP API: the signed-in owner sees only their own rows."""

import os

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, OTHER = 9860000001, 9860000002
_IDS = (OWNER, OTHER)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
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


async def test_owner_crud_is_hidden_from_the_other_account(client) -> None:
    http, heads = client
    assert (await http.get("/api/tutor/students")).status == 401
    created = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali", "status": "debtor", "amount_uzs": 50000, "phone": "+998901112233"},
    )
    assert created.status == 200
    body = await created.json()
    assert body["counts"]["debtor"] == 1
    student_id = body["students"][0]["id"]
    other = await http.get("/api/tutor/students", headers=heads["other"])
    assert (await other.json())["students"] == []
    stolen = await http.patch(
        f"/api/tutor/students/{student_id}",
        headers=heads["other"],
        json={"name": "Hijack"},
    )
    assert stolen.status == 404
    edited = await http.patch(
        f"/api/tutor/students/{student_id}",
        headers=heads["owner"],
        json={"status": "paid"},
    )
    assert edited.status == 200
    paid = await edited.json()
    assert paid["students"][0]["status"] == "paid"
    assert paid["students"][0]["name"] == "Ali"
    removed = await http.delete(f"/api/tutor/students/{student_id}", headers=heads["owner"])
    assert removed.status == 200
    assert (await removed.json())["students"] == []
    blank = await http.post("/api/tutor/students", headers=heads["owner"], json={"name": "  "})
    assert blank.status == 400
    assert (await blank.json())["error"] == "empty"
