"""Cabinet menu buttons open the Mini App on the matching mode."""

from app.bot.callbacks import MenuCB
from app.bot.keyboards.menu import main_menu, study_keyboard
from app.services.study_text import summary


def test_menu_links_open_the_matching_mode() -> None:
    markup = main_menu("uz", False, "https://app.example/app", teaching=True, learning=True)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    urls = [
        button.web_app.url for row in markup.inline_keyboard for button in row if button.web_app
    ]
    learn = next(
        button for row in markup.inline_keyboard for button in row if button.text == "O‘qishim"
    )
    assert "👩‍🏫 O‘qituvchi kabineti" in labels
    assert learn.callback_data == MenuCB(a="learn").pack()
    assert learn.web_app is None
    assert "https://app.example/app?startapp=cabinet#/cabinet" in urls
    opened = study_keyboard("uz", "https://app.example/app")
    study_urls = [
        button.web_app.url for row in opened.inline_keyboard for button in row if button.web_app
    ]
    assert study_urls == ["https://app.example/app#role=student"]


def test_study_summary_names_the_next_lesson_and_fee() -> None:
    text = summary(
        {
            "groups": [
                {
                    "group": {"name": "A <b>"},
                    "next_session": {
                        "starts_at": "2026-12-05T13:00:00+00:00",
                        "status": "scheduled",
                    },
                    "fee": {
                        "mode": "monthly",
                        "amount": 300000,
                        "due_on": "2026-12-05",
                        "status": "due",
                        "paid": 0,
                        "lessons_used": 0,
                        "lessons_total": None,
                    },
                },
                {
                    "group": {"name": "Paket"},
                    "next_session": None,
                    "fee": {
                        "mode": "package",
                        "amount": 100000,
                        "due_on": "2026-12-01",
                        "status": "due",
                        "paid": 0,
                        "lessons_used": 7,
                        "lessons_total": 12,
                    },
                },
            ],
            "pending": [{"group_name": "Fizika"}],
        },
        "uz",
    )
    assert "A &lt;b&gt;" in text
    assert "300 000 so\u2018m" in text
    assert "5-dek" in text
    assert "Paket 7/12" in text
    assert "Tasdiq kutilmoqda: Fizika" in text


def test_teacher_menu_puts_cabinet_first_and_plan_last() -> None:
    markup = main_menu("uz", False, "https://app.example/app", teaching=True, learning=False)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert labels[0] == "👩‍🏫 O‘qituvchi kabineti"
    actions = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    help_at = actions.index(MenuCB(a="help").pack())
    connect_at = actions.index(MenuCB(a="connect").pack())
    plan_at = actions.index(MenuCB(a="plan").pack())
    assert help_at < connect_at < plan_at
