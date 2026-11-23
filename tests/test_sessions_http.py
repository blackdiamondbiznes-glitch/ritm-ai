"""Timetable HTTP: owner isolation, active students, and a lesson beside the group."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.lessons import TutorLesson
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
OWNER, OTHER, STUDENT = 9863000001, 9863000002, 9863000003
_IDS = (OWNER, OTHER, STUDENT)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorLesson).where(TutorLesson.owner_id.in_(ids)))
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
                User(telegram_id=OWNER, full_name="Lola Karimova", language_code="uz"),
                User(telegram_id=OTHER, full_name="Other", language_code="uz"),
                User(telegram_id=STUDENT, full_name="Ali", language_code="uz"),
            ]
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        name: {"Authorization": f"Bearer {issue_session(telegram, secret, 600)}"}
        for name, telegram in (("owner", OWNER), ("other", OTHER), ("student", STUDENT))
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


def _window() -> tuple[str, str, set[str]]:
    today = datetime.now(TASHKENT).date()
    days = [today + timedelta(days=offset) for offset in range(14)]
    wanted = {day.isoformat() for day in days if day.isoweekday() in (1, 3, 5)}
    return today.isoformat(), days[-1].isoformat(), wanted


async def test_owner_week_hides_other_teachers_and_pending_groups(client) -> None:
    http, heads, sessions = client
    opening, closing, wanted = _window()
    created = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Ingliz", "weekdays": [1, 3, 5], "start": "18:00", "end": "19:30"},
    )
    assert created.status == 200
    group_id = (await created.json())["created_id"]
    listed = await http.get(
        f"/api/tutor/sessions?from={opening}&to={closing}", headers=heads["owner"]
    )
    assert listed.status == 200
    rows = await listed.json()
    mine = [row for row in rows if row["group_id"] == group_id]
    assert {row["starts_at"][:10] for row in mine} == wanted
    assert {row["starts_at"][11:16] for row in mine} == {"13:00"}
    assert {row["ends_at"][11:16] for row in mine} == {"14:30"}
    assert all(row["source"] == "schedule" and row["group_name"] == "Ingliz" for row in mine)
    hidden = await http.get(
        f"/api/tutor/sessions?from={opening}&to={closing}", headers=heads["other"]
    )
    assert hidden.status == 200 and (await hidden.json()) == []
    stolen = await http.patch(
        f"/api/tutor/sessions/{mine[0]['id']}",
        headers=heads["other"],
        json={"status": "cancelled"},
    )
    assert stolen.status == 404
    foreign = await http.post(
        f"/api/tutor/groups/{group_id}/sessions",
        headers=heads["other"],
        json={"title": "Sir", "starts_at": f"{opening}T10:00", "ends_at": f"{opening}T11:00"},
    )
    assert foreign.status == 404
    wide = await http.get(
        "/api/tutor/sessions?from=2026-01-01&to=2026-02-15", headers=heads["owner"]
    )
    assert wide.status == 400 and (await wide.json())["error"] == "range"
    long = await http.post(
        f"/api/tutor/groups/{group_id}/sessions",
        headers=heads["owner"],
        json={"title": "Uzun", "starts_at": f"{opening}T10:00", "ends_at": f"{opening}T17:00"},
    )
    assert long.status == 400 and (await long.json())["error"] == "span"

    card = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali Valiyev", "status": "paid", "group_ids": [group_id]},
    )
    assert card.status == 200
    student_id = (await card.json())["created_id"]
    pending = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Kutilmoqda", "weekdays": [2], "start": "09:00", "end": "10:00"},
    )
    pending_id = (await pending.json())["created_id"]
    async with sessions() as session:
        owner_id = (
            await session.execute(select(User.id).where(User.telegram_id == OWNER))
        ).scalar_one()
        row = (
            await session.execute(
                select(TutorStudent).where(
                    TutorStudent.owner_id == owner_id, TutorStudent.id == student_id
                )
            )
        ).scalar_one()
        row.telegram_id = STUDENT
        session.add(TutorGroupMember(group_id=pending_id, student_id=student_id, status="pending"))
        await session.commit()
    seen = await http.get("/api/me/sessions?days=14", headers=heads["student"])
    assert seen.status == 200
    learned = await seen.json()
    assert {row["group_name"] for row in learned} == {"Ingliz"}
    assert learned[0]["teacher_name"] == "Lola Karimova"
    own = await http.get("/api/me/sessions?days=14", headers=heads["owner"])
    assert own.status == 200 and (await own.json()) == []

    lesson = await http.post(
        "/api/tutor/lessons",
        headers=heads["owner"],
        json={"title": "Yakka", "starts_at": f"{opening}T09:00"},
    )
    assert lesson.status == 200
    mixed = await http.get(
        f"/api/tutor/sessions?from={opening}&to={opening}", headers=heads["owner"]
    )
    titles = {row["title"]: row for row in await mixed.json()}
    assert titles["Yakka"]["group_id"] is None and titles["Yakka"]["source"] == "manual"

    now = datetime.now(UTC)
    future = [row for row in mine if datetime.fromisoformat(row["starts_at"]) > now]
    assert len(future) >= 2
    moved = await http.patch(
        f"/api/tutor/sessions/{future[0]['id']}",
        headers=heads["owner"],
        json={"starts_at": f"{opening}T21:00", "ends_at": f"{opening}T22:00", "title": "Kochdi"},
    )
    assert moved.status == 200
    body = await moved.json()
    assert body["id"] == future[0]["id"] and body["title"] == "Kochdi"
    assert body["starts_at"].startswith(f"{opening}T16:00:00")
    cancelled = await http.patch(
        f"/api/tutor/sessions/{future[1]['id']}",
        headers=heads["owner"],
        json={"status": "cancelled"},
    )
    assert cancelled.status == 200 and (await cancelled.json())["status"] == "cancelled"
    shifted = await http.patch(
        f"/api/tutor/groups/{group_id}",
        headers=heads["owner"],
        json={"weekdays": [2], "start": "18:00", "end": "19:30"},
    )
    assert shifted.status == 200
    after = await http.get(
        f"/api/tutor/sessions?from={opening}&to={closing}", headers=heads["owner"]
    )
    by_id = {row["id"]: row for row in await after.json()}
    assert by_id[future[0]["id"]]["title"] == "Kochdi"
    assert by_id[future[1]["id"]]["status"] == "cancelled"


_ZOOM = "https://us05web.zoom.us/j/123456789?pwd=abc"


async def test_session_link_reaches_the_owner_week(client) -> None:
    http, heads, _sessions = client
    created = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={
            "name": "Ingliz",
            "weekdays": [1, 2, 3, 4, 5, 6, 7],
            "start": "23:00",
            "end": "23:30",
        },
    )
    group_id = (await created.json())["created_id"]
    today = datetime.now(TASHKENT).date().isoformat()
    rows = await (
        await http.get(f"/api/tutor/sessions?from={today}&to={today}", headers=heads["owner"])
    ).json()
    session_id = next(row["id"] for row in rows if row["group_id"] == group_id)
    saved = await http.patch(
        f"/api/tutor/sessions/{session_id}", headers=heads["owner"], json={"meeting_url": _ZOOM}
    )
    assert saved.status == 200 and (await saved.json())["meeting_url"] == _ZOOM
    bad = await http.patch(
        f"/api/tutor/sessions/{session_id}",
        headers=heads["owner"],
        json={"meeting_url": "ftp://x.uz/a"},
    )
    assert bad.status == 400 and (await bad.json())["error"] == "link"
    extra = await http.post(
        f"/api/tutor/groups/{group_id}/sessions",
        headers=heads["owner"],
        json={
            "title": "Qo'shimcha",
            "starts_at": f"{today}T07:00",
            "ends_at": f"{today}T08:00",
            "meeting_url": _ZOOM,
        },
    )
    assert extra.status == 200 and (await extra.json())["meeting_url"] == _ZOOM
