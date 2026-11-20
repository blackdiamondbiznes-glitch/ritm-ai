"""Locale lookup. All user-facing strings live in locales/*.json."""

import json
from functools import lru_cache
from pathlib import Path

_LOCALES = Path(__file__).resolve().parent / "locales"
_FALLBACK = "uz"


@lru_cache
def _load(locale: str) -> dict[str, str]:
    path = _LOCALES / f"{locale}.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"locale {locale} is not an object")
    return {str(key): str(value) for key, value in data.items()}


def t(key: str, locale: str | None = None, **params: object) -> str:
    """Return a translated string. Missing keys fall back to Uzbek, then the key.

    The language code is `locale` (often passed positionally). Format fields
    may use any name, including `lang`, without colliding with that argument.
    """
    language = locale if locale in {"uz", "ru", "en"} else _FALLBACK
    template = _load(language).get(key) or _load(_FALLBACK).get(key) or key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template
