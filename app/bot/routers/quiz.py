"""Quiz schedule. The question is written later, on the job tick."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks import ChatCB, QuizCB
from app.bot.guard import manages
from app.bot.keyboards.menu import main_menu
from app.bot.keyboards.quiz import quiz_menu
from app.bot.view import show_screen
from app.db.models.chats import Chat
from app.db.models.schedules import Schedule
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.jobs.quiz import QUIZ
from app.services.access import AccessService
from app.services.quiz_launch import QuizLaunch
from app.services.schedule import ScheduleService

router = Router(name="quiz")
_RESULT = {
    "queued": "quiz_queued",
    "profile": "quiz_need_profile",
    "quota": "quiz_quota",
    "module": "quiz_module",
    "inactive": "quiz_inactive",
    "content": "quiz_need_content",
}


@router.callback_query(ChatCB.filter(F.a == "quiz"))
async def open_quiz(
    callback: CallbackQuery,
    callback_data: ChatCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Show the quiz clock, or say this plan does not include it."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    if not await access.is_module_allowed(chat, QUIZ):
        await show_screen(callback, t("quiz_module", lang), main_menu(lang, is_super_admin))
        return
    await _show(callback, chat, current_user, schedules, access, lang)


@router.callback_query(QuizCB.filter(F.a == "time"))
async def pick_time(
    callback: CallbackQuery,
    callback_data: QuizCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Save a local quiz time and turn it on."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    await schedules.set_time(chat, callback_data.v, QUIZ)
    await _show(callback, chat, current_user, schedules, access, lang, "quiz_saved")


@router.callback_query(QuizCB.filter(F.a == "toggle"))
async def toggle(
    callback: CallbackQuery,
    callback_data: QuizCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Pause or resume the quiz without changing the clock."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    current = await schedules.get(chat.id, QUIZ)
    await schedules.set_enabled(chat, not (current is not None and current.enabled), QUIZ)
    await _show(callback, chat, current_user, schedules, access, lang, "quiz_saved")


@router.callback_query(QuizCB.filter(F.a == "now"))
async def send_now(
    callback: CallbackQuery,
    callback_data: QuizCB,
    current_user: User,
    chats: ChatRepository,
    schedules: ScheduleService,
    quiz_launch: QuizLaunch,
    access: AccessService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Queue one quiz. The tick writes it from published posts."""
    chat = await _owned(callback, callback_data.id, current_user, chats, lang, is_super_admin)
    if chat is None:
        return
    code = await quiz_launch.enqueue(current_user, chat)
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
    row = await schedules.get(chat.id, QUIZ)
    left = await access.remaining_ai_quota(user)
    text = t("quiz_title", lang, time=_clock(row), state=_state(row, lang), left=left)
    if note is not None:
        text = t(note, lang) + "\n\n" + text
    await show_screen(callback, text, quiz_menu(lang, chat.id, row is not None and row.enabled))


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
        return t("quiz_on", lang)
    return t("quiz_off", lang)
