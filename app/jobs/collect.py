"""Pure decision: which schedules are due. No database and no Telegram."""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Slot:
    """A schedule that should get one job for this local date."""

    schedule_id: int
    chat_id: int
    slot: str


@dataclass(frozen=True)
class Row:
    """Planner input. `days` uses ISO weekday numbers, Monday is 1."""

    schedule_id: int
    chat_id: int
    timezone: str
    time_of_day: time
    days: tuple[int, ...]


def collect_due(now: datetime, rows: list[Row], taken: set[tuple[int, str]]) -> list[Slot]:
    """One slot per chat per local date, and only after the chosen clock time."""
    found: list[Slot] = []
    for row in rows:
        slot = _slot(now, row)
        if slot is None or (row.chat_id, slot) in taken:
            continue
        found.append(Slot(row.schedule_id, row.chat_id, slot))
    return found


def _slot(now: datetime, row: Row) -> str | None:
    try:
        zone = ZoneInfo(row.timezone)
    except (KeyError, ValueError):
        return None
    local = now.astimezone(zone)
    if local.isoweekday() not in row.days:
        return None
    if (local.hour, local.minute) < (row.time_of_day.hour, row.time_of_day.minute):
        return None
    return local.date().isoformat()
