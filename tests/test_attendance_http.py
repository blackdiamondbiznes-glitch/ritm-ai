"""Attendance HTTP: owner isolation and the student's own history."""

import os
from datetime import datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.attendance import TutorAttendance
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
OWNER, OTHER, STUDENT = 9864200001, 9864200002, 9864200003
_IDS = (OWNER, OTHER, STUDENT)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    lessons = select(TutorLesson.id).where(TutorLesson.owner_id.in_(ids))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorAttendance).where(TutorAttendance.lesson_id.in_(lessons)))
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


async def test_marks_stay_with_the_owner_and_the_active_student(client) -> None:
    http, heads, sessions = client
    today = datetime.now(TASHKENT).date()
    opening = today.isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    created = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Ingliz", "weekdays": [1, 3, 5], "start": "18:00", "end": "19:30"},
    )
    group_id = (await created.json())["created_id"]
    ali = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali Valiyev", "status": "paid", "group_ids": [group_id]},
    )
    ali_id = (await ali.json())["created_id"]
    bex = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Bex", "status": "paid", "group_ids": [group_id]},
    )
    bex_id = (await bex.json())["created_id"]
    async with sessions() as session:
        link = (
            await session.execute(
                select(TutorGroupMember).where(
                    TutorGroupMember.group_id == group_id,
                    TutorGroupMember.student_id == bex_id,
                )
            )
        ).scalar_one()
        link.status = "pending"
        card = await session.get(TutorStudent, ali_id)
        card.telegram_id = STUDENT
        await session.commit()
    lesson = await http.post(
        f"/api/tutor/groups/{group_id}/sessions",
        headers=heads["owner"],
        json={"title": "Bugun", "starts_at": f"{opening}T09:00", "ends_at": f"{opening}T10:00"},
    )
    assert lesson.status == 200
    lesson_id = (await lesson.json())["id"]
    later = await http.post(
        f"/api/tutor/groups/{group_id}/sessions",
        headers=heads["owner"],
        json={"title": "Ertaga", "starts_at": f"{tomorrow}T09:00", "ends_at": f"{tomorrow}T10:00"},
    )
    later_id = (await later.json())["id"]
    hidden = await http.get(f"/api/tutor/sessions/{lesson_id}/attendance", headers=heads["other"])
    assert hidden.status == 404
    stolen = await http.put(
        f"/api/tutor/sessions/{lesson_id}/attendance",
        headers=heads["other"],
        json={"marks": [{"student_id": ali_id, "status": "present"}]},
    )
    assert stolen.status == 404
    pending = await http.put(
        f"/api/tutor/sessions/{lesson_id}/attendance",
        headers=heads["owner"],
        json={"marks": [{"student_id": bex_id, "status": "present"}]},
    )
    assert pending.status == 400 and (await pending.json())["error"] == "student"
    future = await http.put(
        f"/api/tutor/sessions/{later_id}/attendance",
        headers=heads["owner"],
        json={"marks": [{"student_id": ali_id, "status": "present"}]},
    )
    assert future.status == 400 and (await future.json())["error"] == "future"
    saved = await http.put(
        f"/api/tutor/sessions/{lesson_id}/attendance",
        headers=heads["owner"],
        json={
            "marks": [
                {"student_id": ali_id, "status": "present"},
            ]
        },
    )
    assert saved.status == 200
    body = await saved.json()
    assert body["status"] == "done"
    assert body["students"][0]["name"] == "Ali Valiyev"
    assert body["students"][0]["status"] == "present"
    assert all(row["student_id"] != bex_id for row in body["students"])
    month = today.strftime("%Y-%m")
    grid = await http.get(
        f"/api/tutor/groups/{group_id}/attendance?month={month}", headers=heads["owner"]
    )
    assert grid.status == 200
    stats = await grid.json()
    assert stats["students"][0]["rate"] == 1
    foreign = await http.get(
        f"/api/tutor/groups/{group_id}/attendance?month={month}", headers=heads["other"]
    )
    assert foreign.status == 404
    mine = await http.get(f"/api/me/attendance?group_id={group_id}", headers=heads["student"])
    assert mine.status == 200
    history = await mine.json()
    assert history["rate"] == 1
    assert history["marks"][0]["status"] == "present"
    assert history["group_name"] == "Ingliz"
    denied = await http.get(f"/api/me/attendance?group_id={group_id}", headers=heads["owner"])
    assert denied.status == 404
    missing = await http.get("/api/me/attendance", headers=heads["student"])
    assert missing.status == 400
