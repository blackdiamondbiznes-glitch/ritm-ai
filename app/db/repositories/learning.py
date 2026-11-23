"""Batched reads for the student cabinet. One query covers every group."""

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent
from app.db.models.users import User
from app.db.repositories.users import teacher_label

Seat = tuple[TutorGroupMember, TutorGroup, TutorStudent, str | None]


class LearningRepository:
    """Read what one Telegram account studies. No rules here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def seats(self, telegram_id: int, skip_owner_id: int) -> list[Seat]:
        """Active and pending memberships, except groups this account teaches."""
        stmt = (
            select(TutorGroupMember, TutorGroup, TutorStudent, teacher_label())
            .join(TutorGroup, TutorGroup.id == TutorGroupMember.group_id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .join(User, User.id == TutorGroup.owner_id)
            .where(
                TutorStudent.telegram_id == telegram_id,
                TutorGroup.owner_id != skip_owner_id,
                TutorGroupMember.status.in_(("active", "pending")),
            )
            .order_by(TutorGroup.start_min.asc(), TutorGroup.id.asc())
        )
        result = await self._session.execute(stmt)
        return [
            (member, group, student, teacher) for member, group, student, teacher in result.all()
        ]

    async def next_lessons(self, group_ids: list[int], now: datetime) -> dict[int, TutorLesson]:
        """The running or soonest future session of each group. Cancelled sessions are skipped."""
        if not group_ids:
            return {}
        stmt = (
            select(TutorLesson)
            .where(
                TutorLesson.group_id.in_(group_ids),
                TutorLesson.starts_at.is_not(None),
                or_(
                    TutorLesson.ends_at >= now,
                    and_(TutorLesson.ends_at.is_(None), TutorLesson.starts_at >= now),
                ),
                TutorLesson.status != "cancelled",
            )
            .distinct(TutorLesson.group_id)
            .order_by(TutorLesson.group_id, TutorLesson.starts_at.asc(), TutorLesson.id.asc())
        )
        result = await self._session.execute(stmt)
        return {int(row.group_id): row for row in result.scalars().all() if row.group_id}

    async def marks(self, student_ids: list[int], group_ids: list[int]) -> list[tuple]:
        """Every mark for these students in these groups, newest session first."""
        if not student_ids or not group_ids:
            return []
        stmt = (
            select(
                TutorAttendance.student_id,
                TutorLesson.group_id,
                TutorAttendance.status,
                TutorLesson.starts_at,
                TutorLesson.title,
            )
            .join(TutorLesson, TutorLesson.id == TutorAttendance.lesson_id)
            .where(
                TutorAttendance.student_id.in_(student_ids),
                TutorLesson.group_id.in_(group_ids),
            )
            .order_by(TutorLesson.starts_at.desc().nulls_last(), TutorLesson.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def invoices(self, group_ids: list[int], student_ids: list[int]) -> list[TutorInvoice]:
        """Bills for these groups and cards. The caller keeps the real pairs."""
        if not group_ids or not student_ids:
            return []
        stmt = (
            select(TutorInvoice)
            .where(
                TutorInvoice.group_id.in_(group_ids),
                TutorInvoice.student_id.in_(student_ids),
            )
            .order_by(TutorInvoice.due_on.asc(), TutorInvoice.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
