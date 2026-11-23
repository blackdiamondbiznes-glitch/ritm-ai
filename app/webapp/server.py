"""aiohttp server for the Mini App API and static frontend."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import MenuButtonDefault, MenuButtonWebApp, WebAppInfo
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.i18n import t
from app.webapp.admin_routes import setup_admin_routes
from app.webapp.admins import ChatAdminCache
from app.webapp.assets import setup_assets
from app.webapp.attendance_routes import setup_attendance_routes
from app.webapp.cabinet_routes import setup_cabinet_routes
from app.webapp.chart_routes import setup_chart_routes
from app.webapp.dash_routes import setup_dash_routes
from app.webapp.export_routes import setup_export_routes
from app.webapp.fee_routes import setup_fee_routes
from app.webapp.grade_routes import setup_grade_routes
from app.webapp.group_routes import setup_group_routes
from app.webapp.join_routes import setup_join_routes
from app.webapp.learning_routes import setup_learning_routes
from app.webapp.lesson_routes import setup_lesson_routes
from app.webapp.limit_routes import setup_limit_routes
from app.webapp.members import MemberCountCache
from app.webapp.notify_routes import setup_notify_routes
from app.webapp.pay_routes import setup_pay_routes
from app.webapp.rate_limit import RateLimiter
from app.webapp.reminder_routes import setup_reminder_routes
from app.webapp.report_routes import setup_report_routes
from app.webapp.request_routes import setup_request_routes
from app.webapp.role_routes import setup_role_routes
from app.webapp.routes import setup_routes
from app.webapp.session_routes import setup_session_routes
from app.webapp.settings_routes import setup_settings_routes
from app.webapp.student_routes import setup_student_routes

logger = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent / "static"


def create_app(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    limiter: RateLimiter | None = None,
    bot: Bot | None = None,
    members: MemberCountCache | None = None,
    admins: ChatAdminCache | None = None,
    bot_username: str | None = None,
    pending: object | None = None,
) -> web.Application:
    """Build the Mini App application. Static files are served from the same origin."""
    app = web.Application(middlewares=[session_cleanup])
    app["settings"] = settings
    app["sessions"] = sessions
    app["limiter"] = limiter or RateLimiter()
    app["bot"] = bot
    app["members"] = members or MemberCountCache(bot)
    app["admins"] = admins or ChatAdminCache(bot)
    app["bot_username"] = bot_username
    app["pending"] = pending
    setup_routes(app)
    setup_dash_routes(app)
    setup_admin_routes(app)
    setup_chart_routes(app)
    setup_settings_routes(app)
    setup_pay_routes(app)
    setup_student_routes(app)
    setup_group_routes(app)
    setup_request_routes(app)
    setup_grade_routes(app)
    setup_lesson_routes(app)
    setup_learning_routes(app)
    setup_join_routes(app)
    setup_session_routes(app)
    setup_attendance_routes(app)
    setup_fee_routes(app)
    setup_limit_routes(app)
    setup_report_routes(app)
    setup_export_routes(app)
    setup_notify_routes(app)
    setup_cabinet_routes(app)
    setup_reminder_routes(app)
    setup_role_routes(app)
    app.router.add_get("/health", health)
    app.router.add_get("/healthz", health)
    setup_assets(app, STATIC)
    return app


async def health(request: web.Request) -> web.Response:
    """Render health check on the public port: 200 when the database answers."""
    from app.ops.http_health import probe

    status, body = await probe(request.app["settings"], request.app["sessions"])
    return web.Response(status=status, text=body, headers={"Cache-Control": "no-store"})


@web.middleware
async def session_cleanup(request: web.Request, handler):
    """Commit on success, roll back and close the request session."""
    try:
        response = await handler(request)
    except Exception:
        session = request.get("db_session")
        if session is not None:
            await session.rollback()
            await session.close()
        raise
    if (
        request.path.startswith("/api/")
        and isinstance(response, web.Response)
        and response.body is not None
        and len(response.body) > 1024
        and "gzip" in request.headers.get("Accept-Encoding", "")
    ):
        response.enable_compression()
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    session = request.get("db_session")
    if session is not None:
        try:
            if 200 <= response.status < 400:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
    return response


async def start_webapp(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    bot: Bot | None = None,
    bot_username: str | None = None,
    pending: object | None = None,
    configure: Callable[[web.Application], None] | None = None,
) -> web.AppRunner | None:
    """Bind PORT (Render) or WEBAPP_PORT. Returns the runner, or None when disabled.

    ``configure`` may add routes (the Telegram webhook) before the server starts.
    """
    port = settings.http_port
    if port <= 0:
        return None
    app = create_app(settings, sessions, bot=bot, bot_username=bot_username, pending=pending)
    if configure is not None:
        configure(app)
    # No access log: the webhook path carries the secret token.
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("webapp server port=%s", port)
    return runner


async def set_webapp_menu_button(bot: Bot, settings: Settings) -> None:
    """Point the Telegram chat menu at the Mini App when HTTPS is configured."""
    url = settings.public_webapp_url
    try:
        if url:
            button = MenuButtonWebApp(
                text=t("menu_webapp_short", "uz"),
                web_app=WebAppInfo(url=url),
            )
            await bot.set_chat_menu_button(menu_button=button)
            logger.info("webapp menu button set")
            return
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except TelegramAPIError:
        logger.info("webapp menu button not set")
