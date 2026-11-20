"""Wizard step transitions kept out of the router module."""

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from app.bot.copy import summary_text
from app.bot.keyboards.wizard import (
    audience_kb,
    niche_kb,
    summary_kb,
    text_step_kb,
    timezone_kb,
    tone_kb,
)
from app.bot.states import ProfileSG
from app.bot.view import show_screen, show_step
from app.i18n import t


async def take_text(
    message: Message,
    state: FSMContext,
    lang: str,
    field: str,
    limit: int,
    next_key: str,
    next_state: State,
) -> None:
    """Store a text answer or show a length error on the same screen."""
    text = (message.text or "").strip()
    if text.startswith("/"):
        return
    if not text:
        await show_step(message, state, t("input_empty", lang), text_step_kb(lang))
        return
    if len(text) > limit:
        await show_step(message, state, t("input_long", lang, max=limit), text_step_kb(lang))
        return
    await state.update_data(**{field: text})
    await state.set_state(next_state)
    markup = tone_kb(lang) if next_key == "wizard_tone" else text_step_kb(lang)
    await show_step(message, state, t(next_key, lang), markup)


async def show_summary(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """Review screen."""
    await state.set_state(ProfileSG.summary)
    data = await state.get_data()
    await show_screen(callback, summary_text(data, lang), summary_kb(lang))


async def show_timezone(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """Timezone step, using the value already stored in FSM data."""
    await state.set_state(ProfileSG.timezone)
    data = await state.get_data()
    zone = str(data.get("timezone") or "Asia/Tashkent")
    await show_screen(callback, t("wizard_tz", lang, tz=zone), timezone_kb(lang))


async def show_niche(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """First wizard step."""
    await state.set_state(ProfileSG.niche)
    await show_screen(callback, t("wizard_niche", lang), niche_kb(lang))


async def jump_back(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
    current: str | None,
) -> None:
    """Move one step backward."""
    if current == ProfileSG.tone.state:
        await state.set_state(ProfileSG.description)
        await show_screen(callback, t("wizard_desc", lang), text_step_kb(lang))
        return
    if current == ProfileSG.audience.state:
        await state.set_state(ProfileSG.tone)
        await show_screen(callback, t("wizard_tone", lang), tone_kb(lang))
        return
    if current == ProfileSG.language.state:
        await state.set_state(ProfileSG.audience)
        await show_screen(callback, t("wizard_audience", lang), audience_kb(lang))
        return
    await show_timezone(callback, state, lang)
