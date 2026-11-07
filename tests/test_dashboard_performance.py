"""Bounded fixture-only benchmark; numbers do NOT qualify live Guardian cadence."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
import time
import tracemalloc

from copytrade_pm.dashboard.adapter import DashboardReader, SmallTTLCache

T0 = datetime(2026, 11, 7, 9, tzinfo=UTC)


def _source(command: str) -> dict:
    data = {
        "status": {"state": "HALTED", "halts": ["BROKER_STALE"],
                   "health": {"reasons": ["WATCHDOG_UNAVAILABLE"]}},
        "risk": {"finance": {"equity": "10000", "headroom": "500",
                             "daily_headroom": "300", "trailing_headroom": "700"}},
        "broker": {"certainty": "UNKNOWN", "flat_confirmed": False},
        "portfolio": {"decisions": []},
    }[command]
    return {
        "schema": "dashboard_guardian_capture_v1", "command": command,
        "source_observed_at": T0.isoformat(), "captured_at": T0.isoformat(),
        "native": {"schema": f"operator_{command}_v1",
                   "journal_sequence": 4, "account_binding_sha": "b" * 64,
                   "release_sha": "c" * 64, "trading_authorized": False, **data},
    }


def _native(args):
    assert args == ["portfolios", "current"]
    return {"schema": "copytrade_read_result_v1", "observed_at": T0.isoformat(),
            "trading_authorized": False, "scientifically_qualified": False,
            "status": "BLOCKED",
            "source": {"authority": "wallet_registry",
                       "observed_at": T0.isoformat(), "sha256": "a" * 64,
                       "version": "sqlite_v8"},
            "data": {"research_only": True}}


def _percentile(data: list[float], percentage: float) -> float:
    ordered = sorted(data)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentage))], 4)


def test_synthetic_overview_latency_multisession_and_memory():
    def one():
        reader = DashboardReader(
            clock=lambda: T0, guardian_provider=_source,
            native_read=_native, cache=SmallTTLCache(),
        )
        started = time.perf_counter()
        report = reader.overview()
        latency = (time.perf_counter() - started) * 1000
        assert report["metrics"]["equity"]["status"] == "VERIFIED"
        assert report["incidents"] == ["BROKER_STALE", "WATCHDOG_UNAVAILABLE"]
        return latency, len(json.dumps(report).encode())

    tracemalloc.start()
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: one(), range(160)))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    samples = [sample[0] for sample in results]
    payloads = [sample[1] for sample in results]
    evidence = {
        "workload": "SYNTHETIC_IN_MEMORY_FIXTURE_ONLY",
        "sessions": 8, "queries": len(samples),
        "overview_p50_ms": _percentile(samples, 0.5),
        "overview_p95_ms": _percentile(samples, 0.95),
        "max_payload_bytes": max(payloads),
        "tracemalloc_peak_bytes": peak,
        "guardian_cadence": "NOT_MEASURED",
        "real_wallet_search_p95": "NOT_MEASURED",
        "protected_capture_full_chain_cost": "NOT_MEASURED",
    }
    print("DASHBOARD_SYNTHETIC_BENCHMARK=" + json.dumps(evidence, sort_keys=True))
    assert len(samples) == 160
    assert max(payloads) < 65536
    assert max(samples) < 2000
