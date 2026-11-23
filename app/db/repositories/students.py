"""Tutor student queries. No validation here."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    async def by_join_code(self, code: str) -> TutorStudent | None:
        """The student invited by this code."""
        stmt = select(TutorStudent).where(TutorStudent.join_code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def by_owner_telegram(self, owner_id: int, telegram_id: int) -> TutorStudent | None:
        """The card this owner already linked to this Telegram account."""
        stmt = select(TutorStudent).where(
            TutorStudent.owner_id == owner_id,
            TutorStudent.telegram_id == telegram_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_visible(self, owner_id: int) -> int:
        """Cards the teacher can see. Pending requests are not counted."""
        stmt = (
            select(func.count())
            .select_from(TutorStudent)
            .where(TutorStudent.owner_id == owner_id, TutorStudent.status != "pending")
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def insert_or_get(self, row: TutorStudent) -> TutorStudent:
        """Insert the card, or return the one this Telegram account already has."""
        stmt = (
            pg_insert(TutorStudent)
            .values(
                owner_id=row.owner_id,
                name=row.name,
                status=row.status,
                amount_uzs=row.amount_uzs,
                telegram_id=row.telegram_id,
                join_code=row.join_code,
            )
            .on_conflict_do_nothing(
                index_elements=[TutorStudent.owner_id, TutorStudent.telegram_id],
                index_where=TutorStudent.telegram_id.is_not(None),
            )
            .returning(TutorStudent.id)
        )
        new_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if new_id is not None:
            loaded = await self._session.get(TutorStudent, new_id)
            if loaded is None:
                raise RuntimeError("student insert missed")
            return loaded
        found = await self.by_owner_telegram(row.owner_id, int(row.telegram_id or 0))
        if found is None:
            raise RuntimeError("student insert missed")
        return found

    async def by_telegram(self, telegram_id: int) -> list[TutorStudent]:
        """Student rows linked to this Telegram account."""
        stmt = select(TutorStudent).where(TutorStudent.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, row: TutorStudent) -> None:
        """Remove a student."""
        await self._session.delete(row)
        await self._session.flush()
