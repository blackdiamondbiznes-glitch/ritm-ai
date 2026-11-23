"""Tutor lesson queries. No validation here."""

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.repositories.users import teacher_label


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

    async def insert_slot(self, values: dict) -> int | None:
        """Insert one slot. A taken (group, planned_at) pair inserts nothing."""
        stmt = (
            pg_insert(TutorLesson)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=["group_id", "planned_at"],
                index_where=text("planned_at IS NOT NULL"),
            )
            .returning(TutorLesson.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def replaceable(self, group_id: int, now: datetime) -> list[TutorLesson]:
        """Future schedule rows still on their original slot and still scheduled."""
        stmt = select(TutorLesson).where(
            TutorLesson.group_id == group_id,
            TutorLesson.source == "schedule",
            TutorLesson.status == "scheduled",
            TutorLesson.starts_at == TutorLesson.planned_at,
            TutorLesson.starts_at > now,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_many(self, rows: list[TutorLesson]) -> None:
        """Remove these lessons. An empty list does nothing."""
        if not rows:
            return
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()

    async def in_range(
        self, owner_id: int, start: datetime, end: datetime
    ) -> list[tuple[TutorLesson, str | None]]:
        """This owner's lessons that start in [start, end), with the group name."""
        stmt = (
            select(TutorLesson, TutorGroup.name)
            .outerjoin(TutorGroup, TutorGroup.id == TutorLesson.group_id)
            .where(
                TutorLesson.owner_id == owner_id,
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at < end,
            )
            .order_by(TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(row, name) for row, name in result.all()]

    async def for_learner(
        self, telegram_id: int, skip_owner_id: int, start: datetime, end: datetime
    ) -> list[tuple[TutorLesson, str, str | None]]:
        """Sessions in groups where this Telegram account is an active member."""
        stmt = (
            select(TutorLesson, TutorGroup.name, teacher_label())
            .join(TutorGroup, TutorGroup.id == TutorLesson.group_id)
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .join(User, User.id == TutorGroup.owner_id)
            .where(
                TutorStudent.telegram_id == telegram_id,
                TutorGroup.owner_id != skip_owner_id,
                TutorGroupMember.status == "active",
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at < end,
            )
            .order_by(TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(row, name, teacher) for row, name, teacher in result.all()]

    async def for_group_between(
        self, owner_id: int, group_id: int, start: datetime, end: datetime
    ) -> list[TutorLesson]:
        """This owner's sessions of one group that start in [start, end)."""
        stmt = (
            select(TutorLesson)
            .where(
                TutorLesson.owner_id == owner_id,
                TutorLesson.group_id == group_id,
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at < end,
            )
            .order_by(TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
