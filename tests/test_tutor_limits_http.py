"""Free stops at 2 groups and 40 students. A Pro trial stops at 10 and 250."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.enrollment import EnrollmentService
from app.services.tutor_limits import TutorLimitError
from app.services.workspaces import WorkspaceService
from app.webapp.auth import issue_session, session_secret
from app.webapp.context import build_context
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
FREE, TRIAL = 9870000001, 9870000002
_IDS = (FREE, TRIAL)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    group_ids = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(group_ids)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.telegram_id.in_(_IDS)))


def _group(name: str) -> dict:
    return {"name": name, "weekdays": [1], "start": "08:00", "end": "09:00"}


@pytest.fixture
async def client():
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _purge(session)
        session.add_all(
            [
                User(telegram_id=FREE, full_name="Free", language_code="uz"),
                User(telegram_id=TRIAL, full_name="Trial", language_code="ru"),
            ]
        )
        await session.commit()
        trial = (await session.execute(select(User).where(User.telegram_id == TRIAL))).scalar_one()
        pro = (await session.execute(select(Plan).where(Plan.code == "pro"))).scalar_one()
        now = datetime.now(UTC)
        session.add(
            Subscription(
                owner_id=trial.id,
                plan_id=pro.id,
                status=SubscriptionStatus.TRIAL,
                source=SubscriptionSource.TRIAL,
                started_at=now,
                expires_at=now + timedelta(days=14),
            )
        )
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    heads = {
        "free": {"Authorization": f"Bearer {issue_session(FREE, secret, 600)}"},
        "trial": {"Authorization": f"Bearer {issue_session(TRIAL, secret, 600)}"},
    }
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, heads, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_free_stops_at_two_groups_and_forty_students(client) -> None:
    http, heads, sessions = client
    for index in range(40):
        made = await http.post(
            "/api/tutor/students",
            headers=heads["free"],
            json={"name": f"Oquvchi {index}", "status": "paid"},
        )
        assert made.status == 200, await made.text()
    extra = await http.post(
        "/api/tutor/students",
        headers=heads["free"],
        json={"name": "Ortib", "status": "paid"},
    )
    student = await extra.json()
    assert extra.status == 403
    assert student["error"] == "limit_students"
    assert student["limit"] == 40
    assert student["plan"] == "free"
    for name in ("Bir", "Ikki"):
        made = await http.post("/api/tutor/groups", headers=heads["free"], json=_group(name))
        assert made.status == 200
    blocked = await http.post("/api/tutor/groups", headers=heads["free"], json=_group("Uch"))
    body = await blocked.json()
    assert blocked.status == 403
    assert body == {"error": "limit_groups", "limit": 2, "used": 2, "plan": "free"}
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == FREE))).scalar_one()
        group = (
            (await session.execute(select(TutorGroup).where(TutorGroup.owner_id == owner.id)))
            .scalars()
            .first()
        )
        assert group is not None
        access = build_context(
            session, Settings(bot_token="1:test-token", database_url=_URL), owner
        ).access
        service = EnrollmentService(
            GroupRepository(session),
            StudentRepository(session),
            UserRepository(session),
            WorkspaceService(WorkspaceRepository(session), UserRepository(session)),
            access,
        )
        assert await service.enroll(group.enroll_code, 9870000099, "Yangi") == "pending"
        await session.commit()
        card = (
            await session.execute(
                select(TutorStudent).where(TutorStudent.telegram_id == 9870000099)
            )
        ).scalar_one()
        with pytest.raises(TutorLimitError) as caught:
            await service.approve(owner.id, group.id, card.id)
        assert caught.value.code == "limit_students"


async def test_trial_uses_the_pro_caps(client) -> None:
    http, heads, _sessions = client
    for index in range(10):
        made = await http.post(
            "/api/tutor/groups", headers=heads["trial"], json=_group(f"G{index}")
        )
        assert made.status == 200
    blocked = await http.post("/api/tutor/groups", headers=heads["trial"], json=_group("G10"))
    body = await blocked.json()
    assert blocked.status == 403
    assert body["error"] == "limit_groups"
    assert body["limit"] == 10
    assert body["plan"] == "pro"
