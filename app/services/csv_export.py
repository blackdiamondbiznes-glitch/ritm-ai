"""UTF-8 CSV with a BOM so Excel opens Uzbek and Cyrillic text."""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime

from app.db.models.users import User
from app.db.repositories.exports import ExportRepository
from app.db.repositories.groups import GroupRepository
from app.services.access import AccessService
from app.services.clock import TASHKENT
from app.services.month_report import ReportError, _span

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


class ExportError(Exception):
    """The file cannot be built. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CsvExport:
    """Owner-scoped spreadsheets. Pro and Ultra only."""

    def __init__(
        self, rows: ExportRepository, groups: GroupRepository, access: AccessService
    ) -> None:
        self._rows = rows
        self._groups = groups
        self._access = access

    async def students(self, owner: User, today: str) -> tuple[str, bytes]:
        """Every visible card. Group names are joined with a semicolon."""
        await self._allow(owner)
        grouped: dict[int, list] = {}
        for student, group_name in await self._rows.students(owner.id):
            bucket = grouped.setdefault(student.id, [student, []])
            if group_name:
                bucket[1].append(group_name)
        table = [
            [student.name, student.phone or "", student.status, "; ".join(names)]
            for student, names in grouped.values()
        ]
        return f"students-{today}.csv", _csv(["name", "phone", "status", "groups"], table)

    async def payments(self, owner: User, month: str, today: str) -> tuple[str, bytes]:
        """Payments whose date falls in the month."""
        await self._allow(owner)
        try:
            start, end = _span(month)
        except ReportError as exc:
            raise ExportError(exc.code) from exc
        table = [
            [payment.paid_on.isoformat(), group, student, payment.amount_uzs, payment.method]
            for payment, group, student in await self._rows.payments(owner.id, start, end)
        ]
        header = ["paid_on", "group", "student", "amount_uzs", "method"]
        return f"payments-{today}.csv", _csv(header, table)

    async def attendance(
        self, owner: User, group_id: int, month: str, today: str
    ) -> tuple[str, bytes]:
        """One group's marks. A foreign group is missing, a low plan is refused."""
        if await self._groups.get_owned(owner.id, group_id) is None:
            raise ExportError("missing")
        await self._allow(owner)
        if _MONTH.fullmatch(month or "") is None:
            raise ExportError("month")
        start_date, end_date = _span(month)
        start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=TASHKENT)
        end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=TASHKENT)
        table = []
        for name, starts_at, status in await self._rows.attendance(
            owner.id, group_id, start.astimezone(UTC), end.astimezone(UTC)
        ):
            when = starts_at.astimezone(TASHKENT).strftime("%Y-%m-%d %H:%M") if starts_at else ""
            table.append([name, when, status])
        return f"attendance-{today}.csv", _csv(["student", "starts_at", "status"], table)

    async def _allow(self, owner: User) -> None:
        limits = await self._access.tutor_limits(owner)
        if not limits.reports:
            raise ExportError("export")


_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> object:
    """Stop Excel treating a text cell as a formula."""
    if not isinstance(value, str) or not value.startswith(_FORMULA):
        return value
    return "'" + value


def _csv(header: list[str], rows: list[list[object]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
