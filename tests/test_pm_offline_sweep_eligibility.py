"""Causal next-open batching for five delays, independent of PM04 scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.pm_offline_eligibility import compile_eligible
from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid


BASE = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def row(id, offset_sec, position):
    when = BASE + timedelta(seconds=offset_sec)
    return {
        "account": "W001",
        "dex": "default",
        "instrument": "BTC",
        "event_id": id,
        "source_event_at": when,
        "first_known_at": when,
        "position_after": str(position),
    }


@pytest.mark.parametrize("delay", [0, 1, 2, 5, 10])
def test_each_event_eligibility_and_engine_sha(delay):
    # Later-known fill must not enter the preceding execution-open bucket.
    events = [row("a", 10, "1"), row("b", 30, "2"), row("c", 110, "3")]
    a = compile_eligible(
        events, delay_minutes=delay, clock_basis="HISTORICAL_ORACLE", engine="streaming"
    )
    b = compile_eligible(
        events[::-1], delay_minutes=delay, clock_basis="HISTORICAL_ORACLE", engine="in-memory"
    )
    assert a["sha256"] == b["sha256"]
    assert len(a["events"]) == 2
    first, last = a["events"]
    assert first["collapsed_events"] == 2
    assert first["position_after"] == "2"
    assert last["position_after"] == "3"
    assert first["execute_open_at"] == (BASE + timedelta(minutes=delay + 1)).isoformat()
    assert last["execute_open_at"] == (BASE + timedelta(minutes=delay + 2)).isoformat()
    assert first["eligible_at"] <= first["execute_open_at"]
    assert first["execute_open_at"] < last["execute_open_at"]


def test_exact_boundary_requires_strictly_next_bar():
    event = row("exact", 0, 2)
    out = compile_eligible([event], delay_minutes=2, clock_basis="HISTORICAL_ORACLE")
    assert out["events"][0]["execute_open_at"] == (BASE + timedelta(minutes=3)).isoformat()


def test_future_known_never_enters_early_bar():
    events = [row("early", 10, 1), row("later", 110, 8)]
    prefix = compile_eligible([events[0]], delay_minutes=2, clock_basis="HISTORICAL_ORACLE")
    full = compile_eligible(events, delay_minutes=2, clock_basis="HISTORICAL_ORACLE")
    assert prefix["events"][0] == full["events"][0]
    assert full["events"][0]["position_after"] == "1"


def test_missing_prospective_receipt_and_clock_inversion_fail():
    event = row("one", 10, 1)
    with pytest.raises(ManifestBlocked, match="MISSING_RECEIPT_PROVENANCE"):
        compile_eligible([event], delay_minutes=2, clock_basis="PROSPECTIVE_FIRST_KNOWN")
    event["first_known_at"] = event["source_event_at"] - timedelta(seconds=1)
    event["receipt_sha256"] = "a" * 64
    with pytest.raises(ManifestInvalid, match="FIRST_KNOWN_BEFORE_SOURCE_EVENT"):
        compile_eligible([event], delay_minutes=2, clock_basis="PROSPECTIVE_FIRST_KNOWN")


def test_right_censor_preserves_no_early_order():
    events = [row("one", 10, 1), row("two", 110, 2)]
    out = compile_eligible(
        events, delay_minutes=2, clock_basis="HISTORICAL_ORACLE", cutoff=BASE + timedelta(minutes=3)
    )
    assert len(out["events"]) == 1
    assert out["events"][0]["position_after"] == "1"


def test_duplicate_event_id_rejected():
    with pytest.raises(ManifestInvalid, match="DUPLICATE_EVENT_IDENTITY"):
        compile_eligible(
            [row("x", 10, 1), row("x", 30, 2)], delay_minutes=2, clock_basis="HISTORICAL_ORACLE"
        )
