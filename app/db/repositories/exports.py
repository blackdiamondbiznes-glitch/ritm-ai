"""Row reads for the teacher's CSV files. No plan checks here."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attendance import TutorAttendance
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.lessons import TutorLesson
from app.db.models.students import TutorStudent


class ExportRepository:
    """Owner-scoped rows for students, payments, and attendance."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def students(self, owner_id: int) -> list[tuple[TutorStudent, str | None]]:
        """Each visible card and one group name. A card in two groups appears twice."""
        stmt = (
            select(TutorStudent, TutorGroup.name)
            .outerjoin(
                TutorGroupMember,
                (TutorGroupMember.student_id == TutorStudent.id)
                & (TutorGroupMember.status == "active"),
            )
            .outerjoin(TutorGroup, TutorGroup.id == TutorGroupMember.group_id)
            .where(TutorStudent.owner_id == owner_id, TutorStudent.status != "pending")
            .order_by(TutorStudent.name.asc(), TutorStudent.id.asc(), TutorGroup.name.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def payments(
        self, owner_id: int, start: date, end: date
    ) -> list[tuple[TutorFeePayment, str, str]]:
        """Payments in the month, with group and student names."""
        stmt = (
            select(TutorFeePayment, TutorGroup.name, TutorStudent.name)
            .join(TutorInvoice, TutorInvoice.id == TutorFeePayment.invoice_id)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .join(TutorStudent, TutorStudent.id == TutorInvoice.student_id)
            .where(
                TutorGroup.owner_id == owner_id,
                TutorFeePayment.paid_on >= start,
                TutorFeePayment.paid_on < end,
            )
            .order_by(TutorFeePayment.paid_on.asc(), TutorFeePayment.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def attendance(
        self, owner_id: int, group_id: int, start: datetime, end: datetime
    ) -> list[tuple[str, datetime | None, str]]:
        """Student, session start, and status for one owned group."""
        stmt = (
            select(TutorStudent.name, TutorLesson.starts_at, TutorAttendance.status)
            .join(TutorLesson, TutorLesson.id == TutorAttendance.lesson_id)
            .join(TutorStudent, TutorStudent.id == TutorAttendance.student_id)
            .where(
                TutorLesson.owner_id == owner_id,
                TutorLesson.group_id == group_id,
                TutorLesson.starts_at >= start,
                TutorLesson.starts_at < end,
            )
            .order_by(TutorLesson.starts_at.asc(), TutorStudent.name.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())
