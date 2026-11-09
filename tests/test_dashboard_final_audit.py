"""Independent regressions for final dashboard operational review."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Event

import pytest

from copytrade_pm.dashboard.adapter import DashboardReader, SmallTTLCache
from copytrade_pm.dashboard.notifications import process_once, read_state, dashboard_status

T0 = datetime(2026, 11, 7, 10, tzinfo=UTC)


def owner(binding="a", reasons=("BROKER_STALE",), at=T0):
    return {
        "status": "VERIFIED",
        "account_binding_sha": binding * 64,
        "source_observed_at": at.isoformat(),
        "data": {"halts": list(reasons), "health": {"reasons": []}},
    }


def test_account_b_observation_cannot_resolve_account_a_incident(tmp_path):
    path = tmp_path / "alerts.json"
    process_once(path, owner(), now=T0)
    original = read_state(path)["incidents"][0]["id"]
    process_once(path, owner("b", (), T0 + timedelta(seconds=1)), now=T0 + timedelta(seconds=1))
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


@pytest.mark.parametrize(
    "filters",
    [
        {"query": "--help"},
        {"cohort": "--no-excluded"},
    ],
)
def test_browser_filters_cannot_become_cli_options(filters):
    assert DashboardReader().wallets(**filters)["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "filters",
    [
        {"run_id": "--help"},
        {"run_id": ".."},
        {"run_id": 12},
        {"cache_key": 12},
    ],
)
def test_malformed_research_filters_fail_closed(filters):
    assert DashboardReader().research_reports(**filters)["status"] == "BLOCKED"


def test_busy_selection_cannot_hide_guardian_unavailable_state():
    class BusyCache:
        def get(self, *args):
            raise RuntimeError("DASHBOARD_CACHE_READ_BUSY")

    report = DashboardReader(capture_root=None, cache=BusyCache()).overview()
    assert report["metrics"]["equity"]["status"] == "UNAVAILABLE"
    assert report["research_selection"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("break_count", [4, 8])
def test_downsampling_retains_local_extrema_or_explicitly_refuses(break_count):
    pytest.importorskip("polars", reason="dashboard chart optional extra")
    from copytrade_pm.dashboard.chart_data import prepare_series

    points = []
    extrema = set()
    for i in range(256):
        bucket, position = divmod(i, 32)
        value = (
            str(100 + bucket) if position == 5 else (str(-100 - bucket) if position == 21 else "0")
        )
        if position in {5, 21}:
            extrema.add(value)
        points.append(
            {
                "timestamp": (T0 + timedelta(minutes=i)).isoformat(),
                "value": value,
                "series": "equity",
                "metric": "equity",
                "source_id": "fixture-owner",
                "evidence_class": "PAPER_SHADOW",
                "gap_before": position == 15 and bucket < break_count,
            }
        )
    if break_count == 8:
        with pytest.raises(ValueError, match="CRITICAL_FINANCIAL_POINTS"):
            prepare_series(points, max_points=32)
    else:
        output = prepare_series(points, max_points=32)
        assert extrema <= {point["value_exact"] for point in output}
        assert len(output) <= 32


def test_actual_owner_capture_round_trip_without_journal_mutation(tmp_path):
    """Use the actual pinned owner producer; OS ACL acceptance remains separate."""
    pytest.importorskip("prop_production", reason="requires the pinned owner source")
    from hashlib import sha256

    from prop_production.dashboard_capture import COMMANDS, export_capture
    from prop_production.journal import Journal
    from test_dashboard_adapter import fake_native

    journal_path = tmp_path / "fixture-journal.sqlite"
    output = tmp_path / "fixture-captures"
    output.mkdir(mode=0o700)
    with Journal(journal_path, "fixture-final-audit-account", initialize=True) as journal:
        journal.update(
            "RECONCILE",
            1000,
            lambda state: state.update(
                active_release_sha="a" * 64,
                finance={
                    "equity": "0.00",
                    "observed_at_ms": 1000,
                    "risk_floor": "0",
                    "day": 0,
                    "headroom": "0",
                },
            ),
        )
    before = sha256(journal_path.read_bytes()).hexdigest()
    export_capture(journal_path, output, now_ms=1001)
    captures = {name: json.loads((output / f"{name}.json").read_text()) for name in COMMANDS}
    reader = DashboardReader(
        guardian_provider=captures.__getitem__,
        native_read=fake_native,
        clock=lambda: datetime.fromtimestamp(1.001, UTC),
        cache=SmallTTLCache(),
    )
    report = reader.risk_status()
    assert report["metrics"]["equity"]["value"] == "0.00"
    assert report["metrics"]["headroom"]["value"] == "0"
    assert len(captures) == 6
    assert len({item["native"]["journal_sequence"] for item in captures.values()}) == 1
    history = reader.performance_history(risk_report=report)
    assert history["status"] == "VERIFIED_OWNER_SHADOW_TAIL"
    assert {item["evidence_class"] for item in history["points"]} == {"PAPER_SHADOW"}
    assert "fixture-final-audit-account" not in json.dumps(captures)
    assert sha256(journal_path.read_bytes()).hexdigest() == before
