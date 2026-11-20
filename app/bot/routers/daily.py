"""Daily content schedule. Generation itself runs on the job tick."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import ChatCB, DailyCB
from app.bot.guard import manages
from app.bot.keyboards.daily import daily_menu
from app.bot.keyboards.menu import main_menu
from app.bot.view import show_screen
from app.db.models.chats import Chat
from app.db.models.schedules import Schedule
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.access import AccessService
from app.services.schedule import ScheduleService

router = Router(name="daily")
_RESULT = {
    "queued": "daily_queued",
    "profile": "daily_need_profile",
    "quota": "daily_quota",
    "module": "daily_module",
    "inactive": "daily_inactive",
}


@router.callback_query(ChatCB.filter(F.a == "daily"))
async def open_daily(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Show the clock, the switch and how many generations remain."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await _show(callback, chat, current_user, schedules, access, lang)


@router.callback_query(DailyCB.filter(F.a == "time"))
async def pick_time(
    callback: CallbackQuery,
    callback_data: DailyCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Save a local send time and turn the schedule on."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await schedules.set_time(chat, callback_data.v)
    await _show(callback, chat, current_user, schedules, access, lang, "daily_saved")


@router.callback_query(DailyCB.filter(F.a == "toggle"))
async def toggle(
    callback: CallbackQuery,
    callback_data: DailyCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Pause or resume without changing the clock time."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    current = await schedules.get(chat.id)
    await schedules.set_enabled(chat, not (current is not None and current.enabled))
    await _show(callback, chat, current_user, schedules, access, lang, "daily_saved")


@router.callback_query(DailyCB.filter(F.a == "now"))
async def write_now(
    callback: CallbackQuery,
    callback_data: DailyCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Queue a single post. The tick writes and sends it."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    code = await schedules.enqueue_now(current_user, chat)
    await _show(callback, chat, current_user, schedules, access, lang, _RESULT[code])


async def _show(
    callback: CallbackQuery,
    chat: Chat,
    user: User,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    note: str | None = None,
) -> None:
    row = await schedules.get(chat.id)
    left = await access.remaining_ai_quota(user)
    text = t("daily_title", lang, time=_clock(row), state=_state(row, lang), left=left)
    if note is not None:
        text = t(note, lang) + "\n\n" + text
    enabled = row is not None and row.enabled
    await show_screen(callback, text, daily_menu(lang, chat.id, enabled))


async def _owned(
    callback: CallbackQuery,
    chat_id: int,
    user: User,
    chats: ChatRepository,
    lang: str,
    is_super: bool,
) -> Chat | None:
    chat = await chats.get_by_id(chat_id)
    if chat is not None and manages(chat, user, is_super):
        return chat
    await show_screen(callback, t("not_owner", lang), main_menu(lang, is_super))
    return None


def _clock(row: Schedule | None) -> str:
    if row is None:
        return "09:00"
    return row.time_of_day.strftime("%H:%M")


def _state(row: Schedule | None, lang: str) -> str:
    if row is not None and row.enabled:
        return t("daily_on", lang)
    return t("daily_off", lang)
