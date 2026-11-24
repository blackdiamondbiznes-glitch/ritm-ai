"""Student homework submissions and teacher review endpoints."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.homework_submissions import HomeworkSubmissionRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.topics import TopicRepository
from app.services.homework_submissions import (
    HomeworkSubmissionError,
    HomeworkSubmissionService,
)
from app.webapp.context import WebContext
from app.webapp.routes import _context, _error

_STATUS = {
    "missing": 404,
    "answer": 400,
    "score": 400,
    "feedback": 400,
    "graded": 409,
    "student_link_required": 409,
}


def setup_homework_submission_routes(app: web.Application) -> None:
    """Register student and teacher homework endpoints."""
    app.router.add_get("/api/me/homework", student_homework)
    app.router.add_post("/api/me/homework/{topic_id}/submit", student_submit)
    app.router.add_get("/api/tutor/homework", teacher_homework)
    app.router.add_post("/api/tutor/homework/submissions/{submission_id}/grade", teacher_grade)


async def student_homework(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        rows = await _service(ctx).student_tasks(ctx.user)
    except HomeworkSubmissionError as exc:
        return _failure(exc)
    return web.json_response({"assignments": rows})


async def student_submit(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    topic_id = _id(request, "topic_id")
    if topic_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    try:
        result = await _service(ctx).submit(ctx.user, topic_id, body.get("answer"))
    except HomeworkSubmissionError as exc:
        return _failure(exc)
    return web.json_response(result)


async def teacher_homework(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    try:
        rows = await _service(ctx).teacher_tasks(ctx.user.id)
    except HomeworkSubmissionError as exc:
        return _failure(exc)
    return web.json_response({"assignments": rows})


async def teacher_grade(request: web.Request) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    submission_id = _id(request, "submission_id")
    if submission_id is None:
        return _error(400, "bad_request")
    body = await _body(request)
    if isinstance(body, web.Response):
        return body
    try:
        result = await _service(ctx).grade(ctx.user.id, submission_id, body)
    except HomeworkSubmissionError as exc:
        return _failure(exc)
    return web.json_response(result)


def _service(ctx: WebContext) -> HomeworkSubmissionService:
    return HomeworkSubmissionService(
        HomeworkSubmissionRepository(ctx.session),
        TopicRepository(ctx.session),
        GroupRepository(ctx.session),
        StudentRepository(ctx.session),
    )


async def _body(request: web.Request) -> dict[str, Any] | web.Response:
    try:
        value = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, web.HTTPBadRequest):
        return _error(400, "bad_request")
    if not isinstance(value, dict):
        return _error(400, "bad_request")
    return value


def _failure(exc: HomeworkSubmissionError) -> web.Response:
    return _error(_STATUS.get(exc.code, 400), exc.code)


def _id(request: web.Request, key: str) -> int | None:
    try:
        value = int(request.match_info[key])
    except (KeyError, ValueError):
        return None
    return value if value > 0 else None
