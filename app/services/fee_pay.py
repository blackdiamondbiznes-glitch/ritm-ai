"""Record, undo, and waive course payments. Free plans can see invoices only."""

from __future__ import annotations

from datetime import date

from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.users import User
from app.db.repositories.invoices import InvoiceRepository
from app.services.access import AccessService
from app.services.clock import Clock, utcnow
from app.services.fee_rules import invoice_status, tashkent_today
from app.services.fees import AMOUNT_MAX, FeeError, FeeService
from app.services.tutor_limits import TutorLimitError

METHODS = frozenset({"cash", "card", "transfer", "other"})
NOTE_MAX = 200


class FeePay:
    """Money against an invoice. Overpayment is rejected."""

    def __init__(
        self,
        invoices: InvoiceRepository,
        fees: FeeService,
        access: AccessService | None = None,
        now: Clock | None = None,
    ) -> None:
        self._invoices = invoices
        self._fees = fees
        self._access = access
        self._now = now or utcnow
        self._students = None

    async def invoices(self, owner_id: int, status: str | None, group_id: int | None) -> list[dict]:
        """The owner's invoices, optionally one status and one group."""
        if status is not None and status not in ("due", "paid", "overdue", "waived"):
            raise FeeError("status")
        rows = await self._invoices.list_for_owner(owner_id, status, group_id)
        return [_public(row, group_name, student_name) for row, group_name, student_name in rows]

    async def summary(self, owner_id: int) -> dict:
        """Collected this Tashkent month, outstanding balance, and overdue count."""
        today = tashkent_today(self._now())
        start = date(today.year, today.month, 1)
        end = (
            date(today.year + 1, 1, 1)
            if today.month == 12
            else date(today.year, today.month + 1, 1)
        )
        collected = await self._invoices.collected(owner_id, start, end)
        outstanding, overdue = await self._invoices.open_balances(owner_id)
        opening = await self._opening(owner_id)
        return {
            "collected_uzs": collected,
            "outstanding_uzs": outstanding + opening,
            "opening_uzs": opening,
            "overdue_count": overdue,
        }

    def use_students(self, students) -> None:
        """Opening balances on student cards join the fee total."""
        self._students = students

    async def _opening(self, owner_id: int) -> int:
        if self._students is None:
            return 0
        rows = await self._invoices.list_for_owner(owner_id, None, None)
        covered = {
            row.student_id for row, _group, _name in rows if row.status in ("due", "overdue")
        }
        total = 0
        for student in await self._students.list_for_owner(owner_id):
            if student.status == "debtor" and student.id not in covered:
                total += int(student.amount_uzs or 0)
        return total

    async def pay(self, owner_id: int, invoice_id: int, body: dict) -> dict:
        """Add a partial or final payment. The plan must allow recording fees."""
        row = await self._owned(owner_id, invoice_id)
        await self._allow(owner_id)
        if row.status == "waived":
            raise FeeError("status")
        amount = _pay_amount(body.get("amount_uzs"))
        if row.paid_uzs + amount > row.amount_uzs:
            raise FeeError("amount")
        method = body.get("method")
        if not isinstance(method, str) or method not in METHODS:
            raise FeeError("method")
        paid_on = _day(body.get("paid_on"))
        note = _note(body.get("note")) if "note" in body else None
        await self._invoices.add_payment(
            TutorFeePayment(
                invoice_id=row.id,
                amount_uzs=amount,
                paid_on=paid_on,
                method=method,
                note=note,
                created_by=owner_id,
            )
        )
        row.paid_uzs += amount
        row.status = invoice_status(
            row.paid_uzs, row.amount_uzs, row.due_on, tashkent_today(self._now()), row.status
        )
        await self._invoices.save(row)
        return _public(row, None, None)

    async def remove(self, owner_id: int, payment_id: int) -> dict:
        """Delete a payment and restore the invoice status."""
        payment = await self._invoices.payment_owned(owner_id, payment_id)
        if payment is None:
            raise FeeError("missing")
        await self._allow(owner_id)
        row = await self._owned(owner_id, payment.invoice_id)
        await self._invoices.delete_payment(payment)
        row.paid_uzs = max(0, row.paid_uzs - payment.amount_uzs)
        row.status = invoice_status(
            row.paid_uzs, row.amount_uzs, row.due_on, tashkent_today(self._now()), "due"
        )
        await self._invoices.save(row)
        return _public(row, None, None)

    async def waive(self, owner_id: int, invoice_id: int) -> dict:
        """Mark the invoice waived. The plan must allow it."""
        row = await self._owned(owner_id, invoice_id)
        await self._allow(owner_id)
        row.status = "waived"
        await self._invoices.save(row)
        return _public(row, None, None)

    async def mine(self, user: User) -> dict:
        """Each group this account studies in, with the next bill and the history."""
        if user.telegram_id is None:
            return {"groups": []}
        pairs = await self._invoices.learning(user.telegram_id, user.id)
        groups = []
        for group, student in pairs:
            rows = await self._invoices.for_member(group.id, student.id)
            current = _current(rows)
            groups.append(
                {
                    "group_id": group.id,
                    "group_name": group.name,
                    **_progress(current),
                    "history": [_public(row, group.name, student.name) for row in reversed(rows)],
                }
            )
        return {"groups": groups}

    async def _allow(self, owner_id: int) -> None:
        if self._access is None:
            raise FeeError("missing")
        owner = await self._fees.owner(owner_id)
        limits = await self._access.tutor_limits(owner)
        if not limits.fees:
            raise TutorLimitError("limit_fees", 0, 0, limits.plan_code)

    async def _owned(self, owner_id: int, invoice_id: int) -> TutorInvoice:
        row = await self._invoices.get_owned(owner_id, invoice_id)
        if row is None:
            raise FeeError("missing")
        return row


def _public(row: TutorInvoice, group_name: str | None, student_name: str | None) -> dict:
    return {
        "id": row.id,
        "group_id": row.group_id,
        "group_name": group_name,
        "student_id": row.student_id,
        "student_name": student_name,
        "kind": row.kind,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "lessons_total": row.lessons_total,
        "lessons_used": row.lessons_used,
        "amount_uzs": row.amount_uzs,
        "paid_uzs": row.paid_uzs,
        "due_on": row.due_on.isoformat(),
        "status": row.status,
    }


def _current(rows: list[TutorInvoice]) -> TutorInvoice | None:
    open_rows = [row for row in rows if row.status in ("due", "overdue")]
    if open_rows:
        return open_rows[0]
    return rows[-1] if rows else None


def _progress(row: TutorInvoice | None) -> dict:
    if row is None:
        return {
            "amount": None,
            "due_on": None,
            "status": None,
            "paid": None,
            "lessons_used": None,
            "lessons_total": None,
        }
    return {
        "amount": row.amount_uzs,
        "due_on": row.due_on.isoformat(),
        "status": row.status,
        "paid": row.paid_uzs,
        "lessons_used": row.lessons_used,
        "lessons_total": row.lessons_total,
    }


def _pay_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > AMOUNT_MAX:
        raise FeeError("amount")
    return value


def _day(value: object) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise FeeError("date")
    try:
        year, month, day = (int(part) for part in value.split("-"))
        return date(year, month, day)
    except ValueError as exc:
        raise FeeError("date") from exc


def _note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FeeError("note")
    text = value.strip()
    if not text:
        return None
    if len(text) > NOTE_MAX:
        raise FeeError("note")
    return text
