"""Link a student to their Telegram account from /start join_<code>."""

import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.enroll_notice import teacher_notifier
from app.bot.join_reply import join_answer
from app.bot.menus import menu_for
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.enrollment import EnrollmentService
from app.services.roles import RoleService

router = Router(name="join")
logger = logging.getLogger(__name__)


def log_link(kind: str, code: str | None, result: str, user_id: int | None) -> None:
    """One INFO line per deep link. Only the first 4 characters of the code are logged."""
    logger.info(
        "deep link kind=%s code=%s… result=%s user_id=%s", kind, (code or "")[:4], result, user_id
    )


@router.message(CommandStart(deep_link=True))
async def claim_join(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    current_user: User,
    enrollment: EnrollmentService,
    lang: str,
    is_super_admin: bool,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Bind this chat to a student or a group, or let another /start handler run."""
    text = message.text or ""
    args = command.args or ""
    enroll = enroll_from_args(args) or enroll_code_from_text(text)
    if enroll:
        await _enroll(
            message, state, current_user, enrollment, lang, is_super_admin, enroll, modes, chats
        )
        return
    code = join_from_args(args) or code_from_text(text)
    if code is None:
        kind = _broken_kind(args)
        if kind is None:
            raise SkipHandler()
        # A join_/enroll_ payload with a damaged code still gets an answer, never silence.
        await state.clear()
        log_link(kind, args.split("_", 1)[1], "missing", current_user.telegram_id)
        await message.answer(
            t(f"{kind}_missing", lang),
            reply_markup=await menu_for(lang, is_super_admin, current_user, modes, chats),
        )
        return
    await _reply(message, state, current_user, enrollment, lang, is_super_admin, code, modes, chats)


@router.message(F.text.contains("start=enroll_"))
async def claim_pasted_enroll(
    message: Message,
    state: FSMContext,
    current_user: User,
    enrollment: EnrollmentService,
    lang: str,
    is_super_admin: bool,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Accept a group registration URL pasted into the chat."""
    code = enroll_code_from_text(message.text or "")
    if code is None:
        raise SkipHandler()
    await _enroll(
        message, state, current_user, enrollment, lang, is_super_admin, code, modes, chats
    )


@router.message(F.text.contains("start=join_"))
async def claim_pasted_link(
    message: Message,
    state: FSMContext,
    current_user: User,
    enrollment: EnrollmentService,
    lang: str,
    is_super_admin: bool,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    """Accept the ranking URL if it was pasted into the chat instead of opened."""
    code = code_from_text(message.text or "")
    if code is None:
        raise SkipHandler()
    await _reply(message, state, current_user, enrollment, lang, is_super_admin, code, modes, chats)


async def _enroll(
    message: Message,
    state: FSMContext,
    current_user: User,
    enrollment: EnrollmentService,
    lang: str,
    is_super_admin: bool,
    code: str,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    await state.clear()
    result = await enrollment.enroll(
        code,
        current_user.telegram_id,
        current_user.full_name or "",
        notify=teacher_notifier(message.bot),
    )
    log_link("enroll", code, result, current_user.telegram_id)
    text, markup = await join_answer(
        "enroll", code, result, lang, current_user, is_super_admin, enrollment, modes, chats
    )
    await message.answer(text, reply_markup=markup)


async def _reply(
    message: Message,
    state: FSMContext,
    current_user: User,
    enrollment: EnrollmentService,
    lang: str,
    is_super_admin: bool,
    code: str,
    modes: RoleService | None = None,
    chats: ChatRepository | None = None,
) -> None:
    await state.clear()
    result = await enrollment.claim(code, current_user.telegram_id)
    log_link("join", code, result, current_user.telegram_id)
    text, markup = await join_answer(
        "join", code, result, lang, current_user, is_super_admin, enrollment, modes, chats
    )
    await message.answer(text, reply_markup=markup)


def _broken_kind(args: str) -> str | None:
    token = args.strip()
    for kind in ("join", "enroll"):
        if token.startswith(f"{kind}_"):
            return kind
    return None


def enroll_from_args(args: str) -> str | None:
    """Read enroll code from the hidden /start argument Telegram does not show."""
    token = args.strip()
    if not token.startswith("enroll_"):
        return None
    return _token(token.removeprefix("enroll_"))


def join_from_args(args: str) -> str | None:
    """Read a personal join code from the hidden /start argument."""
    token = args.strip()
    if not token.startswith("join_"):
        return None
    return _token(token.removeprefix("join_"))


def enroll_code_from_text(text: str) -> str | None:
    """Read a group registration code from `/start enroll_…` or a pasted link."""
    raw = text.strip()
    marker = "start=enroll_"
    if marker in raw:
        tail = raw.split(marker, 1)[1]
        return _token(tail.split("&", 1)[0].split()[0])
    parts = raw.split(maxsplit=1)
    if len(parts) == 2 and parts[0].split("@", 1)[0] == "/start" and parts[1].startswith("enroll_"):
        return _token(parts[1].removeprefix("enroll_"))
    return None


def code_from_text(text: str) -> str | None:
    """Read a join code from `/start join_…` or from a pasted t.me link."""
    raw = text.strip()
    marker = "start=join_"
    if marker in raw:
        tail = raw.split(marker, 1)[1]
        token = tail.split("&", 1)[0].split()[0]
        return _token(token)
    parts = raw.split(maxsplit=1)
    if len(parts) == 2 and parts[0].split("@", 1)[0] == "/start":
        return _code(parts[1])
    return None


def _code(payload: str) -> str | None:
    if not payload.startswith("join_"):
        return None
    return _token(payload.removeprefix("join_"))


def _token(code: str) -> str | None:
    if code.isalnum() and 6 <= len(code) <= 16:
        return code
    return None
