"""Minimal synchronous CDP client for the local obscura browser.

The Grafana and quant acceptance scripts need a real browser: viewport-exact
layout, rendered SPA text, screenshots. `obscura serve` exposes CDP on
127.0.0.1:9222; this module is the whole client they need.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import time
import urllib.request
from typing import Any

import websockets

DEFAULT_CDP = "http://127.0.0.1:9222"


class Browser:
    """One CDP page target; every call is synchronous."""

    def __init__(self, cdp_url: str = DEFAULT_CDP, timeout: float = 60.0) -> None:
        self._loop = asyncio.new_event_loop()
        self._seq = 0
        self._session: str | None = None
        self._timeout = timeout
        try:
            version = json.load(urllib.request.urlopen(f"{cdp_url}/json/version", timeout=5))
        except OSError as exc:
            raise RuntimeError(
                f"OBSCURA_CDP_UNAVAILABLE {cdp_url}: {exc} "
                "(systemctl --user start obscura)"
            ) from exc
        self._ws = self._loop.run_until_complete(
            websockets.connect(version["webSocketDebuggerUrl"], max_size=32_000_000)
        )
        target = self._cmd("Target.createTarget", {"url": "about:blank"})
        attached = self._cmd(
            "Target.attachToTarget", {"targetId": target["targetId"], "flatten": True}
        )
        self._session = attached["sessionId"]

    def _cmd(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._seq += 1
        message: dict[str, Any] = {"id": self._seq, "method": method, "params": params or {}}
        if self._session is not None:
            message["sessionId"] = self._session
        return self._loop.run_until_complete(self._exchange(message))

    async def _exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        await self._ws.send(json.dumps(message))
        while True:
            reply = json.loads(await asyncio.wait_for(self._ws.recv(), self._timeout))
            if reply.get("id") != message["id"]:
                continue
            if "error" in reply:
                raise RuntimeError(f"CDP {message['method']}: {reply['error']}")
            return reply.get("result", {})

    def eval(self, expression: str) -> Any:
        result = self._cmd(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        return result.get("result", {}).get("value")

    def viewport(self, width: int, height: int) -> None:
        self._cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        actual = self.eval("[window.innerWidth, window.innerHeight]")
        if actual != [width, height]:
            raise AssertionError(f"VIEWPORT_MISMATCH {actual} != [{width}, {height}]")

    def get(self, url: str, timeout: float = 45.0) -> None:
        self._cmd("Page.navigate", {"url": url})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.eval("document.readyState") == "complete":
                return
            time.sleep(0.2)
        raise AssertionError(f"PAGE_LOAD_TIMEOUT {url}")

    def body(self) -> str:
        return self.eval("document.body ? document.body.innerText : ''") or ""

    def html(self) -> str:
        return self.eval("document.documentElement.outerHTML") or ""

    def url(self) -> str:
        return self.eval("location.href") or ""

    def wait_body(self, *markers: str, timeout: float = 45.0) -> str:
        """Poll rendered text until every marker appears; return the last read."""
        deadline = time.monotonic() + timeout
        body = ""
        while time.monotonic() < deadline:
            body = self.body()
            if all(marker in body for marker in markers):
                return body
            time.sleep(0.3)
        return body

    def screenshot(self, path: str | Path) -> None:
        data = self._cmd("Page.captureScreenshot", {"format": "png"})["data"]
        Path(path).write_bytes(base64.b64decode(data))

    def close(self) -> None:
        try:
            self._loop.run_until_complete(self._ws.close())
        finally:
            self._loop.close()

    def __enter__(self) -> "Browser":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
