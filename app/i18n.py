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


def normalize_uz(text: str) -> str:
    """o‘ and g‘ use U+2018. Any other letter plus an apostrophe is U+02BC."""
    marks = "'\u2019\u2018\u02bc\u02bb`\u00b4"
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if char.isascii() and char.isalpha() and nxt and nxt in marks:
            mark = "\u2018" if char.lower() in {"o", "g"} else "\u02bc"
            out.append(char + mark)
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def t(key: str, locale: str | None = None, **params: object) -> str:
    """Return a translated string. Missing keys fall back to Uzbek, then the key.

    The language code is `locale` (often passed positionally). Format fields
    may use any name, including `lang`, without colliding with that argument.
    """
    language = locale if locale in {"uz", "ru", "en"} else _FALLBACK
    template = _load(language).get(key) or _load(_FALLBACK).get(key) or key
    if params:
        try:
            template = template.format(**params)
        except (KeyError, IndexError, ValueError):
            return normalize_uz(template) if language == "uz" else template
    return normalize_uz(template) if language == "uz" else template
