from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.config import Settings
from app.webapp import ai_draft_routes
from app.webapp.panel import ACT, PanelError
from app.webapp.server import create_app


@pytest.mark.parametrize("handler", [ai_draft_routes.draft_post, ai_draft_routes.draft_quiz])
async def test_ai_draft_requires_chat_authorization_before_generation(monkeypatch, handler):
    ctx = SimpleNamespace(
        panel=SimpleNamespace(authorize=AsyncMock(side_effect=PanelError(403, "not_owner"))),
        user=SimpleNamespace(id=7),
    )
    monkeypatch.setattr(ai_draft_routes, "_context", AsyncMock(return_value=ctx))
    request = SimpleNamespace(
        match_info={"chat_id": "42"},
        json=AsyncMock(return_value={}),
    )

    response = await handler(request)

    assert response.status == 403
    ctx.panel.authorize.assert_awaited_once_with(ctx.user, 42, ACT)


def test_ai_draft_routes_are_registered() -> None:
    app = create_app(
        Settings(
            bot_token="1:test-token",
            database_url="postgresql+asyncpg://bot:bot@localhost/test",
        ),
        None,
    )
    paths = {route.resource.canonical for route in app.router.routes()}

    assert "/api/chats/{chat_id}/draft-post" in paths
    assert "/api/chats/{chat_id}/draft-quiz" in paths
