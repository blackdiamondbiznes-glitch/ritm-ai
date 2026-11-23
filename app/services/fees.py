"""Create course invoices. Payments live in fee_pay.py. Packages count in fee_usage.py."""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.users import User
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.services.access import AccessService
from app.services.clock import Clock, utcnow
from app.services.fee_rules import (
    add_month,
    invoice_status,
    on_or_after,
    periods_due,
    tashkent_today,
)

MODES = frozenset({"none", "monthly", "package"})
AMOUNT_MAX = 1_000_000_000


class FeeError(Exception):
    """Invalid fee input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FeeService:
    """Turn a group's price into invoices. Existing invoices keep their amount."""

    def __init__(
        self,
        invoices: InvoiceRepository,
        groups: GroupRepository,
        users: object | None = None,
        access: AccessService | None = None,
        now: Clock | None = None,
    ) -> None:
        self._invoices = invoices
        self._groups = groups
        self._users = users
        self._access = access
        self._now = now or utcnow

    async def set_group_fee(self, owner_id: int, group_id: int, body: dict) -> dict:
        """Store the price. Only invoices created after this use the new numbers."""
        group = await self._owned(owner_id, group_id)
        mode, amount, package, day, due = _fee_input(body)
        group.fee_mode = mode
        group.fee_uzs = amount
        group.package_lessons = package
        group.billing_day = day
        group.due_days = due
        await self._groups.save(group)
        await self.sync_group(group)
        return _fee_body(group)

    async def set_override(self, owner_id: int, group_id: int, student_id: int, body: dict) -> dict:
        """A personal price for future invoices. Null clears it."""
        group = await self._owned(owner_id, group_id)
        link = await self._groups.membership(group.id, student_id)
        if link is None or link.status != "active":
            raise FeeError("missing")
        link.fee_override_uzs = _override(body.get("fee_override_uzs"))
        await self._groups.save_member(link)
        return {"student_id": student_id, "fee_override_uzs": link.fee_override_uzs}

    async def sync_group(self, group: TutorGroup) -> int:
        """Create any invoice whose period has started. Repeating is a no-op."""
        if group.fee_mode == "none":
            return 0
        today = tashkent_today(self._now())
        added = 0
        for student in await self._groups.members(group.id):
            link = await self._groups.membership(group.id, student.id)
            if link is None:
                continue
            added += await self.sync_member(group, link, today)
        return added

    async def sync_member(
        self, group: TutorGroup, link: TutorGroupMember, today: date | None = None
    ) -> int:
        """Create the invoices this active member should already have."""
        if link.status != "active" or group.fee_mode == "none":
            return 0
        today = today or tashkent_today(self._now())
        if link.billing_start is None:
            link.billing_start = today
            await self._groups.save_member(link)
        if group.fee_mode == "monthly" and group.billing_day is not None:
            return await self._monthly(group, link, today, open_first=True)
        if group.fee_mode == "package" and group.package_lessons is not None:
            return await self._first_package(group, link, today)
        return 0

    async def run_daily(self) -> int:
        """Create due invoices for every priced group and mark late ones overdue."""
        today = tashkent_today(self._now())
        added = 0
        for group in await self._groups.all_groups():
            if group.fee_mode != "none":
                added += await self.sync_group(group)
        await self._invoices.mark_overdue(today)
        return added

    async def _monthly(
        self, group: TutorGroup, link: TutorGroupMember, today: date, *, open_first: bool = False
    ) -> int:
        added = 0
        assert link.billing_start is not None and group.billing_day is not None
        spans = periods_due(group.billing_day, link.billing_start, today)
        if open_first and not spans:
            start = on_or_after(link.billing_start, group.billing_day)
            spans = [(start, add_month(start) - timedelta(days=1))]
        for start, end in spans:
            new_id = await self._invoices.insert_ignore(
                _row(group, link, "monthly", start, end, None, today)
            )
            if new_id is not None:
                added += 1
        return added

    async def _first_package(self, group: TutorGroup, link: TutorGroupMember, today: date) -> int:
        existing = await self._invoices.for_member(group.id, link.student_id)
        if any(row.kind == "package" for row in existing):
            return 0
        assert link.billing_start is not None
        new_id = await self._invoices.insert_ignore(
            _row(group, link, "package", link.billing_start, None, group.package_lessons, today)
        )
        return 1 if new_id is not None else 0

    async def _owned(self, owner_id: int, group_id: int) -> TutorGroup:
        group = await self._groups.get_owned(owner_id, group_id)
        if group is None:
            raise FeeError("missing")
        return group

    async def owner(self, owner_id: int) -> User:
        """The user row, or missing when the id is not a person."""
        if self._users is None:
            raise FeeError("missing")
        owner = await self._users.get_by_id(owner_id)
        if owner is None:
            raise FeeError("missing")
        return owner


def _row(group, link, kind, start, end, lessons, today) -> dict:
    amount = group.fee_uzs if link.fee_override_uzs is None else link.fee_override_uzs
    due = start + timedelta(days=group.due_days)
    status = invoice_status(0, amount, due, today, "due")
    return {
        "workspace_id": group.workspace_id,
        "group_id": group.id,
        "student_id": link.student_id,
        "kind": kind,
        "period_start": start,
        "period_end": end,
        "lessons_total": lessons,
        "lessons_used": 0,
        "amount_uzs": amount,
        "paid_uzs": 0,
        "due_on": due,
        "status": status,
    }


def _fee_body(group: TutorGroup) -> dict:
    return {
        "fee_mode": group.fee_mode,
        "fee_uzs": group.fee_uzs,
        "package_lessons": group.package_lessons,
        "billing_day": group.billing_day,
        "due_days": group.due_days,
    }


def _fee_input(body: dict) -> tuple[str, int, int | None, int | None, int]:
    mode = body.get("fee_mode", "none")
    if not isinstance(mode, str) or mode not in MODES:
        raise FeeError("mode")
    amount = _money(body.get("fee_uzs", 0))
    due = _span(body.get("due_days", 5), 0, 31, "due")
    day = _optional_day(body.get("billing_day"))
    package = _optional_size(body.get("package_lessons"))
    if mode == "monthly" and day is None:
        raise FeeError("day")
    if mode == "package" and package is None:
        raise FeeError("package")
    if mode != "monthly":
        day = None
    if mode != "package":
        package = None
    return mode, amount, package, day, due


def _money(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > AMOUNT_MAX:
        raise FeeError("amount")
    return value


def _override(value: object) -> int | None:
    if value is None:
        return None
    return _money(value)


def _span(value: object, low: int, high: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > high:
        raise FeeError(code)
    return value


def _optional_day(value: object) -> int | None:
    if value is None:
        return None
    return _span(value, 1, 28, "day")


def _optional_size(value: object) -> int | None:
    if value is None:
        return None
    return _span(value, 1, 100, "package")
