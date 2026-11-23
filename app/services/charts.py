"""Chart data for the Mini App. Real stored events only, aggregated in Postgres.

Days are bucketed in each chat's own timezone (chat_profiles.timezone, else the
bot default). Every series is gap-filled with generate_series so empty days are
explicit zeros. Telegram gives bots no view counts, so there are none here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chats import ChatProfile
from app.services.clock import Clock, utcnow
from app.services.scoring import resolve_zone

PERIODS = (7, 30, 90)
PLATFORM_ZONE = "Asia/Tashkent"
TOP_LIMIT = 5
# Local days can start up to 14 hours away from UTC; widen the UTC prefilter by that.
_SLACK = timedelta(hours=15)


def pick_days(raw: str | None, default: int = 7) -> int:
    try:
        value = int(raw or default)
    except ValueError:
        return default
    return value if value in PERIODS else default


def pct(part: int, whole: int) -> float | None:
    return round(part * 100 / whole, 1) if whole else None


def change_pct(current: float | None, previous: float | None) -> int | None:
    """Whole-number percent change; None when there is nothing to compare with."""
    if current is None or not previous:
        return None
    return round((current - previous) * 100 / previous)


@dataclass(frozen=True)
class Window:
    """Current [start, end] local dates and the previous window of equal length."""

    start: date
    end: date
    prev_start: date
    prev_end: date

    @classmethod
    def ending(cls, today: date, days: int) -> Window:
        start = today - timedelta(days=days - 1)
        return cls(start, today, start - timedelta(days=days), start - timedelta(days=1))

    def utc_bounds(self) -> tuple[datetime, datetime]:
        """A generous UTC range covering both windows in any timezone."""
        lo = datetime.combine(self.prev_start, datetime.min.time()).replace(tzinfo=UTC) - _SLACK
        hi = (
            datetime.combine(self.end + timedelta(days=1), datetime.min.time()).replace(tzinfo=UTC)
            + _SLACK
        )
        return lo, hi


# Shared CTE: the chats in scope with a validated timezone each.
_SCOPE = """
scope AS (
    SELECT * FROM unnest(CAST(:ids AS integer[]), CAST(:zones AS text[])) AS s(chat_id, tz)
)
"""

_ANSWERS = """
answers AS (
    SELECT a.user_id, a.is_correct, q.chat_id,
           timezone(s.tz, a.answered_at) AS local_at
    FROM quiz_answers a
    JOIN quizzes q ON q.id = a.quiz_id
    JOIN scope s ON s.chat_id = q.chat_id
    WHERE q.chat_id = ANY(CAST(:ids AS integer[]))
      AND a.answered_at >= :lo AND a.answered_at < :hi
)
"""

# Posts and quizzes per local day, gap-filled over both windows.
_DAILY = f"""
WITH {_SCOPE},
days AS (
    SELECT CAST(d AS date) AS day
    FROM generate_series(CAST(:prev_start AS date), CAST(:end AS date), interval '1 day') AS d
),
posts AS (
    SELECT CAST(timezone(s.tz, c.published_at) AS date) AS day, count(*) AS n
    FROM content_items c JOIN scope s ON s.chat_id = c.chat_id
    WHERE c.chat_id = ANY(CAST(:ids AS integer[]))
      AND c.published_at >= :lo AND c.published_at < :hi
    GROUP BY 1
),
quiz AS (
    SELECT CAST(timezone(s.tz, q.created_at) AS date) AS day, count(*) AS n
    FROM quizzes q JOIN scope s ON s.chat_id = q.chat_id
    WHERE q.chat_id = ANY(CAST(:ids AS integer[]))
      AND q.created_at >= :lo AND q.created_at < :hi
    GROUP BY 1
)
SELECT days.day, COALESCE(posts.n, 0), COALESCE(quiz.n, 0)
FROM days
LEFT JOIN posts ON posts.day = days.day
LEFT JOIN quiz ON quiz.day = days.day
ORDER BY days.day
"""

# One pass over the answers, five groupings: per day (both windows), per window,
# and for the current window only per week, per weekday x hour and per chat.
# Current-window-only keys are NULL for previous-window rows; those groups are dropped.
_ANSWER_SETS = f"""
WITH {_SCOPE},
{_ANSWERS},
tagged AS (
    SELECT user_id, is_correct, chat_id, local_at, CAST(local_at AS date) AS day,
           CASE
               WHEN CAST(local_at AS date) BETWEEN :start AND :end THEN 'cur'
               WHEN CAST(local_at AS date) BETWEEN :prev_start AND :prev_end THEN 'prev'
           END AS win
    FROM answers
),
cur AS (
    SELECT *,
           CASE WHEN win = 'cur' THEN CAST(date_trunc('week', day) AS date) END AS week,
           CASE WHEN win = 'cur' THEN CAST(extract(isodow FROM local_at) AS int) END AS dow,
           CASE WHEN win = 'cur' THEN CAST(extract(hour FROM local_at) AS int) END AS hour,
           CASE WHEN win = 'cur' THEN chat_id END AS cur_chat
    FROM tagged WHERE win IS NOT NULL
)
SELECT GROUPING(day) AS g_day, GROUPING(win) AS g_win, GROUPING(week) AS g_week,
       GROUPING(dow, hour) AS g_cell, GROUPING(cur_chat) AS g_chat,
       day, win, week, dow, hour, cur_chat,
       count(*), count(*) FILTER (WHERE is_correct), count(DISTINCT user_id)
