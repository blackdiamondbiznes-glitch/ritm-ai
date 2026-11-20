from app.bot.keyboards.payments import (
    dispute_actions,
    invoice_actions,
    month_picker,
    terms_actions,
    when_actions,
)


def _datas(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def test_payment_keyboards_pack_for_every_plan():
    for code in ("start", "pro", "agency"):
        assert f"p:months:{code}-12" in _datas(month_picker("uz", code))
        assert f"p:terms:{code}-3" in _datas(terms_actions("uz", code, 3))
    big = 2147483647
    for kb in (invoice_actions("uz", big), dispute_actions("uz", big), when_actions("uz")):
        assert all(len(d.encode()) <= 64 for d in _datas(kb))
    assert "p:paid:42" in _datas(invoice_actions("uz", 42))
    assert "p:dispute:42" in _datas(dispute_actions("uz", 42))


def test_month_picker_labels_show_the_period_percent() -> None:
    from app.bot.keyboards.payments import month_picker

    keyboard = month_picker("uz", "pro", {3: 7, 12: 15})
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "1 oy" in labels
    assert "3 oy — −7%" in labels
    assert "12 oy — −15%" in labels
