"""Start, menu, help, cancel and the UI language picker."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import LangCB, MenuCB
from app.bot.enroll_notice import teacher_notifier
from app.bot.join_reply import join_answer
from app.bot.keyboards.menu import back_menu, language_picker, main_menu
from app.bot.menus import home_view, menu_for
from app.bot.routers.join import (
    code_from_text,
    enroll_code_from_text,
    enroll_from_args,
    join_from_args,
    log_link,
)
from app.bot.view import show_screen
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.enrollment import EnrollmentService
from app.services.roles import RoleService
from app.services.user_prefs import PrefsError, needs_language, set_language

router = Router(name="start")


async def _menu(
    lang: str,
    is_admin: bool,
    user: User,
    modes: RoleService | None,
    chats: ChatRepository | None = None,
):
    """Main menu: the student keyboard for students, cabinet buttons for teachers."""
    return await menu_for(lang, is_admin, user, modes, chats)


@router.message(CommandStart())
@router.message(Command("menu"))
async def open_menu(
    message: Message,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    current_user: User,
    enrollment: EnrollmentService,
    command: CommandObject | None = None,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Show the main menu. A ranking link is claimed before the menu."""
    text = message.text or ""
    args = command.args or "" if command else ""
    enroll = enroll_from_args(args) or enroll_code_from_text(text)
    if enroll and (text.startswith("/start") or args.startswith("enroll_")):
        await state.clear()
        result = await enrollment.enroll(
            enroll,
            current_user.telegram_id,
            current_user.full_name or "",
            notify=teacher_notifier(message.bot),
        )
        log_link("enroll", enroll, result, current_user.telegram_id)
        text, markup = await join_answer(
            "enroll", enroll, result, lang, current_user, is_super_admin, enrollment, modes, chats
        )
        await message.answer(text, reply_markup=markup)
        return
    code = join_from_args(args) or code_from_text(text)
    if code and (text.startswith("/start") or args.startswith("join_")):
        await state.clear()
        result = await enrollment.claim(code, current_user.telegram_id)
        log_link("join", code, result, current_user.telegram_id)
        text, markup = await join_answer(
            "join", code, result, lang, current_user, is_super_admin, enrollment, modes, chats
        )
        await message.answer(text, reply_markup=markup)
        return
    await state.clear()
    if needs_language(current_user):
        await message.answer(t("lang_pick", lang), reply_markup=language_picker(first=True))
        return
    title, markup = await home_view(lang, is_super_admin, current_user, modes, chats)
    await message.answer(title, reply_markup=markup)


@router.message(Command("language"))
async def language_command(message: Message, state: FSMContext, lang: str) -> None:
    """Change the interface language at any time."""
    await state.clear()
    await message.answer(t("lang_pick", lang), reply_markup=language_picker(lang))


@router.callback_query(MenuCB.filter(F.a == "lang"))
async def language_screen(callback: CallbackQuery, lang: str) -> None:
    """Language picker from the main menu (bot settings)."""
    await show_screen(callback, t("lang_pick", lang), language_picker(lang))


@router.callback_query(LangCB.filter())
async def pick_language(
    callback: CallbackQuery,
    callback_data: LangCB,
    current_user: User,
    is_super_admin: bool,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Save the choice (same rule as the Mini App), then show the menu in that language."""
    try:
        set_language(current_user, callback_data.v)
    except PrefsError:
        await callback.answer(t("input_bad", current_user.language_code or "uz"), show_alert=True)
        return
    code = current_user.language_code or "uz"
    title, markup = await home_view(code, is_super_admin, current_user, modes, chats)
    await show_screen(callback, f"{t('lang_saved', code)}\n\n{title}", markup)


@router.message(Command("help"))
async def help_command(message: Message, lang: str) -> None:
    """Static help."""
    await message.answer(t("help_text", lang), reply_markup=back_menu(lang))


@router.message(Command("cancel"))
async def cancel_command(
    message: Message,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    current_user: User | None = None,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Leave any wizard and return home."""
    await state.clear()
    markup = main_menu(lang, is_super_admin)
    if current_user is not None:
        markup = await menu_for(lang, is_super_admin, current_user, modes, chats)
    await message.answer(t("cancelled", lang), reply_markup=markup)


@router.callback_query(MenuCB.filter(F.a == "home"))
async def home(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    current_user: User | None = None,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Back to the main menu from any screen that uses it."""
    await state.clear()
    title, markup = t("menu_title", lang), main_menu(lang, is_super_admin)
    if current_user is not None:
        title, markup = await home_view(lang, is_super_admin, current_user, modes, chats)
    await show_screen(callback, title, markup)


@router.callback_query(MenuCB.filter(F.a == "help"))
async def help_screen(callback: CallbackQuery, lang: str) -> None:
    """Help, edited in place."""
    await show_screen(callback, t("help_text", lang), back_menu(lang))
