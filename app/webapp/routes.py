"""JSON API for the owner Mini App."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.models.users import User
from app.db.repositories.users import UserRepository
from app.services.access import AccessService
from app.services.payment_cards import configured_cards
from app.services.payments import PaymentService
from app.webapp.auth import (
    AuthError,
    issue_session,
    read_session,
    session_secret,
    telegram_user_id,
    validate_init_data,
)
from app.webapp.context import WebContext, build_context
from app.webapp.panel import PanelError

AUTH_LIMIT = 20
API_LIMIT = 60


def setup_routes(app: web.Application) -> None:
    """Register API routes on the Mini App application."""
    app.router.add_post("/api/auth", auth)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/chats", chats)
    app.router.add_get("/api/chats/{chat_id}", chat_detail)
    app.router.add_patch("/api/chats/{chat_id}", chat_update)
    app.router.add_post("/api/chats/{chat_id}/post-now", post_now)
    app.router.add_post("/api/chats/{chat_id}/quiz-now", quiz_now)
    app.router.add_get("/api/plan", plan_status)


async def auth(request: web.Request) -> web.Response:
    """Validate Telegram initData and issue a short-lived session token."""
    return await sign_in(request)


async def sign_in(request: web.Request, extra=None) -> web.Response:
    """Shared by /api/auth and /api/bootstrap. `extra(ctx)` adds fields in the same session."""
    if not _rate(request, "auth", AUTH_LIMIT):
        return _error(429, "rate_limit")
    try:
        payload = await request.json()
    except Exception:
        return _error(400, "bad_request")
    init_data = str(payload.get("initData") or payload.get("init_data") or "")
    settings = request.app["settings"]
    try:
        fields = validate_init_data(
            init_data, settings.bot_token, max_age=settings.webapp_auth_max_age
        )
        telegram_id = telegram_user_id(fields)
    except AuthError as exc:
        return _error(401, exc.code)
    user_info = fields.get("user") if isinstance(fields.get("user"), dict) else {}
    async with request.app["sessions"]() as session:
        repo = UserRepository(session)
        user = await repo.upsert_seen(
            telegram_id,
            _opt(user_info.get("username")),
            _full_name(user_info),
            _opt(user_info.get("language_code")),
        )
        if user.is_blocked:
            await session.commit()
            return _error(403, "blocked")
        ctx = build_context(session, settings, user, request.app.get("admins"))
        body = await _session_body(user, settings, ctx, request.app.get("bot_username"))
        if extra is not None:
            body.update(await extra(ctx))
        await session.commit()
    photo = photo_url(user_info)
    if photo:
        body["user"]["photo_url"] = photo
    return web.json_response(body)


async def me(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(
        await _session_body(ctx.user, ctx.settings, ctx, request.app.get("bot_username"))
    )


async def chats(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    managed = await ctx.panel.managed(ctx.user)
    from app.webapp.dash_routes import enrich_chats

    rows = [chat for chat, _role in managed]
    totals = await ctx.engagement.totals_by_chat([row.id for row in rows])
    roles = {chat.id: role for chat, role in managed}
    return web.json_response({"chats": await enrich_chats(request, rows, totals, roles)})


async def chat_detail(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, _body: dict[str, Any]) -> Any:
        from app.webapp.dash_routes import attach_members

        return await attach_members(request, await ctx.panel.detail(ctx.user, chat_id))

    return await _run(request, _do)


async def chat_update(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, body: dict[str, Any]) -> Any:
        from app.webapp.dash_routes import attach_members

        return await attach_members(request, await ctx.panel.update(ctx.user, chat_id, body))

    return await _run(request, _do, read_body=True)


async def post_now(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, _body: dict[str, Any]) -> Any:
        return {"result": await ctx.panel.post_now(ctx.user, chat_id)}

    return await _run(request, _do)


async def quiz_now(request: web.Request) -> web.Response:
    async def _do(ctx: WebContext, chat_id: int, _body: dict[str, Any]) -> Any:
        return {"result": await ctx.panel.quiz_now(ctx.user, chat_id)}

    return await _run(request, _do)


async def plan_status(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _plan_payload(ctx.access, ctx.payments, ctx.user, ctx.settings))


async def _run(request: web.Request, work, *, read_body: bool = False) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        chat_id = int(request.match_info["chat_id"])
    except (KeyError, ValueError):
        return _error(400, "bad_request")
    body: dict[str, Any] = {}
    if read_body:
        try:
            raw = await request.json()
        except Exception:
            return _error(400, "bad_request")
        if not isinstance(raw, dict):
            return _error(400, "bad_request")
        body = raw
    try:
        data = await work(ctx, chat_id, body)
    except PanelError as exc:
        return _error(exc.status, exc.code)
    return web.json_response(data)


async def _context(request: web.Request) -> WebContext | web.Response:
    settings = request.app["settings"]
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else ""
    try:
        telegram_id = read_session(token, secret)
    except AuthError as exc:
        # Unauthenticated traffic is limited per address; behind a tunnel this is shared.
        if not _rate(request, "api", API_LIMIT):
            return _error(429, "rate_limit")
        return _error(401, exc.code)
    # Signed sessions are limited per Telegram user, so one tunnel IP is not one bucket.
    if not request.app["limiter"].allow(f"api:user:{telegram_id}"):
        return _error(429, "rate_limit")
    factory = request.app["sessions"]
    session = factory()
    try:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is None:
            await session.close()
            return _error(401, "unauthorized")
        if user.is_blocked:
            await session.close()
            return _error(403, "blocked")
        request["db_session"] = session
        return build_context(session, settings, user, request.app.get("admins"))
    except Exception:
        await session.close()
        raise


def _rate(request: web.Request, kind: str, limit: int) -> bool:
    limiter = request.app["limiter"]
    ip = request.remote or "unknown"
    if not limiter.allow(f"{kind}:ip:{ip}"):
        return False
    return True


async def _session_body(
    user: User, settings, ctx: WebContext, bot_username: str | None = None
) -> dict:
    secret = session_secret(settings.bot_token, settings.webapp_session_secret)
    from app.webapp.member_view import resolve_roles

    roles = await resolve_roles(ctx)
    token = issue_session(user.telegram_id, secret, settings.webapp_session_ttl)
    return {
        "token": token,
        "user": {
            "telegram_id": user.telegram_id,
            "name": user.full_name,
            "username": user.username,
            "language": user.language_code or "uz",
            "cabinet_niche": user.cabinet_niche,
        },
        "student": await _student_account(ctx),
        "roles": roles,
        "bot_username": bot_username,
        "support": settings.support_handle or None,
        "expires_in": settings.webapp_session_ttl,
    }


async def _student_account(ctx: WebContext) -> dict:
    """The signed-in Telegram account, if a tutor registered them as a student."""
    from app.db.repositories.students import StudentRepository

    rows = await StudentRepository(ctx.session).by_telegram(ctx.user.telegram_id)
    return {"linked": bool(rows), "names": [row.name for row in rows]}


async def _plan_payload(
    access: AccessService, payments: PaymentService, user: User, settings=None
) -> dict:
    snap = await access.snapshot(user)
    pending = await payments.pending_of(user.id) or await payments.draft_of(user)
    offer = await access.founder_offer(user)
    data: dict[str, Any] = {
        "plan": snap.plan.code,
        "plan_name": snap.plan.name,
        "kind": snap.kind,
        "days_left": snap.days_left,
        "chats_used": snap.chats_used,
        "chats_limit": snap.plan.max_chats,
        "ai_used": snap.ai_used,
        "ai_limit": snap.plan.ai_generations_per_month,
        "ai_left": max(0, snap.plan.ai_generations_per_month - snap.ai_used),
        "founder": offer.show_sale,
        "founder_keep": offer.keep,
        "founder_remaining": offer.remaining,
        "founder_slots": offer.slots,
        "pending": None,
    }
    if pending is not None:
        data["pending"] = {
            "id": pending.id,
            "plan_id": pending.plan_id,
            "months": pending.requested_period_months,
            "amount_uzs": pending.amount_uzs,
            "status": pending.status,
            "has_receipt": bool(pending.receipt_file_id),
            "ref": pending.ref_code,
        }
    data["payments_blocked"] = bool(user.payments_blocked)
    data["cards"] = []
    if settings is not None:
        data["cards"] = [
            {"type": card.kind, "number": card.grouped_number, "holder": card.holder}
            for card in configured_cards(settings)
        ]
    return data


def _error(status: int, code: str) -> web.Response:
    return web.json_response({"error": code}, status=status)


def _opt(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _full_name(user: dict) -> str | None:
    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()
    name = " ".join(part for part in (first, last) if part)
    return name or None


def photo_url(user: dict) -> str | None:
    """Telegram's signed avatar URL from initData, only when it is plain https."""
    raw = user.get("photo_url") if isinstance(user, dict) else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text.startswith("https://") or len(text) > 512 or any(c in text for c in "\"'<> "):
        return None
    return text
