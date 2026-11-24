import mimetypes
import os
from datetime import datetime, time
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"
VIEWPORTS = (768, 900, 1024, 1100, 1280)
PHONE_VIEWPORTS = (360, 412)
TASHKENT = ZoneInfo("Asia/Tashkent")

TEXT_OVERFLOW_JS = """() => [...document.querySelectorAll(
    ".pn-skip, #pn-nav a:not(.pn-sr), #pn-switch a, #pn-main h1, #pn-main h2, #pn-main p, "
    + "#pn-main a, #pn-main button, #pn-main th, #pn-main td, #pn-main b, "
    + "#pn-main small, #pn-main span"
)].filter((node) => {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden"
        && !node.classList.contains("pn-sr")
        && rect.width > 0 && rect.height > 0
        && node.scrollWidth > node.clientWidth + 1;
}).map((node) => ({
    text: node.textContent.trim(),
    className: typeof node.className === "string" ? node.className : "",
    viewport: window.innerWidth,
    width: node.clientWidth,
    scrollWidth: node.scrollWidth
}))"""

SMALL_TARGETS_JS = """() => [...document.querySelectorAll(
    "a[href], button:not(:disabled), input:not(:disabled), "
    + "select:not(:disabled), textarea:not(:disabled), [role='button']"
)].filter((node) => {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    if (style.display === "none" || style.visibility === "hidden"
        || rect.width === 0 || rect.height === 0) return false;
    const violatesTarget = rect.width < 44 || rect.height < 44;
    return violatesTarget;
}).map((node) => ({
    tag: node.tagName,
    className: typeof node.className === "string" ? node.className : "",
    width: Math.round(node.getBoundingClientRect().width),
    height: Math.round(node.getBoundingClientRect().height)
}))"""


async def _assert_panel_layout(page, theme: str, width: int) -> None:
    await page.set_viewport_size({"width": width, "height": 900})
    layout = await page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            client: document.documentElement.clientWidth
        })"""
    )
    assert layout["viewport"] == width
    assert layout["document"] <= layout["client"], (
        f"{theme} mavzu, {width} px: sahifa gorizontal siljiydi"
    )
    clipped_text = await page.evaluate(TEXT_OVERFLOW_JS)
    assert not clipped_text, f"{theme} mavzu, {width} px: matn sig‘madi: {clipped_text}"

    too_small = await page.evaluate(SMALL_TARGETS_JS)
    assert not too_small, f"{theme} mavzu, {width} px: 44 px dan kichik nishon bor: {too_small}"


@pytest.mark.e2e
async def test_panel_layout_across_viewports_and_themes() -> None:
    from playwright.async_api import async_playwright

    today = datetime.now(TASHKENT).date()
    starts_at = datetime.combine(today, time(0, 5), tzinfo=TASHKENT).isoformat()
    ends_at = (datetime.combine(today, time(0, 50), tzinfo=TASHKENT)).isoformat()
    lesson = {
        "id": 7,
        "group_id": 3,
        "title": "A",
        "group_name": "A",
        "status": "scheduled",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "students": 1,
        "meeting_url": None,
        "marked": False,
    }
    home = {
        "today": today.isoformat(),
        "lessons": [lesson],
        "unmarked": {"count": 0, "items": []},
        "overdue": {"count": 0, "sum_uzs": 0},
        "requests": {"count": 0, "first": None},
        "homework": None,
        "income": {"sum_uzs": 0, "payments": 0},
        "user": {"name": "Ali", "language": "uz"},
        "teacher": True,
        "bot_username": "ritm_airobot",
        "both_roles": True,
    }
    groups = {"groups": [{"id": 3, "name": "A", "level": ""}]}
    attendance = {
        "starts_at": starts_at,
        "group_id": 3,
        "group_name": "A",
        "students": [{"student_id": 11, "name": "Ali", "status": None}],
    }
    external_requests = []
    unmocked_api = []
    base = "http://ritm.test"

    async with async_playwright() as playwright:
        executable_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        launch_options = {"executable_path": executable_path} if executable_path else {}
        browser = await playwright.chromium.launch(**launch_options)
        page = await browser.new_page()

        async def fulfill(route) -> None:
            request_url = urlsplit(route.request.url)
            if request_url.netloc != "ritm.test":
                external_requests.append(route.request.url)
                await route.abort()
                return

            if request_url.path == "/panel":
                await route.fulfill(
                    status=200,
                    body=(STATIC / "panel.html").read_text(encoding="utf-8"),
                    content_type="text/html",
                )
                return

            if request_url.path.startswith("/s/"):
                asset = STATIC / Path(request_url.path).name
                if asset.is_file():
                    content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                    await route.fulfill(
                        status=200,
                        body=asset.read_bytes(),
                        content_type=content_type,
                    )
                else:
                    await route.fulfill(status=404, body="")
                return

            if request_url.path == "/api/panel/home":
                await route.fulfill(json=home)
                return
            if request_url.path == "/api/tutor/sessions":
                await route.fulfill(json=[lesson])
                return
            if request_url.path == "/api/tutor/groups":
                await route.fulfill(json=groups)
                return
            if request_url.path == "/api/tutor/sessions/7/attendance":
                await route.fulfill(json=attendance)
                return
            if request_url.path.startswith("/api/"):
                unmocked_api.append(route.request.url)
                await route.fulfill(status=501, json={"error": "sinovda soxta javob yo‘q"})
                return

            await route.fulfill(status=404, body="")

        await page.route("**/*", fulfill)

        theme_backgrounds = {}
        try:
            for theme in ("light", "dark"):
                await page.emulate_media(color_scheme=theme)
                await page.goto(f"{base}/panel")
                await page.locator("#pn-main h1").wait_for()
                assert await page.locator("html").get_attribute("data-theme") == theme

                await page.locator(".pn-skip").focus()
                await page.keyboard.press("Tab")
                assert await page.evaluate(
                    "document.activeElement.getAttribute('data-route') === 'home'"
                )
                await page.keyboard.press("Tab")
                assert await page.evaluate(
                    "document.activeElement.getAttribute('data-route') === 'schedule'"
                )
                await page.keyboard.press("Enter")
                await page.wait_for_function("location.hash === '#/schedule'")

                colors = await page.evaluate(
                    """() => getComputedStyle(document.documentElement)
                        .getPropertyValue("--bg").trim()"""
                )
                assert colors
                theme_backgrounds[theme] = colors

                for width in (*VIEWPORTS, *PHONE_VIEWPORTS):
                    await _assert_panel_layout(page, theme, width)

                await page.locator(".pd-week").wait_for()
                await page.locator(".pd-pill").wait_for()
                await page.locator(".pd-mark").first.wait_for()
                for width in (*VIEWPORTS, *PHONE_VIEWPORTS):
                    await _assert_panel_layout(page, theme, width)
            assert theme_backgrounds["light"] != theme_backgrounds["dark"]
        finally:
            await browser.close()

    assert not external_requests, f"Tashqi manzilga so‘rov urinishlari: {external_requests}"
    assert not unmocked_api, f"Soxta javobsiz API so‘rovlari: {unmocked_api}"
