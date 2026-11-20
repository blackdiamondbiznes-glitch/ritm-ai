"""Private answer taps. Channel members arrive here from the deep link."""

from html import escape

from aiogram import Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import PickCB
from app.bot.keyboards.menu import main_menu
from app.bot.view import show_screen
from app.db.models.users import User
from app.i18n import t
from app.services.answers import QuizAnswerService

router = Router(name="quiz_play")


@router.callback_query(PickCB.filter())
async def pick(
    callback: CallbackQuery,
    callback_data: PickCB,
    current_user: User,
    quiz_answers: QuizAnswerService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Grade the first private tap. Later taps stay on the first answer."""
    choice = _choice(callback_data.v)
    code = await quiz_answers.take(callback_data.id, current_user.id, choice)
    await callback.answer(t(f"quiz_{code}", lang), show_alert=True)
    if code not in {"correct", "wrong"}:
        return
    note = await quiz_answers.explanation(callback_data.id)
    text = t(f"quiz_{code}", lang)
    if note:
        text = text + "\n\n" + escape(note)
    await show_screen(callback, text, main_menu(lang, is_super_admin))


def _choice(value: str) -> int:
    if value.isdigit():
        return int(value)
    return -1
