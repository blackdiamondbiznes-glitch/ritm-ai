"""Dedup log for private reports and reminders."""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationLog(Base):
    """One row per owner, chat, kind and calendar day."""

    __tablename__ = "notifications_log"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "chat_key",
            "kind",
            "sent_on",
            name="uq_notifications_log_once",
        ),
        Index("ix_notifications_log_owner_id", "owner_id"),
        Index("ix_notifications_log_chat_id", "chat_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id"))
    chat_key: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_on: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
