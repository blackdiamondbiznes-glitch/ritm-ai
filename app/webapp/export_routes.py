"""CSV downloads. The Mini App sends the session header; the file is not a public link."""

from __future__ import annotations

from datetime import datetime

from aiohttp import web

from app.db.repositories.exports import ExportRepository
from app.db.repositories.groups import GroupRepository
from app.services.clock import TASHKENT
from app.services.csv_export import CsvExport, ExportError
from app.services.month_report import ReportError
from app.webapp.routes import _context, _error

_STATUS = {"missing": 404, "month": 400, "export": 403}


def setup_export_routes(app: web.Application) -> None:
    """Register the three spreadsheets."""
    app.router.add_get("/api/tutor/export/students.csv", students_csv)
    app.router.add_get("/api/tutor/export/payments.csv", payments_csv)
    app.router.add_get("/api/tutor/export/attendance.csv", attendance_csv)


async def students_csv(request: web.Request) -> web.Response:
    """Every visible student of the signed-in teacher."""
    return await _file(request, lambda svc, owner, today: svc.students(owner, today))


async def payments_csv(request: web.Request) -> web.Response:
    """Payments in the requested month."""
    month = request.query.get("month") or ""
    return await _file(request, lambda svc, owner, today: svc.payments(owner, month, today))


async def attendance_csv(request: web.Request) -> web.Response:
    """Marks for one owned group in the requested month."""
    raw = request.query.get("group_id") or ""
    if not raw.isdigit():
        return _error(400, "group")
    month = request.query.get("month") or ""
    group_id = int(raw)
    return await _file(
        request, lambda svc, owner, today: svc.attendance(owner, group_id, month, today)
    )


async def _file(request: web.Request, work) -> web.Response:
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    today = datetime.now(TASHKENT).date().isoformat()
    service = CsvExport(ExportRepository(ctx.session), GroupRepository(ctx.session), ctx.access)
    try:
        name, body = await work(service, ctx.user, today)
    except ExportError as exc:
        return _error(_STATUS.get(exc.code, 400), exc.code)
    except ReportError as exc:
        return _error(_STATUS.get(exc.code, 400), exc.code)
    return web.Response(
        body=body,
        content_type="text/csv",
        charset="utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
