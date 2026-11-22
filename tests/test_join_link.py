"""A ranking link is recognized from /start and from a pasted t.me URL."""

from app.bot.routers.join import code_from_text, enroll_code_from_text


def test_code_comes_from_start_or_a_full_link() -> None:
    assert code_from_text("/start join_abc123") == "abc123"
    assert code_from_text("/start@ritm_airobot join_abc123") == "abc123"
    assert code_from_text("https://t.me/ritm_airobot?start=join_abc123") == "abc123"
    assert code_from_text("/start") is None
    assert enroll_code_from_text("/start enroll_abc123") == "abc123"
    assert enroll_code_from_text("https://t.me/ritm_airobot?start=enroll_abc123") == "abc123"
    assert enroll_code_from_text("/start join_abc123") is None
    assert code_from_text("https://t.me/ritm_airobot") is None
