"""Mini App v2: daily spark data, per-chat totals, leaderboard ownership, quota and avatar."""

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.db.models.chats import Chat, ChatType
from app.db.models.content import ContentItem, ContentKind
from app.db.models.quizzes import Quiz, QuizAnswer
from app.db.models.users import User
from app.db.repositories.engagement import EngagementRepository
from app.services.activity import ActivityService
from app.webapp.panel import OwnerPanel, PanelError
from app.webapp.routes import _plan_payload, photo_url
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.fakes import FakeChats, World, make_chat, make_user

ZONE = "Asia/Tashkent"
NOW = datetime(2026, 11, 20, 15, 0, tzinfo=ZoneInfo(ZONE))


class _DailyFake:
    def __init__(self, rows: dict[date, dict[str, int]]) -> None:
        self.rows = rows
        self.calls: list[tuple] = []

    async def daily_counts(self, chat_ids, started, until, timezone):
        self.calls.append((list(chat_ids), started, until, timezone))
        return self.rows


async def test_daily_fills_seven_local_days_oldest_first() -> None:
    fake = _DailyFake(
        {date(2026, 11, 20): {"posts": 2, "answers": 5}, date(2026, 11, 14): {"quizzes": 1}}
    )
    rows = await ActivityService(fake, now=lambda: NOW).daily([1, 2], ZONE)
    assert [row["date"] for row in rows] == [f"2026-11-{d}" for d in range(14, 21)]
    assert rows[0] == {"date": "2026-11-14", "posts": 0, "quizzes": 1, "answers": 0}
    assert rows[-1] == {"date": "2026-11-20", "posts": 2, "quizzes": 0, "answers": 5}
    assert sum(row["posts"] for row in rows[1:-1]) == 0
    _ids, started, until, zone = fake.calls[0]
    assert started == datetime(2026, 11, 14, tzinfo=ZoneInfo(ZONE))
    assert until == datetime(2026, 11, 21, tzinfo=ZoneInfo(ZONE))
    assert zone == ZONE


async def test_daily_is_empty_without_grouped_source() -> None:
    class _Plain:
        pass

    assert await ActivityService(_Plain(), now=lambda: NOW).daily([1], ZONE) == []


@dataclass
class _Snapshot:
    start: date
    end: date
    frozen: bool
    members: tuple


@dataclass
class _Score:
    points: int


@dataclass
class _Row:
    rank: int
    score: _Score
    telegram_id: int
    full_name: str | None
    username: str | None


class _Profiles:
    async def get(self, _chat_id):
        return None


class _Board:
    def __init__(self) -> None:
        self.seen: list[int] = []

    async def live(self, chat, _zone):
        self.seen.append(chat.id)
        rows = tuple(
            _Row(
                i,
                _Score(100 - i),
                1000 + i,
                f"U{i}" if i != 2 else None,
                "nick" if i == 2 else None,
            )
            for i in range(1, 13)
        )
        return _Snapshot(date(2026, 11, 16), date(2026, 11, 22), False, rows)


def _panel(chats: FakeChats, board: _Board, *, is_super: bool = False) -> OwnerPanel:
    return OwnerPanel(
        chats=chats,
        access=None,
        profiles=_Profiles(),
        schedules=None,
        quiz_launch=None,
        leaderboard=board,
        is_super=is_super,
    )


async def test_leaderboard_endpoint_enforces_ownership_and_caps_top10() -> None:
    owner = make_user(1, 100)
    other = make_user(2, 200)
    chats = FakeChats()
    chat = await chats.add(make_chat(owner))
    board = _Board()
    with pytest.raises(PanelError) as exc:
        await _panel(chats, board).board(other, chat.id)
    assert exc.value.status == 403 and exc.value.code == "not_owner"
    with pytest.raises(PanelError) as missing:
        await _panel(chats, board).board(owner, 999)
    assert missing.value.status == 404
    assert board.seen == []
    data = await _panel(chats, board).board(owner, chat.id)
    members = data["board"]["members"]
    assert len(members) == 10
    assert members[0] == {"rank": 1, "points": 99, "name": "U1"}
    assert members[1]["name"] == "nick"
    assert data["chat"]["id"] == chat.id
    assert data["board"]["start"] == "2026-11-16"
    admin = await _panel(chats, board, is_super=True).board(other, chat.id)
    assert admin["chat"]["id"] == chat.id


