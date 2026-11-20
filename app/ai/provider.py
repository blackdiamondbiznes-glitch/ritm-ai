"""Choose the provider from settings. Callers depend on `complete` only."""

from typing import Protocol

from app.ai.errors import AIConfigError
from app.ai.gemini import GeminiProvider
from app.ai.openai import OpenAIProvider
from app.config import Settings


class AIProvider(Protocol):
    """One model call. Implementations must not log the prompt."""

    name: str
    model: str

    async def complete(self, prompt: str, temperature: float = 0.9) -> str:
        """Return raw model text."""


def build_provider(settings: Settings) -> AIProvider:
    """Gemini unless AI_PROVIDER is openai."""
    if settings.ai_provider == "openai":
        return OpenAIProvider(settings.openai_api_key, settings.openai_model, settings.ai_timeout)
    if settings.ai_provider == "gemini":
        return GeminiProvider(
            settings.gemini_api_key,
            settings.gemini_model,
            settings.ai_timeout,
            settings.gemini_thinking_level,
        )
    raise AIConfigError("provider")
