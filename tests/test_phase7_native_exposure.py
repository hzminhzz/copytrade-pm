"""Fail-closed source-chain tests for exploratory Phase 7 native exposure."""

import csv
import json

import pytest

pytest.importorskip("polars")

import scripts.phase7_native_exposure as native
from scripts.phase7_native_exposure import START_MS, consistent_intervals


def _fill(t: int, start: str, size: str, side: str = "B", coin: str = "BTC") -> dict:
    return {
        "time": t,
        "startPosition": start,
        "sz": size,
        "side": side,
        "coin": coin,
    }


def test_whale_alias_requires_exact_owner_private_identity(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(native, "BASE", tmp_path)
    roster = tmp_path / "docs/HL108_QUALIFIED_ROSTER_SUMMARY_20261103.csv"
    roster.parent.mkdir(parents=True)
    good = "0x5f94" + "a" * 36
    spoof_prefix = "0x5f94" + "b" * 36
    with roster.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["alias", "address"])
        writer.writeheader()
        writer.writerows(
            [
                {"alias": "HL Perps Whale", "address": spoof_prefix},
                {"alias": "HL Perps Whale", "address": good},
            ]
        )
    private = tmp_path / "data/private/gemini_phase3_phase4_eligibility_20261104.json"
    private.parent.mkdir(parents=True)
    private.write_text(
        json.dumps(
            {
                "wallets": {
                    "HL Perps Whale": {
                        "address": good,
                        "identity_status": "PASS_PRIVATE_SOURCE_ROSTER",
                        "excluded": False,
                    }
                }
            }
        )
    )
    assert native._load_private_aliases() == {"Whale_0x5f94": good}
    private.unlink()
    assert "Whale_0x5f94" not in native._load_private_aliases()


def test_only_two_observed_consistent_endpoints_prove_an_interval() -> None:
    raw = [
        _fill(START_MS + 1000, "0", "2"),
        _fill(START_MS + 61_000, "2", "1", side="A"),
        _fill(START_MS + 121_000, "1", "1", side="A"),
    ]
    intervals, status = consistent_intervals(raw)
    assert [(x["qty"], x["end_ms"] - x["start_ms"]) for x in intervals] == [
        (2.0, 60_000),
        (1.0, 60_000),
    ]
    assert status["broken_adjacent_chains"] == 0
    assert all(x["end_ms"] < START_MS + 200_000 for x in intervals)


def test_discontinuous_chain_and_last_event_never_infer_exposure() -> None:
    raw = [
        _fill(START_MS + 1000, "0", "2"),
        _fill(START_MS + 61_000, "10", "1"),
        _fill(START_MS + 121_000, "11", "1", side="A"),
    ]
    intervals, status = consistent_intervals(raw)
    assert len(intervals) == 1
    assert intervals[0]["qty"] == 11.0
    assert status["broken_adjacent_chains"] == 1


def test_same_timestamp_events_cannot_claim_market_minutes() -> None:
    raw = [
        _fill(START_MS + 1000, "0", "2"),
        _fill(START_MS + 1000, "2", "1"),
    ]
    intervals, status = consistent_intervals(raw)
    assert intervals == []
    assert status["same_timestamp_skips"] == 1


def test_hip3_and_unobserved_starts_do_not_enter_main_perp_interval() -> None:
    raw = [
        _fill(START_MS + 1000, "0", "2", coin="xyz:BRENTOIL"),
        _fill(START_MS + 61_000, "2", "1", coin="xyz:BRENTOIL"),
        {"coin": "BTC", "time": START_MS + 2000, "side": "B", "sz": "2"},
    ]
    intervals, status = consistent_intervals(raw)
    assert intervals == []
    assert status["eligible_fills"] == 0
