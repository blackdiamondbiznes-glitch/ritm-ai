"""Authenticated AI drafts for the EduFlow community studio."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiohttp import web

from app.ai.errors import AIConfigError, AIOutputError, AITransient
from app.ai.provider import build_provider
from app.db.models.chats import ChatProfile
from app.db.repositories.cache import CacheRepository
from app.db.repositories.content import ContentRepository
from app.db.repositories.quizzes import QuizRepository
from app.db.repositories.usage import UsageRepository
from app.services.access import AI_METRIC
from app.services.generate import ContentGenerator
from app.services.quiz_mode import QUIZ
from app.services.quizgen import QuizGenerator
from app.webapp.panel import ACT, PanelError
from app.webapp.routes import _context, _error

MAX_TOPIC = 160
_TONE_NAMES = {
    "formal": "formal and clear",
    "friendly": "friendly and conversational",
    "fun": "playful and engaging",
}


def setup_ai_draft_routes(app: web.Application) -> None:
    """Register real AI draft endpoints used by EduFlow."""
    app.router.add_post("/api/chats/{chat_id}/draft-post", draft_post)
    app.router.add_post("/api/chats/{chat_id}/draft-quiz", draft_quiz)


async def draft_post(request: web.Request) -> web.Response:
    """Generate a post draft using the configured server-side AI provider."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    chat_id = _chat_id(request)
    if chat_id is None:
        return _error(400, "bad_request")
    body = await _json_body(request)
    if isinstance(body, web.Response):
        return body
    topic, tone = _input(body)
    if isinstance(topic, web.Response):
        return topic
    try:
        chat, _role = await ctx.panel.authorize(ctx.user, chat_id, ACT)
        if not await ctx.access.is_module_allowed(chat, "daily_content"):
            return _error(403, "module")
        if await ctx.access.remaining_ai_quota(ctx.user) <= 0:
            return _error(403, "quota")
        profile = await ctx.panel.profiles.get(chat.id)
        if profile is None:
            return _error(409, "profile_required")
        if not await _reserve_quota(ctx.session, ctx):
            return _error(403, "quota")
        prompt_profile = _prompt_profile(profile, topic, tone)
        content = ContentRepository(ctx.session)
        history = await content.recent_bodies(chat.id)
        draft = await ContentGenerator(
            build_provider(ctx.settings), CacheRepository(ctx.session)
        ).draft(prompt_profile, _slot(), history)
    except PanelError as exc:
        return _error(exc.status, exc.code)
    except AIConfigError:
        return _error(503, "ai_unavailable")
    except AITransient:
        return _error(503, "ai_temporarily_unavailable")
    except AIOutputError:
        return _error(502, "ai_invalid_response")
    return web.json_response({"body": draft.body, "provider": draft.provider, "model": draft.model})


async def draft_quiz(request: web.Request) -> web.Response:
    """Generate one validated quiz draft from the selected topic or recent posts."""
    ctx = await _context(request)
    if isinstance(ctx, web.Response):
        return ctx
    chat_id = _chat_id(request)
    if chat_id is None:
        return _error(400, "bad_request")
    body = await _json_body(request)
    if isinstance(body, web.Response):
        return body
    topic, tone = _input(body)
    if isinstance(topic, web.Response):
        return topic
    try:
        chat, _role = await ctx.panel.authorize(ctx.user, chat_id, ACT)
        if not await ctx.access.is_module_allowed(chat, QUIZ):
            return _error(403, "module")
        if await ctx.access.remaining_ai_quota(ctx.user) <= 0:
            return _error(403, "quota")
        profile = await ctx.panel.profiles.get(chat.id)
        if profile is None:
            return _error(409, "profile_required")
        if not await _reserve_quota(ctx.session, ctx):
            return _error(403, "quota")
        prompt_profile = _prompt_profile(profile, topic, tone)
        content = ContentRepository(ctx.session)
        source = [item.body for item in await content.latest(chat.id, limit=3)]
        if topic:
            source = [topic, *source]
        if not source:
            return _error(409, "topic_required")
        quizzes = QuizRepository(ctx.session)
        recent = await quizzes.recent_questions(chat.id)
        draft = await QuizGenerator(
            build_provider(ctx.settings), CacheRepository(ctx.session)
        ).draft(prompt_profile, source, _slot(), recent)
    except PanelError as exc:
        return _error(exc.status, exc.code)
    except AIConfigError:
        return _error(503, "ai_unavailable")
    except AITransient:
        return _error(503, "ai_temporarily_unavailable")
    except AIOutputError:
        return _error(502, "ai_invalid_response")
    return web.json_response(
        {
            "question": draft.question,
            "options": list(draft.options),
            "correct": draft.correct,
            "explanation": draft.explanation,
            "provider": draft.provider,
            "model": draft.model,
        }
    )


async def _json_body(request: web.Request) -> dict[str, Any] | web.Response:
    try:
        value = await request.json()
    except (ValueError, web.HTTPBadRequest):
        return _error(400, "bad_request")
    if not isinstance(value, dict):
        return _error(400, "bad_request")
    return value


def _input(body: dict[str, Any]) -> tuple[str, str] | web.Response:
    topic = body.get("topic", "")
    tone = body.get("tone", "friendly")
    if not isinstance(topic, str) or len(topic.strip()) > MAX_TOPIC:
        return _error(400, "topic")
    if not isinstance(tone, str) or tone not in _TONE_NAMES:
        return _error(400, "tone")
    return topic.strip(), tone


def _prompt_profile(profile: ChatProfile, topic: str, tone: str) -> ChatProfile:
    """Build a detached prompt-only profile so UI choices never mutate saved settings."""
    requested = (
        f"{profile.niche_description}\nRequested topic: {topic}"
        if topic
        else profile.niche_description
    )
    return ChatProfile(
        chat_id=profile.chat_id,
        niche_code=profile.niche_code,
        niche_description=requested[:4000],
        language=profile.language,
        tone=f"{profile.tone}; {_TONE_NAMES[tone]}",
        audience_level=profile.audience_level,
        timezone=profile.timezone,
        content_guidelines=profile.content_guidelines,
        banned_topics=profile.banned_topics,
        modules_enabled=list(profile.modules_enabled or []),
        updated_at=profile.updated_at,
    )


async def _reserve_quota(session, ctx) -> bool:
    period = datetime.now(UTC).strftime("%Y-%m")
    usage = UsageRepository(session)
    await usage.bump(ctx.user.id, AI_METRIC, period)
    plan = await ctx.access.get_effective_plan(ctx.user)
    return await usage.get_count(ctx.user.id, AI_METRIC, period) <= plan.ai_generations_per_month


def _chat_id(request: web.Request) -> int | None:
    try:
        value = int(request.match_info["chat_id"])
    except (KeyError, ValueError):
        return None
    return value if value > 0 else None


def _slot() -> str:
    return datetime.now(UTC).isoformat()
