"""Quiz and answer queries. No grading rules here."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quizzes import Quiz, QuizAnswer


class QuizRepository:
    """Insert and load quizzes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, quiz: Quiz) -> Quiz:
        """Insert a quiz and flush so the deep link can use its id."""
        self._session.add(quiz)
        await self._session.flush()
        return quiz

    async def get(self, quiz_id: int) -> Quiz | None:
        """Return one quiz."""
        result = await self._session.execute(select(Quiz).where(Quiz.id == quiz_id))
        return result.scalar_one_or_none()

    async def get_by_poll(self, poll_id: str) -> Quiz | None:
        """Return the quiz posted as this Telegram poll."""
        stmt = select(Quiz).where(Quiz.telegram_poll_id == poll_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def recent_questions(self, chat_id: int, limit: int = 15) -> list[str]:
        """Newest quiz questions for this chat, used to avoid repeats."""
        stmt = (
            select(Quiz.question)
            .where(Quiz.chat_id == chat_id)
            .order_by(Quiz.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all() if row[0]]


class QuizAnswerRepository:
    """One row per user per quiz."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, quiz_id: int, user_id: int) -> QuizAnswer | None:
        """Return the stored answer, if this user already played."""
        stmt = select(QuizAnswer).where(
            QuizAnswer.quiz_id == quiz_id,
            QuizAnswer.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(
        self,
        quiz_id: int,
        user_id: int,
        chosen_index: int,
        is_correct: bool,
        answered_at: datetime,
    ) -> QuizAnswer:
        """Store the first answer."""
        row = QuizAnswer(
            quiz_id=quiz_id,
            user_id=user_id,
            chosen_index=chosen_index,
            is_correct=is_correct,
            answered_at=answered_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row
