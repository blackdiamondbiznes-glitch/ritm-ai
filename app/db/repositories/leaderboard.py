"""Leaderboard queries. Ranking rules live in the service."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.leaderboard import (
    STATUS_ANNOUNCED,
    LeaderboardEntry,
    LeaderboardPeriod,
)
from app.db.models.quizzes import Quiz, QuizAnswer
from app.services.scoring import AnswerRow


class LeaderboardRepository:
    """Load answers and persist a frozen weekly board."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def answers_in_window(
        self, chat_id: int, start: datetime, end: datetime
    ) -> list[AnswerRow]:
        """Answers for this chat whose time is in [start, end)."""
        stmt = (
            select(QuizAnswer.user_id, QuizAnswer.is_correct, QuizAnswer.answered_at)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(
                Quiz.chat_id == chat_id,
                QuizAnswer.answered_at >= start,
                QuizAnswer.answered_at < end,
            )
        )
        result = await self._session.execute(stmt)
        return [AnswerRow(row[0], row[1], row[2]) for row in result.all()]

    async def get_period(self, chat_id: int, period_start: date) -> LeaderboardPeriod | None:
        """Return the stored window, if any."""
        stmt = select(LeaderboardPeriod).where(
            LeaderboardPeriod.chat_id == chat_id,
            LeaderboardPeriod.period_start == period_start,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def last_announced(self, chat_id: int) -> LeaderboardPeriod | None:
        """The most recently frozen week for this chat."""
        stmt = (
            select(LeaderboardPeriod)
            .where(
                LeaderboardPeriod.chat_id == chat_id,
                LeaderboardPeriod.status == STATUS_ANNOUNCED,
            )
            .order_by(LeaderboardPeriod.period_start.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def entries(self, period_id: int) -> list[LeaderboardEntry]:
        """Frozen rows, unordered. The service ranks them."""
        stmt = (
            select(LeaderboardEntry)
            .where(LeaderboardEntry.period_id == period_id)
            .order_by(LeaderboardEntry.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def freeze(
        self,
        chat_id: int,
        period_start: date,
        period_end: date,
        announced_at: datetime,
        rows: list[tuple[int, int, int, int]],
    ) -> LeaderboardPeriod:
        """Store the period as announced and write one entry per user."""
        period = LeaderboardPeriod(
            chat_id=chat_id,
            period_start=period_start,
            period_end=period_end,
            status=STATUS_ANNOUNCED,
            announced_at=announced_at,
        )
        self._session.add(period)
        await self._session.flush()
        for user_id, points, correct_count, total_answers in rows:
            self._session.add(
                LeaderboardEntry(
                    period_id=period.id,
                    user_id=user_id,
                    points=points,
                    correct_count=correct_count,
                    total_answers=total_answers,
                )
            )
        await self._session.flush()
        return period

    async def set_message_id(self, period: LeaderboardPeriod, message_id: int) -> None:
        """Remember the Telegram message after a successful send."""
        period.telegram_message_id = message_id
        await self._session.flush()
