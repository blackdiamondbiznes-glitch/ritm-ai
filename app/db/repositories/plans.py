"""Plan queries."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.plans import Plan


class PlanRepository:
    """Read plans. Seed data lives in the migration."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, plan_id: int) -> Plan | None:
        """Return a plan by primary key."""
        result = await self._session.execute(select(Plan).where(Plan.id == plan_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Plan | None:
        """Return a plan by its stable code."""
        result = await self._session.execute(select(Plan).where(Plan.code == code))
        return result.scalar_one_or_none()

    async def get_free_for_vertical(self, vertical: str) -> Plan | None:
        """Prefer a vertical-specific free plan, then the legacy free plan."""
        stmt = (
            select(Plan)
            .where(
                Plan.code == "free",
                or_(Plan.vertical == vertical, Plan.vertical.is_(None)),
            )
            .order_by(Plan.vertical.is_(None), Plan.id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self, vertical: str | None = None) -> list[Plan]:
        """Active plans ordered for the pricing screen."""
        stmt = select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.id)
        if vertical is not None:
            stmt = stmt.where(or_(Plan.vertical == vertical, Plan.vertical.is_(None)))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
