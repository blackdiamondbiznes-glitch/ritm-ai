"""Email sign-up and sign-in for EduFlow accounts."""

from __future__ import annotations

import json

from aiohttp import ContentTypeError, web
from sqlalchemy.exc import IntegrityError

from app.db.repositories.users import UserRepository
from app.services.clock import utcnow
from app.webapp.context import build_context
from app.webapp.email_auth import (
    EmailAccountError,
    hash_password,
    normalize_email,
    validate_signup,
    verify_password,
)
from app.webapp.rate_limit import RateLimiter
from app.webapp.routes import _context, _error, _session_body, sign_in

AUTH_LIMIT = 10
AUTH_WINDOW_SECONDS = 300


def setup_account_routes(app: web.Application) -> None:
    """Register email-account endpoints."""
    app.router.add_post("/api/eduflow/telegram-login", eduflow_telegram_login)
    app.router.add_post("/api/email/signup", signup)
    app.router.add_post("/api/email/login", login)
    app.router.add_post("/api/email/link", link_email)


async def eduflow_telegram_login(request: web.Request) -> web.Response:
    """Authenticate an EduFlow Mini App using its dedicated Telegram bot token."""
    bot_token = request.app["settings"].eduflow_bot_token.strip()
    if not bot_token:
        return _error(503, "eduflow_auth_unavailable")
    return await sign_in(request, initdata_bot_token=bot_token, eduflow_login=True)


async def signup(request: web.Request) -> web.Response:
    """Create a teacher, student, or community-owner account."""
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    try:
        email = normalize_email(body.get("email"))
        name, password, role = validate_signup(
            body.get("name"), body.get("password"), body.get("role")
        )
    except EmailAccountError as exc:
        return _error(400, exc.code)
    if not _allow(request):
        return _error(429, "rate_limit")

    settings = request.app["settings"]
    async with request.app["sessions"]() as session:
        try:
            users = UserRepository(session)
            if await users.get_by_email(email) is not None:
                return _error(409, "email_exists")
            user = await users.create_email_account(email, hash_password(password), name, role)
            if user.is_blocked:
                return _error(403, "blocked")
            context = build_context(session, settings, user, request.app.get("admins"))
            response = await _session_body(user, settings, context, request.app.get("bot_username"))
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return _error(409, "email_exists")
    return web.json_response(response, status=201)


async def login(request: web.Request) -> web.Response:
    """Verify an email/password pair without exposing account existence."""
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    try:
        email = normalize_email(body.get("email"))
    except EmailAccountError:
        return _error(401, "invalid_credentials")
    password = body.get("password")
    if not isinstance(password, str) or not 1 <= len(password) <= 256:
        return _error(401, "invalid_credentials")
    if not _allow(request):
        return _error(429, "rate_limit")

    settings = request.app["settings"]
    async with request.app["sessions"]() as session:
        users = UserRepository(session)
        user = await users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            return _error(401, "invalid_credentials")
        if user.is_blocked:
            return _error(403, "blocked")
        user.last_seen_at = utcnow()
        telegram_id = user.telegram_id
        is_eduflow_session = telegram_id is not None
        is_eduflow_owner = (
            telegram_id is not None and telegram_id in settings.eduflow_owner_ids
        )
        context = build_context(
            session,
            settings,
            user,
            request.app.get("admins"),
            is_super_override=is_eduflow_owner,
            is_eduflow_session=is_eduflow_session,
        )
        response = await _session_body(user, settings, context, request.app.get("bot_username"))
        await session.commit()
    return web.json_response(response)


async def link_email(request: web.Request) -> web.Response:
    """Attach email login to the currently authenticated Telegram account."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    if ctx.user.telegram_id is None or ctx.user.email is not None:
        return _error(409, "account_already_linked")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    try:
        email = normalize_email(body.get("email"))
        _name, password, role = validate_signup(
            ctx.user.full_name or "Telegram foydalanuvchisi",
            body.get("password"),
            body.get("role"),
        )
    except EmailAccountError as exc:
        return _error(400, exc.code)
    if not _allow(request):
        return _error(429, "rate_limit")
    existing = await ctx.users.get_by_email(email)
    if existing is not None and existing.id != ctx.user.id:
        return _error(409, "email_exists")
    ctx.user.email = email
    ctx.user.password_hash = hash_password(password)
    ctx.user.account_role = role
    return web.json_response(
        await _session_body(ctx.user, ctx.settings, ctx, request.app.get("bot_username"))
    )


async def _body(request: web.Request) -> dict | web.Response:
    try:
        value = await request.json()
    except (ContentTypeError, json.JSONDecodeError, web.HTTPBadRequest):
        return _error(400, "bad_request")
    if not isinstance(value, dict):
        return _error(400, "bad_request")
    return value


def _allow(request: web.Request) -> bool:
    limiter = request.app.get("email_auth_limiter")
    if limiter is None:
        limiter = RateLimiter(limit=AUTH_LIMIT, window=AUTH_WINDOW_SECONDS)
        request.app["email_auth_limiter"] = limiter
    return limiter.allow(f"email-auth:{request.remote or 'unknown'}")
