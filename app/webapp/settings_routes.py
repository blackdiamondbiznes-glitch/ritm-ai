"""Settings that used to live only in the bot chat: chat profile, disconnect, connect,
the weekly board "post now", and per-user preferences. Validation stays in the services."""

from __future__ import annotations

import re
from typing import Any

from aiohttp import web

from app.db.repositories.payments import PaymentRepository
from app.i18n import t
from app.services.user_prefs import PrefsError, default_zone, prefs_payload, update_prefs
from app.webapp.context import WebContext
from app.webapp.panel import PanelError
from app.webapp.routes import _context, _error, _run

# Rights requested in the "add to group/channel" links (the bot must post and manage its posts).
GROUP_RIGHTS = "delete_messages+pin_messages+invite_users"
CHANNEL_RIGHTS = "post_messages+edit_messages+delete_messages"
_CONNECT_ERRORS = {"not_admin", "bot_rights", "limit", "owned", "gone"}


def setup_settings_routes(app: web.Application) -> None:
    app.router.add_get("/api/chats/{chat_id}/profile", chat_profile)
    app.router.add_put("/api/chats/{chat_id}/profile", chat_profile_save)
    app.router.add_post("/api/chats/{chat_id}/disconnect", chat_disconnect)
    app.router.add_post("/api/chats/{chat_id}/board-now", board_now)
    app.router.add_get("/api/me/settings", my_settings)
    app.router.add_patch("/api/me/settings", my_settings_save)
    app.router.add_get("/api/me/payments", my_payments)
    app.router.add_get("/api/connect", connect_info)
    app.router.add_post("/api/connect", connect_confirm)
    app.router.add_post("/api/connect/decline", connect_decline)
    app.router.add_get("/api/docs/terms", terms_doc)


async def chat_profile(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, _body: dict[str, Any]) -> Any:
        zone = default_zone(ctx.user, ctx.settings.default_timezone)
        return await ctx.panel.profile_form(ctx.user, chat_id, _lang(ctx), zone)

    return await _run(request, _do)


async def chat_profile_save(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, body: dict[str, Any]) -> Any:
        await ctx.panel.save_profile(ctx.user, chat_id, body)
        zone = default_zone(ctx.user, ctx.settings.default_timezone)
        return await ctx.panel.profile_form(ctx.user, chat_id, _lang(ctx), zone)

    return await _run(request, _do, read_body=True)


async def chat_disconnect(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, _body: dict[str, Any]) -> Any:
        await ctx.panel.disconnect(ctx.user, chat_id, ctx.lifecycle)
        return {"ok": True}

    return await _run(request, _do)


async def board_now(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, _body: dict[str, Any]) -> Any:
        return {"result": await ctx.panel.board_now(ctx.user, chat_id)}

    return await _run(request, _do)


