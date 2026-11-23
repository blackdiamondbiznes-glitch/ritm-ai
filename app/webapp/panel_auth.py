"""Teacher web panel: page, magic-link sign-in, cookie session, logout, and the home payload."""

from __future__ import annotations

import html

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.users import UserRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services import panel_login
from app.services.panel_home import PanelHome
from app.services.roles import RoleService
from app.webapp.auth import issue_session
from app.webapp.routes import PANEL_COOKIE, _context, _error, _rate, _secret, same_origin
from app.webapp.security import PANEL_CSP

LOGIN_LIMIT = 10
LANGS = ("uz", "ru", "en")
COPY = {
    "uz": {
        "title": "Ritm paneliga kirish",
        "lead": "Bu havola faqat sizga yuborilgan va bir marta ishlaydi.",
        "go": "Panelga kirish",
        "dead": "Havola eskirgan yoki allaqachon ishlatilgan.",
        "again": "Botga /panel yuborib, yangi havola oling.",
        "blocked": "Kirishni tasdiqlab bo‘lmadi.",
        "retry": "Havola hali amal qiladi. Qayta urinib ko‘ring yoki uni Chromeʼda oching.",
        "slow": "Juda ko‘p urinish. Bir daqiqadan keyin qayta urinib ko‘ring.",
    },
    "ru": {
        "title": "Вход в панель Ritm",
        "lead": "Ссылка отправлена только вам и работает один раз.",
        "go": "Войти в панель",
        "dead": "Ссылка устарела или уже использована.",
        "again": "Отправьте боту /panel, чтобы получить новую.",
        "blocked": "Не удалось подтвердить вход.",
        "retry": "Ссылка ещё действует. Попробуйте снова или откройте её в Chrome.",
        "slow": "Слишком много попыток. Повторите через минуту.",
    },
    "en": {
        "title": "Sign in to the Ritm panel",
        "lead": "This link was sent only to you and works once.",
        "go": "Open the panel",
        "dead": "This link has expired or was already used.",
        "again": "Send /panel to the bot to get a new one.",
        "blocked": "Could not confirm the sign-in.",
        "retry": "The link still works. Try again or open it in Chrome.",
        "slow": "Too many attempts. Try again in a minute.",
    },
}


def setup_panel_routes(app: web.Application) -> None:
    """Register the panel page, sign-in, logout, and panel API."""
    app.router.add_get("/panel", panel_page)
    app.router.add_get("/panel/login", login_page)
    app.router.add_post("/panel/login", login_submit)
    app.router.add_post("/panel/logout", logout)
    app.router.add_post("/api/panel/link", send_link)
    app.router.add_get("/api/panel/home", panel_home)


def _panel_headers(response: web.StreamResponse) -> web.StreamResponse:
    """Top-level page: never framed, no inline scripts. Set before the Mini App defaults."""
    response.headers["Content-Security-Policy"] = PANEL_CSP
    response.headers["Cache-Control"] = "no-store"
    # "no-referrer" makes browsers post forms with Origin: null; same-origin keeps the
    # one-time link inside our host and lets the Origin check work.
    response.headers["Referrer-Policy"] = "same-origin"
    return response


async def panel_page(request: web.Request) -> web.StreamResponse:
    store = request.app["assets"]
    if store.panel is None:
        raise web.HTTPNotFound()
    return _panel_headers(store.response(request, store.panel, "no-store"))


def _lang(request: web.Request) -> str:
    raw = request.headers.get("Accept-Language", "")[:2].lower()
    return raw if raw in LANGS else "uz"


def _page(request: web.Request, body: str, status: int = 200) -> web.Response:
    version = request.app["assets"].version
    lang = _lang(request)
    text = (
        f'<!DOCTYPE html><html lang="{lang}" data-theme="light"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Ritm</title>"
        f'<link rel="stylesheet" href="/s/{version}/theme.css">'
        f'<link rel="stylesheet" href="/s/{version}/panel.css"></head>'
        f'<body class="pn-gate"><main class="pn-gate-card"><div class="pn-brand">'
        f'<span class="pn-logo" aria-hidden="true">R</span>Ritm</div>{body}</main></body></html>'
    )
    return _panel_headers(web.Response(text=text, status=status, content_type="text/html"))


