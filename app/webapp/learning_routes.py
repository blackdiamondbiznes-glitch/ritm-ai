"""The student cabinet. One request, only this account's groups."""

from __future__ import annotations

from aiohttp import web

from app.db.repositories.groups import GroupRepository
from app.db.repositories.learning import LearningRepository
from app.db.repositories.topics import TopicRepository
from app.services.learning import LearningService
from app.webapp.routes import _context


def setup_learning_routes(app: web.Application) -> None:
    """Register the student home payload."""
    app.router.add_get("/api/me/learning", learning)


async def learning(request: web.Request) -> web.Response:
    """Groups, next lesson, attendance, fee, rank, and scores for the signed-in student."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    service = LearningService(
        LearningRepository(ctx.session),
        GroupRepository(ctx.session),
        TopicRepository(ctx.session),
    )
    return web.json_response(await service.for_user(ctx.user))
