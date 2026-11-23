"""One month of attendance, fees, and membership changes for a teacher."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.db.models.users import User
from app.db.repositories.cabinet_stats import CabinetStatsRepository
from app.db.repositories.groups import GroupRepository
from app.services.access import AccessService
from app.services.attendance import attendance_rate
from app.services.clock import TASHKENT

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


class ReportError(Exception):
    """The report cannot be shown. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MonthReport:
    """Build the monthly tutor report. Pro and Ultra only."""

    def __init__(
        self,
        stats: CabinetStatsRepository,
        groups: GroupRepository,
        access: AccessService,
    ) -> None:
        self._stats = stats
        self._groups = groups
        self._access = access

    async def for_owner(self, owner: User, month: str) -> dict:
        """Numbers for one Tashkent month. A lower plan is refused."""
        await self._allow(owner)
        return await self._build(owner.id, month)

    async def for_workspace(self, owner_id: int, month: str) -> dict:
        """The same numbers, used by the monthly job after the plan check."""
        return await self._build(owner_id, month)

    async def _allow(self, owner: User) -> None:
        limits = await self._access.tutor_limits(owner)
        if not limits.reports:
            raise ReportError("export")

    async def _build(self, owner_id: int, month: str) -> dict:
        start_date, end_date = _span(month)
        start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=TASHKENT)
        end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=TASHKENT)
        groups = await self._groups.list_for_owner(owner_id)
        marks = await self._stats.marks(owner_id, start.astimezone(UTC), end.astimezone(UTC))
        collected = dict(await self._stats.collected(owner_id, start_date, end_date))
        outstanding = dict(await self._stats.outstanding(owner_id, start_date, end_date))
        by_group: dict[int, list[str]] = {}
        for group_id, status in marks:
            by_group.setdefault(group_id, []).append(status)
        rows = []
        for group, _count in groups:
            rate = attendance_rate(by_group.get(group.id, []))["rate"]
            rows.append(
                {
                    "group_id": group.id,
                    "name": group.name,
                    "attendance_rate": rate,
                    "collected_uzs": collected.get(group.id, 0),
                    "outstanding_uzs": outstanding.get(group.id, 0),
                }
            )
        return {
            "month": month,
            "groups": rows,
            "new_students": await self._stats.joined(
                owner_id, start.astimezone(UTC), end.astimezone(UTC)
            ),
            "left_students": await self._stats.left(
                owner_id, start.astimezone(UTC), end.astimezone(UTC)
            ),
        }


def _span(month: str):
    match = _MONTH.fullmatch(month or "")
    if match is None:
        raise ReportError("month")
    year, mon = int(match.group(1)), int(match.group(2))
    if mon < 1 or mon > 12:
        raise ReportError("month")
    start = datetime(year, mon, 1).date()
    if mon == 12:
        end = datetime(year + 1, 1, 1).date()
    else:
        end = datetime(year, mon + 1, 1).date()
    return start, end