FROM cur
GROUP BY GROUPING SETS ((day), (win), (week), (dow, hour), (cur_chat))
"""

_TOP = f"""
WITH {_SCOPE},
{_ANSWERS},
cur AS (
    SELECT user_id, CAST(local_at AS date) AS day, is_correct FROM answers
    WHERE CAST(local_at AS date) BETWEEN :start AND :end
),
leaders AS (
    SELECT user_id, count(*) FILTER (WHERE is_correct) AS correct, count(*) AS total
    FROM cur GROUP BY user_id
    HAVING count(*) FILTER (WHERE is_correct) > 0
    ORDER BY 2 DESC, 3 ASC, user_id
    LIMIT :top
)
SELECT l.user_id, u.full_name, u.username, l.correct, l.total, c.day,
       count(*) FILTER (WHERE c.is_correct)
FROM leaders l
JOIN users u ON u.id = l.user_id
JOIN cur c ON c.user_id = l.user_id
GROUP BY l.user_id, u.full_name, u.username, l.correct, l.total, c.day
ORDER BY l.correct DESC, l.total ASC, l.user_id, c.day
"""

_MEMBER = """
WITH zones AS (
    SELECT * FROM unnest(CAST(:ids AS integer[]), CAST(:zones AS text[])) AS s(chat_id, tz)
),
mine AS (
    SELECT a.is_correct,
           CAST(date_trunc('week', timezone(COALESCE(z.tz, :tz), a.answered_at)) AS date) AS week
    FROM quiz_answers a
    JOIN quizzes q ON q.id = a.quiz_id
    LEFT JOIN zones z ON z.chat_id = q.chat_id
    WHERE a.user_id = :uid AND a.answered_at >= :lo
),
weeks AS (
    SELECT CAST(w AS date) AS week
    FROM generate_series(CAST(:first AS date), CAST(:last AS date), interval '1 week') AS w
),
agg AS (
    SELECT week, count(*) AS n, count(*) FILTER (WHERE is_correct) AS correct
    FROM mine GROUP BY week
)
SELECT weeks.week, COALESCE(agg.n, 0), COALESCE(agg.correct, 0)
FROM weeks LEFT JOIN agg ON agg.week = weeks.week
ORDER BY weeks.week
"""


class ChartService:
    """Read-only aggregations for chat owners, admins, members and super admins."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        default_timezone: str = PLATFORM_ZONE,
        points_per_correct: int = 10,
        now: Clock | None = None,
    ) -> None:
        self._s = session
        self._default = resolve_zone(default_timezone).key
        self._points = int(points_per_correct)
        self._now = now or utcnow

    async def zones(self, chat_ids: list[int]) -> dict[int, str]:
        """Validated IANA zone per chat (unknown names fall back to the default)."""
        rows = (
            await self._s.execute(
                select(ChatProfile.chat_id, ChatProfile.timezone).where(
                    ChatProfile.chat_id.in_(chat_ids)
                )
            )
        ).all()
        saved = {int(cid): tz for cid, tz in rows}
        return {cid: resolve_zone(saved.get(cid) or self._default).key for cid in chat_ids}

    def today(self, zone: str) -> date:
        return self._now().astimezone(resolve_zone(zone)).date()

    async def chats(self, chats: list[tuple[int, str]], days: int, *, scope: str) -> dict[str, Any]:
        """Charts for one chat or all managed chats. `chats` is (id, title) already authorized."""
        ids = [cid for cid, _title in chats]
        zones = await self.zones(ids)
        zone = zones[ids[0]] if ids else self._default
        window = Window.ending(self.today(zone), days)
        payload: dict[str, Any] = {
            "scope": scope,
            "days": days,
            "timezone": zone,
            "zones": sorted(set(zones.values())),
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
        }
        if not ids:
            payload.update(_empty(window))
            return payload
        lo, hi = window.utc_bounds()
        params = {
            "ids": ids,
            "zones": [zones[cid] for cid in ids],
            "lo": lo,
            "hi": hi,
            "start": window.start,
            "end": window.end,
            "prev_start": window.prev_start,
            "prev_end": window.prev_end,
        }
        run = self._s.execute
        by_day: dict[date, tuple[int, int, int]] = {}
        windows: dict[str, tuple[int, int, int]] = {}
        by_week: dict[date, tuple[int, int, int]] = {}
        grid = [[0] * 24 for _ in range(7)]
        by_chat: dict[int, tuple[int, int, int]] = {}
        for row in (await run(text(_ANSWER_SETS), params)).all():
            g_day, g_win, g_week, g_cell, g_chat, day, win, week, dow, hour, chat = row[:11]
            counts = (int(row[11]), int(row[12]), int(row[13]))
            if not g_day:
                by_day[day] = counts
            elif not g_win:
                windows[win] = counts
            elif not g_week and week is not None:
                by_week[week] = counts
            elif not g_cell and dow is not None:
                grid[int(dow) - 1][int(hour)] = counts[0]
            elif not g_chat and chat is not None:
                by_chat[int(chat)] = counts
        series, previous = [], []
        for day, posts, quizzes in (await run(text(_DAILY), params)).all():
            answers, correct, people = by_day.get(day, (0, 0, 0))
            item = {
                "date": day.isoformat(),
                "posts": int(posts),
                "quizzes": int(quizzes),
                "answers": answers,
                "correct": correct,
                "participants": people,
                "accuracy": pct(correct, answers),
            }
            (series if day >= window.start else previous).append(item)
        payload["series"] = series
        payload["totals"] = _totals(series, previous, windows)
        payload["weekly"] = []
        week = window.start - timedelta(days=window.start.weekday())
        while week <= window.end:
            n, c, p = by_week.get(week, (0, 0, 0))
            payload["weekly"].append(
                {
                    "week": week.isoformat(),
                    "answers": n,
                    "correct": c,
                    "participants": p,
                    "accuracy": pct(c, n),
                }
            )
            week += timedelta(days=7)
        payload["heatmap"] = {"cells": grid, "max": max(max(row) for row in grid)}
        compare = []
        if scope == "all" and len(ids) > 1:
            titles = dict(chats)
            for cid in ids:
                n, c, p = by_chat.get(cid, (0, 0, 0))
                compare.append(
                    {
                        "id": cid,
                        "title": titles.get(cid, ""),
                        "answers": n,
                        "participants": p,
                        "accuracy": pct(c, n),
                    }
                )
            compare.sort(key=lambda row: (-row["answers"], -row["participants"], row["id"]))
        payload["compare"] = compare
        payload["top"] = self._top(
            (await run(text(_TOP), {**params, "top": TOP_LIMIT})).all(), window
        )
        return payload

    def _top(self, rows, window: Window) -> list[dict[str, Any]]:
        """Top participants with cumulative points per day (gap-filled)."""
        days = [
            window.start + timedelta(days=i) for i in range((window.end - window.start).days + 1)
        ]
        people: dict[int, dict[str, Any]] = {}
        daily: dict[int, dict[date, int]] = {}
        for user_id, name, username, correct, total, day, day_correct in rows:
            uid = int(user_id)
            if uid not in people:
                people[uid] = {
                    "user_id": uid,
                    "name": name or (f"@{username}" if username else f"#{uid}"),
                    "points": int(correct) * self._points,
                    "correct": int(correct),
                    "answers": int(total),
                    "accuracy": pct(int(correct), int(total)),
                }
                daily[uid] = {}
            daily[uid][day] = int(day_correct)
        out = []
        for uid, person in people.items():
            running, series = 0, []
            for day in days:
                running += daily[uid].get(day, 0) * self._points
                series.append(running)
            out.append({**person, "series": series})
        return out

    async def member(self, user_id: int, chat_ids: list[int], weeks: int = 12) -> dict[str, Any]:
        """The caller's own points and accuracy per week (Monday weeks, chat timezones)."""
        weeks = max(4, min(int(weeks), 26))
        zones = await self.zones(chat_ids)
        zone = zones[chat_ids[0]] if chat_ids else self._default
        today = self.today(zone)
        last = today - timedelta(days=today.weekday())
        first = last - timedelta(weeks=weeks - 1)
        lo = datetime.combine(first, datetime.min.time()).replace(tzinfo=UTC) - _SLACK
        rows = (
            await self._s.execute(
                text(_MEMBER),
                {
                    "ids": chat_ids,
                    "zones": [zones[cid] for cid in chat_ids],
                    "tz": zone,
                    "uid": user_id,
                    "lo": lo,
                    "first": first,
                    "last": last,
                },
            )
        ).all()
        series = [
            {
                "week": week.isoformat(),
                "answers": int(n),
                "correct": int(c),
                "points": int(c) * self._points,
                "accuracy": pct(int(c), int(n)),
            }
            for week, n, c in rows
        ]
        answers = sum(row["answers"] for row in series)
        correct = sum(row["correct"] for row in series)
        return {
            "weeks": weeks,
            "timezone": zone,
            "series": series,
            "totals": {
                "answers": answers,
                "correct": correct,
                "points": correct * self._points,
                "accuracy": pct(correct, answers),
            },
        }


