"""Start, menu, help, cancel and the UI language picker."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import LangCB, MenuCB
from app.bot.enroll_notice import teacher_notifier
from app.bot.keyboards.menu import back_menu, language_picker, main_menu
from app.bot.routers.join import (
    code_from_text,
    enroll_code_from_text,
    enroll_from_args,
    join_from_args,
)
from app.bot.view import show_screen
from app.db.models.users import User
from app.i18n import t
from app.services.enrollment import EnrollmentService
from app.services.user_prefs import PrefsError, needs_language, set_language

router = Router(name="start")


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
        await message.answer(
            t(f"enroll_{result}", lang), reply_markup=main_menu(lang, is_super_admin)
        )
        return
    code = join_from_args(args) or code_from_text(text)
    if code and (text.startswith("/start") or args.startswith("join_")):
        await state.clear()
        result = await enrollment.claim(code, current_user.telegram_id)
        await message.answer(
            t(f"join_{result}", lang), reply_markup=main_menu(lang, is_super_admin)
        )
        return
    await state.clear()
    if needs_language(current_user):
        await message.answer(t("lang_pick", lang), reply_markup=language_picker(first=True))
        return
    await message.answer(t("menu_title", lang), reply_markup=main_menu(lang, is_super_admin))


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
    callback: CallbackQuery, callback_data: LangCB, current_user: User, is_super_admin: bool
) -> None:
    """Save the choice (same rule as the Mini App), then show the menu in that language."""
    try:
        set_language(current_user, callback_data.v)
    except PrefsError:
        await callback.answer(t("input_bad", current_user.language_code or "uz"), show_alert=True)
        return
    code = current_user.language_code
    text = f"{t('lang_saved', code)}\n\n{t('menu_title', code)}"
    await show_screen(callback, text, main_menu(code, is_super_admin))


@router.message(Command("help"))
async def help_command(message: Message, lang: str) -> None:
    """Static help."""
    await message.answer(t("help_text", lang), reply_markup=back_menu(lang))


@router.message(Command("cancel"))
async def cancel_command(
    message: Message, state: FSMContext, lang: str, is_super_admin: bool
) -> None:
    """Leave any wizard and return home."""
    await state.clear()
    await message.answer(t("cancelled", lang), reply_markup=main_menu(lang, is_super_admin))


@router.callback_query(MenuCB.filter(F.a == "home"))
async def home(callback: CallbackQuery, state: FSMContext, lang: str, is_super_admin: bool) -> None:
    """Back to the main menu from any screen that uses it."""
    await state.clear()
    await show_screen(callback, t("menu_title", lang), main_menu(lang, is_super_admin))


@router.callback_query(MenuCB.filter(F.a == "help"))
async def help_screen(callback: CallbackQuery, lang: str) -> None:
    """Help, edited in place."""
    await show_screen(callback, t("help_text", lang), back_menu(lang))
