"""Payment request queries. Approval rules live in the service."""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.payments import (
    OPEN_STATUSES,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_PENDING,
    Payment,
    PaymentEvent,
)

_FOUNDER_LOCK = 620011
_AMOUNT_LOCK = 620012


class PaymentRepository:
    """Insert and load manual payment rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment: Payment) -> Payment:
        """Insert a payment and flush so the id is available."""
        self._session.add(payment)
        await self._session.flush()
        return payment

    async def get(self, payment_id: int) -> Payment | None:
        """Return one payment by primary key."""
        result = await self._session.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    async def get_pending(self, owner_id: int) -> Payment | None:
        """The owner's open request (waiting for review or disputed), if any."""
        stmt = (
            select(Payment)
            .where(Payment.owner_id == owner_id, Payment.status.in_(OPEN_STATUSES))
            .order_by(Payment.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_draft(self, owner_id: int) -> Payment | None:
        """The owner's issued-but-unsubmitted request, if any."""
        stmt = (
            select(Payment)
            .where(Payment.owner_id == owner_id, Payment.status == STATUS_DRAFT)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int = 20) -> list[Payment]:
        """Oldest open requests first, for the admin queue."""
        return await self.list_by_status(OPEN_STATUSES, limit=limit, oldest_first=True)

    async def list_by_status(
        self, statuses: tuple[str, ...] | None, *, limit: int = 50, oldest_first: bool = False
    ) -> list[Payment]:
        stmt = select(Payment)
        if statuses:
            stmt = stmt.where(Payment.status.in_(statuses))
        order = (Payment.created_at, Payment.id) if oldest_first else (Payment.id.desc(),)
        result = await self._session.execute(stmt.order_by(*order).limit(limit))
        return list(result.scalars().all())

    async def list_for_owner(self, owner_id: int, limit: int = 50) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.owner_id == owner_id)
            .order_by(Payment.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def ref_exists(self, ref_code: str) -> bool:
        stmt = select(Payment.id).where(Payment.ref_code == ref_code).limit(1)
        return (await self._session.execute(stmt)).first() is not None

    async def amounts_in_use(self, base_amount: int) -> set[int]:
        """Exact amounts already promised to other open or draft requests with this base."""
        stmt = select(Payment.amount_uzs).where(
            Payment.base_amount_uzs == base_amount,
            Payment.status.in_((STATUS_DRAFT, *OPEN_STATUSES)),
        )
        return {int(row[0]) for row in (await self._session.execute(stmt)).all()}

    async def with_receipt(self, unique_id: str, exclude_id: int) -> list[Payment]:
        """Other requests that used the same Telegram file (any owner)."""
        stmt = (
            select(Payment)
            .where(Payment.receipt_unique_id == unique_id, Payment.id != exclude_id)
            .order_by(Payment.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(Payment.status, func.count()).group_by(Payment.status)
        return {str(status): int(n) for status, n in (await self._session.execute(stmt)).all()}

    async def approved_total(self, start: datetime, end: datetime) -> tuple[int, int]:
        """(sum, count) of payments approved in [start, end)."""
        stmt = select(func.coalesce(func.sum(Payment.amount_uzs), 0), func.count()).where(
            Payment.status == STATUS_APPROVED,
            Payment.reviewed_at >= start,
            Payment.reviewed_at < end,
        )
        total, count = (await self._session.execute(stmt)).one()
        return int(total), int(count)

    async def lock_founder_slots(self) -> None:
        """Serialize founder assignment across concurrent approvals."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _FOUNDER_LOCK}
        )

    async def lock_amounts(self) -> None:
        """Serialize reference and exact-amount assignment."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AMOUNT_LOCK}
        )


class PaymentEventRepository:
    """Append-only payment history. The database rejects UPDATE and DELETE."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: PaymentEvent) -> PaymentEvent:
        self._session.add(event)
        await self._session.flush()
        return event

    async def for_payment(self, payment_id: int) -> list[PaymentEvent]:
        stmt = (
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == payment_id)
            .order_by(PaymentEvent.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def recent(self, limit: int = 100, action: str | None = None) -> list[PaymentEvent]:
        stmt = select(PaymentEvent)
        if action:
            stmt = stmt.where(PaymentEvent.action == action)
        stmt = stmt.order_by(PaymentEvent.id.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())


__all__ = ["PaymentEventRepository", "PaymentRepository", "STATUS_PENDING"]
