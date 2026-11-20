"""Super-admin Mini App API (M3). Every handler re-checks SUPER_ADMIN_IDS on the server.

Payment decisions call PaymentService and pay_outcome, exactly like the bot buttons,
so the owner gets the same messages and the same immutable events are written.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from app.bot.pay_outcome import announce_approved, announce_fake, announce_rejected
from app.db.repositories.audit import AuditRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.services.admin import AdminError, AdminService
from app.services.admin_panel import AdminPanel
from app.services.charts import pick_days, platform_charts
from app.services.payments import PaymentError
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

logger = logging.getLogger(__name__)

ReceiptFetch = Callable[[str, str | None], Awaitable[tuple[bytes, str]]]
RECEIPT_TIMEOUT = 10.0
RECEIPT_CACHE = 24
RECEIPT_MAX_BYTES = 20 * 1024 * 1024


def setup_admin_routes(app: web.Application) -> None:
    r = app.router
    r.add_get("/api/admin/overview", overview)
    r.add_get("/api/admin/tenants", tenants)
    r.add_get("/api/admin/tenants/{user_id}", tenant)
    r.add_post("/api/admin/tenants/{user_id}/grant", grant)
    r.add_post("/api/admin/tenants/{user_id}/extend", extend)
    r.add_post("/api/admin/tenants/{user_id}/payments-block", payments_block)
    r.add_get("/api/admin/payments", payments)
    r.add_get("/api/admin/payments/{payment_id}", payment)
    r.add_get("/api/admin/payments/{payment_id}/receipt", receipt)
    r.add_post("/api/admin/payments/{payment_id}/approve", approve)
    r.add_post("/api/admin/payments/{payment_id}/reject", reject)
    r.add_post("/api/admin/payments/{payment_id}/fake", fake)
    r.add_get("/api/admin/chats", chats)
    r.add_get("/api/admin/audit", audit)
    r.add_get("/api/admin/charts", charts)
    app.setdefault("receipt_cache", OrderedDict())


async def _super(request: web.Request) -> WebContext | web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    if not ctx.is_super:
        return _error(403, "forbidden")
    return ctx


def _panel(ctx: WebContext) -> AdminPanel:
    return AdminPanel(ctx.session, founder_slots=ctx.settings.founder_slots)


def _admin_service(ctx: WebContext) -> AdminService:
    s = ctx.session
    return AdminService(
        ctx.users, ctx.plans, SubscriptionRepository(s), ChatRepository(s), AuditRepository(s)
    )


def _int(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info[key])
    except (KeyError, ValueError):
        return None


async def _body(request: web.Request) -> dict[str, Any] | None:
    try:
        raw = await request.json()
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


async def overview(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _panel(ctx).overview())


async def tenants(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    q = request.query.get("q", "")[:64]
    return web.json_response({"tenants": await _panel(ctx).tenants(q)})


async def tenant(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    user_id = _int(request, "user_id")
    data = await _tenant_payload(ctx, user_id) if user_id else None
    if data is None:
        return _error(404, "not_found")
    return web.json_response(data)


async def _tenant_payload(ctx: WebContext, user_id: int) -> dict[str, Any] | None:
    data = await _panel(ctx).tenant(user_id)
    if data is not None:
        data["plans"] = [{"code": p.code, "name": p.name} for p in await ctx.plans.list_active()]
    return data


async def grant(request: web.Request) -> web.Response:
    """Replace the plan for N days. Reason required; written to the audit log."""
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    target = await ctx.users.get_by_id(_int(request, "user_id") or 0)
    if body is None:
        return _error(400, "bad_request")
    if target is None:
        return _error(404, "not_found")
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return _error(400, "reason")
    try:
        days = int(body.get("days") or 0)
        await _admin_service(ctx).grant(
            ctx.user, target.telegram_id, str(body.get("plan") or ""), days, reason
        )
    except (AdminError, ValueError) as exc:
        return _error(400, getattr(exc, "code", "bad_days"))
    await ctx.session.commit()
    return web.json_response(await _tenant_payload(ctx, target.id))


async def extend(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    target = await ctx.users.get_by_id(_int(request, "user_id") or 0)
    if body is None:
        return _error(400, "bad_request")
    if target is None:
        return _error(404, "not_found")
    try:
        await _admin_service(ctx).extend(
            ctx.user, target.telegram_id, int(body.get("days") or 0), str(body.get("reason") or "")
        )
    except (AdminError, ValueError) as exc:
        return _error(400, getattr(exc, "code", "bad_days"))
    await ctx.session.commit()
    return web.json_response(await _tenant_payload(ctx, target.id))


async def payments_block(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    target = await ctx.users.get_by_id(_int(request, "user_id") or 0)
    if body is None:
        return _error(400, "bad_request")
    if target is None:
        return _error(404, "not_found")
    try:
        await ctx.payments.set_payments_blocked(
            ctx.user, target, bool(body.get("blocked")), str(body.get("reason") or "")
        )
    except PaymentError as exc:
        return _error(400, exc.code)
    await ctx.session.commit()
    return web.json_response(await _tenant_payload(ctx, target.id))


async def payments(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    status = request.query.get("status", "queue")[:16]
    return web.json_response({"payments": await _panel(ctx).payments(status), "status": status})


async def payment(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    payment_id = _int(request, "payment_id")
    data = await _panel(ctx).payment(payment_id) if payment_id else None
    if data is None:
        return _error(404, "not_found")
    return web.json_response(data)


async def receipt(request: web.Request) -> web.Response:
    """Stream the receipt through the bot. Never exposes the bot token or a Telegram URL."""
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    row = await ctx.payments.get(_int(request, "payment_id") or 0)
    if row is None or not row.receipt_file_id:
        return _error(404, "not_found")
    cache: OrderedDict = request.app["receipt_cache"]
    key = row.receipt_file_id
    hit = cache.get(key)
    if hit is None:
        fetch: ReceiptFetch | None = request.app.get("receipt_fetch") or _bot_fetch(
            request.app.get("bot")
        )
        if fetch is None:
            return _error(503, "unavailable")
        try:
            hit = await asyncio.wait_for(fetch(key, row.receipt_kind), timeout=RECEIPT_TIMEOUT)
        except TimeoutError:
            return _error(504, "timeout")
        except Exception:
            logger.info("receipt fetch failed payment_id=%s", row.id)
            return _error(502, "telegram")
        if len(hit[0]) > RECEIPT_MAX_BYTES:
            return _error(413, "too_large")
        cache[key] = hit
        while len(cache) > RECEIPT_CACHE:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    data, content_type = hit
    return web.Response(
        body=data,
        content_type=content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


def _bot_fetch(bot) -> ReceiptFetch | None:
    if bot is None:
        return None

    async def fetch(file_id: str, kind: str | None) -> tuple[bytes, str]:
        info = await bot.get_file(file_id)
        buffer = await bot.download_file(info.file_path)
        data = buffer.read() if hasattr(buffer, "read") else bytes(buffer or b"")
        guessed = mimetypes.guess_type(info.file_path or "")[0]
        allowed = guessed in ("image/jpeg", "image/png", "image/webp", "application/pdf")
        return data, guessed if allowed else "image/jpeg"

    return fetch


async def _decide(request: web.Request, work) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    payment_id = _int(request, "payment_id")
    body = await _body(request) if request.can_read_body else {}
    if payment_id is None or body is None:
        return _error(400, "bad_request")
    try:
        after = await work(ctx, payment_id, body)
    except PaymentError as exc:
        status = 404 if exc.code == "missing" else 409 if exc.code == "status" else 400
        return _error(status, exc.code)
    await ctx.session.commit()
    if after is not None:
        try:
            await after()
        except Exception:
            logger.info("payment notice failed payment_id=%s", payment_id)
    return web.json_response(await _panel(ctx).payment(payment_id))


async def approve(request: web.Request) -> web.Response:
    bot = request.app.get("bot")

    async def work(ctx: WebContext, payment_id: int, _body: dict):
        paid = await ctx.payments.approve(ctx.user, payment_id, via="webapp")
        owner = await ctx.users.get_by_id(paid.owner_id)
        plan = await ctx.payments.plan_of(paid)
        return lambda: announce_approved(bot, ctx.payments, paid, owner, plan)

    return await _decide(request, work)


async def reject(request: web.Request) -> web.Response:
    bot = request.app.get("bot")

    async def work(ctx: WebContext, payment_id: int, body: dict):
        row = await ctx.payments.reject(
            ctx.user, payment_id, str(body.get("reason") or ""), via="webapp"
        )
        owner = await ctx.users.get_by_id(row.owner_id)
        return lambda: announce_rejected(bot, row, owner)

    return await _decide(request, work)


async def fake(request: web.Request) -> web.Response:
    bot = request.app.get("bot")

    async def work(ctx: WebContext, payment_id: int, body: dict):
        marked = await ctx.payments.mark_fake(
            ctx.user, payment_id, str(body.get("note") or ""), via="webapp"
        )
        return lambda: announce_fake(bot, marked)

    return await _decide(request, work)


async def chats(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response({"chats": await _panel(ctx).chats(request.query.get("q", "")[:64])})


async def audit(request: web.Request) -> web.Response:
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        limit = max(1, min(200, int(request.query.get("limit", "100"))))
    except ValueError:
        limit = 100
    panel = _panel(ctx)
    return web.json_response(
        {"audit": await panel.audit(limit), "disputes": await panel.payments("disputes")}
    )


async def charts(request: web.Request) -> web.Response:
    """Platform charts: revenue, subscriptions, churn, founders, AI usage, failed jobs."""
    ctx = await _super(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(
        await platform_charts(
            ctx.session,
            days=pick_days(request.query.get("days"), default=30),
            founder_slots=ctx.settings.founder_slots,
        )
    )
