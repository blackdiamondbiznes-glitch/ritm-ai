"""Weekly windows and point totals. No database access."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_FALLBACK = "Asia/Tashkent"
_MEDALS = {1: "🥇 ", 2: "🥈 ", 3: "🥉 "}


@dataclass(frozen=True)
class AnswerRow:
    """One stored quiz answer used for scoring."""

    user_id: int
    is_correct: bool
    answered_at: datetime


@dataclass(frozen=True)
class Score:
    """Aggregated points for one member in one week."""

    user_id: int
    points: int
    correct_count: int
    total_answers: int
    first_correct_at: datetime | None


@dataclass(frozen=True)
class Week:
    """Monday 00:00 up to (but not including) the next Monday, in the chat zone."""

    start: datetime
    end: datetime

    @property
    def start_date(self) -> date:
        return self.start.date()

    @property
    def end_date(self) -> date:
        return (self.end - timedelta(seconds=1)).date()


def resolve_zone(name: str | None) -> ZoneInfo:
    """Use the chat timezone, or Asia/Tashkent when the name is unknown."""
    for candidate in (name, _FALLBACK, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, KeyError, ValueError):
            continue
    return ZoneInfo("UTC")


def current_week(now: datetime, timezone: str | None) -> Week:
    """The open Monday–Sunday week that contains `now` in the chat timezone."""
    zone = resolve_zone(timezone)
    local = now.astimezone(zone)
    monday = local.date() - timedelta(days=local.isoweekday() - 1)
    start = datetime.combine(monday, time.min, tzinfo=zone)
    return Week(start, start + timedelta(days=7))


def previous_week(now: datetime, timezone: str | None) -> Week:
    """The Monday–Sunday week that ended before the current local week."""
    week = current_week(now, timezone)
    return Week(week.start - timedelta(days=7), week.start)


def score_answers(rows: list[AnswerRow], points_per_correct: int) -> list[Score]:
    """One score per user. Only `is_correct` rows earn points."""
    totals: dict[int, list[object]] = {}
    for row in rows:
        item = totals.setdefault(row.user_id, [0, 0, None])
        item[1] = int(item[1]) + 1
        if not row.is_correct:
            continue
        item[0] = int(item[0]) + 1
        first = item[2]
        when = row.answered_at
        if first is None or when < first:
            item[2] = when
    scores = [
        Score(user_id, correct * points_per_correct, correct, int(total), first)
        for user_id, (correct, total, first) in totals.items()
    ]
    late = datetime.max.replace(tzinfo=UTC)
    scores.sort(
        key=lambda item: (
            -item.points,
            -item.correct_count,
            item.first_correct_at or late,
            item.user_id,
        )
    )
    return scores


def medal(rank: int) -> str:
    """Gold, silver or bronze prefix for the first three places."""
    return _MEDALS.get(rank, "")
