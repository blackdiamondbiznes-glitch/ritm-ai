"""Leaderboard service: ranking, freeze/dedup, empty skip, escaped names."""

from datetime import UTC, date, datetime, time
from types import SimpleNamespace

from app.bot.copy import board_announcement
from app.db.models.chats import Chat, ChatType
from app.db.models.jobs import Job, JobStatus
from app.db.models.leaderboard import STATUS_ANNOUNCED, LeaderboardEntry, LeaderboardPeriod
from app.db.models.users import User
from app.jobs.collect import Row, collect_due
from app.jobs.leaderboard import LeaderboardHandler
from app.jobs.runner import JobCancel
from app.services.leaderboard import LeaderboardService
from app.services.scoring import AnswerRow

NOW = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)  # Monday 09:00 in Tashkent


def _user(
    user_id: int, name: str, username: str | None = None, telegram_id: int | None = None
) -> User:
    return User(
        id=user_id,
        telegram_id=telegram_id or (1000 + user_id),
        username=username,
        full_name=name,
        language_code="uz",
        is_blocked=False,
        last_seen_at=NOW,
        created_at=NOW,
    )


def _chat() -> Chat:
    return Chat(
        id=7,
        telegram_chat_id=-1007,
        type=ChatType.SUPERGROUP,
        title="Nmadr",
        owner_id=1,
        is_active=True,
        trial_consumed=True,
        added_at=NOW,
    )


class _Boards:
    def __init__(self, answers: list[AnswerRow]) -> None:
        self.answers = answers
        self.periods: list[LeaderboardPeriod] = []
        self.rows: dict[int, list[LeaderboardEntry]] = {}
        self._seq = 0

    async def answers_in_window(
        self, chat_id: int, start: datetime, end: datetime
    ) -> list[AnswerRow]:
        return [row for row in self.answers if start <= row.answered_at < end]

    async def get_period(self, chat_id: int, period_start: date) -> LeaderboardPeriod | None:
        return next(
            (
                row
                for row in self.periods
                if row.chat_id == chat_id and row.period_start == period_start
            ),
            None,
        )

    async def last_announced(self, chat_id: int) -> LeaderboardPeriod | None:
        found = [
            row for row in self.periods if row.chat_id == chat_id and row.status == STATUS_ANNOUNCED
        ]
        found.sort(key=lambda row: row.period_start, reverse=True)
        return found[0] if found else None

    async def entries(self, period_id: int) -> list[LeaderboardEntry]:
        return list(self.rows.get(period_id, []))

    async def freeze(
        self,
        chat_id: int,
        period_start: date,
        period_end: date,
        announced_at: datetime,
        rows: list[tuple[int, int, int, int]],
    ) -> LeaderboardPeriod:
        self._seq += 1
        period = LeaderboardPeriod(
            id=self._seq,
            chat_id=chat_id,
            period_start=period_start,
            period_end=period_end,
            status=STATUS_ANNOUNCED,
            announced_at=announced_at,
        )
        self.periods.append(period)
        self.rows[period.id] = [
            LeaderboardEntry(
                id=index,
                period_id=period.id,
                user_id=user_id,
                points=points,
                correct_count=correct,
                total_answers=total,
            )
            for index, (user_id, points, correct, total) in enumerate(rows, start=1)
        ]
        return period

    async def set_message_id(self, period: LeaderboardPeriod, message_id: int) -> None:
        period.telegram_message_id = message_id


class _Users:
    def __init__(self, users: list[User]) -> None:
        self.users = users

    async def get_by_id(self, user_id: int) -> User | None:
        return next((user for user in self.users if user.id == user_id), None)

    async def list_by_ids(self, ids: list[int]) -> list[User]:
        return [user for user in self.users if user.id in ids]


def _service(answers: list[AnswerRow], users: list[User]) -> tuple[LeaderboardService, _Boards]:
    boards = _Boards(answers)
    return LeaderboardService(boards, _Users(users), 10, now=lambda: NOW), boards


async def test_names_are_html_escaped_and_mentioned_safely() -> None:
    service, _boards = _service(
        [AnswerRow(2, True, datetime(2026, 11, 10, 10, 0, tzinfo=UTC))],
        [_user(2, "<b>Ada</b>", "ada")],
    )
    status, view, period = await service.prepare(_chat(), "Asia/Tashkent", window="previous")
    assert status == "ready" and view is not None and period is not None
    text = board_announcement(view, "uz")
    assert "<b>Ada</b>" not in text
    assert "&lt;b&gt;Ada&lt;/b&gt;" in text
    assert 'href="tg://user?id=1002"' in text
    assert "10 ball (1/1)" in text
    assert "🥇" in text


