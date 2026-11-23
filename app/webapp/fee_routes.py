"""Course fees in the Mini App. A wrong id is 404. Free plans cannot record money."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.bot.widgets.dispatch import edit_card
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.db.repositories.students import StudentRepository
from app.services.fee_pay import FeePay
from app.services.fees import FeeError, FeeService
from app.services.tutor_limits import TutorLimitError, limit_body
from app.services.widget_cards import fee_data
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "mode": 400,
    "amount": 400,
    "day": 400,
    "package": 400,
    "due": 400,
    "method": 400,
    "date": 400,
    "note": 400,
    "status": 400,
}


def setup_fee_routes(app: web.Application) -> None:
    """Register course-fee routes. These are not the Ritm subscription payments."""
    app.router.add_put("/api/tutor/groups/{group_id}/fee", group_fee)
    app.router.add_put("/api/tutor/groups/{group_id}/members/{student_id}/fee", member_fee)
    app.router.add_get("/api/tutor/invoices", invoices)
    app.router.add_post("/api/tutor/invoices/{invoice_id}/payments", pay)
    app.router.add_delete("/api/tutor/payments/{payment_id}", remove_payment)
    app.router.add_post("/api/tutor/invoices/{invoice_id}/waive", waive)
    app.router.add_get("/api/tutor/fees/summary", summary)
    app.router.add_get("/api/me/fees", mine)


async def group_fee(request: web.Request) -> web.Response:
    """Set how this group is priced. Past invoices keep their amount."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    body = await _body(request)
    if group_id is None or isinstance(body, web.Response):
        return body if isinstance(body, web.Response) else _error(400, "bad_request")
    return await _call(
        request, ctx, lambda svc: svc.set_group_fee(ctx.user.id, group_id, body), pay=False
    )


async def member_fee(request: web.Request) -> web.Response:
    """Set or clear one student's price for future invoices."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id, student_id = _int(request, "group_id"), _int(request, "student_id")
    body = await _body(request)
    if group_id is None or student_id is None or isinstance(body, web.Response):
        return body if isinstance(body, web.Response) else _error(400, "bad_request")
    return await _call(
        request,
        ctx,
        lambda svc: svc.set_override(ctx.user.id, group_id, student_id, body),
        pay=False,
    )


async def invoices(request: web.Request) -> web.Response:
    """List this owner's invoices."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    status = request.query.get("status") or None
    raw = request.query.get("group_id")
    group_id = int(raw) if raw and raw.isdigit() else None
    if raw and group_id is None:
        return _error(400, "bad_request")
    return await _call(
        request, ctx, lambda svc: svc.invoices(ctx.user.id, status, group_id), pay=True
    )


async def pay(request: web.Request) -> web.Response:
    """Record a payment. Free plans get 403."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    invoice_id = _int(request, "invoice_id")
    body = await _body(request)
    if invoice_id is None or isinstance(body, web.Response):
        return body if isinstance(body, web.Response) else _error(400, "bad_request")
    return await _call(request, ctx, lambda svc: svc.pay(ctx.user.id, invoice_id, body), pay=True)


async def remove_payment(request: web.Request) -> web.Response:
    """Remove a recorded payment and restore the invoice."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    payment_id = _int(request, "payment_id")
    if payment_id is None:
        return _error(400, "bad_request")
    return await _call(request, ctx, lambda svc: svc.remove(ctx.user.id, payment_id), pay=True)


async def waive(request: web.Request) -> web.Response:
    """Waive one invoice. Free plans get 403."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    invoice_id = _int(request, "invoice_id")
    if invoice_id is None:
        return _error(400, "bad_request")
    return await _call(request, ctx, lambda svc: svc.waive(ctx.user.id, invoice_id), pay=True)


async def summary(request: web.Request) -> web.Response:
    """Collected this month, outstanding, and how many invoices are overdue."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return await _call(request, ctx, lambda svc: svc.summary(ctx.user.id), pay=True)


async def mine(request: web.Request) -> web.Response:
    """The signed-in student's bills."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return await _call(request, ctx, lambda svc: svc.mine(ctx.user), pay=True)


def _fees(ctx: WebContext) -> FeeService:
    return FeeService(
        InvoiceRepository(ctx.session),
        GroupRepository(ctx.session),
        ctx.users,
        ctx.access,
    )


def _pay(ctx: WebContext) -> FeePay:
    service = FeePay(InvoiceRepository(ctx.session), _fees(ctx), ctx.access)
    service.use_students(StudentRepository(ctx.session))
    return service


async def _call(request: web.Request, ctx: WebContext, work, *, pay: bool) -> web.Response:
    try:
        data = await work(_pay(ctx) if pay else _fees(ctx))
    except TutorLimitError as exc:
        return web.json_response(limit_body(exc), status=403)
    except FeeError as exc:
        return _error(_STATUS.get(exc.code, 400), exc.code)
    if pay and isinstance(data, dict) and data.get("id"):
        await _push_fee(request, ctx, data)
    return web.json_response(data)


async def _push_fee(request: web.Request, ctx: WebContext, invoice: dict) -> None:
    bot = request.app.get("bot")
    if bot is None:
        return
    try:
        await edit_card(
            bot,
            ctx.session,
            "fee",
            int(invoice["id"]),
            fee_data(ctx.user.language_code or "uz", invoice.get("group_name") or "", invoice),
        )
    except Exception:
        return


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
