"""A quiz and one answer per user. Matches the master schema."""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuizMode(str, enum.Enum):
    """Where the member answers. Channels cannot host a non-anonymous poll."""

    DEEPLINK = "private_deeplink"
    NATIVE = "group_native"


class Quiz(Base):
    """Question stored for grading. The channel post does not reveal the answer."""

    __tablename__ = "quizzes"
    __table_args__ = (
        Index("ix_quizzes_chat_id", "chat_id"),
        Index("ix_quizzes_content_item_id", "content_item_id"),
        CheckConstraint("correct_index >= 0 AND correct_index <= 9", name="ck_quizzes_correct"),
        CheckConstraint(
            "mode IN ('private_deeplink', 'group_native')",
            name="ck_quizzes_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), nullable=False)
    content_item_id: Mapped[int | None] = mapped_column(ForeignKey("content_items.id"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    telegram_poll_id: Mapped[str | None] = mapped_column(String(64))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QuizAnswer(Base):
    """One choice per user. A second answer does not replace the first."""

    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("quiz_id", "user_id", name="uq_quiz_answers_user"),
        Index("ix_quiz_answers_quiz_id", "quiz_id"),
        Index("ix_quiz_answers_user_id", "user_id"),
        Index(
            "ix_quiz_answers_quiz_answered",
            "quiz_id",
            "answered_at",
            postgresql_include=["user_id", "is_correct"],
        ),
        CheckConstraint("chosen_index >= 0 AND chosen_index <= 9", name="ck_quiz_answers_choice"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    chosen_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
