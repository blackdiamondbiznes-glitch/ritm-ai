"""Clock helper so tests can freeze time."""

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")


def utcnow() -> datetime:
    """Current time in UTC."""
    return datetime.now(UTC)


def format_tashkent(moment: datetime, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Format a UTC or aware datetime in Asia/Tashkent."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(TASHKENT).strftime(fmt)


Clock = Callable[[], datetime]
