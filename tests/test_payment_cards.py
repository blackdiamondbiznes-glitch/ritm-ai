"""Card grouping, optional second card, and quote copy."""

from types import SimpleNamespace

from app.bot.pay_copy import invoice_text
from app.services.payment_cards import PaymentCard, configured_cards, format_card_number
from tests.fakes import make_plans


def test_format_card_number_groups_digits() -> None:
    assert format_card_number("1111222233334444") == "1111 2222 3333 4444"
    assert format_card_number("1111 2222 3333 4444") == "1111 2222 3333 4444"
    assert format_card_number("1111-2222") == "1111 2222"
    assert format_card_number("") == ""


def test_configured_cards_include_the_second_card_when_set() -> None:
    primary_only = configured_cards(
        SimpleNamespace(
            payment_card_number="1111222233334444",
            payment_card_holder="Ada",
            payment_card_type="Uzcard",
            payment_card2_number="",
            payment_card2_holder="",
            payment_card2_type="",
        )
    )
    assert len(primary_only) == 1
    assert primary_only[0].kind == "Uzcard"
    both = configured_cards(
        SimpleNamespace(
            payment_card_number="1111222233334444",
            payment_card_holder="Ada",
            payment_card_type="Uzcard",
            payment_card2_number="4000111122223333",
            payment_card2_holder="Ada",
            payment_card2_type="Visa",
        )
    )
    assert [card.kind for card in both] == ["Uzcard", "Visa"]
    assert both[1].grouped_number == "4000 1111 2222 3333"


def test_invoice_shows_both_cards_ref_and_exact_amount_copyable() -> None:
    plan = next(plan for plan in make_plans() if plan.code == "pro")
    quote = SimpleNamespace(
        plan=plan,
        months=1,
        amount=39000,
        monthly=39000,
        founder=False,
        monthly_equivalent=39000,
        period_percent=0,
        savings=0,
    )
    payment = SimpleNamespace(amount_uzs=39047, base_amount_uzs=39000, ref_code="RITM-AB7K", id=5)
    cards = [
        PaymentCard("1111222233334444", "Ada Example", "Uzcard"),
        PaymentCard("4000111122223333", "Ada Example", "Visa"),
    ]
    text = invoice_text(payment, quote, "uz", cards)
    assert "Uzcard" in text and "Visa" in text
    assert "<code>1111 2222 3333 4444</code>" in text
    assert "<code>4000 1111 2222 3333</code>" in text
    assert "<code>RITM-AB7K</code>" in text
    assert "<code>39 047</code>" in text
    assert "47 so'm" in text