_PLATFORM_MONTHS = """
WITH months AS (
    SELECT CAST(m AS date) AS month,
           timezone(:tz, m) AS m_lo,
           timezone(:tz, m + interval '1 month') AS m_hi
    FROM generate_series(CAST(:first AS timestamp), CAST(:last AS timestamp), interval '1 month')
        AS m
),
revenue AS (
    SELECT CAST(date_trunc('month', timezone(:tz, reviewed_at)) AS date) AS month,
           sum(amount_uzs) AS uzs, count(*) AS n
    FROM payments
    WHERE status = 'approved' AND reviewed_at IS NOT NULL
    GROUP BY 1
),
started AS (
    SELECT CAST(date_trunc('month', timezone(:tz, started_at)) AS date) AS month,
           count(*) FILTER (WHERE source = 'trial') AS trials,
           count(*) FILTER (WHERE source = 'manual_payment') AS paid,
           count(*) FILTER (WHERE source = 'admin_grant') AS grants
    FROM subscriptions
    GROUP BY 1
),
churn AS (
    SELECT CAST(date_trunc('month', timezone(:tz, s.expires_at)) AS date) AS month,
           count(*) FILTER (WHERE s.source = 'trial') AS trial_lost,
           count(*) FILTER (WHERE s.source <> 'trial') AS paid_lost
    FROM subscriptions s
    WHERE s.expires_at <= now() AND s.status <> 'canceled'
      AND NOT EXISTS (
          SELECT 1 FROM subscriptions later
          WHERE later.owner_id = s.owner_id AND later.id <> s.id
            AND later.expires_at > s.expires_at
      )
    GROUP BY 1
),
founders AS (
    SELECT months.month, count(u.id) AS total
    FROM months
    LEFT JOIN users u ON u.is_founder AND u.founder_since < months.m_hi
    GROUP BY months.month
),
ai AS (
    SELECT period_key, sum(count) AS n FROM usage_counters
    WHERE metric = 'ai_generation' GROUP BY period_key
)
SELECT months.month,
       COALESCE(revenue.uzs, 0), COALESCE(revenue.n, 0),
       COALESCE(started.trials, 0), COALESCE(started.paid, 0), COALESCE(started.grants, 0),
       COALESCE(churn.trial_lost, 0), COALESCE(churn.paid_lost, 0),
       founders.total, COALESCE(ai.n, 0)
FROM months
LEFT JOIN revenue ON revenue.month = months.month
LEFT JOIN started ON started.month = months.month
LEFT JOIN churn ON churn.month = months.month
LEFT JOIN founders ON founders.month = months.month
LEFT JOIN ai ON ai.period_key = to_char(months.month, 'YYYY-MM')
ORDER BY months.month
"""

