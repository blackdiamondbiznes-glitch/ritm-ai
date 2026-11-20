"""How the process receives Telegram updates: long polling, webhook or not at all."""

from __future__ import annotations

import logging
from collections.abc import Callable

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from app.config import Settings

logger = logging.getLogger(__name__)


def webhook_routes(
    dispatcher: Dispatcher, bot: Bot, settings: Settings
) -> Callable[[web.Application], None]:
    """Route that feeds Telegram's POSTs to the dispatcher.

    Telegram must send the matching X-Telegram-Bot-Api-Secret-Token header; anything else is 401.
    Updates are handled in the background so slow AI calls never make Telegram retry.
    """

    def configure(app: web.Application) -> None:
        handler = SimpleRequestHandler(
            dispatcher=dispatcher,
            bot=bot,
            secret_token=settings.webhook_token,
            handle_in_background=True,
        )
        handler.register(app, path=settings.webhook_path)

    return configure


async def start_webhook(bot: Bot, settings: Settings, allowed: list[str]) -> None:
    """Point Telegram at this deployment. Pending updates are kept, not dropped."""
    url = settings.webhook_url
    if not url:
        raise RuntimeError(
            "TELEGRAM_MODE=webhook needs an https WEBHOOK_BASE_URL, WEBAPP_URL"
            " or RENDER_EXTERNAL_URL"
        )
    await bot.set_webhook(
        url=url,
        secret_token=settings.webhook_token,
        allowed_updates=allowed,
        drop_pending_updates=False,
    )
    logger.info("telegram webhook set path=%s/…", settings.webhook_path[:4])


async def clear_webhook(bot: Bot) -> None:
    """Polling and a webhook cannot coexist; remove a webhook left by another deployment."""
    await bot.delete_webhook(drop_pending_updates=False)
