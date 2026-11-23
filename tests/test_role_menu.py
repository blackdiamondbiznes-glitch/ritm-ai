"""Cabinet menu buttons open the Mini App on the matching mode."""

from app.bot.keyboards.menu import main_menu


def test_menu_links_open_the_matching_mode() -> None:
    markup = main_menu("uz", False, "https://app.example/app", teaching=True, learning=True)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    urls = [
        button.web_app.url for row in markup.inline_keyboard for button in row if button.web_app
    ]
    assert "Kabinetim" in labels
    assert "O‘qishim" in labels
    assert "https://app.example/app#role=teacher" in urls
    assert "https://app.example/app#role=student" in urls
