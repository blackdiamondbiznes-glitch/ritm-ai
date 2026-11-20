"""Owner payment flow with dispute protection.

plan -> period -> accept terms -> reference code + exact amount + cards -> "I paid"
-> card last 4 -> transfer time -> receipt (required) -> admin queue.
A rejected owner may dispute once. Every step is logged by PaymentService.
"""

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import PayCB
from app.bot.keyboards.menu import main_menu
from app.bot.keyboards.payments import (
    invoice_actions,
    month_picker,
    pending_actions,
    plan_picker,
    step_cancel,
    terms_actions,
    when_actions,
)
from app.bot.pay_copy import (
    invoice_text,
    pay_confirmed,
    pending_text,
    terms_text,
    trial_report_text,
)
from app.bot.pay_notify import notify_payment_submitted
from app.bot.pay_outcome import announce_dispute
from app.bot.plan_copy import pay_plan_text, promo_line
from app.bot.states import PaySG
from app.bot.view import remember_anchor, show_screen, show_step
from app.config import Settings
from app.db.models.payments import Payment
from app.db.models.users import User
from app.db.repositories.plans import PlanRepository
from app.db.repositories.users import UserRepository
from app.i18n import t
from app.services.access import AccessService
from app.services.payment_cards import configured_cards
from app.services.payments import PaymentError, PaymentService, Receipt, parse_transfer_time
from app.services.pricing import is_paid_plan
from app.services.trial_reports import TrialReportService

router = Router(name="payments")

_ERROR_KEYS = {
    "duplicate": "pay_duplicate",
    "blocked": "pay_blocked",
    "terms": "pay_terms_old",
    "expired": "pay_expired",
    "busy": "pay_busy",
    "receipt": "pay_receipt_required",
    "last4": "pay_bad_last4",
    "when": "pay_bad_when",
}
_IMAGE_TYPES = ("image/", "application/pdf")


def parse_period_token(token: str) -> tuple[str, int] | None:
    """Current tokens look like ``pro-12``. Colon form is stale and rejected."""
    if not token or ":" in token or "-" not in token:
        return None
    code, raw = token.split("-", 1)
    if not code or not raw.isdigit():
        return None
    return code, int(raw)


def is_stale_period_token(token: str) -> bool:
    """True for the pre-hyphen payload such as ``pro:12``."""
    return ":" in (token or "")


def error_key(exc: PaymentError) -> str:
    return _ERROR_KEYS.get(exc.code, "pay_bad_plan")


async def _reject_period(callback: CallbackQuery, token: str, lang: str) -> bool:
    """Answer a stale or invalid period token. Returns True when the caller should stop."""
    if is_stale_period_token(token):
        await callback.answer(t("button_stale", lang), show_alert=True)
        return True
    if parse_period_token(token) is None:
        await callback.answer(t("pay_bad_plan", lang), show_alert=True)
        return True
    return False


async def _plan_screen(callback, current_user, plans, access, lang, prefix: str = "") -> None:
    catalog = [plan for plan in await plans.list_active() if is_paid_plan(plan)]
    offer = await access.founder_offer(current_user)
    await show_screen(
        callback,
        prefix + pay_plan_text(catalog, lang, offer),
        plan_picker(lang, catalog, sale=offer.show_sale),
    )


@router.callback_query(PayCB.filter(F.a == "start"))
async def start_pay(
    callback: CallbackQuery,
    current_user: User,
    payments: PaymentService,
    plans: PlanRepository,
    access: AccessService,
    settings: Settings,
    lang: str,
    state: FSMContext,
) -> None:
    """Open request -> its status; issued code -> the invoice again; else the plan picker."""
    await state.clear()
    if current_user.payments_blocked:
        await show_screen(callback, t("pay_blocked", lang), main_menu(lang, False))
        return
    pending = await payments.pending_of(current_user.id)
    if pending is not None:
        plan = await plans.get_by_id(pending.plan_id)
        if plan is not None:
            await show_screen(callback, pending_text(pending, plan, lang), pending_actions(lang))
            return
    draft = await payments.draft_of(current_user)
    if draft is not None:
        plan = await plans.get_by_id(draft.plan_id)
        if plan is not None:
            await _show_invoice(callback, current_user, payments, access, settings, draft, lang)
            return
    await _plan_screen(callback, current_user, plans, access, lang)


@router.callback_query(PayCB.filter(F.a == "cancel"))
async def cancel_pending(
    callback: CallbackQuery,
    current_user: User,
    payments: PaymentService,
    plans: PlanRepository,
    access: AccessService,
    lang: str,
    state: FSMContext,
) -> None:
    """Drop the issued code or the unreviewed request and return to the plan picker."""
    await state.clear()
    await payments.cancel_pending(current_user)
    await _plan_screen(
        callback, current_user, plans, access, lang, t("pay_canceled", lang) + "\n\n"
    )


