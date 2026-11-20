"""Turn published posts into a validated quiz. Quota is charged after a successful send."""

import hashlib
import json
from dataclasses import dataclass

from app.ai.admin_quiz_prompt import build_admin_quiz_prompt
from app.ai.freshness import is_too_similar, pick_angle, prefer_fresh
from app.ai.provider import AIProvider
from app.ai.quiz_prompt import build_quiz_prompt
from app.ai.schemas import QuizCard, load_quiz, load_quiz_batch
from app.db.models.chats import ChatProfile
from app.db.repositories.cache import CacheRepository

RETRY_TEMPERATURE = 1.1
DEFAULT_TEMPERATURE = 0.9


@dataclass(frozen=True)
class QuizDraft:
    """A quiz that is safe to store. The correct index never goes into the channel text."""

    question: str
    options: tuple[str, ...]
    correct: int
    explanation: str | None
    provider: str
    model: str


class QuizGenerator:
    """Cache, provider call, schema check, and one freshness retry."""

    def __init__(self, provider: AIProvider, cache: CacheRepository) -> None:
        self._provider = provider
        self._cache = cache

    async def draft(
        self,
        profile: ChatProfile,
        posts: list[str],
        slot: str,
        recent: list[str] | None = None,
    ) -> QuizDraft:
        """Return a validated quiz. Raises AI errors from the provider or schema."""
        history = list(recent or [])
        angle = pick_angle(slot)
        prompt = build_quiz_prompt(profile, posts, slot, history, angle)
        card = await self._card(prompt, load_quiz)
        if is_too_similar(card.question, history):
            retry = build_quiz_prompt(
                profile, posts, slot, history, pick_angle(slot, 1), retry=True
            )
            second = await self._card(retry, load_quiz, temperature=RETRY_TEMPERATURE, store=False)
            if prefer_fresh(card.question, second.question, history):
                card = second
        return _draft(card, self._provider.name, self._provider.model)

    async def draft_from_admin_post(
        self, profile: ChatProfile, post: str, recent: list[str] | None = None
    ) -> list[QuizDraft]:
        """Return two or three validated quizzes about one admin post."""
        history = list(recent or [])
        prompt = build_admin_quiz_prompt(profile, post, history)
        batch = await self._card(prompt, load_quiz_batch)
        questions = list(batch.questions)
        if _needs_retry(questions, history):
            raw = await self._provider.complete(prompt, temperature=RETRY_TEMPERATURE)
            retry = load_quiz_batch(raw)
            if not _needs_retry(retry.questions, history):
                questions = list(retry.questions)
        return [_draft(card, self._provider.name, self._provider.model) for card in questions]

    async def _card(
        self, prompt: str, loader, temperature: float = DEFAULT_TEMPERATURE, store: bool = True
    ):
        material = f"{self._provider.name}|{self._provider.model}|{prompt}".encode()
        key = hashlib.sha256(material).hexdigest()
        cached = await self._cache.get(key)
        raw = (
            json.dumps(cached)
            if cached is not None
            else await self._provider.complete(prompt, temperature=temperature)
        )
        parsed = loader(raw)
        if cached is None and store:
            payload = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
            await self._cache.put(key, self._provider.name, self._provider.model, payload)
        return parsed


def _needs_retry(questions: list[QuizCard], history: list[str]) -> bool:
    seen = list(history)
    for item in questions:
        if is_too_similar(item.question, seen):
            return True
        seen.append(item.question)
    return False


def _draft(card: QuizCard, provider: str, model: str) -> QuizDraft:
    return QuizDraft(
        card.question.strip(),
        tuple(card.options),
        card.correct,
        card.explanation,
        provider,
        model,
    )
