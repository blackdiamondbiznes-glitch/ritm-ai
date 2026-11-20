"""Stale payment tokens and leftover inline buttons."""

from app.bot.routers.fallback import stale_button
from app.bot.routers.payments import is_stale_period_token, parse_period_token
from app.i18n import t


def test_current_period_token_parses() -> None:
    assert parse_period_token("pro-12") == ("pro", 12)
    assert parse_period_token("start-3") == ("start", 3)
    assert parse_period_token("agency-1") == ("agency", 1)
    assert is_stale_period_token("pro-12") is False


def test_old_colon_period_token_is_stale() -> None:
    assert parse_period_token("pro:12") is None
    assert is_stale_period_token("pro:12") is True
    assert parse_period_token("p:months:pro:12") is None
    assert is_stale_period_token("p:months:pro:12") is True


def test_stale_button_copy_is_clear() -> None:
    assert t("button_stale", "uz") == "Bu tugma eskirgan, /menu ni bosing"
    assert "/menu" in t("button_stale", "ru")
    assert "/menu" in t("button_stale", "en")


class _Callback:
    def __init__(self) -> None:
        self.alert = None

    async def answer(self, text: str, show_alert: bool = False) -> None:
        self.alert = (text, show_alert)


async def test_stale_callback_fallback_shows_the_notice() -> None:
    callback = _Callback()
    await stale_button(callback, "uz")  # type: ignore[arg-type]
    assert callback.alert == ("Bu tugma eskirgan, /menu ni bosing", True)
