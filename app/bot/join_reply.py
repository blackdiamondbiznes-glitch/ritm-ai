"""What a student reads after a join_ or enroll_ link: which group, which teacher."""

from html import escape

from aiogram.types import InlineKeyboardMarkup

from app.bot.menus import menu_for
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.enrollment import EnrollmentService
from app.services.roles import RoleService

NAMED = {("join", "ok"), ("enroll", "ok"), ("enroll", "pending")}


def reply_text(kind: str, result: str, lang: str, group: str | None, teacher: str | None) -> str:
    """Named text when the group or teacher is known, the short text otherwise."""
    if (kind, result) not in NAMED or not (group or teacher):
        return t(f"{kind}_{result}", lang)
    who = teacher or "—"
    if result == "pending":
        return t("enroll_pending_named", lang, group=group or "—", teacher=who)
    if group:
        return t("join_ok_named", lang, group=group, teacher=who)
    return t("join_ok_teacher", lang, teacher=who)


async def join_answer(
    kind: str,
    code: str,
    result: str,
    lang: str,
    user: User,
    is_admin: bool,
    enrollment: EnrollmentService,
    modes: RoleService | None,
    chats: ChatRepository | None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Bot text (HTML-escaped names) and the keyboard that fits this account now."""
    group, teacher = (None, None)
    if (kind, result) in NAMED:
        group, teacher = await enrollment.describe(kind, code)
    text = reply_text(
        kind,
        result,
        lang,
        escape(group) if group else None,
        escape(teacher) if teacher else None,
    )
    return text, await menu_for(lang, is_admin, user, modes, chats)
