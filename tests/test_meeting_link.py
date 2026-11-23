"""Online lesson link: URL rules and the reminder button. HTTP checks sit with the API tests."""

from datetime import UTC, datetime, timedelta

import pytest
from app.bot.widgets.markup import with_join
from app.services.clock import TASHKENT
from app.services.meeting_link import URL_MAX, clean_meeting_url
from tests.notify_world import CHAT_TG, STUDENT, handler, open_db, service, world

ZOOM = "https://us05web.zoom.us/j/123456789?pwd=abc"


def test_clean_meeting_url_keeps_http_links_only() -> None:
    assert clean_meeting_url(f"  {ZOOM} ") == ZOOM
    assert (
        clean_meeting_url("http://meet.google.com/abc-defg-hij")
        == "http://meet.google.com/abc-defg-hij"
    )
    assert clean_meeting_url("") is None
    assert clean_meeting_url(None) is None
    for bad in (
        "javascript:alert(1)",
        "ftp://files.example.com/x",
        "zoom.us/j/1",
        "https://",
        "https://localhost/x",
        "https://zoom.us/j/1 2",
        "https://zoom.us/" + "a" * URL_MAX,
        42,
    ):
        with pytest.raises(ValueError):
            clean_meeting_url(bad)


def test_with_join_puts_the_url_button_first() -> None:
    markup = with_join(None, ZOOM, "uz")
    assert markup is not None
    button = markup.inline_keyboard[0][0]
    assert button.url == ZOOM and button.text == "Darsga kirish"
    assert with_join(None, None, "uz") is None
    assert with_join(None, "javascript:x", "uz") is None


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent.append((chat_id, text, kwargs.get("reply_markup")))


@pytest.fixture
async def db():
    async for factory in open_db():
        yield factory


async def test_lesson_reminder_carries_the_join_button(db) -> None:
    at = datetime(2026, 11, 21, 18, 0, tzinfo=TASHKENT)
    now = at - timedelta(hours=1)
    async with db() as session:
        made = await world(session, now, start=at)
        made["lesson"].meeting_url = ZOOM
        await session.flush()
        await service(session, now).enqueue_due(now)
        from app.db.models.jobs import Job
        from sqlalchemy import select

        jobs = [
            row
            for row in (
                await session.execute(select(Job).where(Job.type == "tutor_notify"))
            ).scalars()
            if row.payload.get("owner_id") == made["user"].id
        ]
        assert {job.payload["params"]["meeting_url"] for job in jobs} == {ZOOM}
        bot = _Bot()
        worker = handler(session, bot, now.astimezone(UTC))
        for job in jobs:
            await worker.handle(job)
        assert {chat for chat, _text, _markup in bot.sent} == {STUDENT, CHAT_TG}
        for _chat, text, markup in bot.sent:
            assert ZOOM not in text
            assert markup.inline_keyboard[0][0].url == ZOOM
