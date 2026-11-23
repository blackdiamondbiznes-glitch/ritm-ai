"""Attendance queries. No validation here."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attendance import TutorAttendance
from app.db.models.lessons import TutorLesson


class AttendanceRepository:
    """Read and write marks for lessons the caller already scoped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_lesson(self, lesson_id: int) -> list[TutorAttendance]:
        """Every mark stored on this lesson."""
        stmt = select(TutorAttendance).where(TutorAttendance.lesson_id == lesson_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def for_lessons(self, lesson_ids: list[int]) -> list[TutorAttendance]:
        """Marks on these lessons. An empty list hits the database for nothing."""
        if not lesson_ids:
            return []
        stmt = select(TutorAttendance).where(TutorAttendance.lesson_id.in_(lesson_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def lesson_ids(self, lesson_ids: list[int]) -> set[int]:
        """Lesson ids in this set that already have at least one mark."""
        if not lesson_ids:
            return set()
        stmt = (
            select(TutorAttendance.lesson_id)
            .where(TutorAttendance.lesson_id.in_(lesson_ids))
            .distinct()
        )
        result = await self._session.execute(stmt)
        return {int(lesson_id) for lesson_id in result.scalars().all()}

    async def upsert(
        self, lesson_id: int, student_id: int, status: str, note: str | None, marked_at: datetime
    ) -> None:
        """Insert the mark, or replace status, note, and time."""
        stmt = (
            pg_insert(TutorAttendance)
            .values(
                lesson_id=lesson_id,
                student_id=student_id,
                status=status,
                note=note,
                marked_at=marked_at,
            )
            .on_conflict_do_update(
                constraint="uq_tutor_attendance_lesson_student",
                set_={"status": status, "note": note, "marked_at": marked_at},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def clear(self, lesson_id: int, student_id: int) -> None:
        """Remove the mark. Missing rows stay missing."""
        stmt = delete(TutorAttendance).where(
            TutorAttendance.lesson_id == lesson_id,
            TutorAttendance.student_id == student_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def statuses_for_student_group(self, student_id: int, group_id: int) -> list[str]:
        """Every status this student has in this group, for the rate."""
        stmt = (
            select(TutorAttendance.status)
            .join(TutorLesson, TutorLesson.id == TutorAttendance.lesson_id)
            .where(
                TutorAttendance.student_id == student_id,
                TutorLesson.group_id == group_id,
            )
        )
        result = await self._session.execute(stmt)
        return [str(status) for status in result.scalars().all()]

    async def recent_for_student_group(
        self, student_id: int, group_id: int, limit: int = 30
    ) -> list[tuple[TutorAttendance, TutorLesson]]:
        """The newest marks for this student in this group."""
        stmt = (
            select(TutorAttendance, TutorLesson)
            .join(TutorLesson, TutorLesson.id == TutorAttendance.lesson_id)
            .where(
                TutorAttendance.student_id == student_id,
                TutorLesson.group_id == group_id,
            )
            .order_by(TutorLesson.starts_at.desc().nulls_last(), TutorLesson.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [(mark, lesson) for mark, lesson in result.all()]
