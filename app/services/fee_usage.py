"""Count present and late marks against the open lesson package."""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.invoices import TutorInvoice
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.services.clock import Clock, utcnow
from app.services.fee_rules import tashkent_today
from app.services.fees import FeeService

ATTENDED = frozenset({"present", "late"})


def usage_deltas(
    before: dict[int, str], planned: list[tuple[int, str | None, object]]
) -> list[tuple[int, int]]:
    """+1 when a mark starts counting, -1 when it stops. Late and present both count."""
    deltas: list[tuple[int, int]] = []
    for student_id, status, _note in planned:
        was = before.get(student_id) in ATTENDED
        now = status in ATTENDED
        if now and not was:
            deltas.append((student_id, 1))
        elif was and not now:
            deltas.append((student_id, -1))
    return deltas


class PackageUsage:
    """Move lessons_used and open the next package when one fills up."""

    def __init__(
        self,
        invoices: InvoiceRepository,
        groups: GroupRepository,
        fees: FeeService,
        now: Clock | None = None,
    ) -> None:
        self._invoices = invoices
        self._groups = groups
        self._fees = fees
        self._now = now or utcnow

    async def adjust(self, group_id: int, deltas: list[tuple[int, int]]) -> None:
        """Apply attendance deltas for one group. Other fee modes do nothing."""
        if not deltas:
            return
        group = await self._groups.get(group_id)
        if group is None or group.fee_mode != "package":
            return
        today = tashkent_today(self._now())
        for student_id, delta in deltas:
            link = await self._groups.membership(group.id, student_id)
            if link is None or link.status != "active":
                continue
            if delta > 0:
                await self._add(group, link, today)
            elif delta < 0:
                await self._remove(group.id, student_id)

    async def _add(self, group: TutorGroup, link: TutorGroupMember, today: date) -> None:
        await self._fees.sync_member(group, link, today)
        rows = await self._packages(group.id, link.student_id)
        open_row = next((row for row in rows if _open(row)), None)
        if open_row is None:
            return
        open_row.lessons_used += 1
        await self._invoices.save(open_row)
        if open_row.lessons_used < (open_row.lessons_total or 0):
            return
        if any(_open(row) for row in rows if row.id != open_row.id):
            return
        start = max(today, open_row.period_start + timedelta(days=1))
        await self._invoices.insert_ignore(
            _next(group, link, start, today, group.package_lessons or open_row.lessons_total or 1)
        )

    async def _remove(self, group_id: int, student_id: int) -> None:
        rows = await self._packages(group_id, student_id)
        used = [row for row in rows if row.lessons_used > 0 and row.status != "waived"]
        if not used:
            return
        row = used[-1]
        row.lessons_used -= 1
        await self._invoices.save(row)

    async def _packages(self, group_id: int, student_id: int) -> list[TutorInvoice]:
        rows = await self._invoices.for_member(group_id, student_id)
        return [row for row in rows if row.kind == "package"]


def _open(row: TutorInvoice) -> bool:
    total = row.lessons_total or 0
    return row.status != "waived" and row.lessons_used < total


def _next(group, link, start: date, today: date, lessons: int) -> dict:
    from app.services.fees import _row

    return _row(group, link, "package", start, None, lessons, today)
