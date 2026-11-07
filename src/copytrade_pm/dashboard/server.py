"""Local-only authenticated ASGI entrypoint for the read-only Marimo dashboard.

Run with: uv run --extra dashboard uvicorn copytrade_pm.dashboard.server:app
A dedicated, unprivileged OS identity and a private TLS/Tailscale proxy are
required before any deployment. This code does not install or start services.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import hmac
import os
from pathlib import Path
import secrets
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

COOKIE_NAME = "__Host-copytrade-viewer"
MAX_BODY = 2048
SESSION_SECONDS = 3600
PAGES = Path(__file__).parent / "pages"


def _assert_secret(secret: str) -> None:
    if len(secret) < 32 or len(secret) > 512 or any(ord(ch) < 33 for ch in secret):
        raise ValueError("DASHBOARD_ACCESS_SECRET_REQUIRES_32_TO_512_NONSPACE_CHARS")


def _cookie(secret: str, epoch: int) -> str:
    message = str(epoch).encode()
    signature = hmac.new(secret.encode(), message, sha256).hexdigest()
    return f"{epoch}.{signature}"


def _valid_cookie(raw: str, secret: str, now: datetime) -> bool:
    try:
        epoch_text, tag = raw.split(".", 1)
        if not epoch_text.isdigit() or len(epoch_text) > 12:
            return False
        epoch = int(epoch_text)
        current = int(now.timestamp())
        if epoch > current or current - epoch >= SESSION_SECONDS:
            return False
        return hmac.compare_digest(_cookie(secret, epoch), raw)
    except (ValueError, OverflowError):
        return False


def _headers(scope: dict) -> dict[str, str]:
    return {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in scope.get("headers", [])
    }


def _allowed_host(headers: dict[str, str]) -> bool:
    host = headers.get("host", "").split(":")[0].lower()
    return host in {"localhost", "127.0.0.1", "[::1]", "::1"}


def _origin_ok(headers: dict[str, str]) -> bool:
    origin = headers.get("origin")
    if not origin:
        return False
    from urllib.parse import urlsplit

    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost", "127.0.0.1", "::1"
    } and parsed.username is None and parsed.password is None


class ViewerAuth:
    """Pure ASGI: same auth checks protect HTTP, static assets, and WebSockets."""

    def __init__(self, downstream, *, secret: str, clock=None):
        _assert_secret(secret)
        self.downstream = downstream
        self.secret = secret
        self.clock = clock or (lambda: datetime.now(UTC))

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in {"http", "websocket"}:
            await self.downstream(scope, receive, send)
            return
        headers = _headers(scope)
        path = scope.get("path", "")
        if not _allowed_host(headers):
            return await self._deny(scope, send, 403)
        if kind == "websocket" and not _origin_ok(headers):
            return await self._deny(scope, send, 403)
        if kind == "http" and scope.get("method") not in {"GET", "HEAD"}:
            if path != "/login" or scope.get("method") != "POST" or not _origin_ok(headers):
                return await self._deny(scope, send, 403)
        cookies = {}
        for item in headers.get("cookie", "").split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                cookies[key] = value
        authenticated = _valid_cookie(cookies.get(COOKIE_NAME, ""), self.secret, self.clock())
        if path == "/login" and kind == "http":
            return await self.downstream(scope, receive, send)
        if not authenticated:
            return await self._deny(scope, send, 401)
        scope["user"] = {"is_authenticated": True, "username": "risk-viewer"}
        await self.downstream(scope, receive, send)

    @staticmethod
    async def _deny(scope, send, code: int) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "ACCESS_DENIED"})
            return
        response = PlainTextResponse("ACCESS_DENIED", status_code=code)
        await response(scope, None, send)


async def login(request: Request) -> Response:
    if request.method == "GET":
        return HTMLResponse(
            "<!doctype html><html><head><meta name='viewport' "
            "content='width=device-width,initial-scale=1'>"
            "<title>Risk Viewer Login</title></head><body>"
            "<main><h1>Private risk viewer</h1>"
            "<form method='post' action='/login'>"
            "<label>Access secret <input type='password' name='secret' "
            "autocomplete='off' minlength='32' required></label>"
            "<button type='submit'>Sign in</button></form></main></body></html>"
        )
    if request.headers.get("content-type", "").split(";")[0] != (
        "application/x-www-form-urlencoded"
    ):
        return PlainTextResponse("INVALID_CONTENT_TYPE", status_code=415)
    try:
        content_length = int(request.headers.get("content-length", "0") or "0")
    except ValueError:
        return PlainTextResponse("INVALID_CONTENT_LENGTH", status_code=400)
    if content_length < 0:
        return PlainTextResponse("INVALID_CONTENT_LENGTH", status_code=400)
    if content_length > MAX_BODY:
        return PlainTextResponse("PAYLOAD_TOO_LARGE", status_code=413)
    body = await request.body()
    if len(body) > MAX_BODY:
        return PlainTextResponse("PAYLOAD_TOO_LARGE", status_code=413)
    values = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    supplied = values.get("secret", [])
    correct = len(supplied) == 1 and secrets.compare_digest(
        supplied[0], request.app.state.viewer_secret
    )
    if not correct:
        return PlainTextResponse("INVALID_CREDENTIALS", status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME, _cookie(request.app.state.viewer_secret, int(datetime.now(UTC).timestamp())),
        max_age=SESSION_SECONDS, secure=True, httponly=True, samesite="strict", path="/",
    )
    return response


def make_app(*, secret: str, clock=None):
    """Fail closed unless configured; build only run-mode notebook routes."""
    _assert_secret(secret)
    import marimo

    server = (
        marimo.create_asgi_app(
            include_code=False, redirect_console_to_browser=False, show_tracebacks=False,
            quiet=True,
        )
        .with_app(path="/", root=PAGES / "overview.py")
        .with_app(path="/research", root=PAGES / "registry.py")
        .with_app(path="/health", root=PAGES / "health.py")
    )
    app = Starlette(
        routes=[Route("/login", login, methods=["GET", "POST"]), Mount("/", server.build())]
    )
    app.state.viewer_secret = secret
    return ViewerAuth(app, secret=secret, clock=clock)


def configured_app():
    secret = os.environ.get("DASHBOARD_ACCESS_SECRET", "")
    _assert_secret(secret)
    return make_app(secret=secret)


# Fail closed at import if no explicit access secret is configured.
# Tests use make_app() with synthetic values and never import this ASGI object.
if os.environ.get("DASHBOARD_ACCESS_SECRET"):
    app = configured_app()
else:
    app = None


if __name__ == "__main__":
    raise SystemExit("Use uvicorn with DASHBOARD_ACCESS_SECRET and loopback-only binding.")
