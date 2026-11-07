"""Phase 3 hostile transport, ingress, URL and runtime authority regression."""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from copytrade_pm.dashboard.server import (
    COOKIE_NAME, _cookie, make_app,
)

KEY = "z" * 64
NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


def test_authenticated_query_redaction_cookie_and_headers():
    with TestClient(make_app(secret=KEY), base_url="https://localhost") as client:
        token = _cookie(KEY, int(datetime.now(UTC).timestamp()))
        client.cookies.set(COOKIE_NAME, token)
        response = client.get(
            "/health?portfolio=gemini.phase5%2FP1%403&utc=7d&token=very_secret",
            follow_redirects=False,
        )
        assert response.status_code == 307
        target = response.headers["location"]
        assert target.startswith("/health/?")
        assert "token" not in target and "very_secret" not in target
        assert parse_qs(urlsplit(target).query) == {
            "portfolio": ["gemini.phase5/P1@3"], "utc": ["7d"],
        }
        assert client.get("/risk?utc=7d").status_code in {200, 307}
        assert client.get("/risk/?token=very_secret",
                          follow_redirects=False).headers["location"] == "/risk/"
        assert client.get("/risk/?utc=x" * 1000, follow_redirects=False).status_code == 414
        fresh = client.get("/risk/", follow_redirects=True)
        assert fresh.status_code == 200
        assert "no-store" in fresh.headers["cache-control"]
        assert fresh.headers["x-content-type-options"] == "nosniff"
        assert fresh.headers["x-frame-options"] == "DENY"
        assert fresh.headers["referrer-policy"] == "no-referrer"


def test_external_host_requires_explicit_tls_origin_and_cookie():
    with pytest.raises(ValueError):
        make_app(secret=KEY, allowed_hosts=frozenset({"*"}))
    with pytest.raises(ValueError):
        make_app(secret=KEY, allowed_origins=frozenset({"http://example.com"}))
    hosts = frozenset({"dashboard.internal.example"})
    origins = frozenset({"https://dashboard.internal.example"})
    app = make_app(secret=KEY, allowed_hosts=hosts, allowed_origins=origins)
    with TestClient(app, base_url="https://dashboard.internal.example") as client:
        # A same-origin Referer permits ordinary browser login form submission
        # while refusing Referer disclosure to other origins.
        assert client.get("/login").headers["referrer-policy"] == "same-origin"
        assert client.get("/risk/").status_code == 401
        assert client.get("/risk/", headers={"host": "malicious.example"}).status_code == 403
        assert client.post("/login", data={"secret": KEY},
                           headers={"origin": "https://malicious.example"}).status_code == 403
        reply = client.post("/login", data={"secret": KEY},
                            headers={"origin": "https://dashboard.internal.example"},
                            follow_redirects=False)
        assert reply.status_code == 303
        assert "secure" in reply.headers["set-cookie"].lower()
        assert "httponly" in reply.headers["set-cookie"].lower()
        assert "samesite=strict" in reply.headers["set-cookie"].lower()


@pytest.mark.parametrize("header", [
    {"x-forwarded-host": "evil.example"}, {"x-original-url": "/login"},
    {"x-rewrite-url": "/login"}, {"host": "localhost@evil.example"},
])
def test_host_rewrite_and_proxy_spoof_denied(header):
    token = _cookie(KEY, int(datetime.now(UTC).timestamp()))
    with TestClient(make_app(secret=KEY), base_url="https://localhost") as client:
        response = client.get("/risk/", headers={
            "cookie": f"{COOKIE_NAME}={token}", **header,
        })
        assert response.status_code == 403


def test_query_does_not_create_mutation_route():
    with TestClient(make_app(secret=KEY), base_url="https://localhost") as client:
        token = _cookie(KEY, int(datetime.now(UTC).timestamp()))
        client.cookies.set(COOKIE_NAME, token)
        for route in ("/halt", "/recover", "/broker/orders", "/registry/write"):
            assert client.post(route, headers={"origin": "https://localhost"}).status_code == 403
        assert client.get("/risk/?portfolio=0x" + "a" * 40,
                          follow_redirects=False).headers["location"] == "/risk/"
