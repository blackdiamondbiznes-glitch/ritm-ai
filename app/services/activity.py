"""Weekly and daily activity totals for the Mini App. No presentation text."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol

from app.services.clock import Clock, utcnow
from app.services.scoring import current_week, previous_week, resolve_zone

METRICS = ("posts", "quizzes", "answers", "participants")


class EngagementCounts(Protocol):
    """The four windowed counters used by the dashboard."""

    async def posts_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int: ...

    async def quizzes_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int: ...

    async def answers_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int: ...

    async def participants_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int: ...


class DailyCounts(Protocol):
    """Per-day grouped counters for the dashboard spark chart."""

    async def daily_counts(
        self, chat_ids: list[int], started: datetime, until: datetime, timezone: str
    ) -> dict[date, dict[str, int]]: ...


DAILY_METRICS = ("posts", "quizzes", "answers")


@dataclass(frozen=True)
class WindowCounts:
    """Four real activity totals for one window."""

    posts: int
    quizzes: int
    answers: int
    participants: int


def change_percent(current: int, previous: int) -> int | None:
    """Whole-number percent change, or None when the previous window is empty."""
    if previous <= 0:
        return None
    return round((current - previous) * 100 / previous)


def pack_metric(current: int, previous: int | None = None) -> dict[str, int]:
    """A metric object. `change_pct` is omitted when it cannot be computed."""
    data = {"value": current}
    if previous is not None:
        change = change_percent(current, previous)
        if change is not None:
            data["change_pct"] = change
    return data


def pack_window(current: WindowCounts, previous: WindowCounts | None = None) -> dict[str, dict]:
    """Map each metric to its value and optional week-over-week change."""
    packed = {}
    for name in METRICS:
        prior = None if previous is None else getattr(previous, name)
        packed[name] = pack_metric(getattr(current, name), prior)
    return packed


def add_counts(left: WindowCounts, right: WindowCounts) -> WindowCounts:
    """Sum two windows, used when aggregating an owner's chats."""
    return WindowCounts(
        left.posts + right.posts,
        left.quizzes + right.quizzes,
        left.answers + right.answers,
        left.participants + right.participants,
    )


class ActivityService:
    """Build today / this-week / last-week totals from stored events."""

    def __init__(self, engagement: EngagementCounts, now: Clock | None = None) -> None:
        self._engagement = engagement
        self._now = now or utcnow

    async def counts(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> WindowCounts:
        """One chat, one half-open window."""
        posts = await self._engagement.posts_since(chat_id, started, until)
        quizzes = await self._engagement.quizzes_since(chat_id, started, until)
        answers = await self._engagement.answers_since(chat_id, started, until)
        people = await self._engagement.participants_since(chat_id, started, until)
        return WindowCounts(posts, quizzes, answers, people)

    async def total(
        self, chat_ids: list[int], started: datetime, until: datetime | None = None
    ) -> WindowCounts:
        """Sum the same window across the owner's chats."""
        acc = WindowCounts(0, 0, 0, 0)
        for chat_id in chat_ids:
            acc = add_counts(acc, await self.counts(chat_id, started, until))
        return acc

    async def overview(self, chat_ids: list[int], timezone: str) -> dict[str, object]:
        """Today and week totals, with last-week change only when it is defined."""
        now = self._now()
        week = current_week(now, timezone)
        prev = previous_week(now, timezone)
        zone = resolve_zone(timezone)
        today_start = datetime.combine(now.astimezone(zone).date(), time.min, tzinfo=zone)
        windows = [(week.start, week.end), (prev.start, prev.end), (today_start, week.end)]
        grouped = getattr(self._engagement, "window_counts", None)
        if grouped is not None:
            rows = await grouped(chat_ids, windows)
            this_week, last_week, today = (
                WindowCounts(**{name: row[name] for name in METRICS}) for row in rows
            )
        else:
            this_week = await self.total(chat_ids, week.start, week.end)
            last_week = await self.total(chat_ids, prev.start, prev.end)
            today = await self.total(chat_ids, today_start, week.end)
        return {
            "timezone": timezone,
            "week": {"start": week.start.isoformat(), "end": week.end.isoformat()},
            "week_counts": pack_window(this_week, last_week),
            "today_counts": pack_window(today),
        }

    async def daily(
        self, chat_ids: list[int], timezone: str, days: int = 7
    ) -> list[dict[str, object]]:
        """One row per local day, oldest first, ending today. Missing days are zero."""
        source = self._engagement
        if not hasattr(source, "daily_counts"):
            return []
        zone = resolve_zone(timezone)
        today = self._now().astimezone(zone).date()
        first = today - timedelta(days=days - 1)
        started = datetime.combine(first, time.min, tzinfo=zone)
        until = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
        rows = await source.daily_counts(chat_ids, started, until, str(zone))
        out: list[dict[str, object]] = []
        for offset in range(days):
            day = first + timedelta(days=offset)
            found = rows.get(day, {})
            item: dict[str, object] = {"date": day.isoformat()}
            for name in DAILY_METRICS:
                item[name] = int(found.get(name, 0))
            out.append(item)
        return out
