"""Notification dedup queries."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notifications import NotificationLog


class NotificationRepository:
    """Record and look up already sent private notices."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_sent(
        self,
        owner_id: int,
        kind: str,
        *,
        chat_id: int | None = None,
        sent_on: date | None = None,
    ) -> bool:
        """True when this notice was already written. `sent_on` None means any day."""
        stmt = select(NotificationLog.id).where(
            NotificationLog.owner_id == owner_id,
            NotificationLog.kind == kind,
            NotificationLog.chat_key == (chat_id or 0),
        )
        if sent_on is not None:
            stmt = stmt.where(NotificationLog.sent_on == sent_on)
        stmt = stmt.limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add(
        self,
        owner_id: int,
        kind: str,
        sent_at: datetime,
        *,
        chat_id: int | None = None,
    ) -> NotificationLog:
        """Store a send so a later tick will not repeat it."""
        row = NotificationLog(
            owner_id=owner_id,
            chat_id=chat_id,
            chat_key=chat_id or 0,
            kind=kind,
            sent_on=sent_at.date(),
            sent_at=sent_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row
