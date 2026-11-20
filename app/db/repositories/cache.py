"""AI response cache."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cache import AiCache


class CacheRepository:
    """Lookup and store validated model JSON."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cache_key: str) -> dict[str, object] | None:
        """Return the stored JSON, or None."""
        stmt = select(AiCache).where(AiCache.cache_key == cache_key)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return dict(row.response)

    async def put(
        self,
        cache_key: str,
        provider: str,
        model: str,
        response: dict[str, object],
    ) -> None:
        """Insert a cache row. Callers skip this when the key already exists."""
        self._session.add(
            AiCache(
                cache_key=cache_key,
                provider=provider,
                model=model,
                response=response,
            )
        )
        await self._session.flush()
