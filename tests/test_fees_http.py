"""Course-fee HTTP: free plans can see debt, only Start and above can record it."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.config import Settings
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.plans import Plan
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.users import User
from app.db.models.workspaces import Workspace
from app.services.clock import TASHKENT
from app.webapp.auth import issue_session, session_secret
from app.webapp.rate_limit import RateLimiter
from app.webapp.server import create_app
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
OWNER, OTHER, STUDENT = 9864400001, 9864400002, 9864400003
_IDS = (OWNER, OTHER, STUDENT)

pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")


async def _purge(session) -> None:
    ids = select(User.id).where(User.telegram_id.in_(_IDS))
    groups = select(TutorGroup.id).where(TutorGroup.owner_id.in_(ids))
    invoices = select(TutorInvoice.id).where(TutorInvoice.group_id.in_(groups))
    await session.execute(delete(TutorFeePayment).where(TutorFeePayment.invoice_id.in_(invoices)))
    await session.execute(delete(TutorInvoice).where(TutorInvoice.group_id.in_(groups)))
    await session.execute(delete(TutorGroupMember).where(TutorGroupMember.group_id.in_(groups)))
    await session.execute(delete(TutorGroup).where(TutorGroup.owner_id.in_(ids)))
    await session.execute(delete(TutorStudent).where(TutorStudent.owner_id.in_(ids)))
    await session.execute(delete(Workspace).where(Workspace.owner_id.in_(ids)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
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


async def test_free_sees_the_invoice_and_start_can_record_the_payment(client) -> None:
    http, heads, sessions = client
    today = datetime.now(TASHKENT).date()
    created = await http.post(
        "/api/tutor/groups",
        headers=heads["owner"],
        json={"name": "Ingliz", "weekdays": [1], "start": "18:00", "end": "19:30"},
    )
    group_id = (await created.json())["created_id"]
    student = await http.post(
        "/api/tutor/students",
        headers=heads["owner"],
        json={"name": "Ali Valiyev", "status": "paid", "group_ids": [group_id]},
    )
    student_id = (await student.json())["created_id"]
    async with sessions() as session:
        link = (
            await session.execute(
                select(TutorGroupMember).where(
                    TutorGroupMember.group_id == group_id,
                    TutorGroupMember.student_id == student_id,
                )
            )
        ).scalar_one()
        link.billing_start = today.replace(day=1)
        card = await session.get(TutorStudent, student_id)
        card.telegram_id = STUDENT
        await session.commit()
    priced = await http.put(
        f"/api/tutor/groups/{group_id}/fee",
        headers=heads["owner"],
        json={
            "fee_mode": "monthly",
            "fee_uzs": 300_000,
            "billing_day": min(today.day, 28),
            "due_days": 10,
        },
    )
    assert priced.status == 200 and (await priced.json())["fee_mode"] == "monthly"
    hidden = await http.put(
        f"/api/tutor/groups/{group_id}/fee",
        headers=heads["other"],
        json={"fee_mode": "none", "fee_uzs": 0, "due_days": 5},
    )
    assert hidden.status == 404
    listed = await http.get("/api/tutor/invoices", headers=heads["owner"])
    rows = await listed.json()
    assert len(rows) == 1 and rows[0]["amount_uzs"] == 300_000
    invoice_id = rows[0]["id"]
    blocked = await http.post(
        f"/api/tutor/invoices/{invoice_id}/payments",
        headers=heads["owner"],
        json={"amount_uzs": 100_000, "paid_on": today.isoformat(), "method": "cash"},
    )
    assert blocked.status == 403 and (await blocked.json())["error"] == "limit_fees"
    async with sessions() as session:
        owner = (await session.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()
        start = (await session.execute(select(Plan).where(Plan.code == "start"))).scalar_one()
        now = datetime.now(UTC)
        session.add(
            Subscription(
                owner_id=owner.id,
                plan_id=start.id,
                status=SubscriptionStatus.ACTIVE,
                source=SubscriptionSource.ADMIN_GRANT,
                started_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
        await session.commit()
    paid = await http.post(
        f"/api/tutor/invoices/{invoice_id}/payments",
        headers=heads["owner"],
        json={"amount_uzs": 100_000, "paid_on": today.isoformat(), "method": "cash"},
    )
    assert paid.status == 200 and (await paid.json())["paid_uzs"] == 100_000
    stolen = await http.post(
        f"/api/tutor/invoices/{invoice_id}/payments",
        headers=heads["other"],
        json={"amount_uzs": 1, "paid_on": today.isoformat(), "method": "cash"},
    )
    assert stolen.status == 404
    summary = await http.get("/api/tutor/fees/summary", headers=heads["owner"])
    body = await summary.json()
    assert body["collected_uzs"] == 100_000 and body["outstanding_uzs"] == 200_000
    mine = await http.get("/api/me/fees", headers=heads["student"])
    seen = await mine.json()
    assert seen["groups"][0]["group_name"] == "Ingliz"
    assert seen["groups"][0]["amount"] == 300_000 and seen["groups"][0]["paid"] == 100_000
    empty = await http.get("/api/me/fees", headers=heads["owner"])
    assert empty.status == 200 and (await empty.json())["groups"] == []
