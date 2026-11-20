"""OpenAI chat completions provider."""

from app.ai.errors import AIConfigError
from app.ai.http import post_json


class OpenAIProvider:
    """JSON-mode chat completion."""

    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.model = model
        self._key = api_key
        self._timeout = timeout

    async def complete(self, prompt: str, temperature: float = 0.9) -> str:
        """Return the raw model text."""
        if not self._key:
            raise AIConfigError("missing_key")
        payload: dict[str, object] = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        url = "https://api.openai.com/v1/chat/completions"
        return await post_json(url, payload, headers, self._timeout, _pick)


def _pick(body: object) -> str:
    if not isinstance(body, dict):
        raise TypeError("body")
    choices = body["choices"]
    if not isinstance(choices, list):
        raise TypeError("choices")
    content = choices[0]["message"]["content"]
    if not isinstance(content, str):
        raise TypeError("content")
    return content
