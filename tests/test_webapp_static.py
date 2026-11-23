"""Mini App static checks: locale parity and screens are wired and lazy-loaded."""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"
PACKS = ("shell", "chat", "tutor", "admin")


def _locale_keys() -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for lang in ("uz", "ru", "en"):
        found: set[str] = set()
        for pack in PACKS:
            text = (STATIC / f"i18n_{pack}_{lang}.js").read_text(encoding="utf-8")
            found |= set(re.findall(r"^  (\w+):", text, re.M))
        keys[lang] = found
    return keys


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
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'import("./admin.js")' in app
    assert 'import("./notice.js")' in app
    assert '<link rel="modulepreload" href="/s/admin.js">' not in html
    assert 'data-tab="admin" hidden' in html
    assert "renderAdmin" in app
    notice = (STATIC / "notice.js").read_text(encoding="utf-8")
    missing = set(re.findall(r't\("(\w+)"', notice)) - _locale_keys()["uz"]
    assert not missing, missing
    nav = (STATIC / "nav.js").read_text(encoding="utf-8")
    assert 'hasRole("super_admin")' in nav


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
    assert '<link rel="modulepreload" href="/s/charts.js">' not in html
    assert 'import("./report.js")' in (STATIC / "app.js").read_text(encoding="utf-8")
    charts = (STATIC / "charts.js").read_text(encoding="utf-8")
    # Dependency-free: no imports beyond our own modules, accessible SVG.
    assert set(re.findall(r'from "([^"]+)"', charts)) == {"./i18n.js", "./ui.js"}
    assert 'role="img"' in charts and "aria-label" in charts
    assert '"stats", "📈", "admStats"' in (STATIC / "admin.js").read_text(encoding="utf-8")


def _locale_key_lists() -> dict[str, list[str]]:
    lists: dict[str, list[str]] = {}
    for lang in ("uz", "ru", "en"):
        keys: list[str] = []
        for pack in PACKS:
            text = (STATIC / f"i18n_{pack}_{lang}.js").read_text(encoding="utf-8")
            keys.extend(re.findall(r"^  (\w+):", text, re.M))
        lists[lang] = keys
    return lists


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
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    for module in ("chatprofile.js", "profile.js"):
        assert f'import("./{module}")' in app
        assert f'<link rel="modulepreload" href="/s/{module}">' not in html
    assert "initScrollers" in app


def test_tutor_students_screen_is_translated_and_preloaded() -> None:
    keys = _locale_keys()["uz"]
    used = set(re.findall(r'\bt\("(\w+)"', (STATIC / "students.js").read_text(encoding="utf-8")))
    assert not used - keys, used - keys
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<link rel="modulepreload" href="/s/students.js">' not in html
    assert 'import("./students.js")' in (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'data-tab="cabinet" hidden' in html
    assert 'data-tab="study" hidden' in html
    assert 'data-i18n="navCab"' in html
    assert 'data-i18n="navToday"' in html
    assert 'go: "cabinet"' in (STATIC / "profile.js").read_text(encoding="utf-8")
    assert 'data-tab="students"' not in html
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "renderStudents" in app
    nav = (STATIC / "nav.js").read_text(encoding="utf-8")
    assert "export function navTabs" in nav
    assert "teacherTabs" in nav or "cabinet" in nav
    assert "studentTabs" in nav or "study" in nav
    assert "currentVertical" in nav
    assert "isTutor()" in nav
    lesson_file = (STATIC / "lessons.js").read_text(encoding="utf-8")
    lesson_keys = set(re.findall(r'\bt\("(\w+)"', lesson_file))
    assert not lesson_keys - keys, lesson_keys - keys
    assert '<link rel="modulepreload" href="/s/lessons.js">' not in html
    assert '<link rel="modulepreload" href="/s/summary.js">' not in html
    assert 'data-tab="lessons"' not in html
    summary = (STATIC / "summary.js").read_text(encoding="utf-8")
    reminders = (STATIC / "reminders.js").read_text(encoding="utf-8")
    groups = (STATIC / "groups.js").read_text(encoding="utf-8")
    assert not set(re.findall(r'\bt\("(\w+)"', summary)) - keys
    assert not set(re.findall(r'\bt\("(\w+)"', reminders)) - keys
    assert not set(re.findall(r'\bt\("(\w+)"', groups)) - keys
    assert '<link rel="modulepreload" href="/s/groups.js">' not in html
    assert '<link rel="modulepreload" href="/s/boards.js">' not in html
    boards = (STATIC / "boards.js").read_text(encoding="utf-8")
    assert not set(re.findall(r'\bt\("(\w+)"', boards)) - keys
    assert '<link rel="modulepreload" href="/s/reminders.js">' not in html
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
        "student_form.js",
        "group_form.js",
        "requests.js",
    ):
        used = set(re.findall(r'\bt\("(\w+)"', (STATIC / name).read_text(encoding="utf-8")))
        assert not used - keys, (name, used - keys)
    assert '<link rel="modulepreload" href="/s/schedule.js">' not in html
    assert "renderSchedule" in (STATIC / "app.js").read_text(encoding="utf-8")
    assert "nextMarkup" in boards
    assert '<link rel="modulepreload" href="/s/study.js">' not in html
    assert '<link rel="modulepreload" href="/s/reports.js">' not in html
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


