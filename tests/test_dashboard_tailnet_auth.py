"""Serve-identity SSO is scoped to the exact tailnet login and trusted ingress.

Keep password-only make_app() backward compatible for safe release rollback.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("marimo", reason="requires dashboard extra")
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from copytrade_pm.dashboard.server import COOKIE_NAME, ViewerAuth, _cookie, make_app

KEY = "t" * 64
LOGIN = "owner@example.com"
HOST = "dashboard.tailnet.example"
HOST_PORT = HOST + ":8443"
ORIGIN = "https://" + HOST_PORT
HEADERS = {
    "host": HOST_PORT,
    "x-forwarded-host": HOST_PORT,
    "x-forwarded-proto": "https",
    "tailscale-user-login": LOGIN,
}


def make_tailnet_app():
    return make_app(
        secret=KEY,
        tailnet_login=LOGIN,
        allowed_hosts=frozenset({HOST}),
        allowed_origins=frozenset({ORIGIN}),
    )


def test_allowed_tailscale_user_sees_root_and_login_not_password_form():
    with TestClient(
        make_tailnet_app(),
        base_url=ORIGIN,
        client=("127.0.0.1", 41234),
    ) as client:
        response = client.get("/", headers=HEADERS)
        assert response.status_code == 200
        assert "marimo" in response.text.lower()
        assert "set-cookie" not in response.headers
        login = client.get("/login", headers=HEADERS, follow_redirects=False)
        assert login.status_code == 303
        assert login.headers["location"] == "/"
        assert "no-store" in login.headers["cache-control"]
        assert (
            client.get("/health?utc=7d", headers=HEADERS, follow_redirects=False).headers[
                "location"
            ]
            == "/?utc=7d#/health"
        )
        assert (
            client.get(
                "/?token=LEAK&wallet=0xdead", headers=HEADERS, follow_redirects=False
            ).headers["location"]
            == "/"
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"tailscale-user-login": "another@example.com"},
        {"tailscale-user-login": ""},
        {"x-forwarded-proto": "http"},
        {"x-forwarded-host": "attacker.example"},
        {"host": "attacker.example"},
    ],
)
def test_bad_identity_or_proxy_fails_closed(bad):
    with TestClient(
        make_tailnet_app(),
        base_url=ORIGIN,
        client=("127.0.0.1", 41234),
    ) as client:
        assert client.get("/", headers={**HEADERS, **bad}).status_code == 403


def test_no_tailnet_identity_or_proxy_cannot_use_old_cookie_or_password():
    with TestClient(
        make_tailnet_app(),
        base_url=ORIGIN,
        client=("127.0.0.1", 41234),
    ) as client:
        assert client.get("/").status_code == 403
        assert (
            client.get("/", headers={"host": HOST_PORT, "tailscale-user-login": LOGIN}).status_code
            == 403
        )
        assert (
            client.post(
                "/login", data={"secret": KEY}, headers={"origin": ORIGIN, **HEADERS}
            ).status_code
            == 403
        )
        cookie = _cookie(KEY, int(datetime.now(UTC).timestamp()))
        assert (
            client.get(
                "/",
                headers={
                    "host": HOST_PORT,
                    "cookie": f"{COOKIE_NAME}={cookie}",
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/kernel/function_call", json={}, headers={"origin": ORIGIN}
            ).status_code
            == 403
        )


def test_spoofed_identity_rejected_from_non_loopback_peer():
    with TestClient(
        make_tailnet_app(),
        base_url=ORIGIN,
        client=("198.51.100.7", 41234),
    ) as client:
        assert client.get("/", headers=HEADERS).status_code == 403


def test_duplicate_identity_header_rejected():
    with TestClient(
        make_tailnet_app(),
        base_url=ORIGIN,
        client=("127.0.0.1", 41234),
    ) as client:
        headers = [*HEADERS.items(), ("tailscale-user-login", LOGIN)]
        assert client.get("/", headers=headers).status_code == 403


def test_tailnet_websocket_requires_same_identity_and_exact_origin():
    async def echo(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({"authorized": websocket.scope["user"]["is_authenticated"]})
        await websocket.close()

    app = ViewerAuth(
        Starlette(routes=[WebSocketRoute("/ws", echo)]),
        secret=KEY,
        tailnet_login=LOGIN,
        allowed_hosts=frozenset({HOST}),
        allowed_origins=frozenset({ORIGIN}),
    )
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 41234)) as client:
        with client.websocket_connect("/ws", headers={**HEADERS, "origin": ORIGIN}) as socket:
            assert socket.receive_json() == {"authorized": True}
        for altered in (
            {"tailscale-user-login": "wrong@example.com"},
            {"origin": "https://evil.example"},
            {"x-forwarded-proto": "http"},
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws", headers={**HEADERS, "origin": ORIGIN, **altered}
                ):
                    pass


@pytest.mark.parametrize("login", ["", "*", "bad\nheader", "name with spaces", "x" * 300])
def test_untrusted_auth_configuration_refused(login):
    with pytest.raises(ValueError):
        make_app(secret=KEY, tailnet_login=login or " ")
