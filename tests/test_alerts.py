"""Admin error alerts are rate-limited and never include message text."""

from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message, Update
from aiogram.types import User as TgUser
from app.bot.alerts import notify_admins, reset_alert_clock


class _Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def _event() -> ErrorEvent:
    user = TgUser(id=11, is_bot=False, first_name="Ada")
    chat = Chat(id=50, type="private")
    message = Message(message_id=3, date=0, chat=chat, text="secret body")
    callback = CallbackQuery(
        id="1", from_user=user, chat_instance="x", data="m:plan", message=message
    )
    update = Update(update_id=99, callback_query=callback)
    return ErrorEvent(update=update, exception=TypeError("boom"))


async def test_alerts_rate_limit_and_omit_the_message_body() -> None:
    reset_alert_clock()
    bot = _Bot()
    settings = type("S", (), {"admin_ids": frozenset({505}), "alert_cooldown_seconds": 300})()
    await notify_admins(_event(), bot, settings)
    await notify_admins(_event(), bot, settings)
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == 505
    text = bot.sent[0][1]
    assert "TypeError" in text
    assert "update_id=99" in text
    assert "secret body" not in text
    assert "boom" not in text
