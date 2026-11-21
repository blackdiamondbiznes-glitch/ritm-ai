"""Tutor reminders in the Mini App. Rows belong to the signed-in owner only."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.repositories.reminders import ReminderRepository
from app.db.repositories.students import StudentRepository
from app.services.reminders import ReminderError, ReminderService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {"missing": 404, "empty": 400, "long": 400, "when": 400, "student": 400}


def setup_reminder_routes(app: web.Application) -> None:
    """Register the tutor reminder API."""
    app.router.add_get("/api/tutor/reminders", reminders_list)
    app.router.add_post("/api/tutor/reminders", reminders_create)
    app.router.add_delete("/api/tutor/reminders/{reminder_id}", reminders_delete)


async def reminders_list(request: web.Request) -> web.Response:
    """List the signed-in owner's reminders."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _service(ctx).list(ctx.user.id))


async def reminders_create(request: web.Request) -> web.Response:
    """Add a reminder and return the updated list."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.create(ctx.user.id, body))


async def reminders_delete(request: web.Request) -> web.Response:
    """Delete one reminder owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        reminder_id = int(request.match_info["reminder_id"])
    except (KeyError, ValueError):
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.remove(ctx.user.id, reminder_id))


def _service(ctx: WebContext) -> ReminderService:
    return ReminderService(ReminderRepository(ctx.session), StudentRepository(ctx.session))


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_service(ctx))
    except ReminderError as exc:
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