# Active subscriptions by plan at the end of each month (or now, for the current month).
_PLATFORM_ACTIVE = """
WITH months AS (
    SELECT CAST(m AS date) AS month,
           LEAST(timezone(:tz, m + interval '1 month'), now()) AS at
    FROM generate_series(CAST(:first AS timestamp), CAST(:last AS timestamp), interval '1 month')
        AS m
)
SELECT months.month, CASE WHEN s.source = 'trial' THEN 'trial' ELSE p.code END, count(*)
FROM months
JOIN subscriptions s ON s.started_at <= months.at AND s.expires_at > months.at
    AND s.status <> 'canceled'
JOIN plans p ON p.id = s.plan_id
GROUP BY 1, 2
ORDER BY 1
"""

_PLATFORM_DAYS = """
WITH days AS (
    SELECT CAST(d AS date) AS day
    FROM generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 day') AS d
),
ai AS (
    SELECT day, sum(count) AS n FROM usage_daily
    WHERE metric = 'ai_generation' AND day BETWEEN :start AND :end
    GROUP BY day
),
jobs_done AS (
    SELECT CAST(timezone(:tz, COALESCE(finished_at, locked_at, run_at)) AS date) AS day,
           count(*) FILTER (WHERE status = 'failed') AS failed,
           count(*) FILTER (WHERE status = 'done') AS done
    FROM jobs
    WHERE status IN ('failed', 'done')
      AND COALESCE(finished_at, locked_at, run_at) >= :lo
    GROUP BY 1
)
SELECT days.day, COALESCE(ai.n, 0), COALESCE(jobs_done.failed, 0), COALESCE(jobs_done.done, 0)
FROM days
LEFT JOIN ai ON ai.day = days.day
LEFT JOIN jobs_done ON jobs_done.day = days.day
ORDER BY days.day
"""


