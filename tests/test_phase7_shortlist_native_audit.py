"""Full-minute source position coverage must never imply account NAV or PnL."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("polars")

import polars as pl

import scripts.phase7_shortlist_native_audit as study
from scripts.phase7_native_exposure import START_MS


def test_full_minute_count_excludes_partial_event_minutes() -> None:
    interval = {"start_ms": START_MS + 1, "end_ms": START_MS + 120_000}
    assert study.complete_minute_bins(interval) == 1
    assert study.complete_minute_bins({"start_ms": START_MS + 2, "end_ms": START_MS + 59_999}) == 0
    assert study.complete_minute_bins({"start_ms": START_MS, "end_ms": START_MS + 120_000}) == 2


def test_asof_join_does_not_include_minute_with_late_exit() -> None:
    intervals = [
        {
            "coin": "BTC",
            "start_ms": START_MS + 1,
            "end_ms": START_MS + 120_000,
            "qty": 1.0,
        }
    ]
    bars = pl.DataFrame(
        {
            "ms": [START_MS, START_MS + 60_000, START_MS + 120_000],
            "close": [100.0, 110.0, 120.0],
        }
    )
    total, unique = study.observed_interval_bars(intervals, bars)
    assert total == 1
    assert unique == 1


def test_partial_market_coverage_never_promotes_complete_book(monkeypatch) -> None:
    source = {
        "fills": [
            {
                "time": START_MS,
                "coin": "BTC",
                "startPosition": "0",
                "side": "B",
                "sz": "1",
            },
            {
                "time": START_MS + 120_000,
                "coin": "BTC",
                "startPosition": "1",
                "side": "A",
                "sz": "1",
            },
        ]
    }
    only_one = pl.DataFrame({"ms": [START_MS + 60_000], "close": [101.0]})
    monkeypatch.setattr(study, "native_marks", lambda *_: only_one)
    result = study.inspect_wallet(source, "a" * 64)
    assert result["verified_full_minute_chain_bars"] == 1
    assert result["verified_lower_bound_fraction_all_chain_minutes"] == 0.5
    assert result["continuous_90d_book"] is False
    assert result["risk_budget_follower_pnl"] is None


def test_wrong_candidate_screen_schema_is_blocked(tmp_path) -> None:
    file = tmp_path / "screen.json"
    file.write_text(json.dumps({"schema": "phase7_first_stage_candidate_screen_v1"}))
    with pytest.raises(ValueError, match="REQUIRES_CORRECTED_STAGE1_SCREEN"):
        study.run(file, tmp_path)


def test_raw_sources_resolve_only_exact_address(tmp_path) -> None:
    root = tmp_path / "data"
    folder = root / "wallet_fills_90d"
    folder.mkdir(parents=True)
    (folder / "source.json").write_text(
        json.dumps(
            {
                "address": "0x" + "1" * 40,
                "fills": [],
            }
        )
    )
    assert study.raw_sources(root, {"0x" + "2" * 40}) == {}
    found = study.raw_sources(root, {"0x" + "1" * 40})
    assert len(found) == 1
    assert len(next(iter(found.values()))["sha256"]) == 64
