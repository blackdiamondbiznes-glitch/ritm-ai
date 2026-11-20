"""Super-admin payment queue. Every handler checks the env allow-list again.

Decisions go through PaymentService and pay_outcome, the same path the Mini App uses.
"""

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminCB, AdminPayCB
from app.bot.keyboards.admin_payments import (
    REJECT_REASONS,
    fake_confirm,
    payment_review,
    payments_list,
    reject_cancel,
    reject_reasons,
)
from app.bot.keyboards.menu import admin_menu, main_menu
from app.bot.pay_copy import admin_payment_line
from app.bot.pay_outcome import announce_approved, announce_fake, announce_rejected
from app.bot.states import RejectSG
from app.bot.view import remember_anchor, show_screen, show_step
from app.db.models.users import User
from app.db.repositories.plans import PlanRepository
from app.db.repositories.users import UserRepository
from app.i18n import t
from app.services.payments import PaymentError, PaymentService

router = Router(name="admin_payments")


@router.callback_query(AdminCB.filter(F.a == "pays"))
async def list_payments(
    callback: CallbackQuery,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    payments: PaymentService,
) -> None:
    """Show requests waiting for review (pending and disputed)."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    rows = await payments.list_pending()
    if not rows:
        await show_screen(callback, t("pay_admin_empty", lang), admin_menu(lang))
        return
    await show_screen(callback, t("pay_admin_title", lang), payments_list(lang, rows))


@router.callback_query(AdminPayCB.filter(F.a == "open"))
async def open_payment(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    payments: PaymentService,
    plans: PlanRepository,
    users: UserRepository,
    bot: Bot,
) -> None:
    """Show one request with flags and history, then the receipt."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    await state.clear()
    payment = await payments.get(callback_data.id)
    if payment is None:
        await show_screen(callback, t("pay_admin_missing", lang), admin_menu(lang))
        return
    owner = await users.get_by_id(payment.owner_id)
    plan = await plans.get_by_id(payment.plan_id)
    duplicates = await payments.duplicates_of(payment)
    events = await payments.history(payment.id)
    text = admin_payment_line(payment, owner, plan, lang, duplicates=duplicates, events=events)
    await show_screen(callback, text, payment_review(lang, payment.id))
    if payment.receipt_file_id and callback.from_user:
        try:
            if payment.receipt_kind == "document":
                await bot.send_document(callback.from_user.id, payment.receipt_file_id)
            else:
                await bot.send_photo(callback.from_user.id, payment.receipt_file_id)
        except (TelegramForbiddenError, TelegramBadRequest):
            return


