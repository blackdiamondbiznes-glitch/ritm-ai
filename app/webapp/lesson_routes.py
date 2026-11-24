"""Tutor lessons in the Mini App. Rows belong to the signed-in owner only."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.lessons import LessonError, LessonService
from app.services.workspaces import WorkspaceService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "link": 400,
    "missing": 404,
    "empty": 400,
    "long": 400,
    "note": 400,
    "amount": 400,
    "choice": 400,
    "when": 400,
    "student": 404,
}


def setup_lesson_routes(app: web.Application) -> None:
    """Register the tutor lesson API."""
    app.router.add_get("/api/tutor/lessons", lessons_list)
    app.router.add_post("/api/tutor/lessons", lessons_create)
    app.router.add_patch("/api/tutor/lessons/{lesson_id}", lessons_update)
    app.router.add_delete("/api/tutor/lessons/{lesson_id}", lessons_delete)


async def lessons_list(request: web.Request) -> web.Response:
    """List the signed-in owner's lessons."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _service(ctx).list(ctx.user.id))


async def lessons_create(request: web.Request) -> web.Response:
    """Add a lesson and return the updated list."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.create(ctx.user.id, body))


async def lessons_update(request: web.Request) -> web.Response:
    """Edit one lesson owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    lesson_id = _lesson_id(request)
    if lesson_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.update(ctx.user.id, lesson_id, body))


async def lessons_delete(request: web.Request) -> web.Response:
    """Delete one lesson owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    lesson_id = _lesson_id(request)
    if lesson_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.remove(ctx.user.id, lesson_id))


def _service(ctx: WebContext) -> LessonService:
    return LessonService(
        LessonRepository(ctx.session),
        StudentRepository(ctx.session),
        WorkspaceService(WorkspaceRepository(ctx.session), ctx.users),
        GroupRepository(ctx.session),
    )


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_service(ctx))
    except LessonError as exc:
        return _error(_STATUS.get(exc.code, 400), exc.code)
    return web.json_response(data)


async def _body(request: web.Request) -> dict[str, Any] | web.Response:
    try:
        raw = await request.json()
    except Exception:
        return _error(400, "bad_request")
    if not isinstance(raw, dict):
        return _error(400, "bad_request")
    return raw


def _lesson_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info["lesson_id"])
    except (KeyError, ValueError):
        return None