async def test_prepare_skips_empty_and_does_not_freeze() -> None:
    service, boards = _service([], [_user(2, "Ada")])
    status, view, period = await service.prepare(_chat(), "Asia/Tashkent", window="previous")
    assert status == "empty" and view is None and period is None
    assert boards.periods == []


async def test_second_announce_is_a_noop_once_the_message_is_saved() -> None:
    service, boards = _service(
        [AnswerRow(2, True, datetime(2026, 11, 10, 10, 0, tzinfo=UTC))],
        [_user(2, "Ada")],
    )
    first = await service.prepare(_chat(), "Asia/Tashkent", window="previous")
    assert first[0] == "ready" and first[2] is not None
    await service.remember(first[2], 88)
    again = await service.prepare(_chat(), "Asia/Tashkent", window="previous")
    assert again[0] == "already"
    assert len(boards.periods) == 1


async def test_live_preview_does_not_freeze_the_current_week() -> None:
    service, boards = _service(
        [AnswerRow(2, True, datetime(2026, 11, 16, 3, 0, tzinfo=UTC))],
        [_user(2, "Ada")],
    )
    status, view, period = await service.prepare(_chat(), "Asia/Tashkent", window="current")
    assert status == "live" and view is not None and period is None
    assert boards.periods == []
    live = await service.live(_chat(), "Asia/Tashkent")
    assert live.members[0].score.points == 10


async def test_collect_due_fires_once_on_the_chosen_weekday() -> None:
    row = Row(1, 7, "Asia/Tashkent", time(9, 0), (1,))
    due = collect_due(NOW, [row], set())
    assert due[0].slot == "2026-11-16"
    assert collect_due(NOW, [row], {(7, "2026-11-16")}) == []
    friday = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    assert collect_due(friday, [row], set()) == []


def _handler(service: LeaderboardService, allowed: bool = True) -> LeaderboardHandler:
    owner = _user(1, "Owner")
    return LeaderboardHandler(
        _Chats(_chat()),
        _Users([_user(2, "Ada"), owner]),
        _Profiles(),
        _Access(allowed),
        service,
        _Sender(),  # type: ignore[arg-type]
        SimpleNamespace(),
        SimpleNamespace(mark_bot_removed=_unused),
    )


async def test_job_posts_previous_week_and_skips_a_replay() -> None:
    answers = [AnswerRow(2, True, datetime(2026, 11, 10, 10, 0, tzinfo=UTC))]
    service, boards = _service(answers, [_user(2, "Ada"), _user(1, "Owner")])
    handler = _handler(service)
    sender = handler._sender  # noqa: SLF001
    await handler.handle(_job("previous"))
    assert len(sender.texts) == 1
    assert "Top-10" in sender.texts[0]
    assert boards.periods[0].telegram_message_id == 501
    await handler.handle(_job("previous"))
    assert len(sender.texts) == 1


async def test_job_skips_empty_week_and_cancels_when_module_is_off() -> None:
    service, _boards = _service([], [_user(1, "Owner")])
    await _handler(service).handle(_job("previous"))
    try:
        await _handler(service, allowed=False).handle(_job("previous"))
    except JobCancel as exc:
        assert exc.code == "module"
    else:
        raise AssertionError("module gate")


def _job(window: str) -> Job:
    return Job(
        id=1,
        chat_id=7,
        type="leaderboard",
        payload={"slot": "2026-11-16", "schedule_id": 1, "window": window},
        run_at=NOW,
        status=JobStatus.PENDING,
        attempts=0,
        max_attempts=5,
    )


class _Chats:
    def __init__(self, chat: Chat) -> None:
        self.chat = chat

    async def get_by_id(self, chat_id: int) -> Chat | None:
        return self.chat if chat_id == self.chat.id else None


class _Profiles:
    async def get(self, chat_id: int) -> SimpleNamespace:
        return SimpleNamespace(timezone="Asia/Tashkent", language="uz")


class _Access:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    async def is_module_allowed(self, chat: Chat, module: str) -> bool:
        return self.allowed


class _Sender:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def post(self, bot: object, chat_id: int, text: str, markup: object = None) -> int:
        self.texts.append(text)
        return 501


async def _unused(*args: object, **kwargs: object) -> None:
    return None