@router.callback_query(AdminPayCB.filter(F.a == "ok"))
async def approve_payment(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    current_user: User,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    payments: PaymentService,
    plans: PlanRepository,
    users: UserRepository,
    bot: Bot,
) -> None:
    """Approve once, then send the owner a receipt message."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    try:
        payment = await payments.approve(current_user, callback_data.id, via="bot")
    except PaymentError as exc:
        await show_screen(callback, t(_admin_error(exc), lang), admin_menu(lang))
        return
    owner = await users.get_by_id(payment.owner_id)
    plan = await plans.get_by_id(payment.plan_id)
    await announce_approved(bot, payments, payment, owner, plan)
    await show_screen(callback, t("pay_admin_approved", lang), admin_menu(lang))


@router.callback_query(AdminPayCB.filter(F.a == "no"))
async def reject_start(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
) -> None:
    """Pick a preset reason or type one. A reason is always required."""
    if await _deny(callback, lang, is_super_admin, state):
        return
    await show_screen(
        callback, t("pay_admin_reason_pick", lang), reject_reasons(lang, callback_data.id)
    )


@router.callback_query(AdminPayCB.filter(F.a == "rr"))
async def reject_preset(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    current_user: User,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    payments: PaymentService,
    users: UserRepository,
    bot: Bot,
) -> None:
    if await _deny(callback, lang, is_super_admin, state):
        return
    if callback_data.v not in REJECT_REASONS:
        await callback.answer(t("button_stale", lang), show_alert=True)
        return
    payment = await payments.get(callback_data.id)
    owner = await users.get_by_id(payment.owner_id) if payment is not None else None
    reason = t(f"pay_reason_{callback_data.v}", (owner.language_code if owner else None) or "uz")
    await _reject(callback, current_user, lang, payments, users, bot, callback_data.id, reason)


@router.callback_query(AdminPayCB.filter(F.a == "rt"))
async def reject_typed_start(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
) -> None:
    if await _deny(callback, lang, is_super_admin, state):
        return
    await state.set_state(RejectSG.reason)
    await state.set_data(remember_anchor(callback, {"payment_id": callback_data.id}))
    await show_screen(
        callback, t("pay_admin_ask_reason", lang), reject_cancel(lang, callback_data.id)
    )


@router.message(RejectSG.reason, F.text)
async def reject_reason(
    message: Message,
    state: FSMContext,
    current_user: User,
    lang: str,
    is_super_admin: bool,
    payments: PaymentService,
    users: UserRepository,
    bot: Bot,
) -> None:
    """Store the typed reason, reject the payment and notify the owner."""
    if not is_super_admin:
        await state.clear()
        await message.answer(t("admin_denied", lang), reply_markup=main_menu(lang, False))
        return
    reason = (message.text or "").strip()
    data = await state.get_data()
    payment_id = int(data.get("payment_id") or 0)
    if not reason:
        await show_step(
            message, state, t("pay_admin_reason_required", lang), reject_cancel(lang, payment_id)
        )
        return
    await state.clear()
    try:
        payment = await payments.reject(current_user, payment_id, reason, via="bot")
    except PaymentError as exc:
        await show_step(message, state, t(_admin_error(exc), lang), admin_menu(lang))
        return
    owner = await users.get_by_id(payment.owner_id)
    await announce_rejected(bot, payment, owner)
    await show_step(message, state, t("pay_admin_rejected", lang), admin_menu(lang))


@router.callback_query(AdminPayCB.filter(F.a == "fk"))
async def fake_start(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
) -> None:
    if await _deny(callback, lang, is_super_admin, state):
        return
    await show_screen(
        callback,
        t("pay_admin_fake_confirm", lang, id=callback_data.id),
        fake_confirm(lang, callback_data.id),
    )


@router.callback_query(AdminPayCB.filter(F.a == "fky"))
async def fake_confirmed(
    callback: CallbackQuery,
    callback_data: AdminPayCB,
    current_user: User,
    lang: str,
    is_super_admin: bool,
    state: FSMContext,
    payments: PaymentService,
    bot: Bot,
) -> None:
    if await _deny(callback, lang, is_super_admin, state):
        return
    try:
        marked = await payments.mark_fake(current_user, callback_data.id, via="bot")
    except PaymentError as exc:
        await show_screen(callback, t(_admin_error(exc), lang), admin_menu(lang))
        return
    await announce_fake(bot, marked)
    key = "pay_admin_faked_blocked" if marked.blocked else "pay_admin_faked"
    await show_screen(callback, t(key, lang), admin_menu(lang))


async def _reject(callback, reviewer, lang, payments, users, bot, payment_id, reason) -> None:
    try:
        payment = await payments.reject(reviewer, payment_id, reason, via="bot")
    except PaymentError as exc:
        await show_screen(callback, t(_admin_error(exc), lang), admin_menu(lang))
        return
    owner = await users.get_by_id(payment.owner_id)
    await announce_rejected(bot, payment, owner)
    await show_screen(callback, t("pay_admin_rejected", lang), admin_menu(lang))


def _admin_error(exc: PaymentError) -> str:
    if exc.code == "missing":
        return "pay_admin_missing"
    if exc.code == "reason":
        return "pay_admin_reason_required"
    return "pay_admin_status"


async def _deny(
    callback: CallbackQuery, lang: str, is_super_admin: bool, state: FSMContext
) -> bool:
    if is_super_admin:
        return False
    await state.clear()
    await show_screen(callback, t("admin_denied", lang), main_menu(lang, False))
    return True
