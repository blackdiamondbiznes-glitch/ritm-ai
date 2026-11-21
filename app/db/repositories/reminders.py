"""Tutor reminder queries. No queue rules here."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reminders import TutorReminder


class ReminderRepository:
    """Read and write one owner's reminders."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(self, owner_id: int) -> list[TutorReminder]:
        """Soonest reminder first."""
        stmt = (
            select(TutorReminder)
            .where(TutorReminder.owner_id == owner_id)
            .order_by(TutorReminder.send_at.asc(), TutorReminder.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_owned(self, owner_id: int, reminder_id: int) -> TutorReminder | None:
        """Return the reminder only when it belongs to this owner."""
        stmt = select(TutorReminder).where(
            TutorReminder.id == reminder_id,
            TutorReminder.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get(self, reminder_id: int) -> TutorReminder | None:
        """Return one reminder by id. Used by the job handler."""
        result = await self._session.execute(
            select(TutorReminder).where(TutorReminder.id == reminder_id)
        )
        return result.scalar_one_or_none()

    async def due(self, now: datetime) -> list[TutorReminder]:
        """Reminders whose time has come and that have no job yet."""
        stmt = (
            select(TutorReminder)
            .where(TutorReminder.queued_at.is_(None), TutorReminder.send_at <= now)
            .order_by(TutorReminder.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, row: TutorReminder) -> TutorReminder:
        """Insert a reminder and assign its id."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, row: TutorReminder) -> TutorReminder:
        """Flush changes on a reminder already loaded in this session."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: TutorReminder) -> None:
        """Remove a reminder."""
        await self._session.delete(row)
        await self._session.flush()
