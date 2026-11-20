"""Usage counters: monthly (limits) and daily (charts)."""

from datetime import date, datetime

from sqlalchemy import (
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


class UsageCounter(Base):
    """One counter per owner, metric and calendar month (`YYYY-MM`)."""

    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("owner_id", "metric", "period_key", name="uq_usage_owner_metric_period"),
        Index("ix_usage_counters_owner_id", "owner_id"),
        CheckConstraint("metric = 'ai_generation'", name="metric_known"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(7), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UsageDaily(Base):
    """Same metric, one row per owner and Tashkent calendar day. Written since 0011."""

    __tablename__ = "usage_daily"
    __table_args__ = (Index("ix_usage_daily_day", "day"),)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
