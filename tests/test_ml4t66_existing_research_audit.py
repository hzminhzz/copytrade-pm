"""Regression controls for the 66-wallet evidence-first cohort audit."""

from __future__ import annotations

from decimal import Decimal

from scripts.ml4t66_existing_research_audit import (
    historical_source_cash_diagnostic,
    known_intervals,
    overlap,
    supported_position_spans,
)


def test_same_ms_source_positions_reconstructed_without_sorting_tid():
    # The shuffled same-ms edges must be ordered via source position graph,
    # then linked only to a known next timestamp. No first-known assertion.
    rows = [
        {"coin": "BTC", "time": 1000, "startPosition": "1", "sz": "1", "side": "B"},
        {"coin": "BTC", "time": 1000, "startPosition": "0", "sz": "1", "side": "B"},
        {"coin": "BTC", "time": 2000, "startPosition": "2", "sz": "1", "side": "A"},
        {"coin": "BTC", "time": 3000, "startPosition": "1", "sz": "1", "side": "A"},
    ]
    intervals, counters = known_intervals(rows)
    assert counters["resolved_same_timestamp_groups"] == 1
    assert counters["verified_between_fill_intervals"] == 2
    assert intervals == {"BTC": [(1000, 2000, 1), (2000, 3000, 1)]}
    spans = supported_position_spans(intervals)
    assert spans["supported_same_side_spans"] == 1
    assert spans["whole_wallet_hold_times_verified"] is False


def test_between_fill_opposite_exposure_does_not_become_zero_conflict():
    hour = 3_600_000
    a = {"BTC": [(hour, 2 * hour, 1), (2 * hour, 3 * hour, -1)]}
    b = {"BTC": [(int(1.5 * hour), int(2.5 * hour), -1)]}
    diagnostic = overlap(a, b)
    assert diagnostic["observed_opposite_fraction"] == 0.5
    assert diagnostic["observed_same_hours"] > 0
    assert diagnostic["observed_opposite_hours"] > 0
    assert overlap(a, {"ETH": [(1000, 3000, 1)]})["observed_opposite_fraction"] is None


def test_static_equity_closedpnl_is_leader_only_and_not_contract_pass():
    rows = [
        {
            "coin": "BTC",
            "px": "100",
            "sz": "1",
            "closed_pnl": "10",
            "fee": "0.5",
        },
        {
            "coin": "BTC",
            "px": "100",
            "sz": "2",
            "closed_pnl": "20",
            "fee": "0.5",
        },
    ]
    result = historical_source_cash_diagnostic(rows, "50000")
    exact_k = (Decimal(1) / Decimal(3)) * (Decimal(10000) / Decimal(50000))
    assert Decimal(result["k_effective_static"]) == exact_k.quantize(Decimal(".00000001"))
    assert result["status"] == "LEADER_HINDSIGHT_ONLY"
    assert result["source_only_not_follower_net_mtm"] is True
    assert result["cost_proxy_uses_unbatched_leader_price_not_future_native_execution"] is True
    assert historical_source_cash_diagnostic(rows, None)["status"] == "UNKNOWN_SOURCE_EQUITY_SCALAR"
