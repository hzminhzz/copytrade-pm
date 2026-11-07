"""Live HTTP and WebSocket auth smoke for a running quant-owned dashboard.

Only prints pass/fail assertions and never logs or displays access credentials.
No broker, journal or registry writes.
"""

from __future__ import annotations

from pathlib import Path
from httpx import Client
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus

BASE = "http://127.0.0.1:18777"
ORIGIN = BASE
HOST = "127.0.0.1"
CONFIG = Path("/home/quant/.config/copytrade-dashboard/private.env")


def secret() -> str:
    for line in CONFIG.read_text().splitlines():
        if line.startswith("DASHBOARD_ACCESS_SECRET="):
            return line.partition("=")[2]
    raise AssertionError("NO_DASHBOARD_SECRET")


def main() -> None:
    with Client(base_url=BASE, follow_redirects=False, timeout=15) as c:
        assert c.get("/login").status_code == 200
        assert c.get("/").status_code == 401
        assert c.get("/research").status_code == 401
        assert c.get("/login", headers={"host": "attacker.example"}).status_code == 403
        assert (
            c.post("/login", data={"secret": "invalid"}, headers={"origin": ORIGIN}).status_code
            == 401
        )
        assert c.post("/login", data={"secret": secret()}).status_code == 403
        r = c.post("/login", data={"secret": secret()}, headers={"origin": ORIGIN})
        assert r.status_code == 303, r.status_code
        raw = r.headers.get("set-cookie", "")
        assert "Secure" in raw and "HttpOnly" in raw and "SameSite=strict" in raw
        cookie = raw.split(";", 1)[0]
        auth = {"cookie": cookie}
        assert c.get("/", headers=auth).status_code == 200
        redirected = c.get("/risk", headers=auth, follow_redirects=False)
        assert redirected.status_code == 307, redirected.status_code
        assert redirected.headers.get("location") == "/#/risk"
        assert c.get("/", headers=auth).status_code == 200
        assert (
            c.post("/api/kernel/execute", json={}, headers={**auth, "origin": ORIGIN}).status_code
            == 403
        )
        assert c.get("/login", headers={"host": "127.0.0.1.evil.example"}).status_code == 403
    try:
        with connect("ws://127.0.0.1:18777/api/kernel/ws", origin=ORIGIN, open_timeout=8):
            raise AssertionError("UNAUTHENTICATED_WEBSOCKET_ADMITTED")
    except InvalidStatus as exc:
        assert exc.response.status_code in (401, 403), exc.response.status_code
    print("LIVE_LOCAL_AUTH_SMOKE_PASSED")


if __name__ == "__main__":
    main()
