"""One stored widget message so later edits can find it."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WidgetMessage(Base):
    """The last widget of this kind sent to one chat for one ref."""

    __tablename__ = "tutor_widget_messages"
    __table_args__ = (
        UniqueConstraint("kind", "ref_id", "telegram_id", name="uq_tutor_widget_messages_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
