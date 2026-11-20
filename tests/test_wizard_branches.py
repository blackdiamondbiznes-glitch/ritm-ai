"""More profile-wizard branches: choices, back, edit, validation."""

import pytest
from app.bot.callbacks import WizardCB
from app.bot.routers import profile as router
from app.bot.states import ProfileSG
from app.db.models.chats import ChatProfile
from app.services.profiles import AUDIENCES, LANGUAGES, PRESET_NICHES, TIMEZONES, TONES
from tests.fakes import NOW
from tests.test_wizard import (
    _DESC,
    _Callback,
    _Message,
    _state,
    _walk,
    _world,
    apply_screen_stubs,
)


@pytest.fixture(autouse=True)
def _patch_screens(monkeypatch) -> None:
    apply_screen_stubs(monkeypatch)


async def test_wizard_each_tone_audience_language_choice() -> None:
    for tone in TONES:
        for audience in AUDIENCES:
            for language in LANGUAGES:
                callback, state = _Callback(), _state()
                await router.begin_wizard(callback, state, "uz", 7, "Asia/Tashkent", None)
                await _walk(
                    callback,
                    state,
                    tone=tone,
                    audience=audience,
                    language=language,
                )
                data = await state.get_data()
                assert data["tone"] == tone
                assert data["audience_level"] == audience
                assert data["language"] == language
                assert "Tekshiring" in callback.message.edits[-1]


async def test_wizard_preset_niches_and_back_from_summary() -> None:
    callback, state = _Callback(), _state()
    await router.begin_wizard(callback, state, "uz", 7, "Asia/Tashkent", None)
    for niche in PRESET_NICHES:
        await router.pick_niche(callback, WizardCB(a="niche", v=niche), state, "uz")
        data = await state.get_data()
        assert data["niche_code"] == niche
        await router.go_back(callback, state, "uz")
        assert await state.get_state() == ProfileSG.niche.state
    await _walk(callback, state, niche="it")
    await router.go_back(callback, state, "uz")
    assert await state.get_state() == ProfileSG.timezone.state


async def test_wizard_rejects_empty_and_long_text() -> None:
    callback, state = _Callback(), _state()
    bot = callback.message.bot
    await router.begin_wizard(callback, state, "uz", 7, "Asia/Tashkent", None)
    await router.pick_niche(callback, WizardCB(a="niche", v="other"), state, "uz")
    await router.custom_niche(_Message("   ", bot), state, "uz")
    assert await state.get_state() == ProfileSG.niche_custom.state
    await router.custom_niche(_Message("x" * 201, bot), state, "uz")
    assert await state.get_state() == ProfileSG.niche_custom.state
    await router.custom_niche(_Message("Qisqa yo'nalish", bot), state, "uz")
    await router.description(_Message("", bot), state, "uz")
    assert await state.get_state() == ProfileSG.description.state
    await router.description(_Message("y" * 501, bot), state, "uz")
    assert await state.get_state() == ProfileSG.description.state


async def test_edit_profile_rerun_keeps_saved_values_and_saves() -> None:
    world, profiles, callback, state = await _world()
    owner = world.users.users[0]
    chat = world.chats.rows[0]
    existing = ChatProfile(
        chat_id=7,
        niche_code="fit",
        niche_description=_DESC,
        language="ru",
        tone="motiv",
        audience_level="high",
        timezone="Europe/Istanbul",
        modules_enabled=["daily_content"],
        updated_at=NOW,
    )
    await router.start_edit(callback, state, "uz", chat, existing, "Asia/Tashkent")
    data = await state.get_data()
    assert data["niche_code"] == "fit"
    assert data["timezone"] == "Europe/Istanbul"
    await _walk(
        callback,
        state,
        niche="fit",
        tone="motiv",
        audience="high",
        language="ru",
        keep_zone=True,
    )
    # keep_zone uses the zone already in FSM (Europe/Istanbul from start_edit,
    # then _walk's pick_language does not reset it; begin path set Asia/Tashkent
    # first... start_edit set Istanbul, _walk pick_niche overwrites niche but
    # not timezone. keep_zone keeps Istanbul.
    await router.save_profile(
        callback, state, "uz", False, owner, world.chats, profiles, world.access
    )
    saved = await profiles.get(7)
    assert saved is not None
    assert saved.timezone == "Europe/Istanbul"
    assert saved.tone == "motiv"
    assert saved.language == "ru"


async def test_all_listed_timezones_are_accepted() -> None:
    for zone in TIMEZONES:
        callback, state = _Callback(), _state()
        await router.begin_wizard(callback, state, "uz", 7, "Asia/Tashkent", None)
        await _walk(callback, state, keep_zone=False, zone=zone)
        data = await state.get_data()
        assert data["timezone"] == zone
