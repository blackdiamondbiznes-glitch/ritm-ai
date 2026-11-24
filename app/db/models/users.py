"""Owner accounts. One row per Telegram user."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """A person who talks to the bot. Owners and members share this table."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "account_role IS NULL OR account_role IN ('teacher', 'student', 'community_owner')",
            name="ck_users_account_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(256))
    account_role: Mapped[str | None] = mapped_column(String(32))
    username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str] = mapped_column(String(8), default="uz", server_default="uz")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    trial_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_founder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    founder_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fake_receipts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    payments_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ui_language_set: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notify_reports: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_expiry: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    default_timezone: Mapped[str | None] = mapped_column(String(64))
    cabinet_niche: Mapped[str | None] = mapped_column(String(16))
    # Shown to students instead of the Telegram name. Empty means "use full_name".
    teacher_name: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
