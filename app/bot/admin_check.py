"""Whether a group message comes from a chat administrator."""

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from app.bot.members import user_is_manager

logger = logging.getLogger(__name__)

_TTL = 300.0


class AdminStatusCache:
    """Short-lived getChatMember results, keyed by chat and user."""

    def __init__(self, ttl_seconds: float = _TTL) -> None:
        self._ttl = ttl_seconds
        self._rows: dict[tuple[int, int], tuple[float, bool]] = {}

    def get(self, chat_id: int, user_id: int) -> bool | None:
        """Return a cached flag, or None on a miss or expiry."""
        row = self._rows.get((chat_id, user_id))
        if row is None:
            return None
        expires, value = row
        if expires < time.monotonic():
            self._rows.pop((chat_id, user_id), None)
            return None
        return value

    def put(self, chat_id: int, user_id: int, is_admin: bool) -> None:
        """Remember one membership check."""
        self._rows[(chat_id, user_id)] = (time.monotonic() + self._ttl, is_admin)


async def sender_is_admin(bot: Bot, cache: AdminStatusCache, message: Message) -> bool:
    """Channel posts are always from an admin. Groups use getChatMember with a cache.

    Anonymous-admin posts (`sender_chat` is this chat) are accepted without an API call.
    A failed Telegram lookup is treated as not-admin so the handler stays silent.
    """
    if message.chat.type == "channel":
        return True
    if message.sender_chat is not None and message.sender_chat.id == message.chat.id:
        return True
    user = message.from_user
    if user is None:
        return False
    cached = cache.get(message.chat.id, user.id)
    if cached is not None:
        return cached
    try:
        member = await bot.get_chat_member(message.chat.id, user.id)
    except TelegramAPIError:
        logger.info("admin lookup failed chat_id=%s user_id=%s", message.chat.id, user.id)
        return False
    ok = user_is_manager(member)
    cache.put(message.chat.id, user.id, ok)
    return ok
