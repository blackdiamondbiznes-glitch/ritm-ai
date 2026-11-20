"""Reusable ownership check. Super admins may manage any chat."""

from app.db.models.chats import Chat
from app.db.models.users import User


def manages(chat: Chat, user: User, is_super: bool) -> bool:
    """True when the user owns the chat or is a platform admin."""
    return is_super or chat.owner_id == user.id
