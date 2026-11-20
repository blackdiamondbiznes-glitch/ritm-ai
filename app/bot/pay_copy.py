"""Payment and trial-report texts. Dynamic values are HTML-escaped."""

from html import escape

from app.db.models.payments import Payment
from app.db.models.plans import Plan
from app.db.models.users import User
from app.i18n import t
from app.services.clock import format_tashkent
from app.services.payment_cards import PaymentCard
from app.services.payments import Quote


def _card_block(card: PaymentCard, lang: str) -> str:
    number = escape(card.grouped_number)
    holder = escape(card.holder)
    if card.kind:
        return t("pay_card_typed", lang, type=escape(card.kind), card=number, holder=holder)
    return t("pay_card", lang, card=number, holder=holder)


def pending_text(payment: Payment, plan: Plan, lang: str) -> str:
    """The owner already has a request under review."""
    status = "pay_status_disputed" if payment.status == "disputed" else "pay_status_pending"
    return t(
        "pay_pending_ref",
        lang,
        ref=escape(payment.ref_code or f"#{payment.id}"),
        plan=escape(plan.name),
        months=payment.requested_period_months,
        amount=_money(payment.amount_uzs),
        status=t(status, lang),
    )


def pay_confirmed(lang: str, payment: Payment | None = None, hours: int = 12) -> str:
    """After the owner submits a request."""
    if payment is None:
        return t("pay_submitted", lang)
    return t(
        "pay_submitted_ref",
        lang,
        ref=escape(payment.ref_code or f"#{payment.id}"),
        amount=_money(payment.amount_uzs),
        hours=hours,
    )


def terms_text(lang: str, version: str, hours: int) -> str:
    """Short offer the owner accepts before a reference code is issued."""
    return t("pay_terms", lang, version=escape(version), hours=hours)


def invoice_text(
    payment: Payment, quote: Quote, lang: str, cards: list[PaymentCard], promo: str = ""
) -> str:
    """Exact amount, reference code and both cards, all tap-to-copy."""
    extras = []
    if getattr(quote, "period_percent", 0) and getattr(quote, "savings", 0):
        extras.append(
            t("pay_savings_line", lang, percent=quote.period_percent, saved=_money(quote.savings))
        )
    if promo:
        extras.append(promo)
    base = payment.base_amount_uzs or payment.amount_uzs
    return t(
        "pay_invoice",
        lang,
        plan=escape(quote.plan.name),
        months=quote.months,
        monthly=_money(quote.monthly),
        rate=t("pay_founder_rate", lang) if quote.founder else t("pay_regular_rate", lang),
        extras=("\n".join(extras) + "\n") if extras else "",
        amount=_money(payment.amount_uzs),
        ref=escape(payment.ref_code or ""),
        offset=max(0, payment.amount_uzs - base),
        cards="\n\n".join(_card_block(card, lang) for card in cards),
    )


def history_lines(events: list, lang: str, limit: int = 8) -> str:
    """Compact, Tashkent-time payment history for admin messages."""
    if not events:
        return ""
    lines = []
    for event in events[-limit:]:
        when = format_tashkent(event.created_at, "%d.%m %H:%M") if event.created_at else "—"
        label = t(f"pay_event_{event.action}", lang)
        lines.append(f"• {when} — {escape(label)}")
    return t("pay_history_title", lang) + "\n" + "\n".join(lines)


def _flags(payment: Payment, owner: User | None, duplicates: list, lang: str) -> str:
    parts = []
    dup_ids = [row.id for row in duplicates] or (
        [payment.duplicate_of_id] if getattr(payment, "duplicate_of_id", None) else []
    )
    if dup_ids:
        parts.append(t("pay_flag_duplicate", lang, ids=", ".join(f"#{i}" for i in dup_ids)))
    fakes = int(getattr(owner, "fake_receipts", 0) or 0) if owner is not None else 0
    if fakes:
        parts.append(t("pay_flag_fakes", lang, n=fakes))
    if getattr(payment, "dispute_text", None):
        parts.append(t("pay_flag_dispute", lang, text=escape(payment.dispute_text)))
        if payment.reject_reason:
            parts.append(t("pay_flag_rejected", lang, reason=escape(payment.reject_reason)))
    return "".join(parts)


def _transfer(payment: Payment) -> str:
    moment = getattr(payment, "transfer_at", None)
    return format_tashkent(moment) if moment else "—"


def dispute_alert(
    payment: Payment, owner: User | None, lang: str, events: list | None = None
) -> str:
    """Push text for super admins when an owner disputes a rejection."""
    return t(
        "pay_admin_dispute_alert",
        lang,
        id=payment.id,
        ref=escape(payment.ref_code or "—"),
        name=escape((owner.full_name if owner and owner.full_name else "") or "—"),
        telegram_id=owner.telegram_id if owner is not None else 0,
        amount=_money(payment.amount_uzs),
        last4=escape(payment.payer_card_last4 or "—"),
        text=escape(payment.dispute_text or ""),
        reason=escape(payment.reject_reason or "—"),
        history=history_lines(events or [], lang),
    )