def test_shell_language_packs_are_preloaded_not_all_screens() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for name in (
        "app.js",
        "api.js",
        "i18n.js",
        "i18n_shell_uz.js",
        "i18n_chat_uz.js",
        "i18n_tutor_uz.js",
        "ui.js",
        "nav.js",
    ):
        assert f'<link rel="modulepreload" href="/s/{name}">' in html
    assert "i18n_admin_uz.js" not in html
    assert "i18n_shell_ru.js" not in html
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'import("./admin.js")' in app
    assert "min-height: 44px" in (STATIC / "layout.css").read_text(encoding="utf-8")
    assert "themeParams" in (STATIC / "api.js").read_text(encoding="utf-8")
    assert "Inter," not in (STATIC / "theme.css").read_text(encoding="utf-8")
    assert "err-retry" in (STATIC / "ui.js").read_text(encoding="utf-8")


def test_student_app_has_three_tabs_and_no_role_buttons() -> None:
    """Phase A/B: no O'quvchi/O'qituvchi bar; student app is Bosh / Darslar / Profil."""
    keys = _locale_keys()["uz"]
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    roles = (STATIC / "roles.js").read_text(encoding="utf-8")
    vertical = (STATIC / "vertical.js").read_text(encoding="utf-8")
    assert "rolebar" not in html
    assert "rolebar" not in (STATIC / "layout.css").read_text(encoding="utf-8")
    assert "mountRoles" not in app and "mountRoles" not in roles
    assert 'data-tab="agenda" hidden' in html and 'id="i-calendar"' in html
    assert 'studentTabs: ["study", "agenda"]' in vertical
    assert "renderAgenda" in app
    assert '<link rel="modulepreload" href="/s/study.js">' not in html
    for name in ("study.js", "profile.js", "roles.js", "nav.js"):
        used = set(re.findall(r'\bt\("(\w+)"', (STATIC / name).read_text(encoding="utf-8")))
        assert not used - keys, (name, used - keys)
    profile = (STATIC / "profile.js").read_text(encoding="utf-8")
    assert 'act: "role"' in profile and "bothRoles()" in profile
    assert "ritm.role" in roles


def test_cabinet_menu_replaces_the_section_grid() -> None:
    """Teacher sections live in a hamburger drawer shown on every cabinet screen."""
    keys = _locale_keys()
    nav_file = (STATIC / "cabinet_nav.js").read_text(encoding="utf-8")
    used = set(re.findall(r'\bt\("(\w+)"', nav_file)) | {
        "grpNav",
        "schNav",
        "stuTitle",
        "lesTitle",
        "remTitle",
        "feeNav",
    }
    for lang, have in keys.items():
        assert not used - have, (lang, used - have)
    for name in (
        "cabinet/groups",
        "cabinet/schedule",
        "cabinet/students",
        "cabinet/lessons",
        "cabinet/reminders",
        "cabinet/fees",
    ):
        assert f'"{name}"' in nav_file
    assert (
        "showModal" in nav_file
        and 'aria-current="page"' in nav_file
        and "aria-expanded" in nav_file
    )
    for path in STATIC.glob("*.js"):
        assert "cabinetSwitch(" not in path.read_text(encoding="utf-8"), path.name
    assert "cab-switch" not in (STATIC / "layout.css").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<symbol id="i-menu"' in html and '<symbol id="i-close"' in html
    assert "if (closeCabinetMenu()) return;" in (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'syncCabinetMenu(tab === "cabinet"' in (STATIC / "nav.js").read_text(encoding="utf-8")
