"""Which home menu an account gets. Owners and teachers keep the full menu."""

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.menu import main_menu, student_menu
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.roles import RoleService


async def only_student(
    user: User, modes: RoleService | None, chats: ChatRepository | None
) -> tuple[bool, dict | None]:
    """True when the account studies somewhere, teaches nowhere and owns no chat."""
    if modes is None:
        return False, None
    found = await modes.for_user(user)
    if found["teaching"]:
        return False, found
    studies = bool(found["learning"] or found["pending"]) or await modes.has_card(user)
    if not studies:
        return False, found
    if chats is not None and await chats.count_active(user.id) > 0:
        return False, found
    if user.cabinet_niche == "tutor":
        return False, found
    return True, found


async def menu_for(
    lang: str,
    is_admin: bool,
    user: User,
    modes: RoleService | None,
    chats: ChatRepository | None = None,
) -> InlineKeyboardMarkup:
    """The student keyboard for students, the owner menu with cabinet buttons for others."""
    student, found = await only_student(user, modes, chats)
    if student:
        return student_menu(lang, is_admin)
    teaching = bool(found and found["teaching"])
    learning = bool(found and found["learning"])
    return main_menu(lang, is_admin, teaching=teaching, learning=learning)


async def home_view(
    lang: str,
    is_admin: bool,
    user: User,
    modes: RoleService | None,
    chats: ChatRepository | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Title and keyboard for /start, /menu and the Back button."""
    student, _found = await only_student(user, modes, chats)
    if student:
        return t("menu_title_student", lang), student_menu(lang, is_admin)
    return t("menu_title", lang), await menu_for(lang, is_admin, user, modes, chats)