@router.callback_query(PayCB.filter(F.a == "plan"))
async def pick_plan(
    callback: CallbackQuery,
    callback_data: PayCB,
    lang: str,
    plans: PlanRepository,
    settings: Settings,
) -> None:
    """Ask how many months to pay for."""
    plan = await plans.get_by_code(callback_data.v)
    if plan is None or not is_paid_plan(plan):
        await callback.answer(t("pay_bad_plan", lang), show_alert=True)
        return
    await show_screen(
        callback,
        t("pay_pick_months", lang, plan=plan.name),
        month_picker(lang, plan.code, settings.period_discount_map),
    )


@router.callback_query(PayCB.filter(F.a == "months"))
async def pick_months(
    callback: CallbackQuery,
    callback_data: PayCB,
    current_user: User,
    settings: Settings,
    lang: str,
) -> None:
    """Show the short offer. Nothing is created until the owner accepts it."""
    if await _reject_period(callback, callback_data.v, lang):
        return
    parsed = parse_period_token(callback_data.v)
    if parsed is None:
        return
    if not configured_cards(settings):
        await show_screen(callback, t("pay_unconfigured", lang), main_menu(lang, False))
        return
    if current_user.payments_blocked:
        await show_screen(callback, t("pay_blocked", lang), main_menu(lang, False))
        return
    code, months = parsed
    await show_screen(
        callback,
        terms_text(lang, settings.payment_terms_version, settings.payment_review_hours),
        terms_actions(lang, code, months),
    )


@router.callback_query(PayCB.filter(F.a == "terms"))
async def accept_terms(
    callback: CallbackQuery,
    callback_data: PayCB,
    current_user: User,
    payments: PaymentService,
    access: AccessService,
    settings: Settings,
    lang: str,
) -> None:
    """Record the acceptance and issue the reference code and exact amount."""
    if await _reject_period(callback, callback_data.v, lang):
        return
    parsed = parse_period_token(callback_data.v)
    if parsed is None:
        return
    try:
        draft = await payments.start(
            current_user, parsed[0], parsed[1], terms_version=settings.payment_terms_version
        )
    except PaymentError as exc:
        await callback.answer(t(error_key(exc), lang), show_alert=True)
        return
    await _show_invoice(callback, current_user, payments, access, settings, draft, lang)


async def _show_invoice(callback, owner, payments, access, settings, draft: Payment, lang) -> None:
    cards = configured_cards(settings)
    if not cards:
        await show_screen(callback, t("pay_unconfigured", lang), main_menu(lang, False))
        return
    plan = await payments.plan_of(draft)
    quote = await payments.quote(owner, plan.code, draft.requested_period_months)
    offer = await access.founder_offer(owner)
    text = invoice_text(draft, quote, lang, cards, promo=promo_line(offer, [quote.plan], lang))
    await show_screen(callback, text, invoice_actions(lang, draft.id))


@router.callback_query(PayCB.filter(F.a == "paid"))
async def paid(
    callback: CallbackQuery,
    callback_data: PayCB,
    current_user: User,
    payments: PaymentService,
    state: FSMContext,
    lang: str,
) -> None:
    """Start the evidence steps for the owner's own issued code."""
    if not callback_data.v.isdigit():
        await callback.answer(t("button_stale", lang), show_alert=True)
        return
    draft = await payments.draft_of(current_user)
    if draft is None or draft.id != int(callback_data.v):
        await callback.answer(t("pay_expired", lang), show_alert=True)
        return
    await state.set_state(PaySG.last4)
    await state.set_data(remember_anchor(callback, {"payment_id": draft.id}))
    await show_screen(callback, t("pay_ask_last4", lang), step_cancel(lang))


@router.message(PaySG.last4, F.text)
async def got_last4(message: Message, state: FSMContext, lang: str) -> None:
    digits = "".join(ch for ch in (message.text or "") if ch.isdigit())
    if len(digits) != 4:
        await show_step(message, state, t("pay_bad_last4", lang), step_cancel(lang))
        return
    await state.update_data(last4=digits)
    await state.set_state(PaySG.when)
    await show_step(message, state, t("pay_ask_when", lang), when_actions(lang))


@router.message(PaySG.when, F.text)
async def got_when(
    message: Message, state: FSMContext, payments: PaymentService, lang: str
) -> None:
    moment = parse_transfer_time(message.text or "", payments.now())
    if moment is None:
        await show_step(message, state, t("pay_bad_when", lang), when_actions(lang))
        return
    await state.update_data(when=moment.isoformat())
    await state.set_state(PaySG.receipt)
    await show_step(message, state, t("pay_ask_receipt", lang), step_cancel(lang))


