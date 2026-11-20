"""Concurrent reviews of one payment request apply exactly once (row lock)."""

import asyncio

from app.db.models.payments import PaymentEvent
from app.db.models.subscriptions import Subscription
from app.services.payments import PaymentError
from sqlalchemy import func, select
from tests.test_payment_trust import TERMS, db, pytestmark, service, submit, user

__all__ = ["db", "pytestmark"]


async def _pending(sessions) -> tuple[int, int]:
    async with sessions() as s:
        svc = service(s)
        owner = await user(s, 0)
        draft = await svc.start(owner, "pro", 1, terms_version=TERMS)
        payment = (await submit(svc, owner, draft)).payment
        await s.commit()
        return payment.id, owner.id


async def _review(sessions, payment_id: int, action: str) -> str:
    async with sessions() as s:
        svc = service(s)
        admin = await user(s, 3)
        try:
            if action == "approve":
                await svc.approve(admin, payment_id, via="race")
            else:
                await svc.reject(admin, payment_id, "race reject", via="race")
        except PaymentError as exc:
            await s.rollback()
            return f"error:{exc.code}"
        await s.commit()
        return "ok"


async def _count(sessions, stmt) -> int:
    async with sessions() as s:
        return int(await s.scalar(stmt))


async def test_double_approve_extends_once(db) -> None:
    payment_id, owner_id = await _pending(db)
    results = await asyncio.gather(*(_review(db, payment_id, "approve") for _ in range(3)))
    assert results == ["ok", "ok", "ok"]  # later approvals are no-ops
    approved = select(func.count()).where(
        PaymentEvent.payment_id == payment_id, PaymentEvent.action == "approved"
    )
    assert await _count(db, approved) == 1
    subs = select(func.count()).where(Subscription.owner_id == owner_id)
    assert await _count(db, subs) == 1


async def test_approve_and_reject_race_one_wins(db) -> None:
    payment_id, _owner_id = await _pending(db)
    results = await asyncio.gather(
        _review(db, payment_id, "approve"), _review(db, payment_id, "reject")
    )
    assert sorted(results) == ["error:status", "ok"]
    decided = select(func.count()).where(
        PaymentEvent.payment_id == payment_id,
        PaymentEvent.action.in_(("approved", "rejected")),
    )
    assert await _count(db, decided) == 1
