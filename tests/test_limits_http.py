"""Plan usage on the cabinet home, and a downgrade that keeps existing rows."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.usage import UsageCounter
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.services.notify_rules import METRIC, period_key
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER = 9865000001
_IDS = (OWNER,)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(UsageCounter).where(UsageCounter.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
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
        session.add(User(telegram_id=OWNER, full_name="Lola", language_code="uz"))
        await session.commit()
    settings = Settings(bot_token="1:test-token", database_url=_URL)
    app = create_app(settings, sessions, limiter=RateLimiter(limit=10000))
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    head = {"Authorization": f"Bearer {issue_session(OWNER, secret, 600)}"}
    try:
        async with TestClient(TestServer(app)) as http:
            yield http, head, sessions
    finally:
        async with sessions() as session:
            await _purge(session)
            await session.commit()
        await engine.dispose()


async def test_limits_follow_the_plan_and_a_downgrade_keeps_rows(client) -> None:
    http, head, sessions = client
    now = datetime.now(UTC)
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
        start = (await session.execute(select(Plan).where(Plan.code == "start"))).scalar_one()
        session.add(
            Subscription(
                owner_id=owner.id,
                plan_id=start.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now - timedelta(days=10),
                expires_at=now + timedelta(days=20),
            )
        )
        session.add(
            UsageCounter(owner_id=owner.id, metric=METRIC, period_key=period_key(now), count=12)
        )
        await session.commit()
        owner_id = owner.id
    ids = []
    for name in ("Bir", "Ikki", "Uch"):
        made = await http.post("/api/tutor/groups", headers=head, json=_group(name))
        assert made.status == 200, await made.text()
        ids.append((await made.json())["created_id"])
    async with sessions() as session:
        group = await session.get(TutorGroup, ids[0])
        assert group is not None
        for index in range(40):
            session.add(
                TutorStudent(
                    owner_id=owner_id,
                    workspace_id=group.workspace_id,
                    name=f"Oquvchi {index}",
                    status="paid",
                    amount_uzs=0,
                    join_code=f"l{index:02d}x{OWNER}",
                )
            )
        pending = TutorStudent(
            owner_id=owner_id,
            workspace_id=group.workspace_id,
            name="Kutayotgan",
            status="pending",
            amount_uzs=0,
            telegram_id=9865000099,
            join_code="pend5001",
        )
        session.add(pending)
        await session.flush()
        session.add(TutorGroupMember(group_id=ids[0], student_id=pending.id, status="pending"))
        await session.commit()
        pending_id = pending.id
    limits = await http.get("/api/tutor/limits", headers=head)
    body = await limits.json()
    assert limits.status == 200
    assert body["plan"] == "start" and body["reports"] is False
    assert body["groups"] == {"used": 3, "limit": 4}
    assert body["students"] == {"used": 40, "limit": 80}
    assert body["notifications"] == {"used": 12, "limit": 300}
    async with sessions() as session:
        sub = (
            await session.execute(select(Subscription).where(Subscription.owner_id == owner_id))
        ).scalar_one()
        sub.expires_at = now - timedelta(days=1)
        await session.commit()
    after = await (await http.get("/api/tutor/limits", headers=head)).json()
    assert after["plan"] == "free"
    assert after["groups"] == {"used": 3, "limit": 2}
    assert after["students"] == {"used": 40, "limit": 40}
    assert after["notifications"] == {"used": 12, "limit": 0}
    listed = await http.get("/api/tutor/groups", headers=head)
    assert listed.status == 200 and len((await listed.json())["groups"]) == 3
    edited = await http.patch(
        f"/api/tutor/groups/{ids[0]}", headers=head, json={"name": "Saqlangan"}
    )
    assert edited.status == 200 and (await edited.json())["group"]["name"] == "Saqlangan"
    blocked = await http.post("/api/tutor/groups", headers=head, json=_group("Tort"))
    assert blocked.status == 403 and (await blocked.json())["error"] == "limit_groups"
    extra = await http.post(
        "/api/tutor/students", headers=head, json={"name": "Ortib", "status": "paid"}
    )
    assert extra.status == 403 and (await extra.json())["error"] == "limit_students"
    async with sessions() as session:
        card = (
            (
                await session.execute(
                    select(TutorStudent).where(
                        TutorStudent.owner_id == owner_id, TutorStudent.status == "paid"
                    )
                )
            )
            .scalars()
            .first()
        )
        assert card is not None
        card_id = card.id
    renamed = await http.patch(
        f"/api/tutor/students/{card_id}", headers=head, json={"name": "Yangilangan"}
    )
    assert renamed.status == 200
    approved = await http.post(f"/api/tutor/requests/{ids[0]}/{pending_id}/approve", headers=head)
    assert approved.status == 403 and (await approved.json())["error"] == "limit_students"
    still = await http.get(f"/api/tutor/groups/{ids[0]}", headers=head)
    assert still.status == 200 and (await still.json())["group"]["name"] == "Saqlangan"
