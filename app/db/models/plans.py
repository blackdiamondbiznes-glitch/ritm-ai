"""Sellable plans. Prices and limits live here, never in code."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Plan(Base):
    """A plan row. `vertical=None` keeps a legacy cross-product plan."""

    __tablename__ = "plans"
    __table_args__ = (Index("ix_plans_vertical", "vertical"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    vertical: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    price_uzs: Mapped[int] = mapped_column(Integer, nullable=False)
    founder_price_uzs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    period_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    max_chats: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tutor_groups: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2"
    )
    max_tutor_students: Mapped[int] = mapped_column(
        Integer, nullable=False, default=40, server_default="40"
    )
    max_tutor_notifications_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ai_generations_per_month: Mapped[int] = mapped_column(Integer, nullable=False)
    modules: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
