"""Leaderboard screen, weekly schedule and the announce-now button."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import BoardCB, ChatCB
from app.bot.copy import board_screen
from app.bot.guard import manages
from app.bot.keyboards.leaderboard import board_menu
from app.bot.keyboards.menu import main_menu
from app.bot.view import show_screen
from app.db.models.chats import Chat
from app.db.models.schedules import Schedule
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.access import AccessService
from app.services.leaderboard import MODULE, LeaderboardService
from app.services.profiles import ProfileService
from app.services.schedule import ScheduleService

router = Router(name="leaderboard")
_RESULT = {
    "queued": "board_queued",
    "profile": "board_need_profile",
    "module": "board_module",
    "inactive": "board_inactive",
    "empty": "board_empty",
}


@router.callback_query(ChatCB.filter(F.a == "board"))
async def open_board(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    profiles: ProfileService,
    leaderboard: LeaderboardService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Show the last board, a live preview and the weekly clock."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    if not await access.is_module_allowed(chat, MODULE):
        await show_screen(callback, t("board_module", lang), main_menu(lang, is_super_admin))
        return
    await _show(callback, chat, schedules, profiles, leaderboard, lang)


@router.callback_query(BoardCB.filter(F.a == "time"))
async def pick_time(
    callback: CallbackQuery,
    callback_data: BoardCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    profiles: ProfileService,
    leaderboard: LeaderboardService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Save the local announcement time and turn the schedule on."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await schedules.set_time(chat, callback_data.v, MODULE)
    await _show(callback, chat, schedules, profiles, leaderboard, lang, "board_saved")


@router.callback_query(BoardCB.filter(F.a == "day"))
async def pick_day(
    callback: CallbackQuery,
    callback_data: BoardCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    profiles: ProfileService,
    leaderboard: LeaderboardService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Save a single weekday. The scoring week stays Monday–Sunday."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await schedules.set_weekday(chat, _day(callback_data.v), MODULE)
    await _show(callback, chat, schedules, profiles, leaderboard, lang, "board_saved")


@router.callback_query(BoardCB.filter(F.a == "toggle"))
async def toggle(
    callback: CallbackQuery,
    callback_data: BoardCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    profiles: ProfileService,
    leaderboard: LeaderboardService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Pause or resume the weekly announcement."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    current = await schedules.get(chat.id, MODULE)
    await schedules.set_enabled(chat, not (current is not None and current.enabled), MODULE)
    await _show(callback, chat, schedules, profiles, leaderboard, lang, "board_saved")


@router.callback_query(BoardCB.filter(F.a == "now"))
async def announce_now(
    callback: CallbackQuery,
    callback_data: BoardCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    profiles: ProfileService,
    leaderboard: LeaderboardService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Queue a live Top-10 for this week, so it can be tested immediately."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    live = None
    profile = await profiles.get(chat.id)
    if profile is not None:
        live = await leaderboard.live(chat, profile.timezone)
    if live is None or not live.members:
        await _show(callback, chat, schedules, profiles, leaderboard, lang, "board_empty")
        return
    code = await schedules.enqueue_now(current_user, chat, MODULE, extra={"window": "current"})
    await _show(callback, chat, schedules, profiles, leaderboard, lang, _RESULT[code])


async def _show(
    callback: CallbackQuery,
    chat: Chat,
    schedules: ScheduleService,
    profiles: ProfileService,
    leaderboard: LeaderboardService,
    lang: str,
    note: str | None = None,
) -> None:
    row = await schedules.get(chat.id, MODULE)
    profile = await profiles.get(chat.id)
    zone = profile.timezone if profile is not None else "Asia/Tashkent"
    last = await leaderboard.last(chat.id)
    live = await leaderboard.live(chat, zone)
    weekday = _weekday(row)
    text = board_screen(
        last,
        live,
        lang,
        weekday=t(f"weekday_full_{weekday}", lang),
        clock=_clock(row),
        state=_state(row, lang),
        note=t(note, lang) if note else None,
    )
    await show_screen(callback, text, board_menu(lang, chat.id, weekday, _enabled(row)))


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


def _weekday(row: Schedule | None) -> int:
    if row is None or not row.days_of_week:
        return 1
    return int(row.days_of_week[0])


def _enabled(row: Schedule | None) -> bool:
    return row is not None and row.enabled


def _state(row: Schedule | None, lang: str) -> str:
    if _enabled(row):
        return t("board_on", lang)
    return t("board_off", lang)


def _day(value: str) -> int:
    try:
        day = int(value)
    except ValueError:
        return 0
    return day
