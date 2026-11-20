"""Validated model output. Anything else is rejected."""

import json

from pydantic import BaseModel, Field

from app.ai.errors import AIOutputError

_BODY_MAX = 900


class DailyPost(BaseModel):
    """One plain-text channel post."""

    body: str = Field(min_length=1, max_length=_BODY_MAX)


class QuizCard(BaseModel):
    """Two to ten different options and one correct index."""

    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)
    correct: int = Field(ge=0, le=9)
    explanation: str | None = Field(default=None, max_length=200)

    def model_post_init(self, context: object) -> None:
        cleaned = [_option(item) for item in self.options]
        if len(set(cleaned)) < len(cleaned):
            raise ValueError("dup")
        if self.correct >= len(cleaned):
            raise ValueError("index")
        object.__setattr__(self, "options", cleaned)
        note = (self.explanation or "").strip()
        object.__setattr__(self, "explanation", note or None)


class QuizBatch(BaseModel):
    """Two or three quizzes from one admin post."""

    questions: list[QuizCard] = Field(min_length=2, max_length=3)


def load_daily_post(raw: str) -> DailyPost:
    """Parse a model reply. Fenced JSON is accepted; other shapes are not."""
    try:
        return DailyPost.model_validate(_object(raw))
    except ValueError as exc:
        raise AIOutputError("schema") from exc


def load_quiz(raw: str) -> QuizCard:
    """Parse a quiz reply. Same fence rules as a daily post."""
    try:
        return QuizCard.model_validate(_object(raw))
    except ValueError as exc:
        raise AIOutputError("schema") from exc


def load_quiz_batch(raw: str) -> QuizBatch:
    """Parse a 2–3 question admin-post reply."""
    try:
        return QuizBatch.model_validate(_object(raw))
    except ValueError as exc:
        raise AIOutputError("schema") from exc


def _object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIOutputError("json") from exc
    if not isinstance(data, dict):
        raise AIOutputError("shape")
    return data


def _option(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("option")
    text = value.strip()
    if not text or len(text) > 100:
        raise ValueError("option")
    return text
