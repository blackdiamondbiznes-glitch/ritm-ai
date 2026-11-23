"""Cabinet home numbers. The signed-in owner sees only their own rows."""

from __future__ import annotations

from aiohttp import web

from app.db.repositories.lessons import LessonRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.cabinet import CabinetService
from app.services.workspaces import WorkspaceService
from app.webapp.context import WebContext
from app.webapp.routes import _context


def setup_cabinet_routes(app: web.Application) -> None:
    """Register the cabinet summary and the tutor switch."""
    app.router.add_get("/api/tutor/summary", cabinet_summary)
    app.router.add_post("/api/tutor/enable", cabinet_enable)


async def cabinet_enable(request: web.Request) -> web.Response:
    """Turn the tutor cabinet on for the signed-in owner. Safe to call again."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    space = await WorkspaceService(WorkspaceRepository(ctx.session), ctx.users).ensure(ctx.user)
    await ctx.session.flush()
    data = await _service(ctx).summary(ctx.user.id)
    data["cabinet_niche"] = "tutor"
    data["workspace_id"] = space.id
    return web.json_response(data)


async def cabinet_summary(request: web.Request) -> web.Response:
    """Counts for the cabinet home."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    data = await _service(ctx).summary(ctx.user.id)
    return web.json_response(data)


def _service(ctx: WebContext) -> CabinetService:
    return CabinetService(StudentRepository(ctx.session), LessonRepository(ctx.session))