async def login_page(request: web.Request) -> web.Response:
    """GET only shows a button. Link scanners that open the URL do not spend the token."""
    copy = COPY[_lang(request)]
    raw = request.query.get("t", "")
    if not raw or len(raw) > panel_login.TOKEN_MAX:
        return _dead(request, 400)
    return _page(request, f"<h1>{html.escape(copy['title'])}</h1>{_form(copy, raw, 'lead')}")


def _form(copy: dict, raw: str, lead: str) -> str:
    return (
        f"<p>{html.escape(copy[lead])}</p>"
        '<form method="post" action="/panel/login">'
        f'<input type="hidden" name="t" value="{html.escape(raw, quote=True)}">'
        f'<button type="submit" class="pn-btn pn-btn-primary">{html.escape(copy["go"])}</button>'
        "</form>"
    )


def _notice(request: web.Request, title: str, lead: str, status: int) -> web.Response:
    copy = COPY[_lang(request)]
    body = f"<h1>{html.escape(copy[title])}</h1><p>{html.escape(copy[lead])}</p>"
    return _page(request, body, status)


def _dead(request: web.Request, status: int) -> web.Response:
    return _notice(request, "dead", "again", status)


async def login_submit(request: web.Request) -> web.StreamResponse:
    """Spend the token once and set the HttpOnly session cookie."""
    if not _rate(request, "panel_login", LOGIN_LIMIT):
        return _notice(request, "slow", "again", 429)
    form = await request.post()
    raw = str(form.get("t") or "")
    if not raw or len(raw) > panel_login.TOKEN_MAX:
        return _dead(request, 400)
    if not same_origin(request):
        # Checked before consume(): a refused post leaves the one-time token usable.
        copy = COPY[_lang(request)]
        body = f"<h1>{html.escape(copy['blocked'])}</h1>{_form(copy, raw, 'retry')}"
        return _page(request, body, 403)
    async with request.app["sessions"]() as session:
        user_id = await panel_login.consume(session, raw)
        user = await UserRepository(session).get_by_id(user_id) if user_id else None
        await session.commit()
    if user is None or user.is_blocked:
        return _dead(request, 410)
    settings = request.app["settings"]
    ttl = settings.webapp_session_ttl
    response = web.Response(status=303, headers={"Location": "/panel"})
    response.set_cookie(
        PANEL_COOKIE,
        issue_session(user.telegram_id, _secret(settings), ttl),
        max_age=ttl,
        path="/",
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return _panel_headers(response)


async def logout(request: web.Request) -> web.StreamResponse:
    """Drop the cookie. Cross-site posts are refused so nobody can sign a teacher out."""
    if not same_origin(request):
        return _notice(request, "blocked", "again", 403)
    response = web.Response(status=303, headers={"Location": "/panel"})
    response.del_cookie(PANEL_COOKIE, path="/")
    return _panel_headers(response)


async def send_link(request: web.Request) -> web.Response:
    """Mini App button: the bot sends the link to the teacher's chat; it is never returned here."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    if not await panel_login.is_teacher(ctx.session, ctx.user):
        return _error(403, "not_teacher")
    bot = request.app.get("bot")
    base = ctx.settings.public_webapp_url
    if bot is None or not base:
        return _error(503, "unavailable")
    lang = ctx.user.language_code if ctx.user.language_code in LANGS else "uz"
    sent = await panel_login.send_link(bot, ctx.session, ctx.user, base, lang)
    if not sent:
        return _error(502, "not_sent")
    return web.json_response({"sent": True})


async def panel_home(request: web.Request) -> web.Response:
    """Exceptions for the signed-in teacher plus who they are."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    modes = await RoleService(
        WorkspaceRepository(ctx.session), GroupRepository(ctx.session)
    ).for_user(ctx.user)
    teacher = any(row["groups"] > 0 or row["students"] > 0 for row in modes["teaching"])
    data = await PanelHome(ctx.session).for_owner(ctx.user.id)
    data["user"] = {
        "name": ctx.user.teacher_name or ctx.user.full_name or "",
        "language": ctx.user.language_code or "uz",
    }
    data["teacher"] = teacher
    data["both_roles"] = teacher and bool(modes["learning"])
    return web.json_response(data)
