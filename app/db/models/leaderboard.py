"""Weekly leaderboard periods and frozen score rows."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS_OPEN = "open"
STATUS_ANNOUNCED = "announced"


class LeaderboardPeriod(Base):
    """One Monday–Sunday window for one chat."""

    __tablename__ = "leaderboard_periods"
    __table_args__ = (
        UniqueConstraint("chat_id", "period_start", name="uq_leaderboard_periods_chat_start"),
        Index("ix_leaderboard_periods_chat_id", "chat_id"),
        CheckConstraint("status IN ('open', 'announced')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LeaderboardEntry(Base):
    """Frozen points for one member in one period."""

    __tablename__ = "leaderboard_entries"
    __table_args__ = (
        UniqueConstraint("period_id", "user_id", name="uq_leaderboard_entries_period_user"),
        Index("ix_leaderboard_entries_period_id", "period_id"),
        Index("ix_leaderboard_entries_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("leaderboard_periods.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_answers: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
