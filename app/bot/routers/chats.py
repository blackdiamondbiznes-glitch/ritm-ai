"""Owner chat list, card, edit and disconnect."""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.callbacks import ChatCB, MenuCB
from app.bot.guard import manages
from app.bot.keyboards.chats import chat_list, disconnect_confirm
from app.bot.keyboards.menu import back_menu, main_menu
from app.bot.routers.profile import start_edit
from app.bot.screens import render_card
from app.bot.view import show_screen
from app.config import Settings
from app.db.models.chats import Chat
from app.db.models.users import User
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.access import AccessService
from app.services.lifecycle import ChatLifecycleService
from app.services.profiles import ProfileService
from app.services.quiz_mode import ADMIN_POST_QUIZ
from app.services.user_prefs import default_zone

router = Router(name="chats")


@router.callback_query(MenuCB.filter(F.a == "chats"))
@router.callback_query(ChatCB.filter(F.a == "list"))
async def list_chats(
    callback: CallbackQuery,
    current_user: User,
    chats: ChatRepository,
    lang: str,
) -> None:
    """Active chats that belong to the current owner."""
    rows = await chats.list_active_for_owner(current_user.id)
    if not rows:
        await show_screen(callback, t("chats_empty", lang), back_menu(lang))
        return
    await show_screen(callback, t("chats_title", lang), chat_list(lang, rows))


@router.callback_query(ChatCB.filter(F.a == "open"))
async def open_chat(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    access: AccessService,
    profiles: ProfileService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Chat card. Ownership is checked again here."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await render_card(callback, chat, current_user, access, profiles, lang)


@router.callback_query(ChatCB.filter(F.a == "edit"))
async def edit_chat(
    callback: CallbackQuery,
    callback_data: ChatCB,
    state: FSMContext,
    current_user: User,
    chats: ChatRepository,
    profiles: ProfileService,
    settings: Settings,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Re-run the wizard for this chat."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    profile = await profiles.get(chat.id)
    await start_edit(
        callback, state, lang, chat, profile, default_zone(current_user, settings.default_timezone)
    )


@router.callback_query(ChatCB.filter(F.a == "ask"))
async def ask_disconnect(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Confirm before disconnect. Trial flag is not mentioned as reset."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    text = t("chat_disconnect_ask", lang, title=escape(chat.title))
    await show_screen(callback, text, disconnect_confirm(lang, chat.id))


@router.callback_query(ChatCB.filter(F.a == "yes"))
async def do_disconnect(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    lifecycle: ChatLifecycleService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Deactivate the chat. `trial_consumed` stays as it is."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await lifecycle.disconnect(current_user, chat)
    rows = await chats.list_active_for_owner(current_user.id)
    text = t("chat_disconnected", lang)
    if not rows:
        await show_screen(callback, text, back_menu(lang))
        return
    await show_screen(callback, text, chat_list(lang, rows))


@router.callback_query(ChatCB.filter(F.a == "apq"))
async def toggle_admin_post_quiz(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    access: AccessService,
    profiles: ProfileService,
    audit: AuditRepository,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Turn automatic quizzes from admin posts on or off."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    if not await access.is_module_allowed(chat, ADMIN_POST_QUIZ):
        await render_card(
            callback, chat, current_user, access, profiles, lang, note=t("apq_need_plan", lang)
        )
        return
    profile = await profiles.get(chat.id)
    if profile is None:
        await render_card(
            callback,
            chat,
            current_user,
            access,
            profiles,
            lang,
            note=t("apq_need_profile", lang),
        )
        return
    enabled = ADMIN_POST_QUIZ not in (profile.modules_enabled or [])
    await profiles.set_module(chat.id, ADMIN_POST_QUIZ, enabled)
    await audit.add(
        actor_user_id=current_user.id,
        action="admin_post_quiz_toggled",
        entity="chat",
        entity_id=str(chat.id),
        data={"enabled": enabled},
    )
    note = t("apq_enabled", lang) if enabled else t("apq_disabled", lang)
    await render_card(callback, chat, current_user, access, profiles, lang, note=note)


async def _owned(
    callback: CallbackQuery,
    chat_id: int,
    user: User,
    chats: ChatRepository,
    lang: str,
    is_super_admin: bool,
) -> Chat | None:
    chat = await chats.get_by_id(chat_id)
    if chat is None:
        await show_screen(callback, t("chat_missing", lang), back_menu(lang))
        return None
    if not manages(chat, user, is_super_admin):
        await show_screen(callback, t("not_owner", lang), main_menu(lang, is_super_admin))
        return None
    return chat
