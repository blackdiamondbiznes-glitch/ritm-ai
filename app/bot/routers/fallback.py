"""Last resort for private text and leftover buttons."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import main_menu
from app.bot.menus import menu_for
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.roles import RoleService

router = Router(name="fallback")


@router.message(F.text)
async def use_menu(
    message: Message,
    lang: str,
    is_super_admin: bool,
    current_user: User | None = None,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Point the user back to the menu. Commands are handled earlier."""
    markup = main_menu(lang, is_super_admin)
    if current_user is not None:
        markup = await menu_for(lang, is_super_admin, current_user, modes, chats)
    await message.answer(t("use_menu", lang), reply_markup=markup)


@router.callback_query()
async def stale_button(callback: CallbackQuery, lang: str) -> None:
    """Old or unknown inline buttons get a clear notice, not a generic error."""
    await callback.answer(t("button_stale", lang), show_alert=True)
