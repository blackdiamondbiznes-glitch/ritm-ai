"""Computed teaching and learning roles for the signed-in account."""

from __future__ import annotations

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.workspaces import WorkspaceRepository
from app.services.roles import RoleService
from app.webapp.routes import _context


def setup_role_routes(app: web.Application) -> None:
    """Register the role switch payload."""
    app.router.add_get("/api/me/roles", my_roles)


async def my_roles(request: web.Request) -> web.Response:
    """Cabinets this account teaches and classes it studies in."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    data = await _service(ctx).for_user(ctx.user)
    return web.json_response(data)


def _service(ctx) -> RoleService:
    return RoleService(WorkspaceRepository(ctx.session), GroupRepository(ctx.session))
