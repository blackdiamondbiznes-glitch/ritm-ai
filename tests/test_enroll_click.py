"""A registration tap in a group enrolls the member and answers there."""

from aiogram import Dispatcher, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import AnswerCallbackQuery, SendMessage
from app.bot.callbacks import EnrollCB
from app.bot.keyboards.enroll import enroll_keyboard
from app.bot.routers import setup_routers
from app.bot.routers.enroll import on_group_enroll
from app.db.models.users import User
from tests.test_view import _Bot, _callback, _message, _of


def test_registration_button_is_a_callback() -> None:
    button = enroll_keyboard("uz", "abc123def0").inline_keyboard[0][0]
    assert button.url is None
    assert button.callback_data == EnrollCB(c="abc123def0").pack()
    assert "yozilaman" in button.text


def _release_routers() -> None:
    import app.bot.routers as package

    for name in dir(package):
        router = getattr(getattr(package, name, None), "router", None)
        if isinstance(router, Router):
            router._parent_router = None


def _detach(router: Router) -> None:
    for child in list(router.sub_routers):
        _detach(child)
        child._parent_router = None
    router.sub_routers.clear()


def test_group_signup_is_not_limited_to_private_chats() -> None:
    _release_routers()
    dispatcher = Dispatcher()
    try:
        setup_routers(dispatcher)
        assert any(item.name == "enroll" for item in dispatcher.sub_routers)
        private = next(item for item in dispatcher.sub_routers if item.name == "private")
        assert all(item.name != "enroll" for item in private.sub_routers)
    finally:
        _detach(dispatcher)
        _release_routers()


class _Grades:
    def __init__(self, result: str = "ok") -> None:
        self.result = result
        self.calls: list[tuple[str, int, str]] = []

    async def enroll(self, code: str, telegram_id: int, full_name: str, notify=None) -> str:
        self.calls.append((code, telegram_id, full_name))
        if notify is not None and self.result == "pending":
            await notify(
                type("Owner", (), {"telegram_id": 1, "language_code": "uz"})(), full_name, "A"
            )
        return self.result

    async def describe(self, kind: str, code: str) -> tuple[str | None, str | None]:
        return "Ingliz A1", "Malika <opa>"


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _TalkBot(_Bot):
    async def send_message(self, chat_id: int, text: str, reply_markup: object = None) -> object:
        return await self(
            SendMessage(chat_id=chat_id, text=text, reply_markup=reply_markup)  # type: ignore[arg-type]
        )


class _QuietBot(_TalkBot):
    async def send_message(self, chat_id: int, text: str, reply_markup: object = None) -> object:
        method = SendMessage(chat_id=chat_id, text=text, reply_markup=reply_markup)  # type: ignore[arg-type]
        raise TelegramForbiddenError(method=method, message="bot was blocked by the user")


async def test_tap_saves_the_membership_and_answers() -> None:
    bot = _TalkBot()
    grades = _Grades()
    session = _Session()
    user = User(id=3, telegram_id=50, full_name="Ali Vali", language_code="uz")
    await on_group_enroll(
        _callback(bot, _message(bot)),
        EnrollCB(c="abc123def0"),
        session,  # type: ignore[arg-type]
        user,
        grades,  # type: ignore[arg-type]
        "uz",
        False,
        bot,  # type: ignore[arg-type]
    )
    assert grades.calls == [("abc123def0", 50, "Ali Vali")]
    assert session.commits == 1
    alert = _of(bot, AnswerCallbackQuery)[0]
    assert alert.show_alert is True
    assert "yozildingiz" in alert.text
    sent = _of(bot, SendMessage)
    assert sent[0].chat_id == 50
    assert "«Ingliz A1»" in sent[0].text
    assert "Malika &lt;opa&gt;" in sent[0].text


async def test_a_blocked_chat_still_gets_the_group_alert() -> None:
    bot = _QuietBot()
    session = _Session()
    user = User(id=3, telegram_id=50, full_name="Ali", language_code="uz")
    await on_group_enroll(
        _callback(bot, _message(bot)),
        EnrollCB(c="abc123def0"),
        session,  # type: ignore[arg-type]
        user,
        _Grades("already"),  # type: ignore[arg-type]
        "uz",
        False,
        bot,  # type: ignore[arg-type]
    )
    assert session.commits == 1
    alert = _of(bot, AnswerCallbackQuery)[0]
    assert "yozilgansiz" in alert.text
