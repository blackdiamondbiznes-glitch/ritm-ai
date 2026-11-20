"""Super-admin tools. Every handler checks the env allow-list again."""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminCB, MenuCB
from app.bot.keyboards.admin import block_choices, day_choices, plan_choices
from app.bot.keyboards.menu import admin_menu, cancel_row, main_menu
from app.bot.states import BlockSG, GrantSG
from app.bot.view import remember_anchor, show_screen, show_step
from app.db.models.users import User
from app.db.repositories.plans import PlanRepository
from app.db.repositories.users import UserRepository
from app.i18n import t
from app.services.admin import AdminError, AdminService

router = Router(name="admin")
_ERRORS = {
    "bad_days": "admin_bad_days",
    "missing_user": "admin_missing_user",
    "bad_plan": "admin_bad_plan",
}


@router.callback_query(MenuCB.filter(F.a == "admin"))
async def admin_home(
    callback: CallbackQuery, lang: str, is_super_admin: bool, state: FSMContext
) -> None:
    """Admin root."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    await state.clear()
    await show_screen(callback, t("admin_title", lang), admin_menu(lang))


@router.callback_query(AdminCB.filter(F.a == "stats"))
async def stats(
    callback: CallbackQuery,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    admin_service: AdminService,
) -> None:
    """User, chat, trial and paid counts."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    row = await admin_service.stats()
    text = t(
        "admin_stats_text",
        lang,
        users=row.users,
        chats=row.chats,
        trials=row.trials,
        paid=row.paid,
    )
    await show_screen(callback, text, admin_menu(lang))


@router.callback_query(AdminCB.filter(F.a == "grant"))
async def grant_start(
    callback: CallbackQuery, state: FSMContext, lang: str, is_super_admin: bool
) -> None:
    """Ask for a Telegram id."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    await state.set_state(GrantSG.telegram_id)
    await state.set_data(remember_anchor(callback, {}))
    await show_screen(callback, t("admin_ask_id", lang), cancel_row(lang))


@router.message(GrantSG.telegram_id, F.text)
async def grant_id(
    message: Message,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    users: UserRepository,
    plans: PlanRepository,
) -> None:
    """Resolve the id, then show plans from the database."""
    if not is_super_admin:
        await state.clear()
        await message.answer(t("admin_denied", lang))
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await show_step(message, state, t("admin_bad_id", lang), cancel_row(lang))
        return
    telegram_id = int(raw)
    if await users.get_by_telegram_id(telegram_id) is None:
        await show_step(message, state, t("admin_missing_user", lang), cancel_row(lang))
        return
    await state.update_data(telegram_id=telegram_id)
    await state.set_state(GrantSG.plan)
    catalog = await plans.list_active()
    text = t("admin_pick_plan", lang, telegram_id=telegram_id)
    await show_step(message, state, text, plan_choices(lang, catalog))


@router.callback_query(GrantSG.plan, AdminCB.filter(F.a == "plan"))
async def grant_plan(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    plans: PlanRepository,
) -> None:
    """Store the plan code and ask for a length."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    plan = await plans.get_by_code(callback_data.v)
    if plan is None:
        await callback.answer(t("admin_bad_plan", lang), show_alert=True)
        return
    await state.update_data(plan_code=plan.code)
    await state.set_state(GrantSG.days)
    text = t("admin_pick_days", lang, plan=escape(plan.name))
    await show_screen(callback, text, day_choices(lang))


@router.callback_query(GrantSG.days, AdminCB.filter(F.a == "days"))
async def grant_days(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    current_user: User,
    admin_service: AdminService,
) -> None:
    """Create the grant and write the audit row inside the service."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    if not callback_data.v.isdigit():
        await callback.answer(t("admin_bad_days", lang), show_alert=True)
        return
    data = await state.get_data()
    try:
        await admin_service.grant(
            current_user,
            int(data.get("telegram_id", 0)),
            str(data.get("plan_code", "")),
            int(callback_data.v),
        )
    except AdminError as exc:
        await state.clear()
        key = _ERRORS.get(exc.code, "error_generic")
        await show_screen(callback, t(key, lang), admin_menu(lang))
        return
    await state.clear()
    text = t(
        "admin_granted",
        lang,
        plan=escape(str(data.get("plan_code", ""))),
        days=callback_data.v,
        telegram_id=data.get("telegram_id", ""),
    )
    await show_screen(callback, text, admin_menu(lang))


@router.callback_query(AdminCB.filter(F.a == "block"))
async def block_start(
    callback: CallbackQuery, state: FSMContext, lang: str, is_super_admin: bool
) -> None:
    """Choose block or unblock before asking for the id."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    await state.set_state(BlockSG.action)
    await state.set_data(remember_anchor(callback, {}))
    await show_screen(callback, t("admin_pick_block", lang), block_choices(lang))


@router.callback_query(BlockSG.action, AdminCB.filter(F.a == "do"))
async def block_action(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
) -> None:
    """Remember the action and ask for the Telegram id."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    if callback_data.v not in {"block", "unblock"}:
        await callback.answer(t("input_bad", lang), show_alert=True)
        return
    await state.update_data(block_action=callback_data.v)
    await state.set_state(BlockSG.telegram_id)
    await show_screen(callback, t("admin_ask_id", lang), cancel_row(lang))


@router.message(BlockSG.telegram_id, F.text)
async def block_id(
    message: Message,
    state: FSMContext,
    lang: str,
    is_super_admin: bool,
    current_user: User,
    admin_service: AdminService,
) -> None:
    """Apply the block flag."""
    if not is_super_admin:
        await state.clear()
        await message.answer(t("admin_denied", lang), reply_markup=main_menu(lang, False))
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await show_step(message, state, t("admin_bad_id", lang), cancel_row(lang))
        return
    data = await state.get_data()
    blocked = data.get("block_action") == "block"
    try:
        await admin_service.set_blocked(current_user, int(raw), blocked)
    except AdminError:
        await show_step(message, state, t("admin_missing_user", lang), cancel_row(lang))
        return
    await state.clear()
    key = "admin_blocked" if blocked else "admin_unblocked"
    await message.answer(t(key, lang), reply_markup=admin_menu(lang))


async def _deny(
    callback: CallbackQuery, lang: str, is_super_admin: bool, state: FSMContext
) -> bool:
    if is_super_admin:
        return False
    await state.clear()
    await show_screen(callback, t("admin_denied", lang), main_menu(lang, False))
    return True