async def platform_charts(
    session: AsyncSession,
    *,
    days: int,
    founder_slots: int,
    months: int = 12,
    now: Clock | None = None,
) -> dict[str, Any]:
    """Super-admin charts in Tashkent time: money, subscriptions, founders, AI, jobs."""
    moment = (now or utcnow)().astimezone(resolve_zone(PLATFORM_ZONE))
    this_month = moment.date().replace(day=1)
    first = this_month
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    window = Window.ending(moment.date(), days)
    params = {
        "tz": PLATFORM_ZONE,
        "first": datetime.combine(first, datetime.min.time()),
        "last": datetime.combine(this_month, datetime.min.time()),
    }
    rows = (await session.execute(text(_PLATFORM_MONTHS), params)).all()
    active: dict[date, dict[str, int]] = {}
    for month, code, n in (await session.execute(text(_PLATFORM_ACTIVE), params)).all():
        active.setdefault(month, {})[code] = int(n)
    plan_rows = (
        await session.execute(text("SELECT code, name FROM plans ORDER BY sort_order, id"))
    ).all()
    lo, _hi = window.utc_bounds()
    daily = (
        await session.execute(
            text(_PLATFORM_DAYS),
            {"tz": PLATFORM_ZONE, "start": window.start, "end": window.end, "lo": lo},
        )
    ).all()
    since = await session.scalar(text("SELECT min(day) FROM usage_daily"))
    series = []
    for month, uzs, paid_n, trials, paid, grants, trial_lost, paid_lost, founders, ai in rows:
        series.append(
            {
                "month": month.strftime("%Y-%m"),
                "revenue_uzs": int(uzs),
                "payments": int(paid_n),
                "new_trials": int(trials),
                "new_paid": int(paid),
                "new_grants": int(grants),
                "churn_trial": int(trial_lost),
                "churn_paid": int(paid_lost),
                "founders": int(founders or 0),
                "ai": int(ai),
                "active": active.get(month, {}),
            }
        )
    used = series[-1]["founders"] if series else 0
    return {
        "timezone": PLATFORM_ZONE,
        "days": days,
        "months": series,
        "plans": [{"code": code, "name": name} for code, name in plan_rows]
        + [{"code": "trial", "name": "Trial"}],
        "founder": {
            "slots": int(founder_slots),
            "used": used,
            "left": max(0, founder_slots - used),
        },
        "daily": [
            {"date": day.isoformat(), "ai": int(ai), "jobs_failed": int(f), "jobs_done": int(d)}
            for day, ai, f, d in daily
        ],
        # usage_daily is written since migration 0011; older AI usage exists only per month.
        "ai_daily_since": since.isoformat() if since else None,
    }