def admin_payment_line(
    payment: Payment,
    owner: User | None,
    plan: Plan | None,
    lang: str,
    *,
    duplicates: list | None = None,
    events: list | None = None,
) -> str:
    """One request for the super admin, with everything needed to match the bank app."""
    name = escape((owner.full_name if owner and owner.full_name else "") or "—")
    telegram_id = owner.telegram_id if owner is not None else 0
    plan_name = escape(plan.name if plan is not None else "—")
    when = format_tashkent(payment.created_at) if payment.created_at else "—"
    receipt = t("pay_receipt_yes", lang) if payment.receipt_file_id else t("pay_receipt_no", lang)
    if payment.submitted_at:
        when = format_tashkent(payment.submitted_at)
    return t(
        "pay_admin_item_v2",
        lang,
        id=payment.id,
        status=escape(payment.status),
        ref=escape(payment.ref_code or "—"),
        last4=escape(payment.payer_card_last4 or "—"),
        transfer=_transfer(payment),
        name=name,
        telegram_id=telegram_id,
        plan=plan_name,
        months=payment.requested_period_months,
        amount=_money(payment.amount_uzs),
        when=when,
        receipt=receipt,
        flags=_flags(payment, owner, duplicates or [], lang),
        history=history_lines(events or [], lang),
    )


def approved_notice(plan: Plan, until, lang: str, payment: Payment | None = None) -> str:
    """Private confirmation after a payment is accepted. With a payment it is a full receipt."""
    stamp = format_tashkent(until, "%d.%m.%Y") if until is not None else "—"
    if payment is None:
        return t("pay_approved", lang, plan=escape(plan.name), until=stamp)
    approved = format_tashkent(payment.reviewed_at) if payment.reviewed_at else "—"
    return t(
        "pay_approved_receipt",
        lang,
        ref=escape(payment.ref_code or f"#{payment.id}"),
        plan=escape(plan.name),
        months=payment.requested_period_months,
        amount=_money(payment.amount_uzs),
        approved=approved,
        until=stamp,
        terms=escape(payment.terms_version or "—"),
    )


def rejected_notice(reason: str, lang: str, payment: Payment | None = None) -> str:
    """Private notice after a payment is refused."""
    text = escape((reason or "").strip() or t("pay_reject_default", lang))
    if payment is None:
        return t("pay_rejected", lang, reason=text)
    return t(
        "pay_rejected_ref", lang, reason=text, ref=escape(payment.ref_code or f"#{payment.id}")
    )


def fake_notice(payment: Payment, lang: str, *, blocked: bool) -> str:
    text = t("pay_fake_notice", lang, ref=escape(payment.ref_code or f"#{payment.id}"))
    if blocked:
        text += "\n\n" + t("pay_fake_blocked", lang)
    return text


def admin_payment_alert(
    payment: Payment,
    owner: User | None,
    plan: Plan | None,
    lang: str,
    *,
    founder: bool,
    duplicates: list | None = None,
) -> str:
    """Push text for super admins when a request is submitted."""
    name = escape((owner.full_name if owner and owner.full_name else "") or "—")
    handle = ""
    if owner is not None and owner.username:
        handle = "\n@" + escape(owner.username)
    telegram_id = owner.telegram_id if owner is not None else 0
    plan_name = escape(plan.name if plan is not None else "—")
    when = format_tashkent(payment.created_at) if payment.created_at else "—"
    rate = t("pay_founder_rate", lang) if founder else t("pay_regular_rate", lang)
    if payment.submitted_at:
        when = format_tashkent(payment.submitted_at)
    return t(
        "pay_admin_alert_v2",
        lang,
        id=payment.id,
        ref=escape(payment.ref_code or "—"),
        last4=escape(payment.payer_card_last4 or "—"),
        transfer=_transfer(payment),
        terms=escape(payment.terms_version or "—"),
        flags=_flags(payment, owner, duplicates or [], lang),
        name=name,
        username=handle,
        telegram_id=telegram_id,
        plan=plan_name,
        months=payment.requested_period_months,
        amount=_money(payment.amount_uzs),
        rate=rate,
        when=when,
    )


def trial_report_text(stats: object, lang: str) -> str:
    """Short private engagement summary for a trial owner."""
    title = escape(getattr(getattr(stats, "chat", None), "title", "") or "Chat")
    posts = int(getattr(stats, "posts", 0))
    answers = int(getattr(stats, "answers", 0))
    people = int(getattr(stats, "participants", 0))
    best = escape(str(getattr(stats, "best_day", None) or t("report_best_none", lang)))
    takeaway = _takeaway(posts, answers, people, lang)
    body = t(
        "report_body",
        lang,
        title=title,
        posts=posts,
        answers=answers,
        people=people,
        best=best,
        takeaway=takeaway,
    )
    if getattr(stats, "late", False):
        left = int(getattr(stats, "days_left", 0))
        return body + "\n\n" + t("report_late", lang, days=left)
    return body


def expiry_notice(lang: str) -> str:
    """One-time notice when a trial has ended."""
    return t("report_expired", lang)


def _takeaway(posts: int, answers: int, people: int, lang: str) -> str:
    if people >= 3 or answers >= 5 or posts >= 3:
        return t("report_active", lang)
    if people or answers or posts:
        return t("report_steady", lang)
    return t("report_quiet", lang)


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")