async def my_settings(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(_settings_body(ctx))


async def my_settings_save(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _json(request)
    if body is None:
        return _error(400, "bad_request")
    try:
        update_prefs(ctx.user, body)
    except PrefsError as exc:
        return _error(400, exc.code)
    return web.json_response(_settings_body(ctx))


async def my_payments(request: web.Request) -> web.Response:
    """The caller's own payment requests only (never anyone else's)."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    rows = await PaymentRepository(ctx.session).list_for_owner(ctx.user.id, limit=50)
    names: dict[int, str] = {}
    out = []
    for row in rows:
        if row.plan_id not in names:
            plan = await ctx.plans.get_by_id(row.plan_id)
            names[row.plan_id] = plan.name if plan is not None else "—"
        out.append(
            {
                "id": row.id,
                "ref": row.ref_code,
                "plan": names[row.plan_id],
                "months": row.requested_period_months,
                "amount_uzs": row.amount_uzs,
                "status": row.status,
                "reason": row.reject_reason if row.status in ("rejected", "disputed") else None,
                "created_at": _iso(row.created_at),
                "submitted_at": _iso(row.submitted_at),
                "reviewed_at": _iso(row.reviewed_at),
            }
        )
    return web.json_response({"payments": out})


async def connect_info(request: web.Request) -> web.Response:
    """How to add the bot, plus chats this user just added and has not confirmed yet."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    name = request.app.get("bot_username")
    pending = request.app.get("pending")
    rows = pending.list_for(ctx.user.telegram_id) if pending is not None else []
    snap = await ctx.access.snapshot(ctx.user)
    links = None
    if name:
        links = {
            "group": f"https://t.me/{name}?startgroup=connect&admin={GROUP_RIGHTS}",
            "channel": f"https://t.me/{name}?startchannel=connect&admin={CHANNEL_RIGHTS}",
            "bot": f"https://t.me/{name}",
        }
    return web.json_response(
        {
            "links": links,
            "pending": [
                {
                    "telegram_chat_id": row.telegram_chat_id,
                    "title": row.title,
                    "type": row.chat_type,
                }
                for row in rows
            ],
            "chats_used": snap.chats_used,
            "chats_limit": snap.plan.max_chats,
            "can_confirm": pending is not None and request.app.get("bot") is not None,
        }
    )


async def connect_confirm(request: web.Request) -> web.Response:
    """Same checks as the bot's confirm button: the adder must match, rights are re-read live."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _json(request)
    target = _chat_key(body)
    if target is None:
        return _error(400, "bad_request")
    pending = request.app.get("pending")
    bot = request.app.get("bot")
    if pending is None or bot is None:
        return _error(503, "unavailable")
    item = pending.get(target)
    if item is None or item.added_by_telegram_id != ctx.user.telegram_id:
        return _error(404, "gone")
    from app.bot.connect_flow import link_chat

    outcome = await link_chat(bot, bot.id, item.telegram_chat_id, ctx.user, ctx.lifecycle)
    if not outcome.ok or outcome.chat_id is None:
        code = outcome.code if outcome.code in _CONNECT_ERRORS else "failed"
        return web.json_response(
            {"error": code, "used": outcome.used, "max": outcome.limit}, status=409
        )
    pending.pop(item.telegram_chat_id)
    return web.json_response(
        {
            "chat_id": outcome.chat_id,
            "already": outcome.code == "already",
            "trial_started": bool(outcome.trial_started),
            "trial_days": ctx.settings.trial_days,
        }
    )


async def connect_decline(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    target = _chat_key(await _json(request))
    pending = request.app.get("pending")
    if target is None or pending is None:
        return _error(400, "bad_request")
    item = pending.get(target)
    if item is not None and item.added_by_telegram_id == ctx.user.telegram_id:
        pending.pop(target)
    return web.json_response({"ok": True})


async def terms_doc(request: web.Request) -> web.Response:
    """The payment offer the user accepts in the bot, as plain text (same source and version)."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    settings = ctx.settings
    raw = t(
        "pay_terms",
        _lang(ctx),
        version=settings.payment_terms_version,
        hours=settings.payment_review_hours,
    )
    text = re.sub(r"<[^>]+>", "", raw)
    parts = text.split("\n\n")
    if len(parts) > 2:
        parts = parts[:-1]  # drop the "accept to continue" prompt; acceptance happens in the bot
    return web.json_response(
        {"version": settings.payment_terms_version, "text": "\n\n".join(parts).strip()}
    )


def _settings_body(ctx: WebContext) -> dict[str, Any]:
    data = prefs_payload(ctx.user, ctx.settings.default_timezone)
    data["support"] = ctx.settings.support_handle or None
    return data


def _lang(ctx: WebContext) -> str:
    return ctx.user.language_code or "uz"


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


async def _json(request: web.Request) -> dict[str, Any] | None:
    try:
        raw = await request.json()
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _chat_key(body: dict[str, Any] | None) -> int | None:
    if not body:
        return None
    value = body.get("telegram_chat_id")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


__all__ = ["PanelError", "setup_settings_routes"]
