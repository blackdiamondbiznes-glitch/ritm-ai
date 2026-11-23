"""/panel: a teacher gets a one-time link to the web panel in this chat."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User
from app.i18n import t
from app.services import panel_login

router = Router(name="panel")


@router.message(Command("panel"))
async def panel_link(
    message: Message,
    lang: str,
    current_user: User,
    session: AsyncSession | None = None,
) -> None:
    """Teachers only. The link is a URL button, valid 15 minutes, usable once."""
    if session is None:
        return
    if not await panel_login.is_teacher(session, current_user):
        await message.answer(t("panel_not_teacher", lang))
        return
    from app.config import get_settings

    base = get_settings().public_webapp_url
    if not base:
        await message.answer(t("panel_unavailable", lang))
        return
    await panel_login.send_link(message.bot, session, current_user, base, lang)
