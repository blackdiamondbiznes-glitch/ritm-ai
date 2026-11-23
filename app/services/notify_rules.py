"""Quiet hours and the small choices shared by notice planning and sending."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.clock import TASHKENT

NOTIFY = "tutor_notify"
METRIC = "tutor_notify"
LESSON_MINUTES = frozenset({15, 30, 60, 120})
FEE_DAYS = frozenset({1, 3, 7})
_LANGS = frozenset({"uz", "ru", "en"})


def quiet_wake(now: datetime) -> datetime | None:
    """22:00–08:00 Tashkent waits until 08:00. Other hours send now."""
    local = now.astimezone(TASHKENT)
    if local.hour >= 22:
        nxt = (local + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        return nxt.astimezone(UTC)
    if local.hour < 8:
        wake = local.replace(hour=8, minute=0, second=0, microsecond=0)
        return wake.astimezone(UTC)
    return None


def language(code: str | None) -> str:
    """A supported language, otherwise Uzbek."""
    return code if code in _LANGS else "uz"


def lesson_label(name: str, level: str | None) -> str:
    """Group name plus level, the text shown in a lesson notice."""
    if level:
        return f"{name} {level}"
    return name


def run_at(now: datetime, starts_at: datetime | None, kind: str) -> tuple[datetime, bool]:
    """When to send, and whether a lesson reminder would arrive too late."""
    wake = quiet_wake(now)
    if wake is None:
        return now, False
    if kind == "lesson" and starts_at is not None and wake >= starts_at:
        return now, True
    return wake, False


def period_key(now: datetime) -> str:
    """Tashkent calendar month, the key used by the send quota."""
    return now.astimezone(TASHKENT).strftime("%Y-%m")


def day_ref(day: object) -> int:
    """YYYYMMDD as an integer so one day is one event id."""
    return int(day.strftime("%Y%m%d"))  # type: ignore[attr-defined]


def month_ref(now: datetime) -> int:
    """Negative YYYYMM so the monthly quota note cannot clash with a real id."""
    return -int(now.astimezone(TASHKENT).strftime("%Y%m"))


def move_ref(lesson_id: int, starts_at: datetime) -> int:
    """One move event per lesson and new start. A repeat of the same time is one send."""
    return lesson_id * 10_000_000_000 + int(starts_at.timestamp())
