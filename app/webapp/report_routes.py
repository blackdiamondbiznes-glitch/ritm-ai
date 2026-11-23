"""Monthly tutor report. Pro and Ultra only."""

from __future__ import annotations

from aiohttp import web

from app.db.repositories.cabinet_stats import CabinetStatsRepository
from app.db.repositories.groups import GroupRepository
from app.services.month_report import MonthReport, ReportError
from app.webapp.routes import _context, _error

_STATUS = {"missing": 404, "month": 400, "export": 403}


def setup_report_routes(app: web.Application) -> None:
    """Register the monthly report."""
    app.router.add_get("/api/tutor/reports/monthly", monthly)


async def monthly(request: web.Request) -> web.Response:
    """Numbers for one YYYY-MM. A lower plan is 403."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    service = MonthReport(
        CabinetStatsRepository(ctx.session),
        GroupRepository(ctx.session),
        ctx.access,
    )
    try:
        data = await service.for_owner(ctx.user, request.query.get("month") or "")
    except ReportError as exc:
        return _error(_STATUS.get(exc.code, 400), exc.code)
    return web.json_response(data)
