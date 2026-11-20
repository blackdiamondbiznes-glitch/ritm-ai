"""Load the current user and stop blocked accounts."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser

from app.config import Settings
from app.db.repositories.users import UserRepository
from app.i18n import t


def event_user(event: TelegramObject) -> TgUser | None:
    """Return the Telegram user on the update.

    Messages and callbacks expose `.from_user`. PollAnswer exposes `.user`.
    """
    found = getattr(event, "from_user", None) or getattr(event, "user", None)
    return found if isinstance(found, TgUser) else None


class UserMiddleware(BaseMiddleware):
    """Get-or-create the user, refresh last_seen, attach language."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = event_user(event)
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        repo = UserRepository(data["session"])
        user = await repo.upsert_seen(
            tg_user.id,
            tg_user.username,
            tg_user.full_name,
            tg_user.language_code,
        )
        data["current_user"] = user
        data["lang"] = user.language_code or "uz"
        data["is_super_admin"] = user.telegram_id in self._settings.admin_ids
        if user.is_blocked:
            await _tell_blocked(event, data.get("bot"), user.language_code)
            return None
        return await handler(event, data)


async def _tell_blocked(event: TelegramObject, bot: object, lang: str) -> None:
    text = t("blocked", lang)
    try:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
            return
        if isinstance(event, Message):
            await event.answer(text)
            return
        user = event_user(event)
        if user is not None and bot is not None:
            await bot.send_message(user.id, text)  # type: ignore[attr-defined]
    except TelegramAPIError:
        return
