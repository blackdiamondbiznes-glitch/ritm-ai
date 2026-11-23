"""Profile wizard: summary TypeError regression and every step through Save."""

from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from app.bot.callbacks import WizardCB
from app.bot.copy import summary_text
from app.bot.routers import profile as router
from app.bot.states import ProfileSG
from app.db.models.chats import ChatProfile
from app.services.profiles import ProfileService
from tests.fakes import World, make_chat, make_user

_DESC = "Kanalingiz nima haqida va auditoriya kim ekanini yozamiz."


def apply_screen_stubs(monkeypatch) -> None:
    async def show_screen(callback, text, markup, *, alert=None, new=False):
        await callback.answer(alert, show_alert=bool(alert))
        message = getattr(callback, "message", None)
        if message is None:
            return
        message.markup = markup
        if new:
            message.news.append(text)
        else:
            message.edits.append(text)

    async def show_step(message, state, text, markup):
        await message.delete()
        message.edits.append(text)
        message.markup = markup

    modules = (
        "app.bot.view",
        "app.bot.wizard_nav",
        "app.bot.routers.profile",
        "app.bot.screens",
    )
    for module in modules:
        monkeypatch.setattr(f"{module}.show_screen", show_screen)
        if module in {"app.bot.view", "app.bot.wizard_nav"}:
            monkeypatch.setattr(f"{module}.show_step", show_step)


@pytest.fixture(autouse=True)
def _patch_screens(monkeypatch) -> None:
    apply_screen_stubs(monkeypatch)


def test_summary_text_does_not_pass_lang_twice() -> None:
    text = summary_text(
        {
            "niche_code": "edu",
            "niche_description": _DESC,
            "tone": "friendly",
            "audience_level": "beginner",
            "language": "uz",
            "timezone": "Asia/Tashkent",
        },
        "uz",
    )
    assert "Tekshiring" in text
    assert "O‘zbek" in text
    assert "Asia/Tashkent" in text
    assert "Do‘stona" in text


def _state() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=50, user_id=50))


class _Bot:
    def __init__(self) -> None:
        self.edits: list[str] = []
        self.news: list[str] = []

    async def edit_message_text(
        self, text: str, chat_id: int, message_id: int, reply_markup: object = None
    ) -> None:
        self.edits.append(text)


class _Message:
    def __init__(self, text: str = "", bot: _Bot | None = None) -> None:
        self.text = text
        self.message_id = 10
        self.chat = SimpleNamespace(id=50)
        self.from_user = SimpleNamespace(id=50)
        self.bot = bot or _Bot()
        self.edits: list[str] = []
        self.news: list[str] = []
        self.answers: list[str] = []
        self.deleted = False
        self.markup = None

    async def edit_text(self, text: str, reply_markup: object = None) -> None:
        self.edits.append(text)
        self.markup = reply_markup

    async def answer(self, text: str, reply_markup: object = None) -> SimpleNamespace:
        self.answers.append(text)
        return SimpleNamespace(message_id=11)

    async def delete(self) -> None:
        self.deleted = True


class _Callback:
    def __init__(self, message: _Message | None = None) -> None:
        self.message = message or _Message()
        self.from_user = SimpleNamespace(id=50)
        self.alerts: list[str] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        if text:
            self.alerts.append(text)


class _Profiles:
    def __init__(self) -> None:
        self.rows: dict[int, ChatProfile] = {}

    async def get(self, chat_id: int) -> ChatProfile | None:
        return self.rows.get(chat_id)

    async def upsert(self, chat_id: int, fields: dict[str, object]) -> ChatProfile:
        row = self.rows.get(chat_id)
        if row is None:
            row = ChatProfile(chat_id=chat_id, **fields)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
        self.rows[chat_id] = row
        return row


async def _world() -> tuple[World, ProfileService, _Callback, FSMContext]:
    world = World()
    owner = world.add_user(make_user(user_id=1, telegram_id=50))
    chat = make_chat(owner)
    chat.id = 7
    world.chats.rows.append(chat)
    repo = _Profiles()
    service = ProfileService(repo, world.access)
    return world, service, _Callback(), _state()


async def _walk(
    callback: _Callback,
    state: FSMContext,
    *,
    niche: str = "edu",
    custom: str | None = None,
    description: str = _DESC,
    tone: str = "friendly",
    audience: str = "beginner",
    language: str = "uz",
    keep_zone: bool = True,
    zone: str = "Asia/Tashkent",
) -> None:
    if custom is not None:
        await router.pick_niche(callback, WizardCB(a="niche", v="other"), state, "uz")
        assert await state.get_state() == ProfileSG.niche_custom.state
        await router.custom_niche(_Message(custom, callback.message.bot), state, "uz")
    else:
        await router.pick_niche(callback, WizardCB(a="niche", v=niche), state, "uz")
    await router.description(_Message(description, callback.message.bot), state, "uz")
    await router.pick_tone(callback, WizardCB(a="tone", v=tone), state, "uz")
    await router.pick_audience(callback, WizardCB(a="aud", v=audience), state, "uz")
    await router.pick_language(callback, WizardCB(a="lang", v=language), state, "uz")
    assert await state.get_state() == ProfileSG.timezone.state
    if keep_zone:
        await router.keep_zone(callback, state, "uz")
    else:
        await router.open_zones(callback, "uz")
        await router.pick_zone(callback, WizardCB(a="tz", v=zone), state, "uz")
    assert await state.get_state() == ProfileSG.summary.state
    assert callback.message.edits
    assert "Tekshiring" in callback.message.edits[-1]


async def test_full_wizard_keep_timezone_saves_profile() -> None:
    world, profiles, callback, state = await _world()
    owner = world.users.users[0]
    await router.begin_wizard(callback, state, "uz", 7, "Asia/Tashkent", banner=None)
    await _walk(callback, state)
    await router.save_profile(
        callback, state, "uz", False, owner, world.chats, profiles, world.access
    )
    saved = await profiles.get(7)
    assert saved is not None
    assert saved.niche_code == "edu"
    assert saved.niche_description == _DESC
    assert saved.tone == "friendly"
    assert saved.audience_level == "beginner"
    assert saved.language == "uz"
    assert saved.timezone == "Asia/Tashkent"
    assert "daily_content" in (saved.modules_enabled or [])
    assert await state.get_state() is None
    assert any("Profil saqlandi" in text for text in callback.message.news)
    assert not any("Profil saqlandi" in text for text in callback.message.edits)


async def test_wizard_custom_niche_and_timezone_change() -> None:
    world, profiles, callback, state = await _world()
    owner = world.users.users[0]
    await router.begin_wizard(callback, state, "uz", 7, "Asia/Tashkent", None)
    await _walk(callback, state, custom="Arab tili darslari", keep_zone=False, zone="Asia/Dubai")
    await router.save_profile(
        callback, state, "uz", False, owner, world.chats, profiles, world.access
    )
    saved = await profiles.get(7)
    assert saved is not None
    assert saved.niche_code == "Arab tili darslari"
    assert saved.timezone == "Asia/Dubai"
