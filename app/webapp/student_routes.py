"""Tutor students in the Mini App. Rows belong to the signed-in owner only."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.students import StudentError, StudentService
from app.services.tutor_limits import TutorLimitError, limit_body
from app.services.workspaces import WorkspaceService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "empty": 400,
    "long": 400,
    "note": 400,
    "phone": 400,
    "amount": 400,
    "choice": 400,
    "group": 400,
}


def setup_student_routes(app: web.Application) -> None:
    """Register the tutor student API."""
    app.router.add_get("/api/tutor/students", students_list)
    app.router.add_get("/api/tutor/students/{student_id}", students_profile)
    app.router.add_post("/api/tutor/students", students_create)
    app.router.add_patch("/api/tutor/students/{student_id}", students_update)
    app.router.add_delete("/api/tutor/students/{student_id}", students_delete)


async def students_list(request: web.Request) -> web.Response:
    """List the signed-in owner's students."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _service(ctx).list(ctx.user.id))


async def students_profile(request: web.Request) -> web.Response:
    """One student, with only that student's lessons and reminders."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    student_id = _student_id(request)
    if student_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.profile(ctx.user.id, student_id))


async def students_create(request: web.Request) -> web.Response:
    """Add a student and return the updated list."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.create(ctx.user.id, body))


async def students_update(request: web.Request) -> web.Response:
    """Edit one student owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    student_id = _student_id(request)
    if student_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.update(ctx.user.id, student_id, body))


async def students_delete(request: web.Request) -> web.Response:
    """Delete one student owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    student_id = _student_id(request)
    if student_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.remove(ctx.user.id, student_id))


def _service(ctx: WebContext) -> StudentService:
    return StudentService(
        StudentRepository(ctx.session),
        LessonRepository(ctx.session),
        ReminderRepository(ctx.session),
        GroupRepository(ctx.session),
        ctx.access,
        ctx.users,
        WorkspaceService(WorkspaceRepository(ctx.session), ctx.users),
    )


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_service(ctx))
    except TutorLimitError as exc:
        return web.json_response(limit_body(exc), status=403)
    except StudentError as exc:
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


def _student_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info["student_id"])
    except (KeyError, ValueError):
        return None
