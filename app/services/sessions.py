"""Dated sessions generated from a group's weekly slot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models.groups import TutorGroup
from app.db.models.lessons import TutorLesson
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.services.clock import TASHKENT, Clock, utcnow

HORIZON_DAYS = 14
KIND = "tutor_sessions"


class SessionError(Exception):
    """Invalid session input. `code` is a stable API error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def has_attendance(_row: TutorLesson) -> bool:
    """Phase 3 records attendance. Until that table exists, nothing is locked."""
    return False


def sessions_due(now: datetime, last_day: str | None) -> str | None:
    """Return today's Tashkent date when the daily fill has not run yet."""
    day = now.astimezone(TASHKENT).date().isoformat()
    if last_day == day:
        return None
    return day


def slots_for(
    group: TutorGroup, now: datetime, horizon_days: int = HORIZON_DAYS
) -> list[tuple[datetime, datetime]]:
    """Slots on the group's weekdays for the next `horizon_days` Tashkent dates.

    Today is included even when the clock is already past the start time.
    """
    local = now.astimezone(TASHKENT).date()
    days = {int(part) for part in group.weekdays.split(",") if part}
    start_h, start_m = divmod(group.start_min, 60)
    end_h, end_m = divmod(group.end_min, 60)
    found: list[tuple[datetime, datetime]] = []
    for offset in range(horizon_days):
        day = local + timedelta(days=offset)
        if day.isoweekday() not in days:
            continue
        start = datetime(day.year, day.month, day.day, start_h, start_m, tzinfo=TASHKENT)
        end = datetime(day.year, day.month, day.day, end_h, end_m, tzinfo=TASHKENT)
        found.append((start.astimezone(UTC), end.astimezone(UTC)))
    return found


class SessionPlanner:
    """Fill a horizon of schedule sessions. A taken slot is left alone."""

    def __init__(
        self,
        lessons: LessonRepository,
        groups: GroupRepository,
        now: Clock | None = None,
    ) -> None:
        self._lessons = lessons
        self._groups = groups
        self._now = now or utcnow

    async def fill(self, group: TutorGroup, horizon_days: int = HORIZON_DAYS) -> int:
        """Insert missing schedule sessions. Cancelled and moved slots stay."""
        added = 0
        for start, end in slots_for(group, self._now(), horizon_days):
            new_id = await self._lessons.insert_slot(_schedule_row(group, start, end))
            if new_id is not None:
                added += 1
        return added

    async def refill(self, group: TutorGroup) -> int:
        """Drop untouched future schedule rows with no attendance, then fill."""
        rows = await self._lessons.replaceable(group.id, self._now())
        await self._lessons.delete_many([row for row in rows if not has_attendance(row)])
        return await self.fill(group)

    async def fill_all(self, horizon_days: int = HORIZON_DAYS) -> int:
        """Fill every group. Does not delete rows the teacher already changed."""
        added = 0
        for group in await self._groups.all_groups():
            added += await self.fill(group, horizon_days)
        return added


def _schedule_row(group: TutorGroup, start: datetime, end: datetime) -> dict:
    return {
        "owner_id": group.owner_id,
        "workspace_id": group.workspace_id,
        "group_id": group.id,
        "student_id": None,
        "title": group.name,
        "status": "scheduled",
        "source": "schedule",
        "amount_uzs": 0,
        "starts_at": start,
        "ends_at": end,
        "planned_at": start,
        "note": None,
    }
