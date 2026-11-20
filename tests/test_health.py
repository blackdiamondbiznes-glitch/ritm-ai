"""Health report text includes timings and never includes secrets."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.bot.routers.admin_health import render_health
from app.services.health import HealthReport, HealthService


def test_render_health_uses_locale_and_omits_keys() -> None:
    report = HealthReport(
        db_ok=True,
        db_ms=12,
        last_tick_at=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        tick_age_seconds=45,
        provider="gemini",
        model="gemini-3.6-flash",
        ai_configured=True,
        pending_jobs=2,
        failed_24h=1,
    )
    text = render_health(report, "uz")
    assert "12 ms" in text
    assert "45 s" in text
    assert "gemini-3.6-flash" in text
    assert "Navbatda: 2" in text
    assert "1" in text
    assert "AIza" not in text
    assert "sk-" not in text


def test_ai_configured_follows_the_selected_provider() -> None:
    service = HealthService(
        session=SimpleNamespace(),
        settings=SimpleNamespace(
            ai_provider="gemini",
            gemini_api_key="x",
            gemini_model="gemini-3.6-flash",
            openai_api_key="",
            openai_model="gpt-4o-mini",
        ),
    )
    assert service._ai_configured() is True
    service = HealthService(
        session=SimpleNamespace(),
        settings=SimpleNamespace(
            ai_provider="gemini",
            gemini_api_key="  ",
            gemini_model="gemini-3.6-flash",
            openai_api_key="sk",
            openai_model="gpt-4o-mini",
        ),
    )
    assert service._ai_configured() is False
