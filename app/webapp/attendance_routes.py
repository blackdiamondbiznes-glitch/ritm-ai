"""Attendance in the Mini App. A wrong id is 404."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.db.repositories.lessons import LessonRepository
from app.services.attendance import AttendanceError, AttendanceService
from app.services.fee_usage import PackageUsage
from app.services.fees import FeeService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "student": 400,
    "future": 400,
    "choice": 400,
    "note": 400,
    "marks": 400,
    "month": 400,
    "group": 400,
}


def setup_attendance_routes(app: web.Application) -> None:
    """Register the attendance API."""
    app.router.add_get("/api/tutor/sessions/{session_id}/attendance", sheet)
    app.router.add_put("/api/tutor/sessions/{session_id}/attendance", save)
    app.router.add_get("/api/tutor/groups/{group_id}/attendance", month)
    app.router.add_get("/api/me/attendance", mine)


async def sheet(request: web.Request) -> web.Response:
    """Active members of one owned session and their marks."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    session_id = _int(request, "session_id")
    if session_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.sheet(ctx.user.id, session_id))


async def save(request: web.Request) -> web.Response:
    """Upsert or clear marks on one owned session."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    session_id = _int(request, "session_id")
    if session_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.save(ctx.user.id, session_id, body))


async def month(request: web.Request) -> web.Response:
    """One group's attendance matrix for a Tashkent month."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    if group_id is None:
        return _error(400, "bad_request")
    return await _call(
        ctx, lambda svc: svc.group_stats(ctx.user.id, group_id, request.query.get("month", ""))
    )


async def mine(request: web.Request) -> web.Response:
    """The signed-in student's own marks in one group."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    raw = request.query.get("group_id", "")
    if not raw.isdigit():
        return _error(400, "group")
    return await _call(ctx, lambda svc: svc.student_history(ctx.user, int(raw)))


def _service(ctx: WebContext) -> AttendanceService:
    session = ctx.session
    invoices = InvoiceRepository(session)
    groups = GroupRepository(session)
    fees = FeeService(invoices, groups, ctx.users, ctx.access)
    return AttendanceService(
        AttendanceRepository(session),
        LessonRepository(session),
        groups,
        fees=PackageUsage(invoices, groups, fees),
    )


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_service(ctx))
    except AttendanceError as exc:
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
