"""HTTP security headers for the Mini App. Telegram Web frames the page; do not send DENY."""

from __future__ import annotations

from aiohttp import web

# Telegram Web (and its forks) load the Mini App in an iframe. iOS/Android use a
# top-level WebView, where frame-ancestors does not apply.
TELEGRAM_FRAMES = (
    "https://web.telegram.org https://webk.telegram.org https://webz.telegram.org "
    "https://*.telegram.org"
)

# Inline styles are used in the shell skeleton and in generated markup. There are
# no inline scripts in index.html; telegram-web-app.js is the only third-party script.
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://telegram.org https://*.telegram.org; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' blob: data: https:; "
    "font-src 'self'; "
    "connect-src 'self' https://telegram.org https://*.telegram.org; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    f"frame-ancestors 'self' {TELEGRAM_FRAMES}"
)

# The teacher panel is a top-level page: it may frame our own cabinet screens but is
# never framed itself, and it has no inline script or style.
PANEL_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: https:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
}


def apply_security_headers(response: web.StreamResponse) -> web.StreamResponse:
    """Attach the policy if the handler did not already set a header."""
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    # Never advertise a policy that would block Telegram Web's iframe.
    response.headers.pop("X-Frame-Options", None)
    return response


@web.middleware
async def security_headers(request: web.Request, handler):
    """Add CSP and companion headers to every successful response."""
    response = await handler(request)
    return apply_security_headers(response)
