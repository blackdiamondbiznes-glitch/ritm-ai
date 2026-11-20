"""Gemini Flash-class provider. The key travels in a header, not the URL."""

from app.ai.errors import AIConfigError
from app.ai.http import post_json


class GeminiProvider:
    """Google Gemini generateContent."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        thinking_level: str = "low",
    ) -> None:
        self.model = model
        self._key = api_key
        self._timeout = timeout
        self._thinking_level = thinking_level.strip()

    async def complete(self, prompt: str, temperature: float = 0.9) -> str:
        """Return the raw model text."""
        if not self._key:
            raise AIConfigError("missing_key")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config(self._thinking_level, temperature),
        }
        headers = {"x-goog-api-key": self._key}
        return await post_json(url, payload, headers, self._timeout, _pick)


def generation_config(thinking_level: str, temperature: float = 0.9) -> dict[str, object]:
    """Build generateContent generationConfig. Empty thinking_level omits the field."""
    config: dict[str, object] = {
        "temperature": temperature,
        "responseMimeType": "application/json",
    }
    level = thinking_level.strip()
    if level:
        # generateContent REST: generationConfig.thinkingConfig.thinkingLevel
        # (Interactions API uses generation_config.thinking_level instead.)
        config["thinkingConfig"] = {"thinkingLevel": level}
    return config


def _pick(body: object) -> str:
    if not isinstance(body, dict):
        raise TypeError("body")
    candidates = body["candidates"]
    if not isinstance(candidates, list):
        raise TypeError("candidates")
    content = candidates[0]["content"]
    parts = content["parts"]
    if not isinstance(parts, list):
        raise TypeError("parts")
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("thought") is True:
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
    if not texts:
        raise TypeError("text")
    return texts[-1]
