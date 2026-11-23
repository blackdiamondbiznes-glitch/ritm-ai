"""Mini App static checks: locale parity and the admin module is wired and preloaded."""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"


def _locale_keys() -> dict[str, set[str]]:
    source = (STATIC / "i18n.js").read_text(encoding="utf-8")
    body = source[source.index("const T = {") : source.index("\n};", source.index("const T = {"))]
    parts = re.split(r"\n  (uz|ru|en): \{\n", body)
    return {
        parts[i]: set(re.findall(r"^    (\w+):", parts[i + 1], re.M))
        for i in range(1, len(parts), 2)
    }


def test_mini_app_locales_have_identical_keys() -> None:
    keys = _locale_keys()
    assert set(keys) == {"uz", "ru", "en"}
    assert keys["uz"] == keys["ru"] == keys["en"]


def test_admin_strings_are_translated() -> None:
    admin = (STATIC / "admin.js").read_text(encoding="utf-8")
    used = set(re.findall(r't\("(\w+)"', admin))
    missing = used - _locale_keys()["uz"]
    assert not missing, missing


def test_admin_tab_is_wired_and_preloaded() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<link rel="modulepreload" href="/s/admin.js">' in html
    assert 'data-tab="admin" hidden' in html
    assert "renderAdmin" in (STATIC / "app.js").read_text(encoding="utf-8")
    assert "renderNotice" in (STATIC / "app.js").read_text(encoding="utf-8")
    assert '<link rel="modulepreload" href="/s/notice.js">' in html
    notice = (STATIC / "notice.js").read_text(encoding="utf-8")
    missing = set(re.findall(r't\("(\w+)"', notice)) - _locale_keys()["uz"]
    assert not missing, missing
    ui = (STATIC / "ui.js").read_text(encoding="utf-8")
    assert 'hasRole("super_admin")' in ui


def test_no_real_card_numbers_in_static_files() -> None:
    for path in STATIC.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b", text), path.name


def test_chart_screens_are_translated_and_preloaded() -> None:
    keys = _locale_keys()["uz"]
    for name in ("charts.js", "report.js", "history.js", "admin.js"):
        used = set(re.findall(r't\("(\w+)"', (STATIC / name).read_text(encoding="utf-8")))
        assert not used - keys, (name, used - keys)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<link rel="modulepreload" href="/s/charts.js">' in html
    charts = (STATIC / "charts.js").read_text(encoding="utf-8")
    # Dependency-free: no imports beyond our own modules, accessible SVG.
    assert set(re.findall(r'from "([^"]+)"', charts)) == {"./i18n.js", "./ui.js"}
    assert 'role="img"' in charts and "aria-label" in charts
    assert '"stats", "📈", "admStats"' in (STATIC / "admin.js").read_text(encoding="utf-8")


def _locale_key_lists() -> dict[str, list[str]]:
    source = (STATIC / "i18n.js").read_text(encoding="utf-8")
    body = source[source.index("const T = {") : source.index("\n};", source.index("const T = {"))]
    parts = re.split(r"\n  (uz|ru|en): \{\n", body)
    return {
        parts[i]: re.findall(r"^    (\w+):", parts[i + 1], re.M) for i in range(1, len(parts), 2)
    }


def test_no_duplicate_locale_keys() -> None:
    for lang, keys in _locale_key_lists().items():
        dupes = {key for key in keys if keys.count(key) > 1}
        assert not dupes, (lang, dupes)


def test_settings_screens_are_translated_and_preloaded() -> None:
    keys = _locale_keys()["uz"]
    for name in ("profile.js", "chatprofile.js", "chats.js", "ui.js", "home.js", "board.js"):
        used = set(re.findall(r'\bt\("(\w+)"', (STATIC / name).read_text(encoding="utf-8")))
        assert not used - keys, (name, used - keys)
    profile = (STATIC / "profile.js").read_text(encoding="utf-8")
    faq = int(re.search(r"FAQ_COUNT = (\d+)", profile).group(1))
    privacy = int(re.search(r"PRIVACY_COUNT = (\d+)", profile).group(1))
    assert {f"faqQ{faq}", f"faqA{faq}", f"prvH{privacy}", f"prvP{privacy}"} <= keys
    assert f"faqQ{faq + 1}" not in keys and f"prvH{privacy + 1}" not in keys
    # Payment statuses shown in the history all have labels.
    assert {
        f"pst_{s}"
        for s in ("draft", "pending", "approved", "rejected", "disputed", "canceled", "expired")
    } <= keys
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for module in ("chatprofile.js", "scroller.js", "profile.js"):
        assert f'<link rel="modulepreload" href="/s/{module}">' in html