async def test_plan_payload_reports_remaining_ai_quota() -> None:
    world = World()
    owner = world.add_user(make_user(1, 100))

    class _Payments:
        async def draft_of(self, _owner):
            return None

        async def pending_of(self, _owner_id):
            return None

    data = await _plan_payload(world.access, _Payments(), owner)
    assert data["ai_left"] == max(0, data["ai_limit"] - data["ai_used"])
    assert data["ai_left"] >= 0


def test_photo_url_accepts_only_plain_https() -> None:
    assert (
        photo_url({"photo_url": "https://t.me/i/userpic/320/abc.svg"})
        == "https://t.me/i/userpic/320/abc.svg"
    )
    assert photo_url({"photo_url": "http://t.me/x.jpg"}) is None
    assert photo_url({"photo_url": "javascript:alert(1)"}) is None
    assert photo_url({"photo_url": 'https://x/"><script>'}) is None
    assert photo_url({}) is None
    assert photo_url({"photo_url": 5}) is None


_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/engagement")
_TG_USERS = (9200000001, 9200000002)
_TG_CHATS = (-9200000001, -9200000002)


async def _cleanup(session) -> None:
    chat_ids = select(Chat.id).where(Chat.telegram_chat_id.in_(_TG_CHATS))
    quiz_ids = select(Quiz.id).where(Quiz.chat_id.in_(chat_ids))
    await session.execute(delete(QuizAnswer).where(QuizAnswer.quiz_id.in_(quiz_ids)))
    await session.execute(delete(Quiz).where(Quiz.chat_id.in_(chat_ids)))
    await session.execute(delete(ContentItem).where(ContentItem.chat_id.in_(chat_ids)))
    await session.execute(delete(Chat).where(Chat.telegram_chat_id.in_(_TG_CHATS)))
    await session.execute(delete(User).where(User.telegram_id.in_(_TG_USERS)))


