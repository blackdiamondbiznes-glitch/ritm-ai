"""Last resort for private text and leftover buttons."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import main_menu
from app.i18n import t

router = Router(name="fallback")


@router.message(F.text)
async def use_menu(message: Message, lang: str, is_super_admin: bool) -> None:
    """Point the user back to the menu. Commands are handled earlier."""
    await message.answer(t("use_menu", lang), reply_markup=main_menu(lang, is_super_admin))


@router.callback_query()
async def stale_button(callback: CallbackQuery, lang: str) -> None:
    """Old or unknown inline buttons get a clear notice, not a generic error."""
    await callback.answer(t("button_stale", lang), show_alert=True)
