"""Tutor student queries. No validation here."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.students import TutorStudent


class StudentRepository:
    """Read and write one owner's students."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(self, owner_id: int) -> list[TutorStudent]:
        """Newest students of this owner first."""
        stmt = (
            select(TutorStudent)
            .where(TutorStudent.owner_id == owner_id)
            .order_by(TutorStudent.created_at.desc(), TutorStudent.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_owned(self, owner_id: int, student_id: int) -> TutorStudent | None:
        """Return the student only when it belongs to this owner."""
        stmt = select(TutorStudent).where(
            TutorStudent.id == student_id,
            TutorStudent.owner_id == owner_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, row: TutorStudent) -> TutorStudent:
        """Insert a student and assign its id."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, row: TutorStudent) -> TutorStudent:
        """Flush changes on a student already loaded in this session."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: TutorStudent) -> None:
        """Remove a student."""
        await self._session.delete(row)
        await self._session.flush()
