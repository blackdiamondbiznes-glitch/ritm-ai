"""Dated sessions in the Mini App. A wrong id is 404."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.services.notify import notify_for
from app.services.session_view import SessionView
from app.services.sessions import SessionError
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "empty": 400,
    "long": 400,
    "note": 400,
    "choice": 400,
    "when": 400,
    "time": 400,
    "span": 400,
    "range": 400,
    "slot": 400,
}


def setup_session_routes(app: web.Application) -> None:
    """Register the timetable API."""
    app.router.add_get("/api/tutor/sessions", sessions_list)
    app.router.add_post("/api/tutor/groups/{group_id}/sessions", sessions_add)
    app.router.add_patch("/api/tutor/sessions/{session_id}", sessions_update)
    app.router.add_get("/api/me/sessions", sessions_mine)


async def sessions_list(request: web.Request) -> web.Response:
    """The signed-in owner's lessons and group sessions in a date window."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return await _call(
        ctx,
        lambda svc: svc.between(ctx.user.id, request.query.get("from"), request.query.get("to")),
    )


async def sessions_add(request: web.Request) -> web.Response:
    """Add one extra session on a group the owner teaches."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    if group_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.add_extra(ctx.user.id, group_id, body))


async def sessions_update(request: web.Request) -> web.Response:
    """Cancel, finish, rename, or move one owned session."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    session_id = _int(request, "session_id")
    if session_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.update(ctx.user.id, session_id, body))


async def sessions_mine(request: web.Request) -> web.Response:
    """Upcoming sessions for groups this account studies in."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    raw = request.query.get("days", "14")
    if not raw.isdigit():
        return _error(400, "range")
    return await _call(ctx, lambda svc: svc.for_student(ctx.user, int(raw)))


def _view(ctx: WebContext) -> SessionView:
    return SessionView(
        LessonRepository(ctx.session),
        GroupRepository(ctx.session),
        notifier=notify_for(ctx.session),
    )


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_view(ctx))
    except SessionError as exc:
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


def _int(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info[key])
    except (KeyError, ValueError):
        return None
