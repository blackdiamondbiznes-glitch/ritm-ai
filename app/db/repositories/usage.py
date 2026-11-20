"""Usage counter queries."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.usage import UsageCounter, UsageDaily

DAY_ZONE = "Asia/Tashkent"


class UsageRepository:
    """Read and increment monthly counters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_count(self, owner_id: int, metric: str, period_key: str) -> int:
        """Return the stored count, or zero when the row does not exist yet."""
        row = await self._row(owner_id, metric, period_key)
        if row is None:
            return 0
        return int(row.count)

    async def bump(self, owner_id: int, metric: str, period_key: str) -> int:
        """Add one to the monthly counter and return the new value."""
        row = await self._row(owner_id, metric, period_key)
        if row is None:
            row = UsageCounter(
                owner_id=owner_id,
                metric=metric,
                period_key=period_key,
                count=1,
            )
            self._session.add(row)
        else:
            row.count = int(row.count) + 1
        await self._session.flush()
        await self._bump_day(owner_id, metric)
        return int(row.count)

    async def _bump_day(self, owner_id: int, metric: str) -> None:
        """Daily copy for charts; the monthly row stays the source for limits."""
        today = func.cast(func.timezone(DAY_ZONE, func.now()), UsageDaily.day.type)
        stmt = insert(UsageDaily).values(owner_id=owner_id, metric=metric, day=today, count=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UsageDaily.owner_id, UsageDaily.metric, UsageDaily.day],
            set_={"count": UsageDaily.count + 1},
        )
        await self._session.execute(stmt)

    async def _row(self, owner_id: int, metric: str, period_key: str) -> UsageCounter | None:
        stmt = select(UsageCounter).where(
            UsageCounter.owner_id == owner_id,
            UsageCounter.metric == metric,
            UsageCounter.period_key == period_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
