"""Receiving cards shown on the payment screen. Never log the numbers."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class PaymentCard:
    """One receiving card. `kind` is the network name, such as Uzcard or Visa."""

    number: str
    holder: str
    kind: str = ""

    @property
    def grouped_number(self) -> str:
        """Digits in groups of four, for display only."""
        return format_card_number(self.number)


def format_card_number(number: str) -> str:
    """Group digits in fours, for example 1111 2222 3333 4444."""
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return ""
    return " ".join(digits[index : index + 4] for index in range(0, len(digits), 4))


def configured_cards(settings: Settings) -> list[PaymentCard]:
    """Primary card, plus an optional second card when both number and holder are set."""
    cards: list[PaymentCard] = []
    pairs = (
        (settings.payment_card_number, settings.payment_card_holder, settings.payment_card_type),
        (
            settings.payment_card2_number,
            settings.payment_card2_holder,
            settings.payment_card2_type,
        ),
    )
    for number, holder, kind in pairs:
        if number.strip() and holder.strip():
            cards.append(
                PaymentCard(number=number.strip(), holder=holder.strip(), kind=kind.strip())
            )
    return cards
