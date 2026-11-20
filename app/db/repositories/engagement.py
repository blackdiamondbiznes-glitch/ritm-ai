"""Activity totals used in trial reports and the Mini App. No message wording here."""

from datetime import date, datetime

from sqlalchemy import Date, Select, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.content import ContentItem
from app.db.models.quizzes import Quiz, QuizAnswer


class EngagementRepository:
    """Count posts, quizzes, answers and participants for one chat."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def posts_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int:
        """Published content rows in [started, until)."""
        return await self._count(
            ContentItem,
            ContentItem.chat_id == chat_id,
            ContentItem.published_at.is_not(None),
            ContentItem.published_at >= started,
            *(() if until is None else (ContentItem.published_at < until,)),
        )

    async def quizzes_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int:
        """Quiz rows created in [started, until)."""
        return await self._count(
            Quiz,
            Quiz.chat_id == chat_id,
            Quiz.created_at >= started,
            *(() if until is None else (Quiz.created_at < until,)),
        )

    async def answers_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int:
        """Quiz answers recorded for this chat in [started, until)."""
        stmt = (
            select(func.count())
            .select_from(QuizAnswer)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(Quiz.chat_id == chat_id, QuizAnswer.answered_at >= started)
        )
        if until is not None:
            stmt = stmt.where(QuizAnswer.answered_at < until)
        return await self._scalar(stmt)

    async def participants_since(
        self, chat_id: int, started: datetime, until: datetime | None = None
    ) -> int:
        """Distinct members who answered a quiz in this window."""
        stmt = (
            select(func.count(func.distinct(QuizAnswer.user_id)))
            .select_from(QuizAnswer)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(Quiz.chat_id == chat_id, QuizAnswer.answered_at >= started)
        )
        if until is not None:
            stmt = stmt.where(QuizAnswer.answered_at < until)
        return await self._scalar(stmt)

    async def best_day(self, chat_id: int, started: datetime):
        """The UTC date with the most quiz answers, if any."""
        day = cast(QuizAnswer.answered_at, Date)
        stmt = (
            select(day, func.count())
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(Quiz.chat_id == chat_id, QuizAnswer.answered_at >= started)
            .group_by(day)
            .order_by(func.count().desc(), day)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        return None if row is None else row[0]

    async def window_counts(
        self, chat_ids: list[int], windows: list[tuple[datetime, datetime]]
    ) -> list[dict[str, int]]:
        """Posts, quizzes, answers and per-chat participants for several windows.

        Three grouped queries regardless of how many chats or windows. Participants
        are distinct per chat and then summed, matching the per-chat counters.
        """
        names = ("posts", "quizzes", "answers", "participants")
        out = [dict.fromkeys(names, 0) for _ in windows]
        if not chat_ids or not windows:
            return out
        low = min(start for start, _end in windows)
        high = max(end for _start, end in windows)

        def _filters(column):
            return [and_(column >= start, column < end) for start, end in windows]

        post_cols = [func.count().filter(cond) for cond in _filters(ContentItem.published_at)]
        posts = select(*post_cols).where(
            ContentItem.chat_id.in_(chat_ids),
            ContentItem.published_at.is_not(None),
            ContentItem.published_at >= low,
            ContentItem.published_at < high,
        )
        quiz_cols = [func.count().filter(cond) for cond in _filters(Quiz.created_at)]
        quizzes = select(*quiz_cols).where(
            Quiz.chat_id.in_(chat_ids), Quiz.created_at >= low, Quiz.created_at < high
        )
        answer_filters = _filters(QuizAnswer.answered_at)
        answer_cols = [func.count().filter(cond) for cond in answer_filters]
        people_cols = [
            func.count(func.distinct(QuizAnswer.user_id)).filter(cond) for cond in answer_filters
        ]
        answers = (
            select(*answer_cols, *people_cols)
            .select_from(QuizAnswer)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(
                Quiz.chat_id.in_(chat_ids),
                QuizAnswer.answered_at >= low,
                QuizAnswer.answered_at < high,
            )
            .group_by(Quiz.chat_id)
        )
        size = len(windows)
        for name, stmt in (("posts", posts), ("quizzes", quizzes)):
            row = (await self._session.execute(stmt)).one()
            for index in range(size):
                out[index][name] = int(row[index] or 0)
        for row in (await self._session.execute(answers)).all():
            for index in range(size):
                out[index]["answers"] += int(row[index] or 0)
                out[index]["participants"] += int(row[size + index] or 0)
        return out

    async def daily_counts(
        self, chat_ids: list[int], started: datetime, until: datetime, timezone: str
    ) -> dict[date, dict[str, int]]:
        """Posts, quizzes and answers per local calendar day in [started, until)."""
        if not chat_ids:
            return {}
        out: dict[date, dict[str, int]] = {}
        post_day = cast(func.timezone(timezone, ContentItem.published_at), Date)
        posts = (
            select(post_day, func.count())
            .where(
                ContentItem.chat_id.in_(chat_ids),
                ContentItem.published_at.is_not(None),
                ContentItem.published_at >= started,
                ContentItem.published_at < until,
            )
            .group_by(post_day)
        )
        quiz_day = cast(func.timezone(timezone, Quiz.created_at), Date)
        quizzes = (
            select(quiz_day, func.count())
            .where(Quiz.chat_id.in_(chat_ids), Quiz.created_at >= started, Quiz.created_at < until)
            .group_by(quiz_day)
        )
        answer_day = cast(func.timezone(timezone, QuizAnswer.answered_at), Date)
        answers = (
            select(answer_day, func.count())
            .select_from(QuizAnswer)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(
                Quiz.chat_id.in_(chat_ids),
                QuizAnswer.answered_at >= started,
                QuizAnswer.answered_at < until,
            )
            .group_by(answer_day)
        )
        for name, stmt in (("posts", posts), ("quizzes", quizzes), ("answers", answers)):
            result = await self._session.execute(stmt)
            for day, count in result.all():
                out.setdefault(day, {})[name] = int(count)
        return out

    async def totals_by_chat(self, chat_ids: list[int]) -> dict[int, dict[str, int]]:
        """All-time published posts and created quizzes per chat."""
        out: dict[int, dict[str, int]] = {cid: {"posts": 0, "quizzes": 0} for cid in chat_ids}
        if not chat_ids:
            return out
        posts = (
            select(ContentItem.chat_id, func.count())
            .where(ContentItem.chat_id.in_(chat_ids), ContentItem.published_at.is_not(None))
            .group_by(ContentItem.chat_id)
        )
        quizzes = (
            select(Quiz.chat_id, func.count())
            .where(Quiz.chat_id.in_(chat_ids))
            .group_by(Quiz.chat_id)
        )
        for name, stmt in (("posts", posts), ("quizzes", quizzes)):
            result = await self._session.execute(stmt)
            for chat_id, count in result.all():
                out.setdefault(chat_id, {"posts": 0, "quizzes": 0})[name] = int(count)
        return out

    async def is_participant(self, chat_id: int, user_id: int) -> bool:
        """True when this user has answered at least one quiz in this chat."""
        stmt = (
            select(QuizAnswer.id)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(Quiz.chat_id == chat_id, QuizAnswer.user_id == user_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None

    async def member_totals(self, user_id: int) -> dict[int, dict[str, object]]:
        """All-time answers, correct answers and last answer time per chat for one user."""
        correct = func.count().filter(QuizAnswer.is_correct.is_(True))
        stmt = (
            select(Quiz.chat_id, func.count(), correct, func.max(QuizAnswer.answered_at))
            .select_from(QuizAnswer)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(QuizAnswer.user_id == user_id)
            .group_by(Quiz.chat_id)
        )
        result = await self._session.execute(stmt)
        return {
            int(chat_id): {"answers": int(total), "correct": int(right or 0), "last_at": last}
            for chat_id, total, right, last in result.all()
        }

    async def member_history(self, user_id: int, limit: int = 20) -> list[dict[str, object]]:
        """The user's most recent answers with the question and options."""
        stmt = (
            select(
                Quiz.chat_id,
                Quiz.question,
                Quiz.options,
                Quiz.correct_index,
                QuizAnswer.chosen_index,
                QuizAnswer.is_correct,
                QuizAnswer.answered_at,
            )
            .select_from(QuizAnswer)
            .join(Quiz, Quiz.id == QuizAnswer.quiz_id)
            .where(QuizAnswer.user_id == user_id)
            .order_by(QuizAnswer.answered_at.desc(), QuizAnswer.id.desc())
            .limit(max(1, min(limit, 100)))
        )
        result = await self._session.execute(stmt)
        rows = []
        for chat_id, question, options, correct_index, chosen, is_correct, when in result.all():
            opts = list(options or [])
            rows.append(
                {
                    "chat_id": int(chat_id),
                    "question": question,
                    "chosen": opts[chosen] if 0 <= chosen < len(opts) else None,
                    "correct": opts[correct_index] if 0 <= correct_index < len(opts) else None,
                    "is_correct": bool(is_correct),
                    "answered_at": when,
                }
            )
        return rows

    async def _count(self, model, *clauses: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(model).where(*clauses)
        return await self._scalar(stmt)

    async def _scalar(self, stmt: Select[tuple[int]]) -> int:
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
