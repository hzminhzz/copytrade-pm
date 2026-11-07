"""Local-only authenticated ASGI entrypoint for the read-only Marimo dashboard.

Run with: uv run --extra dashboard uvicorn copytrade_pm.dashboard.server:app
A dedicated, unprivileged OS identity and a private TLS/Tailscale proxy are
required before any deployment. This code does not install or start services.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import hmac
import os
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

from .navigation import LEGACY_PATHS, valid_scope

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
    except ValueError, OverflowError:
        return False


def _headers(scope: dict) -> dict[str, str]:
    return {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in scope.get("headers", [])
    }


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOOPBACK_ORIGINS = frozenset(
    {
        "http://localhost",
        "https://localhost",
        "http://127.0.0.1",
        "https://127.0.0.1",
        "http://[::1]",
        "https://[::1]",
    }
)


def _validated_hosts(hosts: frozenset[str]) -> frozenset[str]:
    if not hosts or len(hosts) > 16:
        raise ValueError("DASHBOARD_HOST_ALLOWLIST_REQUIRED")
    for host in hosts:
        if (
            not host
            or len(host) > 253
            or host != host.lower()
            or any(ch in host for ch in "@/?#*\\ ")
            or (host.startswith("[") and host != "[::1]")
        ):
            raise ValueError("DASHBOARD_HOST_ALLOWLIST_INVALID")
        if host.startswith(".") or host.endswith("."):
            raise ValueError("DASHBOARD_HOST_ALLOWLIST_INVALID")
    return hosts


def _allowed_host(headers: dict[str, str], allowed: frozenset[str] | None = None) -> bool:
    raw = headers.get("host", "")
    try:
        parsed = urlsplit("//" + raw)
        host = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return False
    return host.lower() in (allowed or LOOPBACK_HOSTS)


def _validated_origins(origins: frozenset[str]) -> frozenset[str]:
    if not origins or len(origins) > 16:
        raise ValueError("DASHBOARD_ORIGIN_ALLOWLIST_REQUIRED")
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or origin != parsed.geturl()
            or (parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS)
        ):
            raise ValueError("DASHBOARD_ORIGIN_ALLOWLIST_INVALID")
    return origins


def _origin_ok(headers: dict[str, str], allowed: frozenset[str] | None = None) -> bool:
    origin = headers.get("origin")
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
        if parsed.port is not None and parsed.port not in range(1, 65536):
            return False
    except ValueError:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    return origin in (allowed or LOOPBACK_ORIGINS)


class ViewerAuth:
    """Pure ASGI: same auth checks protect HTTP, static assets, and WebSockets."""

    def __init__(
        self,
        downstream,
        *,
        secret: str,
        clock=None,
        allowed_hosts: frozenset[str] | None = None,
        allowed_origins: frozenset[str] | None = None,
    ):
        _assert_secret(secret)
        self.downstream = downstream
        self.secret = secret
        self.clock = clock or (lambda: datetime.now(UTC))
        self.allowed_hosts = _validated_hosts(allowed_hosts or LOOPBACK_HOSTS)
        self.allowed_origins = _validated_origins(allowed_origins or LOOPBACK_ORIGINS)

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in {"http", "websocket"}:
            await self.downstream(scope, receive, send)
            return
        headers = _headers(scope)
        path = scope.get("path", "")
        names = [name.decode("latin1").lower() for name, _ in scope.get("headers", [])]
        if any(
            names.count(name) > 1
            for name in ("host", "origin", "cookie", "content-length", "content-type")
        ) or any(
            name in names for name in ("x-original-url", "x-rewrite-url", "transfer-encoding")
        ):
            return await self._deny(scope, send, 403)
        if "x-forwarded-host" in names:
            # Tailscale Serve supplies a redundant forwarded host after TLS
            # termination. Accept only its exact HTTPS, same-Host echo from
            # a real loopback socket; never use it to resolve routing/auth.
            client = scope.get("client")
            peer = client[0] if isinstance(client, (tuple, list)) and client else None
            if (
                peer not in {"127.0.0.1", "::1"}
                or names.count("x-forwarded-host") != 1
                or names.count("x-forwarded-proto") != 1
                or headers["x-forwarded-host"] != headers.get("host")
                or headers["x-forwarded-proto"] != "https"
            ):
                return await self._deny(scope, send, 403)
        if not _allowed_host(headers, self.allowed_hosts):
            return await self._deny(scope, send, 403)
        if kind == "websocket" and not _origin_ok(headers, self.allowed_origins):
            return await self._deny(scope, send, 403)
        if kind == "http" and scope.get("method") not in {"GET", "HEAD"}:
            # mo.routes laziness uses function_call; ordinary read-only
            # filters and refresh controls use set_ui_element_value.
            # Never admit execute/run/save/file-edit/command endpoints.
            ui_post = path in {
                "/api/kernel/function_call",
                "/api/kernel/set_ui_element_value",
            }
            allowed_post = (
                scope.get("method") == "POST"
                and (path == "/login" or ui_post)
                and _origin_ok(headers, self.allowed_origins)
            )
            if not allowed_post:
                return await self._deny(scope, send, 403)
            if ui_post:
                if headers.get("content-type", "").split(";")[0] != "application/json":
                    return await self._deny(scope, send, 415)
                try:
                    length = int(headers.get("content-length", "0"))
                except ValueError:
                    return await self._deny(scope, send, 400)
                if not 0 < length <= 16_384:
                    return await self._deny(scope, send, 413)
        cookies = {}
        for item in headers.get("cookie", "").split(";"):
            if "=" in item:
                key, value = item.strip().split("=", 1)
                cookies[key] = value
        authenticated = _valid_cookie(cookies.get(COOKIE_NAME, ""), self.secret, self.clock())
        if kind == "http" and scope.get("method") == "POST" and (path == "/login" or authenticated):
            limit = MAX_BODY if path == "/login" else 16_384
            try:
                declared = int(headers.get("content-length", "0"))
            except ValueError:
                return await self._deny(scope, send, 400)
            if declared < 0:
                return await self._deny(scope, send, 400)
            if declared > limit:
                return await self._deny(scope, send, 413)
            body = bytearray()
            try:
                async with asyncio.timeout(5):
                    while True:
                        message = await receive()
                        if message.get("type") != "http.request":
                            return await self._deny(scope, send, 400)
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > limit:
                            return await self._deny(scope, send, 413)
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await self._deny(scope, send, 408)
            if len(body) != declared:
                return await self._deny(scope, send, 400)
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if delivered:
                    return {"type": "http.disconnect"}
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            receive = bounded_receive
        if path == "/login" and kind == "http":
            return await self.downstream(scope, receive, send)
        if not authenticated:
            # Show human visitors the login screen, but keep APIs, assets,
            # and WebSockets fail-closed. Never propagate untrusted query data.
            clean_path = path if path == "/" else path.rstrip("/") + "/"
            if (
                kind == "http"
                and scope.get("method") in {"GET", "HEAD"}
                and (clean_path == "/" or clean_path in LEGACY_PATHS)
            ):
                response = RedirectResponse(
                    "/login",
                    status_code=303,
                    headers={
                        "Cache-Control": "no-store, private",
                        "Referrer-Policy": "no-referrer",
                    },
                )
                return await response(scope, receive, send)
            return await self._deny(scope, send, 401)
        scope["user"] = {"is_authenticated": True, "username": "risk-viewer"}
        if kind == "http" and scope.get("method") in {"GET", "HEAD"}:
            # Keep only safe, bookmarkable page scope. Never forward arbitrary
            # token, wallet or account parameters to the Marimo frontend.
            clean_path = path if path == "/" else path.rstrip("/") + "/"
            if clean_path == "/" or clean_path in LEGACY_PATHS:
                raw = scope.get("query_string", b"")
                if len(raw) > 512:
                    return await self._deny(scope, send, 414)
                parsed = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
                single = {key: values[0] for key, values in parsed.items() if len(values) == 1}
                safe = valid_scope(single)
                query = urlencode(safe).encode()
                # All legacy pages are aliases of a single authenticated
                # Marimo app. Fragments never reach ASGI; they route in-client.
                if clean_path != "/" or raw != query:
                    target = "/" + ("?" + query.decode() if query else "")
                    target += LEGACY_PATHS.get(clean_path, "")
                    response = RedirectResponse(
                        target, status_code=307, headers={"Cache-Control": "no-store"}
                    )
                    return await response(scope, receive, send)
        if kind == "http":

            async def secure_send(message):
                if message.get("type") == "http.response.start":
                    existing = list(message.get("headers", []))
                    hardened = {
                        b"cache-control": b"no-store, private",
                        b"x-content-type-options": b"nosniff",
                        b"x-frame-options": b"DENY",
                        b"referrer-policy": b"no-referrer",
                    }
                    existing = [
                        (key, value) for key, value in existing if key.lower() not in hardened
                    ]
                    existing.extend(hardened.items())
                    message["headers"] = existing
                await send(message)

            await self.downstream(scope, receive, secure_send)
        else:
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
            "<button type='submit'>Sign in</button></form></main></body></html>",
            headers={
                "Cache-Control": "no-store, private",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "same-origin",
            },
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
        supplied[0].encode("utf-8"), request.app.state.viewer_secret.encode("utf-8")
    )
    if not correct:
        return PlainTextResponse("INVALID_CREDENTIALS", status_code=401)
    response = RedirectResponse(
        "/",
        status_code=303,
        headers={"Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer"},
    )
    response.set_cookie(
        COOKIE_NAME,
        _cookie(request.app.state.viewer_secret, int(datetime.now(UTC).timestamp())),
        max_age=SESSION_SECONDS,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


def make_app(
    *,
    secret: str,
    clock=None,
    allowed_hosts: frozenset[str] | None = None,
    allowed_origins: frozenset[str] | None = None,
):
    """Fail closed unless configured; build only run-mode notebook routes."""
    _assert_secret(secret)
    import marimo

    server = marimo.create_asgi_app(
        include_code=False,
        redirect_console_to_browser=False,
        show_tracebacks=False,
        quiet=True,
    ).with_app(path="/", root=PAGES / "dashboard.py")
    app = Starlette(
        routes=[Route("/login", login, methods=["GET", "POST"]), Mount("/", server.build())]
    )
    app.state.viewer_secret = secret
    return ViewerAuth(
        app,
        secret=secret,
        clock=clock,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def configured_app():
    secret = os.environ.get("DASHBOARD_ACCESS_SECRET", "")
    _assert_secret(secret)
    hosts = frozenset(filter(None, os.environ.get("DASHBOARD_ALLOWED_HOSTS", "").split(",")))
    origins = frozenset(filter(None, os.environ.get("DASHBOARD_ALLOWED_ORIGINS", "").split(",")))
    if bool(hosts) != bool(origins):
        raise ValueError("DASHBOARD_HOST_AND_ORIGIN_MUST_BE_CONFIGURED_TOGETHER")
    return make_app(secret=secret, allowed_hosts=hosts or None, allowed_origins=origins or None)


# Fail closed at import if no explicit access secret is configured.
# Tests use make_app() with synthetic values and never import this ASGI object.
if os.environ.get("DASHBOARD_ACCESS_SECRET"):
    app = configured_app()
else:
    app = None


if __name__ == "__main__":
    raise SystemExit("Use uvicorn with DASHBOARD_ACCESS_SECRET and loopback-only binding.")
