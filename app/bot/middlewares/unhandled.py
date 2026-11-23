"""Log updates that no handler took, so a silent bot is visible in the logs."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class UnhandledLogMiddleware(BaseMiddleware):
    """Outer update middleware. Logs ids and the update type, never message text."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            result = await handler(event, data)
        except Exception:
            logger.exception("update crashed id=%s", getattr(event, "update_id", None))
            raise
        if result is UNHANDLED and isinstance(event, Update):
            logger.info("update not handled id=%s type=%s", event.update_id, event.event_type)
        return result
