"""Open a channel quiz from /start quiz_<id>. Group quizzes stay on the poll."""

from aiogram import Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.copy import quiz_question_html
from app.bot.keyboards.menu import main_menu
from app.bot.keyboards.quiz import answer_keyboard
from app.db.models.users import User
from app.i18n import t
from app.services.answers import QuizAnswerService
from app.services.quiz_mode import DEEPLINK

router = Router(name="quiz_link")


@router.message(CommandStart(deep_link=True))
async def open_linked(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    current_user: User,
    quiz_answers: QuizAnswerService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Show the private quiz, or let the normal /start handler run."""
    quiz_id = _quiz_id(command.args or "")
    if quiz_id is None:
        raise SkipHandler()
    await state.clear()
    await _show(message, quiz_id, current_user, quiz_answers, lang, is_super_admin)


async def _show(
    message: Message,
    quiz_id: int,
    user: User,
    answers: QuizAnswerService,
    lang: str,
    is_super: bool,
) -> None:
    card = await answers.card(quiz_id)
    if card is None:
        await message.answer(t("quiz_missing", lang), reply_markup=main_menu(lang, is_super))
        return
    if card.mode != DEEPLINK:
        await message.answer(t("quiz_group_only", lang), reply_markup=main_menu(lang, is_super))
        return
    previous = await answers.already(quiz_id, user.id)
    if previous:
        await message.answer(t("quiz_repeat", lang), reply_markup=main_menu(lang, is_super))
        return
    await message.answer(
        quiz_question_html(card.question),
        reply_markup=answer_keyboard(quiz_id, card.options),
    )


def _quiz_id(payload: str) -> int | None:
    if not payload.startswith("quiz_"):
        return None
    raw = payload.removeprefix("quiz_")
    if raw.isdigit():
        return int(raw)
    return None
