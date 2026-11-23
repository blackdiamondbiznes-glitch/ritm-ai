"""Environment settings. Secrets never have defaults that look real."""

import hashlib
import hmac
from datetime import time
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db.url import normalize_database_url
from app.services.pricing import parse_period_discounts

TELEGRAM_MODES = ("polling", "webhook", "off")
WEBHOOK_PREFIX = "/tg/"


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    database_url: str
    super_admin_ids: str = ""
    trial_days: int = 5
    throttle_seconds: float = 0.5
    default_timezone: str = "Asia/Tashkent"
    log_level: str = "INFO"
    pending_ttl_hours: int = Field(default=24)
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ai_timeout: float = 120
    gemini_thinking_level: str = "low"
    job_tick_seconds: int = 30
    send_gap_seconds: float = 0.05
    admin_post_min_chars: int = 200
    admin_post_quiz_delay_seconds: int = 600
    points_per_correct_answer: int = 10
    leaderboard_announce_time: str = "09:00"
    payment_card_number: str = ""
    payment_card_holder: str = ""
    payment_card_type: str = ""
    payment_card2_number: str = ""
    payment_card2_holder: str = ""
    payment_card2_type: str = ""
    founder_slots: int = 20
    support_username: str = ""
    payment_terms_version: str = "2026-11-v1"
    payment_review_hours: int = 12
    payment_draft_ttl_hours: int = 24
    payment_fake_block_after: int = 2
    period_discounts: str = "3:7,12:15"
    backup_dir: str = "./backups"
    backup_retention_days: int = 14
    # Daily pg_dump sent to every SUPER_ADMIN_IDS chat (Render has no free backups).
    backup_enabled: bool = True
    backup_time: str = "04:00"
    backup_max_mb: int = 45
    backup_timeout_seconds: int = 600
    alert_cooldown_seconds: int = 300
    health_port: int = 8080
    health_file: str = "/tmp/ritm-health"
    health_stale_seconds: int = 120
    webapp_port: int = 8081
    webapp_url: str = ""
    webapp_auth_max_age: int = 86400
    webapp_session_ttl: int = 43200
    webapp_session_secret: str = ""
    # polling: long polling (local Docker). webhook: Telegram pushes updates to
    # <public url>/tg/<secret> (Render). off: no Telegram updates, no scheduled
    # jobs, no menu/commands changes; only the Mini App and health run (staging).
    telegram_mode: str = "polling"
    webhook_base_url: str = ""
    webhook_secret: str = ""
    # Private-chat HTML widgets (Bot API 10.4). Off sends the caption only.
    widgets_enabled: bool = True
    # Render injects PORT (the one public port) and RENDER_EXTERNAL_URL.
    port: int = 0
    render_external_url: str = ""

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("telegram_mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        mode = (value or "polling").strip().lower()
        if mode not in TELEGRAM_MODES:
            raise ValueError(f"TELEGRAM_MODE must be one of {', '.join(TELEGRAM_MODES)}")
        return mode

    @property
    def http_port(self) -> int:
        """Port for the Mini App server: Render's PORT when given, else WEBAPP_PORT."""
        return self.port if self.port > 0 else self.webapp_port

    @property
    def public_base_url(self) -> str | None:
        """Public HTTPS origin of this deployment, or None."""
        for raw in (self.webhook_base_url, self.webapp_url, self.render_external_url):
            url = raw.strip().rstrip("/")
            if url.startswith("https://"):
                return url
        return None

    @property
    def webhook_token(self) -> str:
        """Secret used in the webhook path and as Telegram's secret_token header.

        WEBHOOK_SECRET when set (A-Z, a-z, 0-9, _ and -), else derived from the bot token,
        so it is stable across restarts and never stored anywhere.
        """
        raw = self.webhook_secret.strip()
        if raw:
            if not (1 <= len(raw) <= 256) or not all(c.isalnum() or c in "_-" for c in raw):
                raise ValueError("WEBHOOK_SECRET may only use letters, digits, _ and -")
            return raw
        digest = hmac.new(self.bot_token.encode(), b"ritm-webhook", hashlib.sha256)
        return digest.hexdigest()[:48]

    @property
    def webhook_path(self) -> str:
        return f"{WEBHOOK_PREFIX}{self.webhook_token}"

    @property
    def webhook_url(self) -> str | None:
        """Full webhook URL, or None when there is no public HTTPS origin."""
        base = self.public_base_url
        return f"{base}{self.webhook_path}" if base else None

    @property
    def support_handle(self) -> str:
        """Support username without '@', or '' when unset or malformed."""
        raw = self.support_username.strip().removeprefix("@").removeprefix("https://t.me/")
        ok = 5 <= len(raw) <= 32 and all(c.isalnum() or c == "_" for c in raw)
        return raw if ok else ""

    @property
    def period_discount_map(self) -> dict[int, int]:
        """Month-to-percent period discounts, for example 3:7 and 12:15."""
        return parse_period_discounts(self.period_discounts)

    @property
    def leaderboard_clock(self) -> time:
        """Local time used when a chat first enables the weekly board."""
        raw = self.leaderboard_announce_time.strip()
        try:
            hours, minutes = raw.split(":", 1)
            return time(int(hours), int(minutes))
        except ValueError:
            return time(9, 0)

    @property
    def backup_clock(self) -> time:
        """Asia/Tashkent time after which the daily backup runs."""
        try:
            hours, minutes = self.backup_time.strip().split(":", 1)
            return time(int(hours), int(minutes))
        except ValueError:
            return time(4, 0)

    @property
    def admin_ids(self) -> frozenset[int]:
        """Telegram ids allowed to open the admin panel."""
        found: set[int] = set()
        for part in self.super_admin_ids.split(","):
            text = part.strip()
            if not text:
                continue
            found.add(int(text))
        return frozenset(found)

    @property
    def public_webapp_url(self) -> str | None:
        """HTTPS Mini App origin, or None when the menu button must stay hidden."""
        for raw in (self.webapp_url, self.render_external_url):
            url = raw.strip().rstrip("/")
            if url.startswith("https://"):
                return url
        return None


@lru_cache
def get_settings() -> Settings:
    """Return the process settings object."""
    return Settings()
