"""Locale files share one key set. Handlers must not invent strings."""

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1] / "app" / "locales"


def test_locale_keys_match() -> None:
    tables = {
        name: json.loads((_ROOT / name).read_text(encoding="utf-8"))
        for name in ("uz.json", "ru.json", "en.json")
    }
    uz_keys = set(tables["uz.json"])
    assert uz_keys == set(tables["ru.json"])
    assert uz_keys == set(tables["en.json"])
    assert "menu_title" in uz_keys
    assert all(isinstance(value, str) and value.strip() for value in tables["uz.json"].values())
