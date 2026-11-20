"""Turn a profile into a validated post. Quota is charged by the caller."""

import hashlib
import json
from dataclasses import dataclass

from app.ai.freshness import is_too_similar, pick_angle, prefer_fresh
from app.ai.prompts import build_daily_prompt
from app.ai.provider import AIProvider
from app.ai.schemas import load_daily_post
from app.db.models.chats import ChatProfile
from app.db.repositories.cache import CacheRepository

RETRY_TEMPERATURE = 1.1
DEFAULT_TEMPERATURE = 0.9


@dataclass(frozen=True)
class Draft:
    """A post that is safe to store and send."""

    body: str
    provider: str
    model: str


class ContentGenerator:
    """Cache lookup, provider call, schema check, and one freshness retry."""

    def __init__(self, provider: AIProvider, cache: CacheRepository) -> None:
        self._provider = provider
        self._cache = cache

    async def draft(
        self, profile: ChatProfile, slot: str, recent: list[str] | None = None
    ) -> Draft:
        """Return a validated body. Raises AI errors from the provider or schema."""
        history = list(recent or [])
        angle = pick_angle(slot)
        prompt = build_daily_prompt(profile, slot, history, angle)
        post = await self._load(prompt)
        if is_too_similar(post.body, history):
            retry = build_daily_prompt(profile, slot, history, pick_angle(slot, 1), retry=True)
            second = await self._load(retry, temperature=RETRY_TEMPERATURE, store=False)
            if prefer_fresh(post.body, second.body, history):
                post = second
        return Draft(post.body.strip(), self._provider.name, self._provider.model)

    async def _load(
        self, prompt: str, temperature: float = DEFAULT_TEMPERATURE, store: bool = True
    ):
        key = _key(self._provider.name, self._provider.model, prompt)
        cached = await self._cache.get(key)
        if cached is not None:
            return load_daily_post(json.dumps(cached))
        raw = await self._provider.complete(prompt, temperature=temperature)
        post = load_daily_post(raw)
        if store:
            await self._cache.put(
                key, self._provider.name, self._provider.model, {"body": post.body}
            )
        return post


def _key(provider: str, model: str, prompt: str) -> str:
    material = f"{provider}|{model}|{prompt}".encode()
    return hashlib.sha256(material).hexdigest()
