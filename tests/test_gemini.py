"""Gemini request config and thought-part parsing."""

from app.ai.gemini import _pick, generation_config


def test_generation_config_includes_thinking_level() -> None:
    config = generation_config("low")
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert config["responseMimeType"] == "application/json"
    assert config["temperature"] == 0.9


def test_generation_config_omits_thinking_when_empty() -> None:
    config = generation_config("  ")
    assert "thinkingConfig" not in config


def test_pick_skips_thought_parts() -> None:
    body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "internal notes", "thought": True},
                        {"text": '{"body":"Salom"}'},
                    ]
                }
            }
        ]
    }
    assert _pick(body) == '{"body":"Salom"}'
