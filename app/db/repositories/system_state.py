"""Read and write operational key-value rows."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system_state import SystemState
from app.services.clock import Clock, utcnow


class SystemStateRepository:
    """Tiny key-value store used by health checks."""

    def __init__(self, session: AsyncSession, now: Clock | None = None) -> None:
        self._session = session
        self._now = now or utcnow

    async def put(self, key: str, value: str) -> None:
        """Insert or update a key."""
        row = await self.get_row(key)
        stamp = self._now()
        if row is None:
            self._session.add(SystemState(key=key, value=value, updated_at=stamp))
        else:
            row.value = value
            row.updated_at = stamp
        await self._session.flush()

    async def get(self, key: str) -> str | None:
        """Return the stored value, if any."""
        row = await self.get_row(key)
        return None if row is None else row.value

    async def get_row(self, key: str) -> SystemState | None:
        """Return the full row, including the timestamp."""
        result = await self._session.execute(select(SystemState).where(SystemState.key == key))
        return result.scalar_one_or_none()
