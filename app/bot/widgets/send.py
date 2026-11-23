"""Send a widget, or the caption as a normal message if the API refuses it."""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, Message

from app.bot.widgets.pack import load

logger = logging.getLogger(__name__)


def dumps(data: dict) -> str:
    """Compact JSON for chat_data. Telegram counts UTF-8 bytes, max 1024."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def clip_data(data: dict) -> str:
    """Drop optional fields until the payload fits in 1024 bytes."""
    payload = dumps(data)
    if len(payload.encode("utf-8")) <= 1024:
        return payload
    trimmed = dict(data)
    for key in ("hw", "groups", "w", "exp"):
        if key in trimmed:
            if key == "groups" and isinstance(trimmed[key], list):
                trimmed[key] = trimmed[key][:3]
            elif isinstance(trimmed[key], str):
                trimmed[key] = trimmed[key][:80]
            payload = dumps(trimmed)
            if len(payload.encode("utf-8")) <= 1024:
                return payload
    raw = dumps(trimmed).encode("utf-8")
    return raw[:1024].decode("utf-8", errors="ignore")


async def send_card(
    bot: Bot,
    *,
    chat_id: int,
    kind: str,
    data: dict,
    caption: str,
    markup: InlineKeyboardMarkup | None = None,
    allow_queries: bool = False,
    enabled: bool = True,
) -> Message | None:
    """Try sendWidget; on any API or size problem, send the caption instead."""
    payload = clip_data(data)
    if enabled and hasattr(bot, "send_widget"):
        try:
            return await bot.send_widget(
                chat_id=chat_id,
                html=load(kind),
                chat_data=payload,
                caption=caption[:1024],
                allow_queries=allow_queries,
                reply_markup=markup,
            )
        except (TelegramAPIError, OSError, ValueError):
            logger.exception("send_widget failed kind=%s chat_id=%s", kind, chat_id)
    try:
        return await bot.send_message(chat_id, caption, reply_markup=markup)
    except TelegramAPIError:
        raise
