"""Per-user rate limit. Default: one update per 0.5 seconds."""

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, TelegramObject


class ThrottleMiddleware(BaseMiddleware):
    """Drop updates that arrive too quickly from the same Telegram user."""

    def __init__(self, seconds: float) -> None:
        self._seconds = seconds
        self._seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        now = time.monotonic()
        previous = self._seen.get(user.id)
        if previous is not None and now - previous < self._seconds:
            await _silence(event)
            return None
        self._seen[user.id] = now
        if len(self._seen) > 5000:
            cutoff = now - 60
            self._seen = {key: stamp for key, stamp in self._seen.items() if stamp >= cutoff}
        return await handler(event, data)


async def _silence(event: TelegramObject) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except TelegramAPIError:
            return