@router.callback_query(PaySG.when, PayCB.filter(F.a == "now"))
async def when_now(
    callback: CallbackQuery, state: FSMContext, payments: PaymentService, lang: str
) -> None:
    await state.update_data(when=payments.now().isoformat())
    await state.set_state(PaySG.receipt)
    await show_screen(callback, t("pay_ask_receipt", lang), step_cancel(lang))


@router.callback_query(PayCB.filter(F.a == "skip"))
async def skip_receipt(callback: CallbackQuery, lang: str) -> None:
    """Old 'continue without receipt' buttons: the receipt is required now."""
    await callback.answer(t("pay_receipt_required", lang), show_alert=True)


@router.message(PaySG.receipt, F.photo | F.document)
async def receipt_file(
    message: Message,
    state: FSMContext,
    current_user: User,
    payments: PaymentService,
    plans: PlanRepository,
    access: AccessService,
    settings: Settings,
    bot: Bot,
    lang: str,
) -> None:
    """Store the receipt ids and send the request to the admins."""
    receipt = _receipt_of(message)
    if receipt is None:
        await show_step(message, state, t("pay_receipt_required", lang), step_cancel(lang))
        return
    data = await state.get_data()
    try:
        when = datetime.fromisoformat(str(data.get("when") or ""))
    except ValueError:
        when = None
    try:
        result = await payments.submit(
            current_user,
            int(data.get("payment_id") or 0),
            receipt=receipt,
            card_last4=str(data.get("last4") or ""),
            transfer_at=when,
        )
    except PaymentError as exc:
        await state.clear()
        await show_step(message, state, t(error_key(exc), lang), main_menu(lang, False))
        return
    await state.clear()
    plan = await plans.get_by_id(result.payment.plan_id)
    founder = await access.offers_founder_price(current_user)
    await notify_payment_submitted(
        bot,
        settings,
        result.payment,
        current_user,
        plan,
        founder=founder,
        duplicates=result.duplicates,
    )
    await show_step(
        message,
        state,
        pay_confirmed(lang, result.payment, settings.payment_review_hours),
        main_menu(lang, False),
    )


@router.message(PaySG.receipt)
async def receipt_missing(message: Message, state: FSMContext, lang: str) -> None:
    await show_step(message, state, t("pay_receipt_required", lang), step_cancel(lang))


@router.callback_query(PayCB.filter(F.a == "dispute"))
async def dispute_start(
    callback: CallbackQuery,
    callback_data: PayCB,
    current_user: User,
    payments: PaymentService,
    state: FSMContext,
    lang: str,
) -> None:
    """Ask for the objection text. Only the owner's own, non-fake, first-time rejection."""
    payment = await payments.get(int(callback_data.v)) if callback_data.v.isdigit() else None
    if (
        payment is None
        or payment.owner_id != current_user.id
        or payment.is_fake
        or payment.status != "rejected"
        or payment.disputed_at is not None
    ):
        await callback.answer(t("pay_dispute_denied", lang), show_alert=True)
        return
    await state.set_state(PaySG.dispute)
    await state.set_data(remember_anchor(callback, {"payment_id": payment.id}))
    await show_screen(callback, t("pay_dispute_ask", lang), step_cancel(lang), new=True)


@router.message(PaySG.dispute, F.text)
async def dispute_text(
    message: Message,
    state: FSMContext,
    current_user: User,
    payments: PaymentService,
    users: UserRepository,
    settings: Settings,
    bot: Bot,
    lang: str,
) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        payment = await payments.dispute(
            current_user, int(data.get("payment_id") or 0), message.text or ""
        )
    except PaymentError:
        await show_step(message, state, t("pay_dispute_denied", lang), main_menu(lang, False))
        return
    events = await payments.history(payment.id)
    await announce_dispute(bot, settings, payment, current_user, events)
    await show_step(message, state, t("pay_dispute_sent", lang), main_menu(lang, False))


@router.callback_query(PayCB.filter(F.a == "report"))
async def trial_report_now(
    callback: CallbackQuery,
    current_user: User,
    reports: TrialReportService,
    lang: str,
) -> None:
    """Show a live trial report here, without consuming a scheduled milestone."""
    stats = await reports.live_report(current_user.id)
    if stats is None:
        await callback.answer(t("report_not_trial", lang), show_alert=True)
        return
    from app.bot.keyboards.payments import report_actions

    await show_screen(callback, trial_report_text(stats, lang), report_actions(lang), new=True)


def _receipt_of(message: Message) -> Receipt | None:
    if message.photo:
        best = message.photo[-1]
        return Receipt(best.file_id, best.file_unique_id, "photo")
    doc = message.document
    if doc is not None and (doc.mime_type or "").startswith(_IMAGE_TYPES):
        return Receipt(doc.file_id, doc.file_unique_id, "document")
    return None
