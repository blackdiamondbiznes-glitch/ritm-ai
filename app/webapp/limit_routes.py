"""Plan usage for the cabinet home."""

from __future__ import annotations

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.usage import UsageRepository
from app.services.tutor_usage import usage_snapshot
from app.webapp.routes import _context


def setup_limit_routes(app: web.Application) -> None:
    """Register the usage line."""
    app.router.add_get("/api/tutor/limits", limits)


async def limits(request: web.Request) -> web.Response:
    """How much of the plan this teacher has used."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    data = await usage_snapshot(
        ctx.access,
        GroupRepository(ctx.session),
        StudentRepository(ctx.session),
        UsageRepository(ctx.session),
        ctx.user,
    )
    return web.json_response(data)
