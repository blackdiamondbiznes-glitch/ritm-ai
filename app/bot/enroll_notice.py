"""Messages sent when a student asks to join a group."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from app.db.models.users import User
from app.i18n import t

logger = logging.getLogger(__name__)


async def tell(bot: Bot | None, chat_id: int | None, text: str) -> None:
    """Send a private notice. A blocked chat is ignored."""
    if bot is None or chat_id is None:
        return
    try:
        await bot.send_message(chat_id, text)
    except TelegramForbiddenError:
        logger.info("enroll notice skipped chat_id=%s", chat_id)


def ask_text(lang: str, name: str, group: str) -> str:
    """Teacher alert. Names are escaped because the bot parses HTML."""
    return t("enroll_ask", lang, name=escape(name), group=escape(group))


def decision_text(lang: str, key: str, group: str) -> str:
    """Student alert after the teacher decides."""
    return t(key, lang, group=escape(group))


def teacher_notifier(bot: Bot):
    """Callback EnrollmentService calls after a new request is stored."""

    async def notify(owner: User, name: str, group_name: str) -> None:
        await tell(bot, owner.telegram_id, ask_text(owner.language_code or "uz", name, group_name))

    return notify