@pytest.mark.skipif(not _URL.startswith("postgresql"), reason="Postgres is required")
async def test_repository_groups_by_local_day_and_totals_per_chat() -> None:
    engine = create_async_engine(_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await _cleanup(session)
        await session.commit()
    try:
        async with sessions() as session:
            owner = User(telegram_id=_TG_USERS[0], language_code="uz")
            member = User(telegram_id=_TG_USERS[1], language_code="uz")
            session.add_all([owner, member])
            await session.flush()
            added = datetime(2026, 11, 1, tzinfo=UTC)
            mine = Chat(
                telegram_chat_id=_TG_CHATS[0],
                type=ChatType.CHANNEL,
                title="A",
                owner_id=owner.id,
                added_at=added,
            )
            two = Chat(
                telegram_chat_id=_TG_CHATS[1],
                type=ChatType.CHANNEL,
                title="B",
                owner_id=owner.id,
                added_at=added,
            )
            session.add_all([mine, two])
            await session.flush()
            # 2026-11-19 20:30 UTC is already 2026-11-20 01:30 in Tashkent.
            late = datetime(2026, 11, 19, 20, 30, tzinfo=UTC)
            early = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
            old = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
            session.add_all(
                [
                    ContentItem(
                        chat_id=mine.id,
                        kind=ContentKind.DAILY,
                        body="a",
                        meta={},
                        published_at=late,
                    ),
                    ContentItem(
                        chat_id=mine.id,
                        kind=ContentKind.DAILY,
                        body="b",
                        meta={},
                        published_at=early,
                    ),
                    ContentItem(
                        chat_id=mine.id, kind=ContentKind.DAILY, body="c", meta={}, published_at=old
                    ),
                    ContentItem(chat_id=mine.id, kind=ContentKind.DAILY, body="draft", meta={}),
                    ContentItem(
                        chat_id=two.id,
                        kind=ContentKind.DAILY,
                        body="d",
                        meta={},
                        published_at=early,
                    ),
                ]
            )
            quiz = Quiz(
                chat_id=mine.id,
                question="q",
                options=["a", "b"],
                correct_index=0,
                mode="group_native",
                created_at=late,
            )
            old_quiz = Quiz(
                chat_id=two.id,
                question="q",
                options=["a", "b"],
                correct_index=0,
                mode="group_native",
                created_at=old,
            )
            session.add_all([quiz, old_quiz])
            await session.flush()
            session.add_all(
                [
                    QuizAnswer(
                        quiz_id=quiz.id,
                        user_id=member.id,
                        chosen_index=0,
                        is_correct=True,
                        answered_at=late,
                    ),
                    QuizAnswer(
                        quiz_id=quiz.id,
                        user_id=owner.id,
                        chosen_index=1,
                        is_correct=False,
                        answered_at=late + timedelta(hours=1),
                    ),
                ]
            )
            await session.commit()
            ids = (mine.id, two.id)

        async with sessions() as session:
            repo = EngagementRepository(session)
            zone = ZoneInfo(ZONE)
            started = datetime(2026, 11, 14, tzinfo=zone)
            until = datetime(2026, 11, 21, tzinfo=zone)
            daily = await repo.daily_counts([ids[0]], started, until, ZONE)
            assert daily == {
                date(2026, 11, 19): {"posts": 1},
                date(2026, 11, 20): {"posts": 1, "quizzes": 1, "answers": 2},
            }
            both = await repo.daily_counts(list(ids), started, until, ZONE)
            assert both[date(2026, 11, 19)] == {"posts": 2}
            assert await repo.daily_counts([], started, until, ZONE) == {}
            totals = await repo.totals_by_chat(list(ids))
            assert totals[ids[0]] == {"posts": 3, "quizzes": 1}
            assert totals[ids[1]] == {"posts": 1, "quizzes": 1}
            assert await repo.totals_by_chat([]) == {}
            windows = [(started, until), (datetime(2026, 11, 20, tzinfo=zone), until)]
            grouped = await repo.window_counts(list(ids), windows)
            for index, (low, high) in enumerate(windows):
                expected = {"posts": 0, "quizzes": 0, "answers": 0, "participants": 0}
                for chat_id in ids:
                    expected["posts"] += await repo.posts_since(chat_id, low, high)
                    expected["quizzes"] += await repo.quizzes_since(chat_id, low, high)
                    expected["answers"] += await repo.answers_since(chat_id, low, high)
                    expected["participants"] += await repo.participants_since(chat_id, low, high)
                assert grouped[index] == expected
            assert grouped[0] == {"posts": 3, "quizzes": 1, "answers": 2, "participants": 2}
            assert (
                await repo.window_counts([], windows)
                == [{"posts": 0, "quizzes": 0, "answers": 0, "participants": 0}] * 2
            )
            service = ActivityService(repo, now=lambda: datetime(2026, 11, 20, 15, 0, tzinfo=zone))
            rows = await service.daily([ids[0]], ZONE)
            assert rows[-1] == {"date": "2026-11-20", "posts": 1, "quizzes": 1, "answers": 2}
            assert rows[-2]["posts"] == 1
    finally:
        async with sessions() as session:
            await _cleanup(session)
            await session.commit()
        await engine.dispose()


class _Schedules:
    """Mirrors ScheduleService: a new time or weekday switches the schedule on."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def set_time(self, chat, code, module):
        self.rows.setdefault(module, {})
        self.rows[module].update(time=code, enabled=True)

    async def set_enabled(self, chat, enabled, module):
        self.rows.setdefault(module, {})["enabled"] = enabled

    async def set_weekday(self, chat, day, module):
        self.rows.setdefault(module, {})
        self.rows[module].update(days=[day], enabled=True)


class _AllAccess:
    async def is_module_allowed(self, _chat, _module):
        return True


async def test_saving_with_schedules_off_keeps_them_off() -> None:
    owner = make_user(1, 100)
    chats = FakeChats()
    chat = await chats.add(make_chat(owner))
    schedules = _Schedules()
    panel = OwnerPanel(
        chats=chats,
        access=_AllAccess(),
        profiles=_Profiles(),
        schedules=schedules,
        quiz_launch=None,
        leaderboard=_Board(),
        is_super=False,
    )

    async def _detail(_chat, _role):
        return {}

    panel._detail = _detail
    body = {
        "daily_time": "09:00",
        "daily_enabled": False,
        "quiz_time": "12:00",
        "quiz_enabled": False,
        "board_time": "21:00",
        "board_enabled": False,
        "board_weekday": 5,
    }
    await panel.update(owner, chat.id, body)
    assert schedules.rows["daily_content"]["enabled"] is False
    assert schedules.rows["quiz"]["enabled"] is False
    assert schedules.rows["leaderboard"] == {"time": "2100", "enabled": False, "days": [5]}
    with pytest.raises(PanelError):
        await panel.update(owner, chat.id, {"board_weekday": "x"})
    with pytest.raises(PanelError):
        await panel.update(owner, chat.id, {"board_weekday": 9})
    await panel.update(owner, chat.id, {"admin_post_quiz": False})
    with pytest.raises(PanelError) as need:
        await panel.update(owner, chat.id, {"admin_post_quiz": True})
    assert need.value.code == "profile"
