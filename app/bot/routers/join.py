"""Link a student to their Telegram account from /start join_<code>."""

from aiogram import Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import CommandObject, CommandStart
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
    command: CommandObject,
    state: FSMContext,
    current_user: User,
    grades: GradeService,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Bind this chat to the invited student, or let another /start handler run."""
    code = _code(command.args or "")
    if code is None:
        raise SkipHandler()
    await state.clear()
    result = await grades.claim(code, current_user.telegram_id)
    await message.answer(t(f"join_{result}", lang), reply_markup=main_menu(lang, is_super_admin))


def _code(payload: str) -> str | None:
    if not payload.startswith("join_"):
        return None
    code = payload.removeprefix("join_")
    if code.isalnum() and 6 <= len(code) <= 16:
        return code
    return None
