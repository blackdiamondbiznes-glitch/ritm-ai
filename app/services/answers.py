"""Grade a quiz. The first answer sticks."""

from dataclasses import dataclass

from app.db.repositories.quizzes import QuizAnswerRepository, QuizRepository
from app.services.clock import Clock, utcnow


@dataclass(frozen=True)
class QuizCard:
    """What the private chat may show before an answer."""

    question: str
    options: tuple[str, ...]
    mode: str


class QuizAnswerService:
    """Record one choice and say whether it was right."""

    def __init__(
        self,
        quizzes: QuizRepository,
        answers: QuizAnswerRepository,
        now: Clock | None = None,
    ) -> None:
        self._quizzes = quizzes
        self._answers = answers
        self._now = now or utcnow

    async def card(self, quiz_id: int) -> QuizCard | None:
        """Return the question, or None when the id is unknown."""
        quiz = await self._quizzes.get(quiz_id)
        if quiz is None:
            return None
        return QuizCard(quiz.question, tuple(quiz.options), quiz.mode)

    async def already(self, quiz_id: int, user_id: int) -> bool:
        """True when this user has a stored answer."""
        return await self._answers.get(quiz_id, user_id) is not None

    async def take(self, quiz_id: int, user_id: int, choice: int) -> str:
        """Return correct, wrong, repeat, missing or bad."""
        if choice < 0 or choice > 9:
            return "bad"
        quiz = await self._quizzes.get(quiz_id)
        if quiz is None:
            return "missing"
        if choice >= len(quiz.options):
            return "bad"
        if await self._answers.get(quiz_id, user_id) is not None:
            return "repeat"
        right = choice == int(quiz.correct_index)
        await self._answers.add(quiz_id, user_id, choice, right, self._now())
        if right:
            return "correct"
        return "wrong"

    async def take_poll(self, poll_id: str, user_id: int, choice: int) -> str:
        """Grade a native group poll. Unknown polls are ignored."""
        quiz = await self._quizzes.get_by_poll(poll_id)
        if quiz is None:
            return "missing"
        return await self.take(quiz.id, user_id, choice)

    async def explanation(self, quiz_id: int) -> str:
        """Short note shown only after the member has answered in private."""
        quiz = await self._quizzes.get(quiz_id)
        if quiz is None or not quiz.explanation:
            return ""
        return quiz.explanation
