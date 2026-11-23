"""Teacher approval of students who asked to join a group."""

from __future__ import annotations

from aiohttp import web

from app.bot.enroll_notice import decision_text, tell
from app.bot.widgets.dispatch import edit_card
from app.db.repositories.groups import GroupRepository
from app.db.repositories.invoices import InvoiceRepository
from app.db.repositories.students import StudentRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.enrollment import EnrollmentError, EnrollmentService
from app.services.fees import FeeService
from app.services.tutor_limits import TutorLimitError, limit_body
from app.services.widget_cards import enroll_data, enroll_ref
from app.services.workspaces import WorkspaceService
from app.webapp.routes import _context, _error


def setup_request_routes(app: web.Application) -> None:
    """Register the registration-request API."""
    app.router.add_get("/api/tutor/requests", requests_list)
    app.router.add_post("/api/tutor/requests/{group_id}/{student_id}/approve", requests_approve)
    app.router.add_post("/api/tutor/requests/{group_id}/{student_id}/reject", requests_reject)


async def requests_list(request: web.Request) -> web.Response:
    """Requests waiting for the signed-in teacher."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    return web.json_response(await _service(ctx).requests(ctx.user.id))


async def requests_approve(request: web.Request) -> web.Response:
    """Accept one request and tell the student."""
    return await _decide(request, "approve", "enroll_yes")


async def requests_reject(request: web.Request) -> web.Response:
    """Decline one request and tell the student."""
    return await _decide(request, "reject", "enroll_no")


async def _decide(request: web.Request, action: str, key: str) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    group_id = _int(request, "group_id")
    student_id = _int(request, "student_id")
    if group_id is None or student_id is None:
        return _error(400, "bad_request")
    pending = await StudentRepository(ctx.session).get_owned(ctx.user.id, student_id)
    name = pending.name if pending is not None else ""
    try:
        if action == "approve":
            result = await _service(ctx).approve(ctx.user.id, group_id, student_id)
        else:
            result = await _service(ctx).reject(ctx.user.id, group_id, student_id)
    except TutorLimitError as exc:
        return web.json_response(limit_body(exc), status=403)
    except EnrollmentError as exc:
        return _error(404 if exc.code == "missing" else 400, exc.code)
    await _tell_student(request, ctx, result, key)
    await _refresh_enroll(request, ctx, group_id, student_id, result, key, name)
    return web.json_response(await _service(ctx).requests(ctx.user.id))


async def _tell_student(request: web.Request, ctx, result: dict, key: str) -> None:
    telegram_id = result.get("telegram_id")
    if not isinstance(telegram_id, int):
        return
    user = await ctx.users.get_by_telegram_id(telegram_id)
    lang = user.language_code if user is not None else "uz"
    await tell(request.app.get("bot"), telegram_id, decision_text(lang, key, result["group"]))


def _service(ctx) -> EnrollmentService:
    return EnrollmentService(
        GroupRepository(ctx.session),
        StudentRepository(ctx.session),
        ctx.users,
        WorkspaceService(WorkspaceRepository(ctx.session), ctx.users),
        ctx.access,
        FeeService(
            InvoiceRepository(ctx.session), GroupRepository(ctx.session), ctx.users, ctx.access
        ),
    )


def _int(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info[key])
    except (KeyError, ValueError):
        return None


async def _refresh_enroll(
    request, ctx, group_id: int, student_id: int, result: dict, key: str, name: str
) -> None:
    bot = request.app.get("bot")
    if bot is None:
        return
    status = "yes" if key == "enroll_yes" else "no"
    try:
        await edit_card(
            bot,
            ctx.session,
            "enroll",
            enroll_ref(group_id, student_id),
            enroll_data(
                ctx.user.language_code or "uz",
                name,
                result.get("group") or "",
                group_id,
                student_id,
                status,
            ),
        )
    except Exception:
        return
