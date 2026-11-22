"""Link a student to their Telegram account from /start join_<code>."""

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.menu import main_menu
from app.db.models.users import User
from app.i18n import t
from app.services.grades import GradeService

router = Router(name="join")


@router.message(CommandStart(deep_link=True))
async def claim_join(
    message: Message,
    state: FSMContext,
    current_user: User,
    grades: GradeService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Bind this chat to a student or a group, or let another /start handler run."""
    text = message.text or ""
    enroll = enroll_code_from_text(text)
    if enroll:
        await _enroll(message, state, current_user, grades, lang, is_super_admin, enroll)
        return
    code = code_from_text(text)
    if code is None:
        raise SkipHandler()
    await _reply(message, state, current_user, grades, lang, is_super_admin, code)


@router.message(F.text.contains("start=enroll_"))
async def claim_pasted_enroll(
    message: Message,
    state: FSMContext,
    current_user: User,
    grades: GradeService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Accept a group registration URL pasted into the chat."""
    code = enroll_code_from_text(message.text or "")
    if code is None:
        raise SkipHandler()
    await _enroll(message, state, current_user, grades, lang, is_super_admin, code)


@router.message(F.text.contains("start=join_"))
async def claim_pasted_link(
    message: Message,
    state: FSMContext,
    current_user: User,
    grades: GradeService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Accept the ranking URL if it was pasted into the chat instead of opened."""
    code = code_from_text(message.text or "")
    if code is None:
        raise SkipHandler()
    await _reply(message, state, current_user, grades, lang, is_super_admin, code)


async def _enroll(
    message: Message,
    state: FSMContext,
    current_user: User,
    grades: GradeService,
    lang: str,
    is_super_admin: bool,
    code: str,
) -> None:
    await state.clear()
    result = await grades.enroll(code, current_user.telegram_id, current_user.full_name or "")
    await message.answer(
        t(f"enroll_{result}", lang), reply_markup=main_menu(lang, is_super_admin)
    )


async def _reply(
    message: Message,
    state: FSMContext,
    current_user: User,
    grades: GradeService,
    lang: str,
    is_super_admin: bool,
    code: str,
) -> None:
    await state.clear()
    result = await grades.claim(code, current_user.telegram_id)
    await message.answer(
        t(f"join_{result}", lang), reply_markup=main_menu(lang, is_super_admin)
    )


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
