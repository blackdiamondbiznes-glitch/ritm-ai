"""Which home menu an account gets. Owners and teachers keep the full menu."""

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.menu import main_menu, student_menu
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.roles import RoleService


def actually_teaches(found: dict | None) -> bool:
    """True when a cabinet has at least one group or student. An empty niche does not count."""
    if not found:
        return False
    return any(
        int(item.get("groups") or 0) > 0 or int(item.get("students") or 0) > 0
        for item in found.get("teaching") or []
    )


async def only_student(
    user: User, modes: RoleService | None, chats: ChatRepository | None
) -> tuple[bool, dict | None]:
    """True when the account studies somewhere, teaches nowhere and owns no chat."""
    if modes is None:
        return False, None
    found = await modes.for_user(user)
    if actually_teaches(found):
        return False, found
    studies = bool(found["learning"] or found["pending"]) or await modes.has_card(user)
    if not studies:
        return False, found
    if chats is not None and await chats.count_active(user.id) > 0:
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
    teaching = actually_teaches(found)
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
    student, found = await only_student(user, modes, chats)
    if student:
        return t("menu_title_student", lang), student_menu(lang, is_admin)
    markup = await menu_for(lang, is_admin, user, modes, chats)
    title = t("menu_title_teacher", lang) if actually_teaches(found) else t("menu_title", lang)
    return title, markup


async def help_text_for(
    lang: str,
    user: User,
    modes: RoleService | None,
    chats: ChatRepository | None = None,
) -> str:
    """Role-specific help: student, teacher, or channel-owner default."""
    student, found = await only_student(user, modes, chats)
    if student:
        return t("help_text_student", lang)
    if actually_teaches(found):
        return t("help_text_teacher", lang)
    return t("help_text", lang)
