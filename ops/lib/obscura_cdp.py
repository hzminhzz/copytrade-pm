"""Small synchronous CDP client for the local obscura browser.

Each Browser owns one target. Closing a browser must destroy that target; merely
closing the browser-level WebSocket leaves a page behind in obscura.
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
CLEANUP_TIMEOUT = 3.0


class Browser:
    """One CDP page target with bounded synchronous requests and cleanup."""

    def __init__(self, cdp_url: str = DEFAULT_CDP, timeout: float = 60.0) -> None:
        if not 0 < timeout <= 300:
            raise ValueError("CDP_INVALID_TIMEOUT")
        self._loop = asyncio.new_event_loop()
        self._seq = 0
        self._session: str | None = None
        self._target_id: str | None = None
        self._ws: Any = None
        self._timeout = timeout
        try:
            try:
                with urllib.request.urlopen(
                    f"{cdp_url}/json/version", timeout=min(timeout, 5.0)
                ) as response:
                    version = json.load(response)
            except OSError as exc:
                raise RuntimeError(
                    f"OBSCURA_CDP_UNAVAILABLE {cdp_url}: {exc} (systemctl --user start obscura)"
                ) from exc
            self._ws = self._loop.run_until_complete(
                asyncio.wait_for(
                    websockets.connect(version["webSocketDebuggerUrl"], max_size=32_000_000),
                    timeout=min(timeout, 10.0),
                )
            )
            target = self._cmd("Target.createTarget", {"url": "about:blank"})
            self._target_id = target["targetId"]
            attached = self._cmd(
                "Target.attachToTarget", {"targetId": self._target_id, "flatten": True}
            )
            self._session = attached["sessionId"]
        except BaseException:
            try:
                self.close()
            except Exception:
                # Preserve the original constructor error, not a secondary cleanup error.
                pass
            raise

    def _cmd(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if self._loop.is_closed() or self._ws is None:
            raise RuntimeError("CDP_CONNECTION_CLOSED")
        self._seq += 1
        message: dict[str, Any] = {"id": self._seq, "method": method, "params": params or {}}
        if self._session is not None:
            message["sessionId"] = self._session
        limit = min(self._timeout, timeout) if timeout is not None else self._timeout
        return self._loop.run_until_complete(
            asyncio.wait_for(self._exchange(message), timeout=limit)
        )

    async def _exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        await self._ws.send(json.dumps(message))
        while True:
            reply = json.loads(await self._ws.recv())
            if not isinstance(reply, dict):
                raise RuntimeError("CDP_INVALID_RESPONSE")
            if reply.get("id") != message["id"]:
                # CDP events are asynchronous; one in-flight request per browser.
                continue
            if "error" in reply:
                raise RuntimeError(f"CDP {message['method']}: {reply['error']}")
            result = reply.get("result", {})
            if not isinstance(result, dict):
                raise RuntimeError("CDP_INVALID_RESULT")
            return result

    def eval(self, expression: str) -> Any:
        result = self._cmd(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(f"CDP_JS_EXCEPTION: {result['exceptionDetails']}")
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
        if self._loop.is_closed():
            return
        error: Exception | None = None
        try:
            if self._ws is not None and self._target_id is not None:
                # Target.closeTarget is a browser-level command, not a page command.
                self._session = None
                try:
                    self._cmd(
                        "Target.closeTarget",
                        {"targetId": self._target_id},
                        timeout=CLEANUP_TIMEOUT,
                    )
                except Exception as exc:
                    error = exc
        finally:
            if self._ws is not None:
                try:
                    self._loop.run_until_complete(
                        asyncio.wait_for(self._ws.close(), timeout=CLEANUP_TIMEOUT)
                    )
                except Exception as exc:
                    if error is None:
                        error = exc
            self._ws = None
            self._target_id = None
            self._loop.close()
        if error is not None:
            raise RuntimeError("CDP_TARGET_CLEANUP_FAILED") from error

    def __enter__(self) -> "Browser":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except Exception:
                # Preserve the primary browser assertion or protocol failure.
                pass
