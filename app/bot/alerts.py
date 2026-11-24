"""Rate-limited error notices for super admins. Never include secrets or text."""

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from app.bot.errors import error_context
from app.config import Settings

logger = logging.getLogger(__name__)
_last_sent_at: float | None = None


async def notify_admins(event: ErrorEvent, bot: Bot, settings: Settings) -> None:
    """Send a short alert when the cooldown has elapsed."""
    global _last_sent_at
    ids = settings.admin_ids
    if not ids:
        return
    now = time.monotonic()
    if _last_sent_at is not None and now - _last_sent_at < max(
        0, settings.alert_cooldown_seconds
    ):
        return
    _last_sent_at = now
    user_id, chat_id = error_context(event.update)
    update_id = getattr(event.update, "update_id", None)
    text = (
        "Ritm AI xatosi\n"
        f"error={type(event.exception).__name__}\n"
        f"update_id={update_id}\n"
        f"user_id={user_id}\n"
        f"chat_id={chat_id}"
    )
    for telegram_id in ids:
        try:
            await bot.send_message(telegram_id, text)
        except TelegramAPIError:
            logger.info("alert not delivered telegram_id=%s", telegram_id)


def reset_alert_clock() -> None:
    """Test helper: forget the last send time."""
    global _last_sent_at
    _last_sent_at = None
