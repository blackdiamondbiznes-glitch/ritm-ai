"""Shared chat-card render used by several routers."""

from aiogram.types import CallbackQuery

from app.bot.copy import chat_card_text
from app.bot.keyboards.chats import chat_card
from app.bot.view import show_screen
from app.db.models.chats import Chat
from app.db.models.users import User
from app.services.access import AccessService
from app.services.leaderboard import MODULE as LEADERBOARD
from app.services.profiles import ProfileService
from app.services.quiz_mode import ADMIN_POST_QUIZ


async def render_card(
    callback: CallbackQuery,
    chat: Chat,
    user: User,
    access: AccessService,
    profiles: ProfileService,
    lang: str,
    *,
    note: str | None = None,
    new: bool = False,
) -> None:
    """Show the chat card. `new=True` posts it at the bottom of the chat."""
    snap = await access.snapshot(user)
    profile = await profiles.get(chat.id)
    text = chat_card_text(chat, snap, profile, lang, note=note)
    allowed = await access.is_module_allowed(chat, ADMIN_POST_QUIZ)
    enabled = bool(profile and ADMIN_POST_QUIZ in (profile.modules_enabled or []))
    rating = await access.is_module_allowed(chat, LEADERBOARD)
    await show_screen(
        callback,
        text,
        chat_card(
            lang,
            chat.id,
            admin_quiz=enabled if allowed else None,
            leaderboard=rating,
        ),
        new=new,
    )
