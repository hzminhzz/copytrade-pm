"""TD-11/TD-12 regression, restart, privacy and failure semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import pytest

from copytrade_pm.dashboard.navigation import ROUTES, navigation_html, valid_scope
from copytrade_pm.dashboard.notifications import (
    MAX_ATTEMPTS,
    NotificationStateError,
    acknowledge,
    dashboard_status,
    process_once,
    read_state,
)

T0 = datetime(2026, 11, 7, 9, tzinfo=UTC)


def source(reasons=("BROKER_STALE",), *, at=T0, state="VERIFIED"):
    return {
        "status": state,
        "account_binding_sha": "a" * 64,
        "source_observed_at": at.isoformat(),
        "data": {"halts": list(reasons), "health": {"reasons": []}},
    }


class FailingDelivery:
    def __init__(self):
        self.calls = 0

    def send(self, record):
        self.calls += 1
        raise ConnectionError("private destination must not be leaked")


def test_dedup_restart_resolution_and_ack_is_not_guardian_mutation(tmp_path):
    state = tmp_path / "notifications.json"
    first = process_once(state, source(), now=T0)
    assert first["status"] == "DRY_RUN_ONLY"
    assert first["external_delivery"] == "NOT_CONFIGURED"
    record = first["incidents"][0]
    assert record["status"] == "DRY_RUN_DELIVERED"
    assert record["source_observed_at"] == T0.isoformat()
    assert record["attempts"] == 1
    second = process_once(state, source(), now=T0 + timedelta(seconds=1))
    assert len(second["incidents"]) == 1
    assert read_state(state)["incidents"][0]["id"] == record["id"]
    assert acknowledge(state, record["id"])
    assert read_state(state)["incidents"][0]["status"] == "ACKNOWLEDGED"
    assert source()["data"]["halts"] == ["BROKER_STALE"]
    process_once(state, source(()), now=T0 + timedelta(seconds=2))
    assert not read_state(state)["incidents"][0]["active"]
    reopened = process_once(state, source(), now=T0 + timedelta(seconds=3))
    assert len(reopened["incidents"]) == 2
    assert reopened["incidents"][-1]["id"] != record["id"]


def test_retry_max_and_survive_restart(tmp_path):
    path = tmp_path / "state.json"
    sink = FailingDelivery()
    first = process_once(path, source(), now=T0, delivery=sink)
    assert first["incidents"][0]["status"] == "RETRY"
    assert first["incidents"][0]["attempts"] == 1
    process_once(path, source(), now=T0 + timedelta(seconds=1), delivery=sink)
    assert sink.calls == 1
    process_once(path, source(), now=T0 + timedelta(seconds=5), delivery=sink)
    assert sink.calls == 2
    last = process_once(path, source(), now=T0 + timedelta(seconds=35), delivery=sink)
    assert sink.calls == MAX_ATTEMPTS
    assert last["incidents"][0]["status"] == "FAILED"
    assert last["incidents"][0]["attempts"] == MAX_ATTEMPTS
    assert last["incidents"][0]["last_error"] == "ConnectionError"
    process_once(path, source(), now=T0 + timedelta(minutes=3), delivery=sink)
    assert sink.calls == MAX_ATTEMPTS


def test_invalid_and_unavailable_sources_never_clear_live_incidents(tmp_path):
    path = tmp_path / "alerts.json"
    process_once(path, source(), now=T0)
    later = T0 + timedelta(seconds=2)
    process_once(path, {"status": "STALE"}, now=later)
    assert read_state(path)["incidents"][0]["active"]
    with pytest.raises(NotificationStateError, match="CLOCK_REGRESSION"):
        process_once(path, source((), at=T0 - timedelta(seconds=5)), now=later)
    assert read_state(path)["incidents"][0]["active"]
    with pytest.raises(NotificationStateError, match="CAUSE_INVALID"):
        process_once(path, source(("0xPRIVATE",)), now=later)
    assert read_state(path)["incidents"][0]["active"]


def test_corruption_symlink_and_oversize_fail_closed(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text('{"schema":"wrong"}')
    with pytest.raises(NotificationStateError):
        process_once(path, source(), now=T0)
    assert dashboard_status(path)["status"] == "BLOCKED"
    path.unlink()
    target = tmp_path / "secret"
    target.write_text("{}")
    path.symlink_to(target)
    assert dashboard_status(path)["status"] == "BLOCKED"
    path.unlink()
    path.write_text("z" * 66000)
    assert dashboard_status(path)["status"] == "BLOCKED"


def test_notification_file_schema_has_no_external_destination(tmp_path):
    path = tmp_path / "notifications.json"
    process_once(path, source(), now=T0)
    raw = path.read_text()
    assert "BROKER_STALE" in raw
    assert '"external_delivery":"NOT_CONFIGURED"' in raw
    assert "http" not in raw and "telegram" not in raw
    assert json.loads(raw)["schema"] == "dashboard_notification_state_v1"
    assert not (tmp_path / "guardian.json").exists()


@pytest.mark.parametrize(
    "unsafe",
    [
        {"portfolio": "0x12345678901234567890/A@1", "utc": "5m"},
        {"portfolio": "research/0x1234567890@2", "utc": "7d"},
        {"portfolio": "../etc/passwd", "utc": "7d"},
        {"portfolio": "portfolio/abc@1?secret=a", "utc": "7d"},
        {"portfolio": "x" * 256, "utc": "7d"},
        {"portfolio": "portfolio/a@1", "utc": "2026-11-07T00:00:00Z"},
    ],
)
def test_navigation_drops_unsafe_scope(unsafe):
    safe = valid_scope(unsafe)
    assert "portfolio" not in safe or safe["portfolio"] == "portfolio/a@1"
    html = navigation_html(unsafe)
    assert "0x1234" not in html
    assert "secret=" not in html and "../etc/" not in html
    assert "2026-11-07T00" not in html


def test_navigation_same_bounded_scope_across_eight_views():
    scope = {"portfolio": "gemini.phase5/P1@3", "utc": "30d", "token": "secret-value"}
    html = navigation_html(scope)
    assert html.count("href=") == len(ROUTES) == 8
    assert html.count("portfolio=gemini.phase5") == 8
    assert html.count("utc=30d") == 8
    assert "secret-value" not in html
    assert "aria-label=" in html
