"""In-app payment for the Mini App, on the same PaymentService the bot uses.

GET  /api/pay/options   plans x periods priced by PaymentService.quote, cards, open request
POST /api/pay/start     accept the offer, issue the reference code and exact amount (draft)
POST /api/pay/submit    multipart: payment_id, last4, when, receipt -> admin queue
POST /api/pay/cancel    drop the draft or the unreviewed request

Payments belong to the owner (the signed-in user), never to one chat: the bot works the
same way, and an approved plan covers all of the owner's chats.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web
from sqlalchemy import inspect

from app.bot.pay_notify import notify_payment_submitted
from app.i18n import t
from app.services.clock import TASHKENT
from app.services.payment_cards import configured_cards
from app.services.payments import (
    TRANSFER_FUTURE_SLACK,
    TRANSFER_MAX_AGE,
    PaymentError,
)
from app.services.pricing import PERIODS, is_paid_plan, period_percent
from app.webapp.context import WebContext
from app.webapp.rate_limit import RateLimiter
from app.webapp.receipts import ReceiptError, check_upload, read_part, store_receipt
from app.webapp.routes import _context, _error, _plan_payload

logger = logging.getLogger(__name__)
SUBMIT_LIMIT = 6  # receipt uploads per user per 10 minutes
_STATUS = {"duplicate": 409, "status": 409, "expired": 409, "busy": 409, "blocked": 403}
_FIELDS = {"payment_id", "last4", "when"}


def setup_pay_routes(app: web.Application) -> None:
    app["pay_limiter"] = RateLimiter(limit=SUBMIT_LIMIT, window=600)
    app.router.add_get("/api/pay/options", pay_options)
    app.router.add_post("/api/pay/start", pay_start)
    app.router.add_post("/api/pay/submit", pay_submit)
    app.router.add_post("/api/pay/cancel", pay_cancel)


async def pay_options(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await options_body(ctx))


async def pay_start(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        body = await request.json()
    except Exception:
        return _error(400, "bad_request")
    if not isinstance(body, dict):
        return _error(400, "bad_request")
    if not configured_cards(ctx.settings):
        return _error(503, "unconfigured")
    months = body.get("months")
    if not isinstance(months, int) or isinstance(months, bool):
        return _error(400, "months")
    # The offer is accepted by ticking the box; the version must be the one we showed.
    accepted = body.get("accept") is True
    version = str(body.get("terms_version") or "") if accepted else ""
    try:
        await ctx.payments.start(
            ctx.user, str(body.get("plan") or ""), months, terms_version=version or None
        )
    except PaymentError as exc:
        return _payment_error(exc)
    return web.json_response(await options_body(ctx))


async def pay_submit(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    if not request.app["pay_limiter"].allow(f"pay:{ctx.user.telegram_id}"):
        return _error(429, "rate_limit")
    if not request.content_type.startswith("multipart/"):
        return _error(400, "bad_request")
    try:
        fields, data = await _read_form(request)
        upload = check_upload(data)
    except ReceiptError as exc:
        return _error(exc.status, exc.code)
    except ValueError:
        return _error(400, "bad_request")
    draft = await ctx.payments.draft_of(ctx.user)
    pid = fields.get("payment_id", "")
    problem = _precheck(ctx, draft, pid, fields)
    if problem is not None:
        return problem
    lang = ctx.user.language_code or "uz"
    caption = t("pay_receipt_app", lang, ref=draft.ref_code or f"#{draft.id}")
    try:
        receipt = await store_receipt(request.app.get("bot"), ctx.user.telegram_id, upload, caption)
    except ReceiptError as exc:
        return _error(exc.status, exc.code)
    try:
        result = await ctx.payments.submit(
            ctx.user,
            draft.id,
            receipt=receipt,
            card_last4=fields.get("last4", ""),
            transfer_at=parse_when(fields.get("when", ""), ctx.payments.now()),
            via="webapp",
        )
    except PaymentError as exc:
        return _payment_error(exc)
    plan = await ctx.plans.get_by_id(result.payment.plan_id)
    founder = await ctx.access.offers_founder_price(ctx.user)
    # Commit first so an admin tapping "approve" right away finds the pending row.
    await ctx.session.commit()
    bot = request.app.get("bot")
    if bot is not None:
        await notify_payment_submitted(
            bot,
            ctx.settings,
            result.payment,
            ctx.user,
            plan,
            founder=founder,
            duplicates=result.duplicates,
        )
    body = await options_body(ctx)
    body["submitted"] = {"ref": result.payment.ref_code, "amount_uzs": result.payment.amount_uzs}
    return web.json_response(body)


async def pay_cancel(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    await ctx.payments.cancel_pending(ctx.user)
    return web.json_response(await options_body(ctx))


async def options_body(ctx: WebContext) -> dict[str, Any]:
    """Everything the Tarifim screen needs, priced by the same code as the bot."""
    settings = ctx.settings
    plans: list[dict[str, Any]] = []
    for plan in await ctx.plans.list_active():
        if not is_paid_plan(plan):
            continue
        periods = []
        for months in PERIODS:
            quote = await ctx.payments.quote(ctx.user, plan.code, months)
            periods.append(
                {
                    "months": months,
                    "percent": quote.period_percent,
                    "amount": quote.amount,
                    "list_total": quote.list_total,
                    "regular_total": int(plan.price_uzs) * months,
                    "savings": quote.savings,
                    "per_month": quote.monthly_equivalent,
                }
            )
        plans.append(
            {
                "code": plan.code,
                "name": plan.name,
                "price": int(plan.price_uzs),
                "monthly": periods[0]["amount"],
                "founder": quote.founder,
                "max_chats": plan.max_chats,
                "ai_limit": plan.ai_generations_per_month,
                "periods": periods,
            }
        )
    body = await _plan_payload(ctx.access, ctx.payments, ctx.user, settings)
    body["plans"] = plans
    body["discounts"] = {str(m): period_percent(m, settings.period_discount_map) for m in PERIODS}
    body["terms_version"] = settings.payment_terms_version
    body["review_hours"] = settings.payment_review_hours
    body["invoice"] = await _invoice(ctx)
    return body


async def _invoice(ctx: WebContext) -> dict[str, Any] | None:
    draft = await ctx.payments.draft_of(ctx.user)
    if draft is None:
        return None
    if "created_at" in inspect(draft).unloaded:
        await ctx.session.refresh(draft, ["created_at"])  # server default after a fresh insert
    plan = await ctx.payments.plan_of(draft)
    expires = draft.created_at + timedelta(hours=max(1, ctx.settings.payment_draft_ttl_hours))
    return {
        "id": draft.id,
        "ref": draft.ref_code,
        "amount_uzs": draft.amount_uzs,
        "base_amount_uzs": draft.base_amount_uzs or draft.amount_uzs,
        "plan": plan.code if plan else None,
        "plan_name": plan.name if plan else "",
        "months": draft.requested_period_months,
        "expires_at": expires.isoformat() if draft.created_at else None,
    }


def parse_when(raw: str, now: datetime) -> datetime | None:
    """`now`, or the Mini App's datetime-local value (YYYY-MM-DDTHH:MM) in Tashkent time."""
    text = (raw or "").strip()
    if text == "now":
        return now
    try:
        local = datetime.strptime(text[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return local.replace(tzinfo=TASHKENT).astimezone(now.tzinfo or TASHKENT)


def _precheck(ctx: WebContext, draft, pid: str, fields: dict[str, str]) -> web.Response | None:
    """Refuse before uploading anything to Telegram, using the service's own rules."""
    if ctx.user.payments_blocked:
        return _error(403, "blocked")
    if draft is None or not pid.isdigit() or draft.id != int(pid):
        return _error(409, "expired")
    if not re.fullmatch(r"\d{4}", fields.get("last4", "").strip()):
        return _error(400, "last4")
    now = ctx.payments.now()
    when = parse_when(fields.get("when", ""), now)
    if when is None or not (now - TRANSFER_MAX_AGE <= when <= now + TRANSFER_FUTURE_SLACK):
        return _error(400, "when")
    return None


async def _read_form(request: web.Request) -> tuple[dict[str, str], bytes]:
    reader = await request.multipart()
    fields: dict[str, str] = {}
    data = b""
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "receipt":
            data = await read_part(part)
        elif part.name in _FIELDS:
            fields[part.name] = (await read_part(part, 256)).decode("utf-8", "replace")
        else:
            await read_part(part, 1024)
    return fields, data


def _payment_error(exc: PaymentError) -> web.Response:
    return _error(_STATUS.get(exc.code, 400), exc.code)
