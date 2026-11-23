"""Middleware chain: throttle, session, user, services."""

from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.admin_check import AdminStatusCache
from app.bot.middlewares.correlation import CorrelationMiddleware
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.services import ServicesMiddleware
from app.bot.middlewares.throttle import ThrottleMiddleware
from app.bot.middlewares.unhandled import UnhandledLogMiddleware
from app.bot.middlewares.user import UserMiddleware
from app.config import Settings


def install_middlewares(
    dispatcher: Dispatcher,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Attach the chain to every update type that handlers consume."""
    dispatcher["admin_cache"] = AdminStatusCache()
    correlation = CorrelationMiddleware()
    database = DbSessionMiddleware(session_factory)
    users = UserMiddleware(settings)
    services = ServicesMiddleware(settings)
    for observer in (
        dispatcher.message,
        dispatcher.callback_query,
        dispatcher.my_chat_member,
        dispatcher.widget_query,
    ):
        observer.middleware(correlation)
        observer.middleware(database)
        observer.middleware(users)
        observer.middleware(services)
    # Throttle is an OUTER middleware: it runs once per update. As an inner middleware it ran
    # again for every handler that raised SkipHandler (quiz_link -> join), so `/start join_…`
    # was silently dropped as "too fast". my_chat_member (sent together with the first /start)
    # is never throttled, and each observer keeps its own clock.
    dispatcher.message.outer_middleware(ThrottleMiddleware(settings.throttle_seconds))
    dispatcher.callback_query.outer_middleware(ThrottleMiddleware(settings.throttle_seconds))
    dispatcher.widget_query.outer_middleware(ThrottleMiddleware(settings.throttle_seconds))
    dispatcher.update.outer_middleware(UnhandledLogMiddleware())
    # Poll votes are not throttled: a member may answer right after opening the quiz.
    # PollAnswer carries `.user`, not `.from_user`.
    dispatcher.poll_answer.middleware(correlation)
    dispatcher.poll_answer.middleware(database)
    dispatcher.poll_answer.middleware(users)
    dispatcher.poll_answer.middleware(services)
    # Channel posts have no from_user. Do not throttle them or invent a user.
    dispatcher.channel_post.middleware(correlation)
    dispatcher.channel_post.middleware(database)
    dispatcher.channel_post.middleware(users)
    dispatcher.channel_post.middleware(services)
