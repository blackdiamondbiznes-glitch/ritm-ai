"""The error handler must log a traceback and ids, never the message text."""

import logging

from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message, Update
from aiogram.types import User as TgUser
from app.bot.errors import error_context, log_handler_error


def _callback_update() -> Update:
    user = TgUser(id=5052443384, is_bot=False, first_name="Ada")
    chat = Chat(id=50, type="private")
    message = Message(message_id=3, date=0, chat=chat, text="secret body")
    callback = CallbackQuery(
        id="1", from_user=user, chat_instance="x", data="w:tzkeep:-", message=message
    )
    return Update(update_id=1, callback_query=callback)


def test_error_context_reads_callback_ids() -> None:
    user_id, chat_id = error_context(_callback_update())
    assert user_id == 5052443384
    assert chat_id == 50


def test_log_handler_error_includes_traceback_and_ids(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="app.bot.errors")
    try:
        raise TypeError("t() got multiple values for argument 'lang'")
    except TypeError as exc:
        event = ErrorEvent(update=_callback_update(), exception=exc)
        log_handler_error(event)
    text = caplog.text
    assert "TypeError" in text
    assert "user_id=5052443384" in text
    assert "chat_id=50" in text
    assert "Traceback" in text
    assert "secret body" not in text
