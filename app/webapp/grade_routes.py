"""Topic marks and the group ranking. The owner grades. A linked student only reads."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.topics import TopicRepository
from app.services.grades import GradeError, GradeService
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "empty": 400,
    "long": 400,
    "date": 400,
    "score": 400,
    "student": 400,
}


def setup_grade_routes(app: web.Application) -> None:
    """Register topic marks, the teacher board, and the student board."""
    app.router.add_get("/api/tutor/groups/{group_id}/board", group_board)
    app.router.add_post("/api/tutor/groups/{group_id}/topics", topic_create)
    app.router.add_get("/api/tutor/groups/{group_id}/topics/{topic_id}", topic_sheet)
    app.router.add_put("/api/tutor/groups/{group_id}/topics/{topic_id}", topic_save)
    app.router.add_get("/api/me/boards", my_boards)


async def group_board(request: web.Request) -> web.Response:
    """Topics and ranking for one owned group."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    if group_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.board(ctx.user.id, group_id))


async def topic_create(request: web.Request) -> web.Response:
    """Add a topic and return its mark sheet."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    if group_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.add_topic(ctx.user.id, group_id, body))


async def topic_sheet(request: web.Request) -> web.Response:
    """The mark sheet for one topic."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    topic_id = _int(request, "topic_id")
    if group_id is None or topic_id is None:
        return _error(400, "bad_request")
    return await _call(ctx, lambda svc: svc.sheet(ctx.user.id, group_id, topic_id))


async def topic_save(request: web.Request) -> web.Response:
    """Save the marks on one topic."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    topic_id = _int(request, "topic_id")
    if group_id is None or topic_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    return await _call(ctx, lambda svc: svc.save_marks(ctx.user.id, group_id, topic_id, body))


async def my_boards(request: web.Request) -> web.Response:
    """Rankings for the groups this Telegram account studies in."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    boards = await _service(ctx).boards_for(ctx.user.telegram_id)
    return web.json_response({"boards": boards})


def _service(ctx: WebContext) -> GradeService:
    return GradeService(
        GroupRepository(ctx.session),
        StudentRepository(ctx.session),
        TopicRepository(ctx.session),
    )


async def _call(ctx: WebContext, work) -> web.Response:
    try:
        data = await work(_service(ctx))
    except GradeError as exc:
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


def _int(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info[key])
    except (KeyError, ValueError):
        return None
