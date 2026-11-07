"""Authenticated ASGI boundary tests (localhost only, HTTP and WebSocket)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("marimo", reason="requires the dashboard extra")

from copytrade_pm.dashboard.server import (
    COOKIE_NAME, ViewerAuth, _cookie, _valid_cookie, make_app,
)

KEY = "x" * 64
NOW = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)


def test_login_cookie_rejects_forgery_and_expiration():
    token = _cookie(KEY, int(NOW.timestamp()))
    assert _valid_cookie(token, KEY, NOW)
    assert not _valid_cookie(token, "y" * 64, NOW)
    assert not _valid_cookie(token, KEY, NOW + timedelta(hours=2))
    assert not _valid_cookie("99999999999999999999999." + "a" * 64, KEY, NOW)


def test_auth_required_for_http_and_actual_marimo_routes():
    from starlette.testclient import TestClient

    app = make_app(secret=KEY)
    with TestClient(app, base_url="https://localhost") as client:
        for path in ("/", "/health", "/research", "/risk", "/execution",
                     "/portfolios", "/performance", "/lab", "/health/assets/no.css"):
            result = client.get(path)
            assert result.status_code == 401
        assert client.get("/login").status_code == 200
        assert client.post("/login", data={"secret": "incorrect"},
                           headers={"origin": "https://localhost"}).status_code == 401
        assert client.post("/login", data={"secret": KEY}).status_code == 403
        malformed = client.post(
            "/login", content=b"secret=test",
            headers={"origin": "https://localhost", "content-length": "invalid",
                     "content-type": "application/x-www-form-urlencoded"},
        )
        assert malformed.status_code == 400
        result = client.post(
            "/login", data={"secret": KEY}, headers={"origin": "https://localhost"},
            follow_redirects=False,
        )
        assert result.status_code == 303
        assert result.cookies.get(COOKIE_NAME)
        for path in ("/", "/health", "/research", "/risk", "/execution",
                     "/portfolios", "/performance", "/lab"):
            response = client.get(path, follow_redirects=True)
            assert response.status_code == 200
            assert "marimo" in response.text.lower()
            assert "edit" not in response.headers.get("x-marimo-mode", "").lower()
        assert client.get("/", headers={"host": "malicious.tld"}).status_code == 403


def test_websocket_auth_applies_before_downstream_app():
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocket, WebSocketDisconnect

    async def echo(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({"authenticated": websocket.scope["user"]["is_authenticated"]})
        await websocket.close()

    protected = ViewerAuth(
        Starlette(routes=[WebSocketRoute("/ws", echo)]),
        secret=KEY, clock=lambda: NOW,
    )
    with TestClient(protected, base_url="https://localhost") as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws", headers={"origin": "https://localhost"}
            ):
                pass
        token = _cookie(KEY, int(NOW.timestamp()))
        headers = {"origin": "https://localhost", "host": "localhost",
                   "cookie": f"{COOKIE_NAME}={token}"}
        with client.websocket_connect("/ws", headers=headers) as socket:
            assert socket.receive_json() == {"authenticated": True}
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws", headers={**headers, "origin": "https://malicious.tld"}
            ):
                pass


def test_secret_strength_and_no_startup_without_config(monkeypatch):
    from copytrade_pm.dashboard.server import configured_app

    monkeypatch.delenv("DASHBOARD_ACCESS_SECRET", raising=False)
    with pytest.raises(ValueError, match="DASHBOARD_ACCESS_SECRET"):
        configured_app()
    with pytest.raises(ValueError):
        make_app(secret="weak")
