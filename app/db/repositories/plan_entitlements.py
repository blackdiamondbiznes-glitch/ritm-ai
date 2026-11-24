"""Plan entitlement queries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.plan_entitlements import PlanEntitlement


class PlanEntitlementRepository:
    """Read feature values for one plan."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_plan(self, plan_id: int) -> dict[str, object]:
        """Return the plan's feature values keyed by their stable feature codes."""
        stmt = select(PlanEntitlement).where(PlanEntitlement.plan_id == plan_id)
        result = await self._session.execute(stmt)
        return {row.feature_key: row.feature_value for row in result.scalars().all()}
