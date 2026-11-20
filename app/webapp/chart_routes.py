"""Chart endpoints. Roles come from the same checks as M2 (panel.authorize) and M3."""

from __future__ import annotations

from aiohttp import web

from app.services.charts import ChartService, pick_days
from app.webapp.context import WebContext
from app.webapp.member_view import member_chats
from app.webapp.panel import VIEW, PanelError
from app.webapp.routes import _context, _error


def setup_chart_routes(app: web.Application) -> None:
    app.router.add_get("/api/charts", chat_charts)
    app.router.add_get("/api/me/charts", my_charts)


def chart_service(ctx: WebContext) -> ChartService:
    return ChartService(
        ctx.session,
        default_timezone=ctx.settings.default_timezone,
        points_per_correct=ctx.settings.points_per_correct_answer,
    )


async def chat_charts(request: web.Request) -> web.Response:
    """?chat=<id> for one chat the caller may view, or ?chat=all for every managed chat."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    days = pick_days(request.query.get("days"))
    raw = request.query.get("chat", "all")
    if raw == "all":
        managed = await ctx.panel.managed(ctx.user)
        chats = [(chat.id, chat.title) for chat, _role in managed]
        scope = "all"
    else:
        try:
            chat_id = int(raw)
        except ValueError:
            return _error(400, "bad_request")
        try:
            chat, _role = await ctx.panel.authorize(ctx.user, chat_id, VIEW)
        except PanelError as exc:
            return _error(exc.status, exc.code)
        chats = [(chat.id, chat.title)]
        scope = "chat"
    data = await chart_service(ctx).chats(chats, days, scope=scope)
    data["chats"] = [{"id": cid, "title": title} for cid, title in chats]
    return web.json_response(data)


async def my_charts(request: web.Request) -> web.Response:
    """The caller's own weekly points and accuracy. Always self-only."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        weeks = int(request.query.get("weeks", "12"))
    except ValueError:
        weeks = 12
    rows = await member_chats(ctx)
    ids = [chat.id for chat, _totals in rows]
    return web.json_response(await chart_service(ctx).member(ctx.user.id, ids, weeks))
