"""A student types the code or pastes the link a teacher sent, inside the Mini App."""

from __future__ import annotations

import json
import logging
import re

from aiohttp import web

from app.bot.enroll_notice import teacher_notifier
from app.i18n import t
from app.webapp.request_routes import _service
from app.webapp.routes import _context, _error

logger = logging.getLogger(__name__)
_TOKEN = re.compile(r"(join|enroll)_([A-Za-z0-9]{6,16})")
_BARE = re.compile(r"^[A-Za-z0-9]{6,16}$")
OK = frozenset({"ok", "pending"})


def setup_join_routes(app: web.Application) -> None:
    """Register the code box used by students without a teacher yet."""
    app.router.add_post("/api/me/join", join)


def parse_code(text: str) -> tuple[str | None, str | None]:
    """("join"|"enroll"|None, code). A bare code has no kind: both are tried."""
    raw = (text or "").strip()
    found = _TOKEN.search(raw)
    if found:
        return found.group(1), found.group(2)
    if _BARE.match(raw):
        return None, raw
    return None, None


async def join(request: web.Request) -> web.Response:
    """Claim a personal link or ask to join a group. Always returns a readable answer."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error(400, "bad_request")
    text = body.get("code") if isinstance(body, dict) else None
    kind, code = parse_code(text if isinstance(text, str) else "")
    user = ctx.user
    lang = user.language_code or "uz"
    service = _service(ctx)
    bot = request.app.get("bot")
    notify = teacher_notifier(bot) if bot is not None else None
    if code is None:
        kind, result = "join", "missing"
    elif kind == "join":
        result = await service.claim(code, user.telegram_id)
    elif kind == "enroll":
        result = await service.enroll(code, user.telegram_id, user.full_name or "", notify=notify)
    else:
        kind, result = "join", await service.claim(code, user.telegram_id)
        if result == "missing":
            kind = "enroll"
            result = await service.enroll(
                code, user.telegram_id, user.full_name or "", notify=notify
            )
    logger.info(
        "mini app code kind=%s code=%s… result=%s user_id=%s",
        kind,
        (code or "")[:4],
        result,
        user.telegram_id,
    )
    return web.json_response(
        {"ok": result in OK, "kind": kind, "result": result, "text": t(f"{kind}_{result}", lang)}
    )
