"""Subscription queries."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus


class SubscriptionRepository:
    """Persist subscriptions. Expiry policy lives in AccessService."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open(self, owner_id: int) -> Subscription | None:
        """The single trial/active row, even if `expires_at` has already passed."""
        stmt = select(Subscription).where(
            Subscription.owner_id == owner_id,
            Subscription.status.in_((SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE)),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, subscription: Subscription) -> Subscription:
        """Insert a subscription and flush so the id is available."""
        self._session.add(subscription)
        await self._session.flush()
        return subscription

    async def count_open_trials(self, now: datetime) -> int:
        """Trials that have not passed `expires_at`."""
        stmt = (
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.TRIAL,
                Subscription.expires_at > now,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_trials(self) -> list[Subscription]:
        """Every trial row, including ones whose expiry has already passed."""
        stmt = select(Subscription).where(Subscription.status == SubscriptionStatus.TRIAL)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_open_paid(self, now: datetime) -> int:
        """Paid grants that have not passed `expires_at`."""
        stmt = (
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.source != SubscriptionSource.TRIAL,
                Subscription.expires_at > now,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
