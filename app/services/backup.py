"""When the daily database backup is due. One run per Asia/Tashkent calendar day."""

from datetime import datetime, time

from app.services.clock import TASHKENT

BACKUP_DAY = "backup_last_day"
BACKUP_RESULT = "backup_last_result"


def backup_due(now: datetime, at: time, last_day: str | None) -> str | None:
    """Return today's local date (YYYY-MM-DD) when a backup should run, else None."""
    local = now.astimezone(TASHKENT)
    day = local.date().isoformat()
    if local.time() < at or last_day == day:
        return None
    return day
