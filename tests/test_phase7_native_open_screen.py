"""Native next-minute context is SHA-bound, exact-time and non-financial."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

pytest.importorskip("polars")

import polars as pl

from scripts.phase7_native_open_screen import (
    DAY_MS,
    MINUTE_MS,
    join_native_context,
    report,
    source_groups,
    strict_next_open_ms,
)
from scripts.phase7_native_exposure import START_MS


def _market(tmp_path, *, tamper=False):
    market = tmp_path / "market"
    folder = market / "crypto_futures_ohlcv_1m_HYPERLIQUID_BTC_PERP" / "year=2026/month=08/day=05"
    folder.mkdir(parents=True)
    start = datetime(2026, 8, 5, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=i) for i in range(1440)],
            "symbol": ["BTC"] * 1440,
            "open": [100.0 + i for i in range(1440)],
            "high": [101.0 + i for i in range(1440)],
            "low": [99.0 + i for i in range(1440)],
            "close": [100.0 + i for i in range(1440)],
            "volume": [1000.0] * 1440,
        }
    )
    file = folder / "data.parquet"
    frame.write_parquet(file)
    (folder / "source.json").write_text(
        json.dumps(
            {
                "exchange": "hyperliquid_futures",
                "source_symbol": "BTC",
                "source_type": "trades",
                "bars": 1440,
                "sha256": "0" * 64 if tamper else sha256(file.read_bytes()).hexdigest(),
            }
        )
    )
    return market


def _candidate(ms: int, *, qty=1, delay=5):
    return pl.DataFrame(
        [
            {
                "alias": "ACT04",
                "coin": "BTC",
                "instrument": "hyperliquid:mainnet:perp:default:BTC",
                "delay_minutes": delay,
                "account_sha256": "synthetic-alias-hash",
                "execute_ms": ms,
                "day_number": ms // DAY_MS,
                "source_fill_count": 1,
                "first_event_ms": START_MS,
                "last_event_ms": START_MS + 1000,
                "signed_qty": qty,
                "reference_last_leader_px": 100.0,
            }
        ]
    )


def test_exact_open_must_be_strictly_later_than_eligible() -> None:
    assert strict_next_open_ms(START_MS + MINUTE_MS) == START_MS + 2 * MINUTE_MS
    assert strict_next_open_ms(START_MS + MINUTE_MS + 99) == START_MS + 2 * MINUTE_MS


def test_valid_native_open_and_only_prior_completed_volume(tmp_path) -> None:
    market = _market(tmp_path)
    candidate = _candidate(START_MS + MINUTE_MS * 2)
    joined, evidence = join_native_context(candidate, market)
    assert evidence["required_market_days"] == 1
    assert evidence["native_day_statuses"] == {"VERIFIED_NATIVE_DAY": 1}
    rec = joined.to_dicts()[0]
    assert rec["match_status"] == "MATCHED_SCREEN_ONLY"
    assert rec["next_open_float_screen_only"] == 102.0
    assert rec["prior_base_volume_screen_only"] == 1000.0
    result = report(joined, {"ACT04": {"status": "SYNTHETIC"}}, evidence)
    e2 = result["portfolios"]["E2"]["delay_context"]["5"]
    assert e2["matched_native_batches"] == 1
    assert e2["matched_notional_usd"] == round(102.0 * 0.00428, 2)
    assert e2["signed_leader_to_next_open_price_move_usd"] == round(2.0 * 0.00428, 2)
    assert e2["full_population_follower_returns"] is None
    assert result["financial_follower_pnl"] is None


def test_prior_minute_capacity_uses_scaled_not_leader_qty(tmp_path) -> None:
    market = _market(tmp_path)
    candidate = _candidate(START_MS + MINUTE_MS * 2, qty=100)
    joined, evidence = join_native_context(candidate, market)
    result = report(joined, {"ACT04": {"status": "SYNTHETIC"}}, evidence)
    e2 = result["portfolios"]["E2"]["delay_context"]["5"]
    assert e2["participation_above_5pct_prior_complete_minute"] == 0
    assert e2["notional_passes_5pct_prior_minute_cap"] == e2["matched_notional_usd"]


def test_high_scaled_participation_requires_research_veto(tmp_path) -> None:
    market = _market(tmp_path)
    joined, evidence = join_native_context(_candidate(START_MS + MINUTE_MS * 2, qty=20_000), market)
    result = report(joined, {"ACT04": {"status": "SYNTHETIC"}}, evidence)
    e2 = result["portfolios"]["E2"]["delay_context"]["5"]
    assert e2["participation_above_5pct_prior_complete_minute"] == 1
    assert e2["notional_passes_5pct_prior_minute_cap"] == 0
    assert e2["matched_notional_usd"] is not None


def test_tampered_native_parquet_is_never_a_matched_execution_open(tmp_path) -> None:
    market = _market(tmp_path, tamper=True)
    joined, evidence = join_native_context(_candidate(START_MS + MINUTE_MS * 2), market)
    assert joined["match_status"].to_list() == ["NATIVE_PARQUET_SHA_MISMATCH"]
    result = report(joined, {"ACT04": {"status": "SYNTHETIC"}}, evidence)
    e2 = result["portfolios"]["E2"]["delay_context"]["5"]
    assert e2["matched_native_batches"] == 0
    assert e2["matched_notional_usd"] is None


def test_midnight_predecessor_unknown_is_not_zero_volume(tmp_path) -> None:
    market = _market(tmp_path)
    candidate = _candidate(START_MS)
    joined, evidence = join_native_context(candidate, market)
    assert evidence["verified_and_predecessor_market_days"] == 2
    assert joined["match_status"].to_list() == ["MISSING_COMPLETED_PRIOR_VOLUME"]


def test_source_tids_must_be_unique_and_main_perp_only() -> None:
    source = [
        {"time": START_MS + 1000, "coin": "BTC", "side": "B", "px": "100", "sz": "2", "tid": 1},
        {"time": START_MS + 1000, "coin": "BTC", "side": "B", "px": "100", "sz": "2", "tid": 1},
        {
            "time": START_MS + 2000,
            "coin": "xyz:BRENTOIL",
            "side": "B",
            "px": "100",
            "sz": "2",
            "tid": 2,
        },
    ]
    by_coin, counts = source_groups(source)
    assert len(by_coin["BTC"]) == 1
    assert counts["DUPLICATE_TID"] == 1
    assert counts["UNSUPPORTED_MAIN_PERP_SCOPE"] == 1
