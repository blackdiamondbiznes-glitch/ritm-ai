"""Audit log writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog


class AuditRepository:
    """Append audit rows. Callers choose the action name."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity: str,
        entity_id: str,
        data: dict[str, object],
    ) -> None:
        """Insert one audit row."""
        self._session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                data=data,
            )
        )
        await self._session.flush()
