"""Native group poll votes. Channels never emit these for our quizzes."""

from aiogram import Router
from aiogram.types import PollAnswer

from app.db.models.users import User
from app.services.answers import QuizAnswerService

router = Router(name="quiz_poll")


@router.poll_answer()
async def voted(
    event: PollAnswer,
    current_user: User,
    quiz_answers: QuizAnswerService,
) -> None:
    """Store the first vote. Telegram already shows the native result."""
    if not event.option_ids:
        return
    await quiz_answers.take_poll(event.poll_id, current_user.id, event.option_ids[0])
