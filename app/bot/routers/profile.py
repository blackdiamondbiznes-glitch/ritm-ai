"""Profile wizard. Each step edits the same message."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import WizardCB
from app.bot.guard import manages
from app.bot.keyboards.menu import main_menu
from app.bot.keyboards.wizard import (
    audience_kb,
    language_kb,
    niche_kb,
    text_step_kb,
    timezone_list_kb,
)
from app.bot.screens import render_card
from app.bot.states import ProfileSG
from app.bot.view import remember_anchor, show_screen
from app.bot.wizard_nav import jump_back, show_niche, show_summary, show_timezone, take_text
from app.db.models.chats import Chat, ChatProfile
from app.db.models.users import User
from app.db.repositories.chats import ChatRepository
from app.i18n import t
from app.services.access import AccessService
from app.services.profiles import (
    PRESET_NICHES,
    TIMEZONES,
    ProfileError,
    ProfileInput,
    ProfileService,
)

router = Router(name="profile")
_ERRORS = {"long": "input_long", "empty": "input_empty", "choice": "input_bad"}


async def begin_wizard(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
    chat_id: int,
    timezone: str,
    banner: str | None,
) -> None:
    """Enter the wizard on the niche step."""
    await state.set_state(ProfileSG.niche)
    await state.set_data(remember_anchor(callback, {"chat_id": chat_id, "timezone": timezone}))
    text = t("wizard_niche", lang)
    if banner:
        text = f"{banner}\n\n{text}"
    await show_screen(callback, text, niche_kb(lang))


async def start_edit(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
    chat: Chat,
    profile: ChatProfile | None,
    timezone: str,
) -> None:
    """Re-open the wizard with the saved answers."""
    data: dict[str, object] = {"chat_id": chat.id, "timezone": timezone}
    if profile is not None:
        data.update(
            niche_code=profile.niche_code,
            niche_description=profile.niche_description,
            tone=profile.tone,
            audience_level=profile.audience_level,
            language=profile.language,
            timezone=profile.timezone,
            custom=profile.niche_code not in PRESET_NICHES,
        )
    await state.set_state(ProfileSG.niche)
    await state.set_data(remember_anchor(callback, data))
    await show_screen(callback, t("wizard_niche", lang), niche_kb(lang))


@router.callback_query(WizardCB.filter(F.a == "cancel"))
async def cancel_wizard(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    chats: ChatRepository,
    current_user: User,
    access: AccessService,
    profiles: ProfileService,
) -> None:
    """Cancel returns to the chat card when the chat already exists."""
    data = await state.get_data()
    await state.clear()
    chat = await _chat_from(data, chats)
    if chat is not None and manages(chat, current_user, is_super_admin):
        await render_card(callback, chat, current_user, access, profiles, lang)
        return
    await show_screen(callback, t("cancelled", lang), main_menu(lang, is_super_admin))


@router.callback_query(WizardCB.filter(F.a == "back"))
async def go_back(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """One step back. The first step leaves via cancel."""
    current = await state.get_state()
    data = await state.get_data()
    if current == ProfileSG.niche_custom.state:
        await show_niche(callback, state, lang)
        return
    if current == ProfileSG.description.state and data.get("custom"):
        await state.set_state(ProfileSG.niche_custom)
        await show_screen(callback, t("wizard_niche_custom", lang), text_step_kb(lang))
        return
    if current in {ProfileSG.description.state, ProfileSG.niche.state}:
        await show_niche(callback, state, lang)
        return
    await jump_back(callback, state, lang, current)


@router.callback_query(ProfileSG.niche, WizardCB.filter(F.a == "niche"))
async def pick_niche(
    callback: CallbackQuery, callback_data: WizardCB, state: FSMContext, lang: str
) -> None:
    """Preset niche, or ask for a short custom name."""
    if callback_data.v == "other":
        await state.update_data(custom=True)
        await state.set_state(ProfileSG.niche_custom)
        await show_screen(callback, t("wizard_niche_custom", lang), text_step_kb(lang))
        return
    if callback_data.v not in PRESET_NICHES:
        await callback.answer(t("input_bad", lang), show_alert=True)
        return
    await state.update_data(niche_code=callback_data.v, custom=False)
    await state.set_state(ProfileSG.description)
    await show_screen(callback, t("wizard_desc", lang), text_step_kb(lang))


@router.message(ProfileSG.niche_custom, F.text)
async def custom_niche(message: Message, state: FSMContext, lang: str) -> None:
    """Free-text niche, 1–200 characters."""
    await take_text(message, state, lang, "niche_code", 200, "wizard_desc", ProfileSG.description)


@router.message(ProfileSG.description, F.text)
async def description(message: Message, state: FSMContext, lang: str) -> None:
    """What the channel is about, 1–500 characters."""
    await take_text(message, state, lang, "niche_description", 500, "wizard_tone", ProfileSG.tone)


@router.callback_query(WizardCB.filter(F.a == "tone"))
async def pick_tone(
    callback: CallbackQuery, callback_data: WizardCB, state: FSMContext, lang: str
) -> None:
    """Store tone and ask for the audience level."""
    await state.update_data(tone=callback_data.v)
    await state.set_state(ProfileSG.audience)
    await show_screen(callback, t("wizard_audience", lang), audience_kb(lang))


@router.callback_query(WizardCB.filter(F.a == "aud"))
async def pick_audience(
    callback: CallbackQuery, callback_data: WizardCB, state: FSMContext, lang: str
) -> None:
    """Store audience and ask for the content language."""
    await state.update_data(audience_level=callback_data.v)
    await state.set_state(ProfileSG.language)
    await show_screen(callback, t("wizard_lang", lang), language_kb(lang))


@router.callback_query(WizardCB.filter(F.a == "lang"))
async def pick_language(
    callback: CallbackQuery, callback_data: WizardCB, state: FSMContext, lang: str
) -> None:
    """Store language and show the timezone step."""
    await state.update_data(language=callback_data.v)
    await show_timezone(callback, state, lang)


@router.callback_query(WizardCB.filter(F.a == "tzopen"))
async def open_zones(callback: CallbackQuery, lang: str) -> None:
    """Short timezone list."""
    await show_screen(callback, t("wizard_tz_pick", lang), timezone_list_kb(lang))


@router.callback_query(WizardCB.filter(F.a == "tz"))
async def pick_zone(
    callback: CallbackQuery, callback_data: WizardCB, state: FSMContext, lang: str
) -> None:
    """Store a timezone from the allowed list."""
    if callback_data.v not in TIMEZONES:
        await callback.answer(t("input_bad", lang), show_alert=True)
        return
    await state.update_data(timezone=callback_data.v)
    await show_summary(callback, state, lang)


@router.callback_query(WizardCB.filter(F.a == "tzkeep"))
async def keep_zone(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """Keep the zone already stored (default Asia/Tashkent)."""
    await show_summary(callback, state, lang)


@router.callback_query(WizardCB.filter(F.a == "save"))
async def save_profile(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    current_user: User,
    chats: ChatRepository,
    profiles: ProfileService,
    access: AccessService,
) -> None:
    """Validate, store, show the chat card."""
    data = await state.get_data()
    chat = await _chat_from(data, chats)
    if chat is None or not manages(chat, current_user, is_super_admin):
        await state.clear()
        await show_screen(callback, t("not_owner", lang), main_menu(lang, is_super_admin))
        return
    try:
        await profiles.save(current_user, chat.id, _input(data))
    except ProfileError as exc:
        await callback.answer(t(_ERRORS.get(exc.code, "input_bad"), lang, max=500), show_alert=True)
        return
    await state.clear()
    note = t("profile_saved", lang)
    await render_card(callback, chat, current_user, access, profiles, lang, note=note, new=True)


async def _chat_from(data: dict[str, object], chats: ChatRepository) -> Chat | None:
    chat_id = data.get("chat_id")
    if not isinstance(chat_id, int):
        return None
    return await chats.get_by_id(chat_id)


def _input(data: dict[str, object]) -> ProfileInput:
    return ProfileInput(
        niche_code=str(data.get("niche_code", "")),
        niche_description=str(data.get("niche_description", "")),
        tone=str(data.get("tone", "")),
        audience_level=str(data.get("audience_level", "")),
        language=str(data.get("language", "")),
        timezone=str(data.get("timezone", "")),
    )
