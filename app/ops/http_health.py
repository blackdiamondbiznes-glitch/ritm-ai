"""Tiny HTTP health endpoint used by Docker and Render probes."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.config import Settings
from app.services.health import HealthService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

Handler = Callable[[], Awaitable[tuple[int, str]]]


async def start_health_server(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> object | None:
    """Bind HEALTH_PORT. Returns the server, or None when the port is disabled."""
    if settings.health_port <= 0:
        return None
    try:
        from asyncio import start_server
    except ImportError:
        return None

    async def _handle(reader, writer) -> None:
        try:
            await reader.readline()
            status, body = await probe(settings, sessions)
            reason = "OK" if status == 200 else "Service Unavailable"
            payload = body.encode()
            header = (
                f"HTTP/1.1 {status} {reason}\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write(header.encode() + payload)
            await writer.drain()
        except Exception:
            logger.exception("health endpoint failed")
        finally:
            writer.close()
            await writer.wait_closed()

    server = await start_server(_handle, "0.0.0.0", settings.health_port)
    logger.info("health server port=%s", settings.health_port)
    return server


async def probe(settings: Settings, sessions: async_sessionmaker[AsyncSession]) -> tuple[int, str]:
    """200 when the database answers, otherwise 503. Never includes secrets."""
    try:
        async with sessions() as session:
            report = await HealthService(session, settings).report()
    except Exception:
        logger.exception("health probe failed")
        return 503, "unhealthy\n"
    if not report.db_ok:
        return 503, "unhealthy\n"
    return 200, "ok\n"
