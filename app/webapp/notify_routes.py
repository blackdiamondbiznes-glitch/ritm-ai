"""Group reminder settings and the linked chat. Sending stays on the job tick."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.services.notify import NotifyError, notify_for
from app.webapp.routes import _context, _error

_STATUS = {"missing": 404, "chat": 400, "choice": 400, "target": 400, "empty": 400, "long": 400}


def setup_notify_routes(app: web.Application) -> None:
    """Register reminder rules and the chat link."""
    app.router.add_get("/api/tutor/groups/{group_id}/notify", notify_read)
    app.router.add_put("/api/tutor/groups/{group_id}/notify", notify_save)
    app.router.add_put("/api/tutor/groups/{group_id}/chat", notify_chat)


async def notify_read(request: web.Request) -> web.Response:
    """Rules and the owner's active chats."""
    return await _work(request, lambda svc, ctx, group_id, _body: svc.read(ctx.user.id, group_id))


async def notify_save(request: web.Request) -> web.Response:
    """Store lesson and fee reminder switches."""
    return await _work(
        request, lambda svc, ctx, group_id, body: svc.save_rules(ctx.user.id, group_id, body)
    )


async def notify_chat(request: web.Request) -> web.Response:
    """Link or clear the Telegram chat for this group."""
    return await _work(
        request, lambda svc, ctx, group_id, body: svc.link_chat(ctx.user.id, group_id, body)
    )


async def _work(request: web.Request, work) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request)
    if group_id is None:
        return _error(400, "bad_request")
    body: dict[str, Any] | None = None
    if request.method != "GET":
        parsed = await _body(request)
        if isinstance(parsed, web.Response):
            return parsed
        body = parsed
    try:
        data = await work(notify_for(ctx.session), ctx, group_id, body or {})
    except NotifyError as exc:
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


def _int(request: web.Request) -> int | None:
    try:
        return int(request.match_info["group_id"])
    except (KeyError, ValueError):
        return None


__all__ = ["setup_notify_routes"]