def test_tutor_students_screen_is_translated_and_preloaded() -> None:
    keys = _locale_keys()["uz"]
    used = set(re.findall(r'\bt\("(\w+)"', (STATIC / "students.js").read_text(encoding="utf-8")))
    assert not used - keys, used - keys
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<link rel="modulepreload" href="/s/students.js">' in html
    assert 'data-tab="cabinet"' not in html
    assert 'data-tab="study"' not in html
    assert 'go: "cabinet"' in (STATIC / "profile.js").read_text(encoding="utf-8")
    assert 'data-tab="students"' not in html
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "renderStudents" in app
    assert '"cabinet"' in (STATIC / "ui.js").read_text(encoding="utf-8")
    lesson_file = (STATIC / "lessons.js").read_text(encoding="utf-8")
    lesson_keys = set(re.findall(r'\bt\("(\w+)"', lesson_file))
    assert not lesson_keys - keys, lesson_keys - keys
    assert '<link rel="modulepreload" href="/s/lessons.js">' in html
    assert '<link rel="modulepreload" href="/s/summary.js">' in html
    assert 'data-tab="lessons"' not in html
    summary = (STATIC / "summary.js").read_text(encoding="utf-8")
    reminders = (STATIC / "reminders.js").read_text(encoding="utf-8")
    groups = (STATIC / "groups.js").read_text(encoding="utf-8")
    assert not set(re.findall(r'\bt\("(\w+)"', summary)) - keys
    assert not set(re.findall(r'\bt\("(\w+)"', reminders)) - keys
    assert not set(re.findall(r'\bt\("(\w+)"', groups)) - keys
    assert '<link rel="modulepreload" href="/s/groups.js">' in html
    assert '<link rel="modulepreload" href="/s/boards.js">' in html
    boards = (STATIC / "boards.js").read_text(encoding="utf-8")
    assert not set(re.findall(r'\bt\("(\w+)"', boards)) - keys
    assert '<link rel="modulepreload" href="/s/reminders.js">' in html
    for name in (
        "schedule.js",
        "next.js",
        "cabinet_nav.js",
        "roll.js",
        "roll_month.js",
        "my_roll.js",
        "group_tabs.js",
        "fees.js",
        "fee_form.js",
        "my_fees.js",
        "limits.js",
        "reports.js",
        "topic_form.js",
        "group_rows.js",
    ):
        used = set(re.findall(r'\bt\("(\w+)"', (STATIC / name).read_text(encoding="utf-8")))
        assert not used - keys, (name, used - keys)
    assert '<link rel="modulepreload" href="/s/schedule.js">' in html
    assert "renderSchedule" in (STATIC / "app.js").read_text(encoding="utf-8")
    assert "nextMarkup" in boards
    assert '<link rel="modulepreload" href="/s/study.js">' in html
    assert '<link rel="modulepreload" href="/s/reports.js">' in html
    assert "renderReports" in app
    assert "renderStudy" in app
    study = (STATIC / "study.js").read_text(encoding="utf-8")
    assert not set(re.findall(r'\bt\("(\w+)"', study)) - keys


def test_desktop_scroll_buttons_are_mouse_only() -> None:
    css = (STATIC / "layout.css").read_text(encoding="utf-8")
    scroller = (STATIC / "scroller.js").read_text(encoding="utf-8")
    assert "(hover: hover) and (pointer: fine)" in scroller
    block = css[css.index("/* M5: horizontal rows") :]
    assert ".hscroll > .hs-btn { display: none; }" in block
    assert "@media (hover: hover) and (pointer: fine)" in block
    assert "0.8" in scroller and '"wheel"' in scroller
    assert "initScrollers" in (STATIC / "app.js").read_text(encoding="utf-8")
    # The bottom bar is aligned to the centered column, not the full window.
    assert "max-width: var(--app-w)" in css and "--app-w: 600px" in css


def test_support_link_points_at_telegram_only() -> None:
    api = (STATIC / "api.js").read_text(encoding="utf-8")
    assert r"^https:\/\/t\.me\/" in api
    assert "https://t.me/${handle}" in (STATIC / "profile.js").read_text(encoding="utf-8")
