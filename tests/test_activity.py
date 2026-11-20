"""Mini App activity totals and member-count cache. No invented metrics."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.activity import ActivityService, change_percent, pack_metric
from app.webapp.dash_routes import build_chat_report
from app.webapp.members import MemberCountCache
from app.webapp.panel import PanelError
from tests.fakes import make_user

ZONE = "Asia/Tashkent"
NOW = datetime(2026, 11, 20, 15, 0, tzinfo=ZoneInfo(ZONE))
WEEK = datetime(2026, 11, 17, 10, 0, tzinfo=ZoneInfo(ZONE))
LAST = datetime(2026, 11, 10, 10, 0, tzinfo=ZoneInfo(ZONE))
TODAY = datetime(2026, 11, 20, 8, 0, tzinfo=ZoneInfo(ZONE))


class FakeEngagement:
    """In-memory timestamps, one list per metric name."""

    def __init__(self, events: dict[str, list[tuple[int, datetime]]]) -> None:
        self.events = events

    def _count(self, name: str, chat_id: int, started: datetime, until: datetime | None) -> int:
        rows = [
            when for cid, when in self.events.get(name, []) if cid == chat_id and when >= started
        ]
        if until is not None:
            rows = [when for when in rows if when < until]
        return len(rows)

    async def posts_since(self, chat_id: int, started: datetime, until=None) -> int:
        return self._count("posts", chat_id, started, until)

    async def quizzes_since(self, chat_id: int, started: datetime, until=None) -> int:
        return self._count("quizzes", chat_id, started, until)

    async def answers_since(self, chat_id: int, started: datetime, until=None) -> int:
        return self._count("answers", chat_id, started, until)

    async def participants_since(self, chat_id: int, started: datetime, until=None) -> int:
        return self._count("participants", chat_id, started, until)


def test_change_percent_omits_undefined_cases() -> None:
    assert change_percent(10, 5) == 100
    assert change_percent(5, 10) == -50
    assert change_percent(3, 0) is None
    assert change_percent(0, 0) is None
    assert "change_pct" not in pack_metric(4, 0)
    assert pack_metric(6, 3)["change_pct"] == 100


async def test_overview_aggregates_windows_and_hides_undefined_change() -> None:
    events = {
        "posts": [(1, LAST), (1, WEEK), (1, TODAY), (2, WEEK)],
        "quizzes": [(1, TODAY)],
        "answers": [(1, LAST), (1, LAST), (1, WEEK), (1, TODAY)],
        "participants": [(1, WEEK)],
    }
    service = ActivityService(FakeEngagement(events), now=lambda: NOW)
    data = await service.overview([1, 2], ZONE)
    week = data["week_counts"]
    today = data["today_counts"]
    assert week["posts"]["value"] == 3
    assert week["posts"]["change_pct"] == 200
    assert week["quizzes"]["value"] == 1
    assert "change_pct" not in week["quizzes"]
    assert week["answers"]["value"] == 2
    assert week["answers"]["change_pct"] == 0
    assert week["participants"]["value"] == 1
    assert today["posts"]["value"] == 1
    assert "change_pct" not in today["posts"]
    assert data["timezone"] == ZONE


async def test_member_count_is_cached_and_omitted_on_failure() -> None:
    calls = {"n": 0}

    async def fetch(chat_id: int) -> int:
        calls["n"] += 1
        if chat_id == 2:
            raise OSError("telegram down")
        return 42

    clock = {"t": 0.0}
    cache = MemberCountCache(ttl=600, clock=lambda: clock["t"], fetch=fetch)
    assert await cache.count(1) == 42
    assert await cache.count(1) == 42
    assert calls["n"] == 1
    clock["t"] = 601
    assert await cache.count(1) == 42
    assert calls["n"] == 2
    assert await cache.count(2) is None
    assert await MemberCountCache().count(1) is None


class _DenyPanel:
    async def detail(self, _user, _chat_id: int) -> dict:
        raise PanelError(403, "not_owner")


class _AllowPanel:
    async def detail(self, _user, chat_id: int) -> dict:
        return {
            "chat": {"id": chat_id, "title": "NmaDR", "telegram_chat_id": -100},
            "profile": {"timezone": ZONE},
            "board": {"members": []},
        }


class _Activity:
    async def overview(self, chat_ids: list[int], timezone: str) -> dict:
        return {
            "timezone": timezone,
            "week_counts": {"posts": {"value": len(chat_ids)}},
            "today_counts": {},
        }


async def test_chat_report_requires_owner_and_omits_failed_member_count() -> None:
    user = make_user()
    try:
        await build_chat_report(user, _DenyPanel(), _Activity(), ZONE, None, 1)
    except PanelError as exc:
        assert exc.status == 403
        assert exc.code == "not_owner"
    else:
        raise AssertionError("not_owner")

    async def boom(_chat_id: int) -> int:
        raise OSError("nope")

    payload = await build_chat_report(
        user,
        _AllowPanel(),
        _Activity(),
        ZONE,
        MemberCountCache(fetch=boom),
        7,
    )
    assert payload["chat"]["id"] == 7
    assert "member_count" not in payload["chat"]
    assert payload["stats"]["week_counts"]["posts"]["value"] == 1

    async def ok(_chat_id: int) -> int:
        return 412

    filled = await build_chat_report(
        user,
        _AllowPanel(),
        _Activity(),
        ZONE,
        MemberCountCache(fetch=ok),
        7,
    )
    assert filled["chat"]["member_count"] == 412
