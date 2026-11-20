"""Owner payment and trial-report keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import MenuCB, PayCB
from app.db.models.plans import Plan
from app.i18n import t
from app.services.pricing import PERIODS, format_soum, is_paid_plan, period_percent


def plan_actions(lang: str, *, trial: bool = False) -> InlineKeyboardMarkup:
    """Plan screen: start a payment, optional trial report, back."""
    rows = [[_btn(t("plan_pay", lang), PayCB(a="start").pack())]]
    if trial:
        rows.append([_btn(t("report_now", lang), PayCB(a="report").pack())])
    rows.append([_btn(t("back", lang), MenuCB(a="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_picker(lang: str, plans: list[Plan], *, sale: bool = False) -> InlineKeyboardMarkup:
    """Paid plans only. Button labels cannot use HTML, so sale prices are plain."""
    rows = [
        [_btn(_plan_button(plan, lang, sale=sale), PayCB(a="plan", v=plan.code).pack())]
        for plan in plans
    ]
    rows.append([_btn(t("back", lang), MenuCB(a="plan").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def month_picker(
    lang: str, plan_code: str, discounts: dict[int, int] | None = None
) -> InlineKeyboardMarkup:
    """1, 3 or 12 months. Sale periods show the percent on the button."""
    rows = [
        [
            _btn(
                _month_label(lang, months, period_percent(months, discounts)),
                PayCB(a="months", v=f"{plan_code}-{months}").pack(),
            )
        ]
        for months in PERIODS
    ]
    rows.append([_btn(t("back", lang), PayCB(a="start").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def terms_actions(lang: str, plan_code: str, months: int) -> InlineKeyboardMarkup:
    """Accept the offer for this plan and period, or go back to the periods."""
    token = f"{plan_code}-{months}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("pay_terms_accept", lang), PayCB(a="terms", v=token).pack())],
            [_btn(t("back", lang), PayCB(a="plan", v=plan_code).pack())],
        ]
    )


def invoice_actions(lang: str, payment_id: int) -> InlineKeyboardMarkup:
    """After the transfer: start the evidence steps, or cancel the code."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("pay_done", lang), PayCB(a="paid", v=str(payment_id)).pack())],
            [_btn(t("pay_cancel", lang), PayCB(a="cancel").pack())],
        ]
    )


def when_actions(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("pay_now_button", lang), PayCB(a="now").pack())],
            [_btn(t("pay_cancel", lang), PayCB(a="cancel").pack())],
        ]
    )


def step_cancel(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(t("pay_cancel", lang), PayCB(a="cancel").pack())]]
    )


def dispute_actions(lang: str, payment_id: int) -> InlineKeyboardMarkup:
    """Shown under a rejection notice."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("pay_dispute_button", lang), PayCB(a="dispute", v=str(payment_id)).pack())]
        ]
    )


def pending_actions(lang: str) -> InlineKeyboardMarkup:
    """Cancel the open request or go back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t("pay_cancel", lang), PayCB(a="cancel").pack())],
            [_btn(t("back", lang), MenuCB(a="plan").pack())],
        ]
    )


def report_actions(lang: str) -> InlineKeyboardMarkup:
    """Open the payment flow from a trial report or expiry notice."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(t("plan_pay", lang), PayCB(a="start").pack())]]
    )


def _plan_button(plan: Plan, lang: str, *, sale: bool) -> str:
    price = int(plan.price_uzs)
    founder = int(plan.founder_price_uzs)
    if sale and is_paid_plan(plan) and 0 < founder < price:
        price = founder
    return t("pay_plan_button", lang, name=plan.name, price=format_soum(price))


def _month_label(lang: str, months: int, percent: int) -> str:
    if percent:
        return t("pay_months_sale", lang, months=months, percent=percent)
    return t("pay_months", lang, months=months)


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)
