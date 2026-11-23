"""Registration replies stay short enough for a Telegram alert."""

import json
from pathlib import Path

from app.bot.enroll_notice import ask_text

_LOCALES = Path(__file__).resolve().parents[1] / "app" / "locales"


def test_every_enroll_string_fits_in_an_alert() -> None:
    for name in ("uz.json", "ru.json", "en.json"):
        data = json.loads((_LOCALES / name).read_text(encoding="utf-8"))
        for key, value in data.items():
            if key.startswith("enroll_"):
                assert len(value) <= 200, (name, key, len(value))


def test_teacher_notice_escapes_html() -> None:
    text = ask_text("uz", "<b>", "A & B")
    assert "<b>" not in text
    assert "&lt;b&gt;" in text
    assert "&amp;" in text
    assert "Yangi so" in text
