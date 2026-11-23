"""Read-only dashboard endpoints: aggregated stats and a per-chat report."""

from __future__ import annotations

from aiohttp import web

from app.db.models.chats import Chat
from app.db.repositories.groups import GroupRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.roles import RoleService
from app.webapp.member_view import member_summary, resolve_roles
from app.webapp.members import MemberCountCache
from app.webapp.panel import EDIT, PanelError, permits
from app.webapp.routes import _context, _error, _plan_payload, sign_in


def setup_dash_routes(app: web.Application) -> None:
    """Register the Mini App dashboard routes."""
    app.router.add_get("/api/stats", stats)
    app.router.add_post("/api/bootstrap", bootstrap)
    app.router.add_get("/api/me/stats", my_stats)
    app.router.add_get("/api/chats/{chat_id}/report", chat_report)
    app.router.add_get("/api/chats/{chat_id}/leaderboard", chat_leaderboard)


async def stats(request: web.Request) -> web.Response:
    """Owner-wide today and weekly counts. No invented metrics."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await build_dash(ctx, request.app.get("members")))


async def bootstrap(request: web.Request) -> web.Response:
    """Sign in and return the home dashboard in one round trip."""
    members = request.app.get("members")

    async def _dash(ctx) -> dict:
        return {"dash": await build_dash(ctx, members)}

    return await sign_in(request, _dash)


async def build_dash(ctx, members: object) -> dict:
    """Role-aware home: managed chats (owned + Telegram-admin) with stats, the
    caller's own plan, and their quiz results as a member."""
    managed = await ctx.panel.managed(ctx.user)
    rows = [chat for chat, _role in managed]
    roles_by_chat = {chat.id: role for chat, role in managed}
    zone = await _timezone(ctx.panel.profiles, rows, ctx.settings.default_timezone)
    ids = [row.id for row in rows]
    overview = await ctx.activity.overview(ids, zone)
    overview["daily"] = await ctx.activity.daily(ids, zone)
    totals = await ctx.engagement.totals_by_chat(ids)
    chats = await _chat_cards(rows, members, totals, roles_by_chat)
    plan = await _plan_payload(ctx.access, ctx.payments, ctx.user, ctx.settings)
    return {
        "roles": await resolve_roles(ctx),
        "plan": plan,
        "stats": overview,
        "chats": chats,
        "member": await member_summary(ctx),
        "modes": await RoleService(
            WorkspaceRepository(ctx.session), GroupRepository(ctx.session)
        ).for_user(ctx.user),
    }


async def my_stats(request: web.Request) -> web.Response:
    """The caller's own points, ranks and recent answers. Always self-only."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    summary = await member_summary(ctx, history=True)
    return web.json_response({"member": summary})


async def chat_leaderboard(request: web.Request) -> web.Response:
    """Live weekly Top-10 for one chat the caller manages."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        chat_id = int(request.match_info["chat_id"])
    except (KeyError, ValueError):
        return _error(400, "bad_request")
    try:
        payload = await ctx.panel.board(ctx.user, chat_id)
    except PanelError as exc:
        return _error(exc.status, exc.code)
    return web.json_response(payload)


async def chat_report(request: web.Request) -> web.Response:
    """Weekly stats and the live Top-10 for one owned chat."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        chat_id = int(request.match_info["chat_id"])
    except (KeyError, ValueError):
        return _error(400, "bad_request")
    try:
        payload = await build_chat_report(
            ctx.user,
            ctx.panel,
            ctx.activity,
            ctx.settings.default_timezone,
            request.app.get("members"),
            chat_id,
        )
    except PanelError as exc:
        return _error(exc.status, exc.code)
    return web.json_response(payload)


async def build_chat_report(
    user,
    panel,
    activity: object,
    default_timezone: str,
    members: object,
    chat_id: int,
) -> dict:
    """Ownership is checked inside panel.detail before any stats are read."""
    detail = await panel.detail(user, chat_id)
    zone = _zone_from_profile(detail.get("profile"), default_timezone)
    overview = await activity.overview([chat_id], zone)
    chat = detail["chat"]
    if isinstance(members, MemberCountCache):
        telegram_id = chat.get("telegram_chat_id")
        if isinstance(telegram_id, int):
            count = await members.count(telegram_id)
            if count is not None:
                chat = {**chat, "member_count": count}
    return {"chat": chat, "stats": overview, "board": detail["board"]}


async def attach_members(request: web.Request, data: dict) -> dict:
    """Add member_count to a chat detail payload when Telegram returns one."""
    chat = data.get("chat") if isinstance(data, dict) else None
    cache = request.app.get("members")
    if not isinstance(chat, dict) or not isinstance(cache, MemberCountCache):
        return data
    telegram_id = chat.get("telegram_chat_id")
    if isinstance(telegram_id, int):
        count = await cache.count(telegram_id)
        if count is not None:
            return {**data, "chat": {**chat, "member_count": count}}
    return data


async def enrich_chats(
    request: web.Request,
    rows: list[Chat],
    totals: dict[int, dict[str, int]] | None = None,
    roles: dict[int, str] | None = None,
) -> list[dict]:
    """Chat list rows plus a cached member count when Telegram provides one."""
    return await _chat_cards(rows, request.app.get("members"), totals, roles)


async def _chat_cards(
    rows: list[Chat],
    cache: object,
    totals: dict[int, dict[str, int]] | None = None,
    roles: dict[int, str] | None = None,
) -> list[dict]:
    cards = []
    members = cache if isinstance(cache, MemberCountCache) else None
    counts = await members.counts([row.telegram_chat_id for row in rows]) if members else {}
    for row in rows:
        item = {
            "id": row.id,
            "title": row.title,
            "type": getattr(row.type, "value", row.type),
            "username": row.username,
            "is_active": row.is_active,
            "telegram_chat_id": row.telegram_chat_id,
        }
        if roles is not None and row.id in roles:
            role = roles[row.id]
            item["role"] = role
            item["can_edit"] = permits(role, EDIT, admins_can_edit=bool(row.admins_can_edit))
        if totals is not None and row.id in totals:
            item["posts_total"] = int(totals[row.id].get("posts", 0))
            item["quizzes_total"] = int(totals[row.id].get("quizzes", 0))
        if row.telegram_chat_id in counts:
            item["member_count"] = counts[row.telegram_chat_id]
        cards.append(item)
    return cards


async def _timezone(profiles, rows: list[Chat], fallback: str) -> str:
    """Prefer the first owned chat's saved zone, otherwise the bot default."""
    if not rows:
        return fallback
    profile = await profiles.get(rows[0].id)
    return _zone_from_profile(
        None if profile is None else {"timezone": profile.timezone},
        fallback,
    )


def _zone_from_profile(profile: dict | None, fallback: str) -> str:
    if not profile:
        return fallback
    zone = profile.get("timezone") if isinstance(profile, dict) else None
    return str(zone) if zone else fallback
