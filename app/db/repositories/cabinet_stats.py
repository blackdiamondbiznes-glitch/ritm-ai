"""Month totals for one teacher's cabinet. No plan rules here."""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent


class CabinetStatsRepository:
    """Read attendance, money, and membership changes for a month."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def marks(self, owner_id: int, start: datetime, end: datetime) -> list[tuple[int, str]]:
        """(group id, status) for marks on sessions that start in the window."""
        stmt = (
            select(TutorLesson.group_id, TutorAttendance.status)
            .join(TutorAttendance, TutorAttendance.lesson_id == TutorLesson.id)
            .where(
                TutorLesson.owner_id == owner_id,
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at < end,
                TutorLesson.group_id.is_not(None),
            )
        )
        result = await self._session.execute(stmt)
        return [(int(group_id), str(status)) for group_id, status in result.all() if group_id]

    async def collected(self, owner_id: int, start: date, end: date) -> list[tuple[int, int]]:
        """(group id, sum) of payments dated in [start, end)."""
        stmt = (
            select(TutorInvoice.group_id, func.coalesce(func.sum(TutorFeePayment.amount_uzs), 0))
            .join(TutorFeePayment, TutorFeePayment.invoice_id == TutorInvoice.id)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(
                TutorGroup.owner_id == owner_id,
                TutorFeePayment.paid_on >= start,
                TutorFeePayment.paid_on < end,
            )
            .group_by(TutorInvoice.group_id)
        )
        result = await self._session.execute(stmt)
        return [(int(group_id), int(total)) for group_id, total in result.all()]

    async def outstanding(self, owner_id: int, start: date, end: date) -> list[tuple[int, int]]:
        """(group id, unpaid) for invoices due in the month and still open."""
        owed = TutorInvoice.amount_uzs - TutorInvoice.paid_uzs
        stmt = (
            select(TutorInvoice.group_id, func.coalesce(func.sum(owed), 0))
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(
                TutorGroup.owner_id == owner_id,
                TutorInvoice.due_on >= start,
                TutorInvoice.due_on < end,
                TutorInvoice.status.in_(("due", "overdue")),
            )
            .group_by(TutorInvoice.group_id)
        )
        result = await self._session.execute(stmt)
        return [(int(group_id), int(total)) for group_id, total in result.all()]

    async def joined(self, owner_id: int, start: datetime, end: datetime) -> int:
        """Active memberships opened in the window."""
        stmt = (
            select(func.count(func.distinct(TutorGroupMember.student_id)))
            .join(TutorGroup, TutorGroup.id == TutorGroupMember.group_id)
            .where(
                TutorGroup.owner_id == owner_id,
                TutorGroupMember.status == "active",
                TutorGroupMember.created_at >= start,
                TutorGroupMember.created_at < end,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def left(self, owner_id: int, start: datetime, end: datetime) -> int:
        """Inactive cards whose record changed in the window."""
        stmt = (
            select(func.count())
            .select_from(TutorStudent)
            .where(
                TutorStudent.owner_id == owner_id,
                TutorStudent.status == "inactive",
                TutorStudent.updated_at >= start,
                TutorStudent.updated_at < end,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())
