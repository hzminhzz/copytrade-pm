"""Live no-password access check through actual Tailscale Serve HTTPS.

This test never reads the viewer secret or the owner identity value.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

CONFIG = Path("/home/quant/.config/copytrade-dashboard/private.env")


def base() -> str:
    values = {}
    for line in CONFIG.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key in {"DASHBOARD_ALLOWED_HOSTS", "DASHBOARD_TAILSCALE_USER_LOGIN"}:
            values[key] = value
    if not values.get("DASHBOARD_TAILSCALE_USER_LOGIN"):
        raise RuntimeError("TAILNET_SSO_NOT_ENABLED")
    host = values["DASHBOARD_ALLOWED_HOSTS"].split(",", 1)[0]
    if not host.endswith(".ts.net"):
        raise RuntimeError("NO_TAILSCALE_HOST")
    return "https://" + host + ":8443"


def main() -> None:
    url = base()
    with httpx.Client(base_url=url, timeout=15, follow_redirects=False) as client:
        root = client.get("/")
        assert root.status_code == 200, root.status_code
        assert "marimo" in root.text.lower()
        assert "Private risk viewer" not in root.text
        assert not client.cookies, "NO_VIEWER_COOKIE_SHOULD_BE_NEEDED"
        login = client.get("/login")
        assert login.status_code == 303 and login.headers["location"] == "/"
        assert client.get("/health?utc=7d", follow_redirects=False).headers["location"] == (
            "/?utc=7d#/health"
        )
        assert client.get("/?token=LEAK", follow_redirects=False).headers["location"] == "/"
        assert (
            client.post(
                "/login", data={"secret": "old-password-unused"}, headers={"origin": url}
            ).status_code
            == 403
        )
        assert (
            client.post("/api/kernel/execute", json={}, headers={"origin": url}).status_code == 403
        )
        assert (
            client.post(
                "/api/kernel/function_call", json={}, headers={"origin": "https://attacker.example"}
            ).status_code
            == 403
        )
    with httpx.Client(base_url="http://127.0.0.1:18777", timeout=15) as direct:
        assert direct.get("/").status_code == 403
        assert direct.get("/login").status_code == 403
    try:
        with connect(
            "ws://127.0.0.1:18777/ws",
            origin=url,
            open_timeout=8,
        ):
            raise AssertionError("DIRECT_WEBSOCKET_WITHOUT_TAILNET_IDENTITY_ADMITTED")
    except InvalidStatus as exc:
        assert exc.response.status_code in (401, 403), exc.response.status_code
    print("LIVE_TAILSCALE_PASSWORDLESS_OWNER_HTTP_AND_WS_NEGATIVES_PASSED")


if __name__ == "__main__":
    main()
