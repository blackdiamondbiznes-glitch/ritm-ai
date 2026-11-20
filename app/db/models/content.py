"""Posts and other texts the bot has stored for a chat."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContentKind(str, enum.Enum):
    """Why a text row exists. Later phases reuse the same table."""

    DAILY = "daily_content"
    ADMIN_POST = "admin_post"
    QUIZ_SOURCE = "quiz_source"


def _values(enum_cls: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_cls]


class ContentItem(Base):
    """A stored body. Telegram ids are filled after a successful send."""

    __tablename__ = "content_items"
    __table_args__ = (Index("ix_content_items_chat_id", "chat_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), nullable=False)
    kind: Mapped[ContentKind] = mapped_column(
        Enum(ContentKind, name="content_kind", native_enum=True, values_callable=_values),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
