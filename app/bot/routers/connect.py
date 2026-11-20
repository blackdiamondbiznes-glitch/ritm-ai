"""Confirm a chat the bot was added to."""

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.callbacks import ConnectCB, MenuCB
from app.bot.connect_flow import link_chat
from app.bot.keyboards.menu import connect_confirm, connect_intro, connect_pick, main_menu
from app.bot.screens import render_card
from app.bot.view import edit_screen, show_screen
from app.config import Settings
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.access import AccessService
from app.services.lifecycle import ChatLifecycleService, ConnectOutcome
from app.services.pending import PendingChatStore
from app.services.profiles import ProfileService
from app.services.user_prefs import default_zone

logger = logging.getLogger(__name__)
router = Router(name="connect")


@router.callback_query(MenuCB.filter(F.a == "connect"))
async def intro(callback: CallbackQuery, lang: str) -> None:
    """Explain how to add the bot."""
    await show_screen(callback, t("connect_intro", lang), connect_intro(lang))


@router.callback_query(ConnectCB.filter(F.a == "check"))
async def check_pending(
    callback: CallbackQuery,
    pending: PendingChatStore,
    current_user: User,
    lang: str,
) -> None:
    """List chats this user recently added the bot to."""
    rows = pending.list_for(current_user.telegram_id)
    if not rows:
        await show_screen(callback, t("connect_none", lang), connect_intro(lang))
        return
    if len(rows) == 1:
        text = t("connect_found", lang, title=escape(rows[0].title))
        await show_screen(callback, text, connect_confirm(lang, rows[0].telegram_chat_id))
        return
    await show_screen(callback, t("connect_pick", lang), connect_pick(lang, rows))


@router.callback_query(ConnectCB.filter(F.a == "pick"))
async def pick_pending(
    callback: CallbackQuery,
    callback_data: ConnectCB,
    pending: PendingChatStore,
    current_user: User,
    lang: str,
) -> None:
    """Open confirm for one chat from the list. The adder must match."""
    item = pending.get(callback_data.id)
    if item is None or item.added_by_telegram_id != current_user.telegram_id:
        await show_screen(callback, t("connect_gone", lang), connect_intro(lang))
        return
    text = t("connect_found", lang, title=escape(item.title))
    await show_screen(callback, text, connect_confirm(lang, item.telegram_chat_id))


@router.callback_query(ConnectCB.filter(F.a == "no"))
async def decline(
    callback: CallbackQuery,
    callback_data: ConnectCB,
    pending: PendingChatStore,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Drop a pending chat."""
    pending.pop(callback_data.id)
    await show_screen(callback, t("removed_ok", lang), main_menu(lang, is_super_admin))


@router.callback_query(ConnectCB.filter(F.a == "ok"))
async def confirm(
    callback: CallbackQuery,
    callback_data: ConnectCB,
    bot: Bot,
    state: FSMContext,
    pending: PendingChatStore,
    current_user: User,
    lifecycle: ChatLifecycleService,
    chats: ChatRepository,
    access: AccessService,
    profiles: ProfileService,
    settings: Settings,
    lang: str,
    is_super_admin: bool,
    bot_id: int,
) -> None:
    """Re-check rights, enforce the limit, then start the trial and wizard."""
    item = pending.get(callback_data.id)
    if item is None or item.added_by_telegram_id != current_user.telegram_id:
        await show_screen(callback, t("connect_gone", lang), connect_intro(lang))
        return
    await edit_screen(callback, t("busy", lang), None)
    outcome = await link_chat(bot, bot_id, item.telegram_chat_id, current_user, lifecycle)
    if not outcome.ok or outcome.chat_id is None:
        await _fail(callback, outcome, lang, is_super_admin)
        return
    pending.pop(item.telegram_chat_id)
    chat = await chats.get_by_id(outcome.chat_id)
    if chat is None:
        await show_screen(callback, t("connect_failed", lang), connect_intro(lang))
        return
    if outcome.code == "already":
        await render_card(callback, chat, current_user, access, profiles, lang)
        return
    from app.bot.routers.profile import begin_wizard

    snap = await access.snapshot(current_user)
    if outcome.trial_started:
        banner = t("trial_started", lang, days=settings.trial_days)
    elif snap.kind == "free":
        banner = t("linked_free", lang)
    else:
        banner = t("linked_kept", lang)
    await begin_wizard(
        callback,
        state,
        lang,
        chat.id,
        default_zone(current_user, settings.default_timezone),
        banner,
    )


async def _fail(
    callback: CallbackQuery,
    outcome: ConnectOutcome,
    lang: str,
    is_super_admin: bool,
) -> None:
    key = {
        "not_admin": "connect_not_admin",
        "bot_rights": "connect_bot_rights",
        "limit": "connect_limit",
        "owned": "connect_owned",
        "gone": "connect_gone",
    }.get(outcome.code, "connect_failed")
    text = t(key, lang, used=outcome.used, max=outcome.limit)
    markup = main_menu(lang, is_super_admin) if outcome.code == "limit" else connect_intro(lang)
    await show_screen(callback, text, markup)
