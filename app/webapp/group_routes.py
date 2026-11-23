"""Tutor groups in the Mini App. Rows belong to the signed-in owner only."""

from __future__ import annotations

from html import escape
from typing import Any

from aiohttp import web

from app.bot.keyboards.enroll import enroll_keyboard
from app.db.repositories.attendance import AttendanceRepository
from app.db.repositories.chats import ChatRepository
from app.db.repositories.groups import GroupRepository
from app.db.repositories.lessons import LessonRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.i18n import t
from app.services.groups import GroupError, GroupService
from app.services.sessions import SessionPlanner
from app.services.tutor_limits import TutorLimitError, limit_body
from app.services.workspaces import WorkspaceService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "empty": 400,
    "long": 400,
    "days": 400,
    "time": 400,
    "student": 400,
    "send": 400,
}


def setup_group_routes(app: web.Application) -> None:
    """Register the tutor group API."""
    app.router.add_get("/api/tutor/groups", groups_list)
    app.router.add_post("/api/tutor/groups", groups_create)
    app.router.add_get("/api/tutor/groups/{group_id}", groups_open)
    app.router.add_patch("/api/tutor/groups/{group_id}", groups_update)
    app.router.add_delete("/api/tutor/groups/{group_id}", groups_delete)
    app.router.add_post("/api/tutor/groups/{group_id}/students", groups_add_student)
    app.router.add_post("/api/tutor/groups/{group_id}/announce", groups_announce)
    app.router.add_delete(
        "/api/tutor/groups/{group_id}/students/{student_id}", groups_remove_student
    )


async def groups_list(request: web.Request) -> web.Response:
    """List the signed-in owner's groups."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _service(ctx).list(ctx.user.id))


async def groups_create(request: web.Request) -> web.Response:
    """Add a group and return the updated list."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.create(ctx.user.id, body))


async def groups_open(request: web.Request) -> web.Response:
    """One group and the students in it."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _group_id(request)
    if group_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.open(ctx.user.id, group_id))


async def groups_update(request: web.Request) -> web.Response:
    """Edit one group owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _group_id(request)
    if group_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.update(ctx.user.id, group_id, body))


async def groups_delete(request: web.Request) -> web.Response:
    """Delete one group owned by the signed-in user."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _group_id(request)
    if group_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.remove(ctx.user.id, group_id))


async def groups_announce(request: web.Request) -> web.Response:
    """Post the group's registration link into one of the owner's chats."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _group_id(request)
    if group_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    chat_id = body.get("chat_id")
    if isinstance(chat_id, bool) or not isinstance(chat_id, int):
        return _error(400, "bad_request")
    group = await GroupRepository(ctx.session).get_owned(ctx.user.id, group_id)
    chat = await ChatRepository(ctx.session).get_by_id(chat_id)
    if group is None or chat is None or chat.owner_id != ctx.user.id or not chat.is_active:
        return _error(404, "missing")
    bot = request.app.get("bot")
    if bot is None:
        return _error(400, "send")
    lang = ctx.user.language_code or "uz"
    try:
        await bot.send_message(
            chat.telegram_chat_id,
            t("enroll_post", lang, name=escape(group.name or "")),
            reply_markup=enroll_keyboard(lang, group.enroll_code),
        )
    except Exception:
        return _error(400, "send")
    return web.json_response({"ok": True})


async def groups_add_student(request: web.Request) -> web.Response:
    """Place one of the owner's students into this group."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _group_id(request)
    if group_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    student_id = body.get("student_id")
    if isinstance(student_id, bool) or not isinstance(student_id, int):
        return _error(400, "student")
    return await _call(ctx, lambda svc: svc.add_student(ctx.user.id, group_id, student_id))


async def groups_remove_student(request: web.Request) -> web.Response:
    """Take a student out of this group."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _group_id(request)
    student_id = _int(request, "student_id")
    if group_id is None or student_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.remove_student(ctx.user.id, group_id, student_id))


def _service(ctx: WebContext) -> GroupService:
    session = ctx.session
    return GroupService(
        GroupRepository(session),
        StudentRepository(session),
        ctx.access,
        ctx.users,
        WorkspaceService(WorkspaceRepository(session), ctx.users),
        SessionPlanner(
            LessonRepository(session),
            GroupRepository(session),
            attendance=AttendanceRepository(session),
        ),
    )


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_service(ctx))
    except TutorLimitError as exc:
        return web.json_response(limit_body(exc), status=403)
    except GroupError as exc:
        return _error(_STATUS.get(exc.code, 400), exc.code)
    return web.json_response(data)


async def _body(request: web.Request) -> dict[str, Any] | web.Response:
    try:
        raw = await request.json()
    except Exception:
        return _error(400, "bad_request")
    if not isinstance(raw, dict):
        return _error(400, "bad_request")
    return raw


def _group_id(request: web.Request) -> int | None:
    return _int(request, "group_id")


def _int(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info[key])
    except (KeyError, ValueError):
        return None
