"""Process entry. Builds the bot, dispatcher and the idle scheduler."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.commands import setup_commands
from app.bot.errors import install_errors
from app.bot.middlewares import install_middlewares
from app.bot.poster import RateLimitedSender
from app.bot.routers import setup_routers
from app.bot.telegram_mode import clear_webhook, start_webhook, webhook_routes
from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.jobs.tick import Tick, _touch_heartbeat, schedule_tick
from app.logging_setup import setup_logging
from app.ops.http_health import start_health_server
from app.services.pending import PendingChatStore
from app.webapp.server import set_webapp_menu_button, start_webapp

logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the bot in TELEGRAM_MODE. Schema changes happen in Alembic, not here."""
    settings = get_settings()
    setup_logging(settings.log_level)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = settings
    dispatcher["pending"] = PendingChatStore(ttl_hours=settings.pending_ttl_hours)
    install_middlewares(dispatcher, settings, session_factory)
    setup_routers(dispatcher)
    install_errors(dispatcher, settings)
    mode = settings.telegram_mode
    scheduler = AsyncIOScheduler()
    if mode != "off":
        # "off" is a staging mode: no posts, quizzes or reminders may go out from here.
        sender = RateLimitedSender(settings.send_gap_seconds)
        schedule_tick(
            scheduler,
            Tick(session_factory, bot, settings, sender),
            settings.job_tick_seconds,
        )
        scheduler.start()
    _touch_heartbeat(settings.health_file)
    health = await start_health_server(settings, session_factory)
    webapp = None
    try:
        me = await bot.get_me()
        dispatcher["bot_id"] = me.id
        webapp = await start_webapp(
            settings,
            session_factory,
            bot,
            me.username,
            pending=dispatcher["pending"],
            configure=webhook_routes(dispatcher, bot, settings) if mode == "webhook" else None,
        )
        logger.info("bot started id=%s mode=%s", me.id, mode)
        allowed = dispatcher.resolve_used_update_types()
        if mode == "off":
            logger.warning("TELEGRAM_MODE=off: no updates, no scheduled jobs; Mini App only")
            await asyncio.Event().wait()
            return
        await setup_commands(bot)
        await set_webapp_menu_button(bot, settings)
        if mode == "webhook":
            if webapp is None:
                raise RuntimeError("TELEGRAM_MODE=webhook needs PORT or WEBAPP_PORT > 0")
            await start_webhook(bot, settings, allowed)
            await asyncio.Event().wait()
            return
        await clear_webhook(bot)
        await dispatcher.start_polling(bot, allowed_updates=allowed)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if health is not None:
            health.close()
            await health.wait_closed()
        if webapp is not None:
            await webapp.cleanup()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
