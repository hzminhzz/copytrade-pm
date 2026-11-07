"""Live private HTTPS/auth/WS negative smoke; no credentials printed."""

from __future__ import annotations

from pathlib import Path

from httpx import Client
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

UA = "OpenAI File Downloader, XaiImageApiFetch/1.0"
SECRET_FILE = Path("/home/quant/.config/copytrade-dashboard/private.env")


def private_base() -> str:
    for line in SECRET_FILE.read_text().splitlines():
        if line.startswith("DASHBOARD_ALLOWED_HOSTS="):
            hostname = line.partition("=")[2].split(",", 1)[0]
            if hostname.endswith(".ts.net"):
                return "https://" + hostname + ":8443"
    raise RuntimeError("PRIVATE_TAILNET_HOST_MISSING")


URL = private_base()


def key() -> str:
    for line in SECRET_FILE.read_text().splitlines():
        if line.startswith("DASHBOARD_ACCESS_SECRET="):
            return line.partition("=")[2]
    raise ValueError("MISSING_VIEWER_CREDENTIAL")


def main():
    with Client(base_url=URL, timeout=15, follow_redirects=False, headers={"User-Agent": UA}) as c:
        assert c.get("/login").status_code == 200
        assert c.get("/").status_code == 401
        assert c.get("/research").status_code == 401
        assert c.post("/login", data={"secret": key()}).status_code == 403
        login = c.post("/login", data={"secret": key()}, headers={"origin": URL})
        assert login.status_code == 303, login.status_code
        raw_cookie = login.headers.get("set-cookie", "")
        assert "Secure" in raw_cookie and "HttpOnly" in raw_cookie
        assert c.get("/").status_code == 200
        assert c.post("/api/kernel/execute", json={}, headers={"origin": URL}).status_code == 403
        assert (
            c.post(
                "/api/kernel/function_call", json={}, headers={"origin": "https://attacker.example"}
            ).status_code
            == 403
        )
    try:
        with connect(
            URL.replace("https://", "wss://") + "/api/kernel/ws",
            origin=URL,
            open_timeout=10,
            additional_headers={"User-Agent": UA},
        ):
            raise AssertionError("UNAUTHENTICATED_WSS_NOT_REJECTED")
    except InvalidStatus as exc:
        assert exc.response.status_code in (401, 403), exc.response.status_code

    # Authenticated WS handshake depends on marimo's full session protocol.
    # The real Firefox test proves that path is operational.
    print("LIVE_TAILSCALE_HTTPS_AND_WSS_AUTH_NEGATIVES_PASS")


if __name__ == "__main__":
    main()
