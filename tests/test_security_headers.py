"""Mini App security headers: CSP allows Telegram and never sends X-Frame-Options DENY."""

from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from app.webapp.assets import setup_assets
from app.webapp.security import CSP, SECURITY_HEADERS, apply_security_headers, security_headers

STATIC = Path(__file__).resolve().parents[1] / "app" / "webapp" / "static"


def test_csp_allows_telegram_script_and_inline_styles() -> None:
    assert "script-src" in CSP and "https://telegram.org" in CSP
    assert "style-src 'self' 'unsafe-inline'" in CSP
    assert "frame-ancestors" in CSP
    assert "https://web.telegram.org" in CSP
    assert "https://*.telegram.org" in CSP
    assert "X-Frame-Options" not in SECURITY_HEADERS
    assert "nosniff" in SECURITY_HEADERS["X-Content-Type-Options"]
    assert SECURITY_HEADERS["Referrer-Policy"] == "no-referrer"


def test_index_has_no_inline_scripts() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'src="https://telegram.org/js/telegram-web-app.js"' in html
    assert "<script>" not in html.replace("<script src=", "").replace('<script type="module"', "")
    assert 'style="' in html  # shell skeleton; requires style-src unsafe-inline


def test_apply_drops_x_frame_options() -> None:
    response = web.Response(text="ok")
    response.headers["X-Frame-Options"] = "DENY"
    apply_security_headers(response)
    assert "X-Frame-Options" not in response.headers
    assert response.headers["Content-Security-Policy"] == CSP


async def test_index_and_assets_send_security_headers() -> None:
    app = web.Application(middlewares=[security_headers])
    store = setup_assets(app, STATIC)
    async with TestClient(TestServer(app)) as client:
        index = await client.get("/")
        assert index.status == 200
        assert index.headers["Content-Security-Policy"] == CSP
        assert index.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" not in index.headers
        body = await index.text()
        assert "telegram-web-app.js" in body
        res = await client.get(f"/s/{store.version}/app.js")
        assert res.status == 200
        assert res.headers["Content-Security-Policy"] == CSP
        assert "X-Frame-Options" not in res.headers
