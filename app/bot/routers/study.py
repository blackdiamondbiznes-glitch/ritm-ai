"""O'qishim sends a short summary and a button into the student Mini App."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import MenuCB
from app.bot.keyboards.menu import _menu_webapp_url, study_keyboard
from app.db.models.users import User
from app.services.learning import LearningService
from app.services.study_text import summary

router = Router(name="study")


@router.callback_query(MenuCB.filter(F.a == "learn"))
async def learn_screen(
    callback: CallbackQuery,
    lang: str,
    current_user: User,
    learning: LearningService | None = None,
) -> None:
    """Reply with the next lesson and fee, plus a button that opens student mode."""
    if learning is None or callback.message is None:
        await callback.answer()
        return
    payload = await learning.for_user(current_user)
    await callback.message.answer(
        summary(payload, lang),
        reply_markup=study_keyboard(lang, _menu_webapp_url()),
    )
    await callback.answer()
