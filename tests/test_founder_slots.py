"""Founder slots are assigned at most once when two approvals race."""

import asyncio
import os
from datetime import UTC, datetime

import pytest
from app.db.models.audit import AuditLog
from app.db.models.payments import METHOD_CARD, STATUS_PENDING, Payment, PaymentEvent
from app.db.models.subscriptions import Subscription
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.payments import PaymentRepository
from app.db.repositories.plans import PlanRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.usage import UsageRepository
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.payments import PaymentService
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.pg import allow_purge

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
_IDS = (9100000001, 9100000002, 9100000003)


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_concurrent_approvals_do_not_over_assign_founder_slots() -> None:
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _cleanup(session)
        await session.commit()
    try:
        payment_ids, reviewer_id, slots = await _seed(sessions)
        await asyncio.gather(
            _approve(sessions, payment_ids[0], reviewer_id, slots),
            _approve(sessions, payment_ids[1], reviewer_id, slots),
        )
        async with sessions() as session:
            result = await session.execute(select(User).where(User.telegram_id.in_(_IDS[:2])))
            owners = list(result.scalars().all())
            assert len(owners) == 2
            assert sum(1 for owner in owners if owner.is_founder) == 1
    finally:
        async with sessions() as session:
            await _cleanup(session)
            await session.commit()
        await engine.dispose()


def _service(session, slots: int) -> PaymentService:
    plans = PlanRepository(session)
    subs = SubscriptionRepository(session)
    users = UserRepository(session)
    access = AccessService(
        plans,
        subs,
        ChatRepository(session),
        UsageRepository(session),
        users,
        now=lambda: NOW,
        founder_slots=slots,
    )
    return PaymentService(
        PaymentRepository(session),
        plans,
        subs,
        users,
        access,
        AuditRepository(session),
        now=lambda: NOW,
    )


async def _seed(sessions) -> tuple[list[int], int, int]:
    async with sessions() as session:
        baseline = await UserRepository(session).count_founders()
        slots = baseline + 1
        pro = await PlanRepository(session).get_by_code("pro")
        assert pro is not None
        reviewer = User(telegram_id=_IDS[2], language_code="uz", last_seen_at=NOW)
        first = User(telegram_id=_IDS[0], language_code="uz", last_seen_at=NOW)
        second = User(telegram_id=_IDS[1], language_code="uz", last_seen_at=NOW)
        session.add_all([reviewer, first, second])
        await session.flush()
        rows = []
        for owner in (first, second):
            row = Payment(
                owner_id=owner.id,
                plan_id=pro.id,
                amount_uzs=int(pro.founder_price_uzs or pro.price_uzs),
                method=METHOD_CARD,
                status=STATUS_PENDING,
                requested_period_months=1,
            )
            session.add(row)
            rows.append(row)
        await session.flush()
        ids = [row.id for row in rows]
        reviewer_id = reviewer.id
        await session.commit()
        return ids, reviewer_id, slots


async def _approve(sessions, payment_id: int, reviewer_id: int, slots: int) -> None:
    async with sessions() as session:
        reviewer = await UserRepository(session).get_by_id(reviewer_id)
        assert reviewer is not None
        await _service(session, slots).approve(reviewer, payment_id)
        await session.commit()


async def _cleanup(session) -> None:
    owners = await session.execute(select(User).where(User.telegram_id.in_(_IDS)))
    ids = [user.id for user in owners.scalars().all()]
    if not ids:
        return
    await allow_purge(session)
    payment_ids = select(Payment.id).where(Payment.owner_id.in_(ids))
    await session.execute(delete(PaymentEvent).where(PaymentEvent.payment_id.in_(payment_ids)))
    await session.execute(delete(AuditLog).where(AuditLog.actor_user_id.in_(ids)))
    await session.execute(delete(Payment).where(Payment.owner_id.in_(ids)))
    await session.execute(delete(Payment).where(Payment.reviewed_by.in_(ids)))
    await session.execute(delete(Subscription).where(Subscription.owner_id.in_(ids)))
    await session.execute(delete(User).where(User.id.in_(ids)))