def _totals(current: list[dict], previous: list[dict], windows: dict[str, tuple]) -> dict:
    def window(rows: list[dict], key: str) -> dict[str, Any]:
        answers, correct, people = windows.get(key, (0, 0, 0))
        return {
            "posts": sum(r["posts"] for r in rows),
            "quizzes": sum(r["quizzes"] for r in rows),
            "answers": int(answers),
            "correct": int(correct),
            "participants": int(people),
            "accuracy": pct(int(correct), int(answers)),
        }

    cur, prev = window(current, "cur"), window(previous, "prev")
    change = {name: change_pct(cur[name], prev[name]) for name in cur if name != "correct"}
    if cur["accuracy"] is not None and prev["accuracy"] is not None:
        change["accuracy"] = round(cur["accuracy"] - prev["accuracy"], 1)  # percentage points
    else:
        change["accuracy"] = None
    return {"current": cur, "previous": prev, "change": change}


def _empty(window: Window) -> dict[str, Any]:
    days = (window.end - window.start).days + 1
    series = [
        {
            "date": (window.start + timedelta(days=i)).isoformat(),
            "posts": 0,
            "quizzes": 0,
            "answers": 0,
            "correct": 0,
            "participants": 0,
            "accuracy": None,
        }
        for i in range(days)
    ]
    zero = {
        "posts": 0,
        "quizzes": 0,
        "answers": 0,
        "correct": 0,
        "participants": 0,
        "accuracy": None,
    }
    return {
        "series": series,
        "totals": {
            "current": zero,
            "previous": dict(zero),
            "change": {k: None for k in zero if k != "correct"},
        },
        "weekly": [],
        "heatmap": {"cells": [[0] * 24 for _ in range(7)], "max": 0},
        "compare": [],
        "top": [],
    }
