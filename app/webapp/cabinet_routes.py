"""Cabinet home numbers. The signed-in owner sees only their own rows."""

from __future__ import annotations

import json

from aiohttp import web

from app.db.repositories.lessons import LessonRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.cabinet import CabinetService
from app.services.workspaces import WorkspaceService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error


def setup_cabinet_routes(app: web.Application) -> None:
    """Register the cabinet summary and the tutor switch."""
    app.router.add_get("/api/tutor/summary", cabinet_summary)
    app.router.add_post("/api/tutor/enable", cabinet_enable)
    app.router.add_post("/api/tutor/name", teacher_name)


NAME_MAX = 80


def _names(user) -> dict:
    return {"teacher_name": user.teacher_name or "", "telegram_name": user.full_name or ""}


async def teacher_name(request: web.Request) -> web.Response:
    """Set the name students see. An empty value goes back to the Telegram name."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "bad_request")
    raw = body.get("name") if isinstance(body, dict) else None
    if raw is not None and not isinstance(raw, str):
        return _error(400, "bad_request")
    name = " ".join((raw or "").split())
    if len(name) > NAME_MAX:
        return _error(400, "name_too_long")
    ctx.user.teacher_name = name or None
    await ctx.session.flush()
    return web.json_response(_names(ctx.user))


async def cabinet_enable(request: web.Request) -> web.Response:
    """Turn the tutor cabinet on for the signed-in owner. Safe to call again."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    space = await WorkspaceService(WorkspaceRepository(ctx.session), ctx.users).ensure(ctx.user)
    await ctx.session.flush()
    data = await _service(ctx).summary(ctx.user.id)
    data.update(_names(ctx.user))
    data["cabinet_niche"] = "tutor"
    data["workspace_id"] = space.id
    return web.json_response(data)


async def cabinet_summary(request: web.Request) -> web.Response:
    """Counts for the cabinet home."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    data = await _service(ctx).summary(ctx.user.id)
    data.update(_names(ctx.user))
    return web.json_response(data)


def _service(ctx: WebContext) -> CabinetService:
    return CabinetService(StudentRepository(ctx.session), LessonRepository(ctx.session))
