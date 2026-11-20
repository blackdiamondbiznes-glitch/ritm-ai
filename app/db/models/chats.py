"""Connected chats and their content profiles."""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatType(str, enum.Enum):
    """Telegram chat kinds the bot can join."""

    CHANNEL = "channel"
    GROUP = "group"
    SUPERGROUP = "supergroup"


def _values(enum_cls: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_cls]


class Chat(Base):
    """A channel or group linked to one owner."""

    __tablename__ = "chats"
    __table_args__ = (
        Index("ix_chats_owner_id", "owner_id"),
        Index("ix_chats_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    type: Mapped[ChatType] = mapped_column(
        Enum(ChatType, name="chat_type", native_enum=True, values_callable=_values),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    discussion_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    trial_consumed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    admins_can_edit: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatProfile(Base):
    """Niche and voice settings used later by content modules."""

    __tablename__ = "chat_profiles"

    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), primary_key=True)
    niche_code: Mapped[str] = mapped_column(String(200), nullable=False)
    niche_description: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="uz", server_default="uz")
    tone: Mapped[str] = mapped_column(String(32), nullable=False)
    audience_level: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Tashkent", server_default="Asia/Tashkent"
    )
    content_guidelines: Mapped[str | None] = mapped_column(Text)
    banned_topics: Mapped[str | None] = mapped_column(Text)
    modules_enabled: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
