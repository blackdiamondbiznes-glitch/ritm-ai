"""One JSON POST helper. Callers pick the text out of the body."""

from collections.abc import Callable

import httpx

from app.ai.errors import AIConfigError, AIOutputError, AITransient


async def post_json(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: float,
    pick: Callable[[object], str],
) -> str:
    """POST JSON and return the model text. Never logs the body or the key."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise AITransient("timeout") from exc
    except httpx.HTTPError as exc:
        raise AITransient("network") from exc
    return _read(response, pick)


def _read(response: httpx.Response, pick: Callable[[object], str]) -> str:
    if response.status_code in {401, 403}:
        raise AIConfigError("auth")
    if response.status_code == 429 or response.status_code >= 500:
        raise AITransient(f"http_{response.status_code}")
    if response.status_code >= 400:
        raise AIOutputError("http")
    try:
        return pick(response.json())
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIOutputError("shape") from exc
