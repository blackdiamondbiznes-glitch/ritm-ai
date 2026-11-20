"""Build, freeze and post a chat's weekly Top-10."""

from dataclasses import dataclass
from datetime import date, datetime

from app.db.models.chats import Chat
from app.db.models.leaderboard import LeaderboardEntry, LeaderboardPeriod
from app.db.models.users import User
from app.db.repositories.leaderboard import LeaderboardRepository
from app.db.repositories.users import UserRepository
from app.services.clock import Clock, utcnow
from app.services.scoring import Score, Week, current_week, previous_week, score_answers

MODULE = "leaderboard"


@dataclass(frozen=True)
class MemberScore:
    """A ranked score plus the member's display fields."""

    rank: int
    score: Score
    telegram_id: int
    full_name: str | None
    username: str | None


@dataclass(frozen=True)
class BoardView:
    """A week ready to render. `frozen` is True for an announced period."""

    start: date
    end: date
    members: tuple[MemberScore, ...]
    frozen: bool


class LeaderboardService:
    """Points come from stored quiz answers. A freeze is written once per week."""

    def __init__(
        self,
        boards: LeaderboardRepository,
        users: UserRepository,
        points_per_correct: int,
        now: Clock | None = None,
    ) -> None:
        self._boards = boards
        self._users = users
        self._points = points_per_correct
        self._now = now or utcnow

    async def live(self, chat: Chat, timezone: str) -> BoardView:
        """Current week, computed on the fly and not written to the database."""
        week = current_week(self._now(), timezone)
        return await self._view(chat.id, week, frozen=False)

    async def last(self, chat_id: int) -> BoardView | None:
        """The last announced week, read from frozen entries."""
        period = await self._boards.last_announced(chat_id)
        if period is None:
            return None
        rows = await self._boards.entries(period.id)
        scores = [_from_entry(row) for row in rows]
        return await self._ranked(scores, period.period_start, period.period_end, True)

    async def prepare(
        self, chat: Chat, timezone: str, *, window: str
    ) -> tuple[str, BoardView | None, LeaderboardPeriod | None]:
        """Compute the board to post. `already` and `empty` have no view.

        Official jobs use `window='previous'` and freeze the rows. A manual
        `current` post is live and is not stored as announced.
        """
        week = _week(self._now(), timezone, window)
        if window == "previous":
            return await self._prepare_previous(chat.id, week)
        view = await self._view(chat.id, week, frozen=False)
        if not view.members:
            return "empty", None, None
        return "live", view, None

    async def remember(self, period: LeaderboardPeriod, message_id: int) -> None:
        """Save the Telegram message id after the announcement is sent."""
        await self._boards.set_message_id(period, message_id)

    async def _prepare_previous(
        self, chat_id: int, week: Week
    ) -> tuple[str, BoardView | None, LeaderboardPeriod | None]:
        existing = await self._boards.get_period(chat_id, week.start_date)
        if existing is not None and existing.status == "announced":
            if existing.telegram_message_id is not None:
                return "already", None, existing
            view = await self._from_period(existing)
            return "ready", view, existing
        view = await self._view(chat_id, week, frozen=False)
        if not view.members:
            return "empty", None, None
        frozen = [
            (
                item.score.user_id,
                item.score.points,
                item.score.correct_count,
                item.score.total_answers,
            )
            for item in view.members
        ]
        period = await self._boards.freeze(
            chat_id, week.start_date, week.end_date, self._now(), frozen
        )
        return "ready", view, period

    async def _from_period(self, period: LeaderboardPeriod) -> BoardView:
        rows = await self._boards.entries(period.id)
        scores = [_from_entry(row) for row in rows]
        return await self._ranked(scores, period.period_start, period.period_end, True)

    async def _view(self, chat_id: int, week: Week, *, frozen: bool) -> BoardView:
        rows = await self._boards.answers_in_window(chat_id, week.start, week.end)
        scores = score_answers(rows, self._points)
        return await self._ranked(scores, week.start_date, week.end_date, frozen)

    async def _ranked(self, scores: list[Score], start: date, end: date, frozen: bool) -> BoardView:
        found = await self._users.list_by_ids([row.user_id for row in scores])
        users = {user.id: user for user in found}
        members = tuple(
            _member(index, row, users.get(row.user_id)) for index, row in enumerate(scores, start=1)
        )
        return BoardView(start, end, members, frozen)


def _week(now: datetime, timezone: str, window: str) -> Week:
    if window == "current":
        return current_week(now, timezone)
    return previous_week(now, timezone)


def _from_entry(row: LeaderboardEntry) -> Score:
    return Score(row.user_id, row.points, row.correct_count, row.total_answers, None)


def _member(rank: int, score: Score, user: User | None) -> MemberScore:
    telegram_id = user.telegram_id if user is not None else 0
    name = user.full_name if user is not None else None
    username = user.username if user is not None else None
    return MemberScore(rank, score, telegram_id, name, username)
