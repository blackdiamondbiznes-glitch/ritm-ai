"""Tutor lesson queries. No validation here."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lessons import TutorLesson


class LessonRepository:
    """Read and write one owner's lessons."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(self, owner_id: int) -> list[TutorLesson]:
        """Soonest dated lesson first. Undated lessons follow, newest first."""
        stmt = (
            select(TutorLesson)
            .where(TutorLesson.owner_id == owner_id)
            .order_by(TutorLesson.starts_at.asc().nulls_last(), TutorLesson.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_owned(self, owner_id: int, lesson_id: int) -> TutorLesson | None:
        """Return the lesson only when it belongs to this owner."""
        stmt = select(TutorLesson).where(
            TutorLesson.id == lesson_id,
            TutorLesson.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, row: TutorLesson) -> TutorLesson:
        """Insert a lesson and assign its id."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, row: TutorLesson) -> TutorLesson:
        """Flush changes on a lesson already loaded in this session."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: TutorLesson) -> None:
        """Remove a lesson."""
        await self._session.delete(row)
        await self._session.flush()
