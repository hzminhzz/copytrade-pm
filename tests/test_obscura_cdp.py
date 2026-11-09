"""Deterministic protocol and cleanup tests for the Grafana obscura CDP client."""

from __future__ import annotations

import asyncio
from collections import deque
import io
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("websockets", reason="source optional extra for CDP tests")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "lib"))
from obscura_cdp import Browser  # noqa: E402


class FakeWebSocket:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.replies: deque[str] = deque()
        self.closed = False
        self.fail_methods: set[str] = set()
        self.silent_methods: set[str] = set()
        self.emit_event = False

    async def send(self, raw: str) -> None:
        request = json.loads(raw)
        self.requests.append(request)
        method = request["method"]
        if method in self.silent_methods:
            return
        if self.emit_event:
            self.replies.append(json.dumps({"method": "Target.targetInfoChanged", "params": {}}))
        if method in self.fail_methods:
            reply = {"id": request["id"], "error": {"code": -32000, "message": "denied"}}
        elif method == "Target.createTarget":
            reply = {"id": request["id"], "result": {"targetId": "page-fake"}}
        elif method == "Target.attachToTarget":
            reply = {"id": request["id"], "result": {"sessionId": "session-fake"}}
        elif method == "Runtime.evaluate":
            reply = {"id": request["id"], "result": {"result": {"value": "OK"}}}
        else:
            reply = {"id": request["id"], "result": {"success": True}}
        self.replies.append(json.dumps(reply))

    async def recv(self) -> str:
        if self.replies:
            return self.replies.popleft()
        await asyncio.sleep(30)
        raise AssertionError("unreachable")

    async def close(self) -> None:
        self.closed = True


def configure_fake_cdp(monkeypatch):
    ws = FakeWebSocket()

    def version(_url: str, *, timeout: float):
        assert timeout > 0
        return io.BytesIO(
            json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser"}).encode()
        )

    async def connect(url: str, *, max_size: int):
        assert url.startswith("ws://127.0.0.1:")
        assert max_size == 32_000_000
        return ws

    monkeypatch.setattr("urllib.request.urlopen", version)
    monkeypatch.setattr("websockets.connect", connect)
    return ws


@pytest.fixture
def fake_cdp(monkeypatch):
    return configure_fake_cdp(monkeypatch)


def test_close_destroys_target_once_using_browser_level_cdp(fake_cdp):
    fake_cdp.emit_event = True
    with Browser(timeout=0.3) as browser:
        assert browser._target_id == "page-fake"
        assert browser._session == "session-fake"
        assert browser.eval("1") == "OK"
    assert browser._loop.is_closed()
    assert fake_cdp.closed
    commands = [r["method"] for r in fake_cdp.requests]
    assert commands == [
        "Target.createTarget",
        "Target.attachToTarget",
        "Runtime.evaluate",
        "Target.closeTarget",
    ]
    assert fake_cdp.requests[-1]["params"] == {"targetId": "page-fake"}
    assert "sessionId" not in fake_cdp.requests[-1]
    browser.close()
    assert len(fake_cdp.requests) == 4


def test_failed_attach_closes_created_target_and_connection(fake_cdp):
    fake_cdp.fail_methods.add("Target.attachToTarget")
    with pytest.raises(RuntimeError, match="Target.attachToTarget"):
        Browser(timeout=0.3)
    assert fake_cdp.closed
    assert [r["method"] for r in fake_cdp.requests][-1] == "Target.closeTarget"


def test_bounded_request_timeout_does_not_prevent_cleanup(fake_cdp):
    with Browser(timeout=0.05) as browser:
        fake_cdp.silent_methods.add("Runtime.evaluate")
        with pytest.raises(TimeoutError):
            browser.eval("while(true){}")
    assert fake_cdp.closed
    assert fake_cdp.requests[-1]["method"] == "Target.closeTarget"


def test_cleanup_protocol_error_still_closes_websocket_and_loop(fake_cdp):
    browser = Browser(timeout=0.3)
    fake_cdp.fail_methods.add("Target.closeTarget")
    with pytest.raises(RuntimeError, match="CDP_TARGET_CLEANUP_FAILED"):
        browser.close()
    assert fake_cdp.closed
    assert browser._loop.is_closed()
    browser.close()


def test_invalid_timeout_is_rejected_before_allocating_loop():
    with pytest.raises(ValueError, match="CDP_INVALID_TIMEOUT"):
        Browser(timeout=0)


def test_unavailable_obscura_reports_recovery_hint(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    with pytest.raises(RuntimeError, match="OBSCURA_CDP_UNAVAILABLE"):
        Browser(timeout=0.2)


def test_timeout_invalidates_session_before_caller_can_reuse_it(fake_cdp):
    browser = Browser(timeout=0.02)
    fake_cdp.silent_methods.add("Runtime.evaluate")
    with pytest.raises(TimeoutError):
        browser.eval("1")
    fake_cdp.silent_methods.clear()
    try:
        with pytest.raises(RuntimeError, match="CDP_CONNECTION_CLOSED"):
            browser.eval("2")
    finally:
        browser.close()


def test_target_detachment_invalidates_session_even_when_late_reply_follows(fake_cdp):
    browser = Browser(timeout=0.1)
    fake_cdp.replies.append(
        json.dumps({"method": "Target.detachedFromTarget", "params": {"sessionId": "session-fake"}})
    )
    try:
        with pytest.raises(RuntimeError, match="CDP_TARGET_DISCONNECTED"):
            browser.eval("1")
        with pytest.raises(RuntimeError, match="CDP_CONNECTION_CLOSED"):
            browser.eval("2")
    finally:
        browser.close()
