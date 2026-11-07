"""Phase 3 hostile transport, ingress, URL and runtime authority regression."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("marimo", reason="requires the dashboard extra")
from starlette.routing import Mount
from starlette.testclient import TestClient

from copytrade_pm.dashboard.server import (
    COOKIE_NAME,
    _cookie,
    make_app,
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
        assert target.startswith("/?") and target.endswith("#/health")
        assert "token" not in target and "very_secret" not in target
        assert parse_qs(urlsplit(target).query) == {
            "portfolio": ["gemini.phase5/P1@3"],
            "utc": ["7d"],
        }
        assert client.get("/risk?utc=7d").status_code in {200, 307}
        assert (
            client.get("/risk/?token=very_secret", follow_redirects=False).headers["location"]
            == "/#/risk"
        )
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
        assert (
            client.post(
                "/login", data={"secret": KEY}, headers={"origin": "https://malicious.example"}
            ).status_code
            == 403
        )
        reply = client.post(
            "/login",
            data={"secret": KEY},
            headers={"origin": "https://dashboard.internal.example"},
            follow_redirects=False,
        )
        assert reply.status_code == 303
        assert "secure" in reply.headers["set-cookie"].lower()
        assert "httponly" in reply.headers["set-cookie"].lower()
        assert "samesite=strict" in reply.headers["set-cookie"].lower()


def test_tailscale_https_proxy_host_echo_requires_loopback_and_exact_host():
    domain = "dashboard.tailnet.example"
    origin = "https://" + domain + ":8443"
    host = domain + ":8443"
    headers = {
        "host": host,
        "x-forwarded-host": host,
        "x-forwarded-proto": "https",
    }
    app = make_app(
        secret=KEY,
        allowed_hosts=frozenset({domain}),
        allowed_origins=frozenset({origin}),
    )
    # An actual loopback TLS-terminating reverse proxy may echo Host.
    with TestClient(app, base_url=origin, client=("127.0.0.1", 42100)) as client:
        assert client.get("/login", headers=headers).status_code == 200
        assert client.get("/", headers=headers).status_code == 401
        signed = client.post(
            "/login",
            headers={**headers, "origin": origin},
            data={"secret": KEY},
            follow_redirects=False,
        )
        assert signed.status_code == 303
        assert client.get("/", headers=headers).status_code == 200
        for invalid in (
            {"x-forwarded-host": "attacker.example"},
            {"x-forwarded-proto": "http"},
            {"host": "attacker.example"},
        ):
            assert client.get("/login", headers={**headers, **invalid}).status_code == 403
    # Identical headers from a non-loopback peer cannot impersonate Tailscale.
    with TestClient(app, base_url=origin, client=("198.51.100.10", 42100)) as client:
        assert client.get("/login", headers=headers).status_code == 403


@pytest.mark.parametrize(
    "header",
    [
        {"x-forwarded-host": "evil.example"},
        {"x-original-url": "/login"},
        {"x-rewrite-url": "/login"},
        {"host": "localhost@evil.example"},
    ],
)
def test_host_rewrite_and_proxy_spoof_denied(header):
    token = _cookie(KEY, int(datetime.now(UTC).timestamp()))
    with TestClient(make_app(secret=KEY), base_url="https://localhost") as client:
        response = client.get(
            "/risk/",
            headers={
                "cookie": f"{COOKIE_NAME}={token}",
                **header,
            },
        )
        assert response.status_code == 403


def test_single_run_only_marimo_app_without_mounted_view_servers():
    app = make_app(secret=KEY)
    mounts = [route for route in app.downstream.routes if isinstance(route, Mount)]
    assert len(mounts) == 1 and mounts[0].path == ""
    backend_mounts = [route for route in mounts[0].app.routes if isinstance(route, Mount)]
    assert len(backend_mounts) == 1 and backend_mounts[0].path == ""


def test_only_authenticated_origin_checked_bounded_ui_posts_are_admitted():
    routes = ("/api/kernel/function_call", "/api/kernel/set_ui_element_value")
    forbidden = (
        "/api/kernel/execute",
        "/api/kernel/run",
        "/api/kernel/save",
        "/api/kernel/restart_session",
        "/api/kernel/shutdown",
        "/api/kernel/set_model_value",
        "/api/files/create",
        "/api/files/delete",
        "/api/kernel/install_missing_packages",
    )
    with TestClient(make_app(secret=KEY), base_url="https://localhost") as client:
        for path in routes:
            assert (
                client.post(path, json={}, headers={"origin": "https://localhost"}).status_code
                == 401
            )
        token = _cookie(KEY, int(datetime.now(UTC).timestamp()))
        client.cookies.set(COOKIE_NAME, token)
        for path in routes:
            assert (
                client.post(path, json={}, headers={"origin": "https://evil.example"}).status_code
                == 403
            )
            assert (
                client.post(
                    path,
                    content=b"x",
                    headers={
                        "origin": "https://localhost",
                        "content-type": "text/plain",
                    },
                ).status_code
                == 415
            )
            assert (
                client.post(
                    path, json={"payload": "a" * 17_000}, headers={"origin": "https://localhost"}
                ).status_code
                == 413
            )
        for path in forbidden:
            assert (
                client.post(
                    path, json={"code": "print(1)"}, headers={"origin": "https://localhost"}
                ).status_code
                == 403
            )


def test_query_does_not_create_mutation_route():
    with TestClient(make_app(secret=KEY), base_url="https://localhost") as client:
        token = _cookie(KEY, int(datetime.now(UTC).timestamp()))
        client.cookies.set(COOKIE_NAME, token)
        for route in ("/halt", "/recover", "/broker/orders", "/registry/write"):
            assert client.post(route, headers={"origin": "https://localhost"}).status_code == 403
        assert (
            client.get("/risk/?portfolio=0x" + "a" * 40, follow_redirects=False).headers["location"]
            == "/#/risk"
        )
