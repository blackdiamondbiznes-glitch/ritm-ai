"""When a module should run for one chat."""

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Schedule(Base):
    """Local time and weekdays for one module on one chat."""

    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("chat_id", "module", name="uq_schedules_chat_module"),
        Index("ix_schedules_chat_id", "chat_id"),
        Index("ix_schedules_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    time_of_day: Mapped[time] = mapped_column(Time, nullable=False)
    days_of_week: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
