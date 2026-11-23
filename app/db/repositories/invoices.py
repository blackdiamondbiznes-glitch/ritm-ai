"""Invoice and course-payment queries. No validation here."""

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.students import TutorStudent


class InvoiceRepository:
    """Read and write one teacher's invoices."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_ignore(self, values: dict) -> int | None:
        """Insert a period. A repeat of the same slot inserts nothing."""
        stmt = (
            pg_insert(TutorInvoice)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_tutor_invoices_period")
            .returning(TutorInvoice.id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_owned(self, owner_id: int, invoice_id: int) -> TutorInvoice | None:
        """The invoice only when its group belongs to this owner."""
        stmt = (
            select(TutorInvoice)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(TutorInvoice.id == invoice_id, TutorGroup.owner_id == owner_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def for_member(self, group_id: int, student_id: int) -> list[TutorInvoice]:
        """Every invoice for this student in this group, oldest period first."""
        stmt = (
            select(TutorInvoice)
            .where(TutorInvoice.group_id == group_id, TutorInvoice.student_id == student_id)
            .order_by(TutorInvoice.period_start.asc(), TutorInvoice.id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_owner(
        self, owner_id: int, status: str | None, group_id: int | None
    ) -> list[tuple[TutorInvoice, str, str]]:
        """Invoices with group and student names. Soonest due date first."""
        stmt = (
            select(TutorInvoice, TutorGroup.name, TutorStudent.name)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .join(TutorStudent, TutorStudent.id == TutorInvoice.student_id)
            .where(TutorGroup.owner_id == owner_id)
            .order_by(TutorInvoice.due_on.asc(), TutorInvoice.id.asc())
        )
        if status:
            stmt = stmt.where(TutorInvoice.status == status)
        if group_id is not None:
            stmt = stmt.where(TutorInvoice.group_id == group_id)
        result = await self._session.execute(stmt)
        return [(row, group_name, student_name) for row, group_name, student_name in result.all()]

    async def save(self, row: TutorInvoice) -> TutorInvoice:
        """Flush changes on an invoice already loaded in this session."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_overdue(self, today: date) -> int:
        """Flip unpaid due invoices whose due date has passed."""
        stmt = (
            update(TutorInvoice)
            .where(
                TutorInvoice.status == "due",
                TutorInvoice.due_on < today,
                TutorInvoice.paid_uzs < TutorInvoice.amount_uzs,
            )
            .values(status="overdue")
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)

    async def add_payment(self, row: TutorFeePayment) -> TutorFeePayment:
        """Insert a payment row."""
        self._session.add(row)
        await self._session.flush()
        return row

    async def payment_owned(self, owner_id: int, payment_id: int) -> TutorFeePayment | None:
        """A payment only when the invoice's group belongs to this owner."""
        stmt = (
            select(TutorFeePayment)
            .join(TutorInvoice, TutorInvoice.id == TutorFeePayment.invoice_id)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(TutorFeePayment.id == payment_id, TutorGroup.owner_id == owner_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def delete_payment(self, row: TutorFeePayment) -> None:
        """Remove a payment."""
        await self._session.delete(row)
        await self._session.flush()

    async def collected(self, owner_id: int, start: date, end: date) -> int:
        """Sum of payments whose paid_on is in [start, end)."""
        stmt = (
            select(func.coalesce(func.sum(TutorFeePayment.amount_uzs), 0))
            .join(TutorInvoice, TutorInvoice.id == TutorFeePayment.invoice_id)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(
                TutorGroup.owner_id == owner_id,
                TutorFeePayment.paid_on >= start,
                TutorFeePayment.paid_on < end,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def open_balances(self, owner_id: int) -> tuple[int, int]:
        """Outstanding sum of due and overdue invoices, and the overdue count."""
        owed = func.coalesce(func.sum(TutorInvoice.amount_uzs - TutorInvoice.paid_uzs), 0)
        late = func.count(TutorInvoice.id).filter(TutorInvoice.status == "overdue")
        stmt = (
            select(owed, late)
            .join(TutorGroup, TutorGroup.id == TutorInvoice.group_id)
            .where(
                TutorGroup.owner_id == owner_id,
                TutorInvoice.status.in_(("due", "overdue")),
            )
        )
        owed_sum, late_count = (await self._session.execute(stmt)).one()
        return int(owed_sum), int(late_count)

    async def learning(
        self, telegram_id: int, skip_owner_id: int
    ) -> list[tuple[TutorGroup, TutorStudent]]:
        """Groups where this account is an active member and not the teacher."""
        stmt = (
            select(TutorGroup, TutorStudent)
            .join(TutorGroupMember, TutorGroupMember.group_id == TutorGroup.id)
            .join(TutorStudent, TutorStudent.id == TutorGroupMember.student_id)
            .where(
                TutorStudent.telegram_id == telegram_id,
                TutorGroup.owner_id != skip_owner_id,
                TutorGroupMember.status == "active",
            )
            .order_by(TutorGroup.id.asc())
        )
        result = await self._session.execute(stmt)
        return [(group, student) for group, student in result.all()]
