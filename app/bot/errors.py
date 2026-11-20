"""Friendly fallback. Logs a traceback, never the message text or secrets."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent, Message, TelegramObject, Update

from app.config import Settings
from app.i18n import t

logger = logging.getLogger(__name__)


def install_errors(dispatcher: Dispatcher, settings: Settings | None = None) -> None:
    """Register the global error handler."""

    @dispatcher.error()
    async def on_error(event: ErrorEvent, bot: Bot) -> None:
        log_handler_error(event)
        if settings is not None:
            from app.bot.alerts import notify_admins

            await notify_admins(event, bot, settings)
        message = _message(event)
        if message is None:
            return
        try:
            await bot.send_message(message.chat.id, t("error_generic", "uz"))
        except TelegramAPIError:
            logger.info("could not send error notice")


def log_handler_error(event: ErrorEvent) -> None:
    """Log the exception with user/chat ids. Does not log message text."""
    user_id, chat_id = error_context(event.update)
    logger.error(
        "update failed error=%s user_id=%s chat_id=%s",
        type(event.exception).__name__,
        user_id,
        chat_id,
        exc_info=event.exception,
    )


def error_context(update: Update | TelegramObject | None) -> tuple[int | None, int | None]:
    """Best-effort user id and chat id from an update."""
    if update is None:
        return None, None
    message = getattr(update, "message", None) or getattr(update, "edited_message", None)
    if message is None:
        channel = getattr(update, "channel_post", None)
        if channel is not None:
            return None, getattr(getattr(channel, "chat", None), "id", None)
        callback = getattr(update, "callback_query", None)
        if callback is not None:
            user = getattr(callback, "from_user", None)
            msg = getattr(callback, "message", None)
            chat = getattr(msg, "chat", None) if msg is not None else None
            return getattr(user, "id", None), getattr(chat, "id", None)
        poll = getattr(update, "poll_answer", None)
        if poll is not None:
            user = getattr(poll, "user", None) or getattr(poll, "from_user", None)
            return getattr(user, "id", None), None
        member = getattr(update, "my_chat_member", None)
        if member is not None:
            user = getattr(member, "from_user", None)
            chat = getattr(member, "chat", None)
            return getattr(user, "id", None), getattr(chat, "id", None)
        return None, None
    user = getattr(message, "from_user", None)
    chat = getattr(message, "chat", None)
    return getattr(user, "id", None), getattr(chat, "id", None)


def _message(event: ErrorEvent) -> Message | None:
    update = event.update
    if update.message is not None:
        return update.message
    if update.callback_query is not None and isinstance(update.callback_query.message, Message):
        return update.callback_query.message
    return None
