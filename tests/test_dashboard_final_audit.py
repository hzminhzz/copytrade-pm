"""Independent regressions for final dashboard operational review."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Event

import pytest

from copytrade_pm.dashboard.adapter import DashboardReader, SmallTTLCache
from copytrade_pm.dashboard.notifications import process_once, read_state, dashboard_status
from copytrade_pm.dashboard.views import overview_cards

T0 = datetime(2026, 11, 7, 10, tzinfo=UTC)


def owner(binding="a", reasons=("BROKER_STALE",), at=T0):
    return {"status": "VERIFIED", "account_binding_sha": binding * 64,
            "source_observed_at": at.isoformat(),
            "data": {"halts": list(reasons), "health": {"reasons": []}}}


def test_account_b_observation_cannot_resolve_account_a_incident(tmp_path):
    path = tmp_path / "alerts.json"
    process_once(path, owner(), now=T0)
    original = read_state(path)["incidents"][0]["id"]
    process_once(path, owner("b", (), T0 + timedelta(seconds=1)),
                 now=T0 + timedelta(seconds=1))
    retained = next(r for r in read_state(path)["incidents"] if r["id"] == original)
    assert retained["active"], "A different account cannot resolve the source incident"


def test_incident_identity_survives_retention_and_repeated_restarts(tmp_path):
    path = tmp_path / "alerts.json"
    seen = set()
    for occurrence in range(132):
        now = T0 + timedelta(seconds=occurrence * 2)
        process_once(path, owner(at=now), now=now)
        record = read_state(path)["incidents"][-1]
        assert record["id"] not in seen
        seen.add(record["id"])
        later = now + timedelta(seconds=1)
        process_once(path, owner(reasons=(), at=later), now=later)
    assert len(read_state(path)["incidents"]) <= 128


def test_dead_notifier_cannot_keep_showing_verified_source(tmp_path):
    path = tmp_path / "alerts.json"
    process_once(path, owner(), now=T0)
    status = dashboard_status(path, now=T0 + timedelta(minutes=10))
    assert status["status"] == "STALE"
    assert status["source_status"] == "STALE"
    assert status["incidents"][0]["active"]
    assert status["external_delivery"] == "NOT_CONFIGURED"


def test_unrelated_slow_cache_fill_does_not_delay_ready_operational_read():
    cache = SmallTTLCache()
    entered, release = Event(), Event()
    cache.get("selection", 30, lambda: "ready")

    def slow_health():
        entered.set()
        assert release.wait(3)
        return "health"

    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(cache.get, "health", 30, slow_health)
        assert entered.wait(1)
        fast = pool.submit(cache.get, "selection", 30, lambda: "unexpected")
        try:
            assert fast.result(timeout=0.3) == "ready"
        finally:
            release.set()
        assert slow.result(timeout=1) == "health"



@pytest.mark.parametrize("filters", [
    {"query": "--help"}, {"cohort": "--no-excluded"},
])
def test_browser_filters_cannot_become_cli_options(filters):
    assert DashboardReader().wallets(**filters)["status"] == "BLOCKED"


@pytest.mark.parametrize("filters", [
    {"run_id": "--help"}, {"run_id": ".."}, {"run_id": 12}, {"cache_key": 12},
])
def test_malformed_research_filters_fail_closed(filters):
    assert DashboardReader().research_reports(**filters)["status"] == "BLOCKED"


def test_busy_selection_cannot_hide_guardian_unavailable_state():
    class BusyCache:
        def get(self, *args):
            raise RuntimeError("DASHBOARD_CACHE_READ_BUSY")

    report = DashboardReader(capture_root=None, cache=BusyCache()).overview()
    assert report["metrics"]["equity"]["status"] == "UNAVAILABLE"
    assert report["research_selection"]["status"] == "UNKNOWN"



@pytest.mark.parametrize("path,content_type", [
    ("/login", "application/x-www-form-urlencoded"),
    ("/api/kernel/function_call", "application/json"),
])
def test_asgi_body_limit_checks_bytes_not_only_claimed_length(path, content_type):
    pytest.importorskip("starlette", reason="requires the dashboard extra")
    from copytrade_pm.dashboard.server import COOKIE_NAME, ViewerAuth, _cookie
    messages, downstream_calls = [], []
    key = "x" * 64

    async def downstream(scope, receive, send):
        downstream_calls.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"x" * 20000, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "query_string": b"",
             "headers": [
                 (b"host", b"localhost"), (b"origin", b"https://localhost"),
                 (b"content-type", content_type.encode()), (b"content-length", b"2"),
                 (b"cookie", f"{COOKIE_NAME}={_cookie(key, int(T0.timestamp()))}".encode()),
             ]}
    asyncio.run(ViewerAuth(downstream, secret=key, clock=lambda: T0)(scope, receive, send))
    assert messages[0]["status"] == 413
    assert not downstream_calls


class Cards:
    def stat(self, value, **kwargs):
        return {"value": value, **kwargs}

    def hstack(self, items, **kwargs):
        return items

    def vstack(self, items):
        return items

    def md(self, text):
        return text


@pytest.mark.parametrize("status", ["STALE", "BLOCKED", "UNAVAILABLE"])
def test_current_status_cards_label_capture_evidence(status):
    report = {
        "metrics": {name: {"value": None, "status": status} for name in
                    ("equity", "headroom", "daily_headroom", "trailing_headroom")},
        "sources": {
            "status": {"status": status, "data": {"state": "HALTED"}},
            "broker": {"status": status, "data": {"certainty": "COHERENT"}},
            "risk": {"status": status, "data": {}},
        },
        "retrieved_at": T0.isoformat(),
    }
    rendered = json.dumps(overview_cards(Cards(), report))
    assert f"Guardian state [{status}]" in rendered
    assert f"Broker certainty [{status}]" in rendered
    if status == "STALE":
        assert "last observed" in rendered
    else:
        assert "COHERENT" not in rendered


def test_invalid_unicode_login_is_rejected_without_server_error():
    pytest.importorskip("marimo", reason="requires the dashboard extra")
    from starlette.testclient import TestClient
    from copytrade_pm.dashboard.server import make_app

    with TestClient(make_app(secret="x" * 64), base_url="https://localhost") as client:
        response = client.post("/login", data={"secret": "sai-mật-khẩu"},
                               headers={"origin": "https://localhost"})
    assert response.status_code == 401


@pytest.mark.parametrize("break_count", [4, 8])
def test_downsampling_retains_local_extrema_or_explicitly_refuses(break_count):
    pytest.importorskip("altair", reason="requires the dashboard extra")
    from copytrade_pm.dashboard.chart_data import prepare_series

    points = []
    extrema = set()
    for i in range(256):
        bucket, position = divmod(i, 32)
        value = str(100 + bucket) if position == 5 else (
            str(-100 - bucket) if position == 21 else "0"
        )
        if position in {5, 21}:
            extrema.add(value)
        points.append({
            "timestamp": (T0 + timedelta(minutes=i)).isoformat(),
            "value": value, "series": "equity", "metric": "equity",
            "source_id": "fixture-owner", "evidence_class": "PAPER_SHADOW",
            "gap_before": position == 15 and bucket < break_count,
        })
    if break_count == 8:
        with pytest.raises(ValueError, match="CRITICAL_FINANCIAL_POINTS"):
            prepare_series(points, max_points=32)
    else:
        output = prepare_series(points, max_points=32)
        assert extrema <= {point["value_exact"] for point in output}
        assert len(output) <= 32
