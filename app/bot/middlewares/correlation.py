"""Tag log lines with the current update id."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.logging_setup import set_correlation


class CorrelationMiddleware(BaseMiddleware):
    """Set a short correlation id for the duration of one update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = data.get("event_update")
        update_id = getattr(update, "update_id", None)
        set_correlation(f"upd:{update_id}" if update_id is not None else "-")
        try:
            return await handler(event, data)
        finally:
            set_correlation("-")
