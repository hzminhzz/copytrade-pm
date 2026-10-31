"""Adversarial synthetic coverage for synchronized historical-only PM equity research."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from copytrade_pm.pm_synchronized_challenge import (
    _pnl,
    _save_private,
    opportunity_gate,
    simulate_equity,
    synchronized_path,
    utc,
    validate_source,
)
from copytrade_pm.pm_shadow import MarketDataBlocked, MinuteBar, Scenario

D = Decimal
T0 = datetime(2026, 10, 29, 0, 0, tzinfo=UTC)


class Market:
    def __init__(self, missing=()):
        self.missing = set(missing)

    def get(self, instrument, at):
        if (instrument, at) in self.missing:
            raise MarketDataBlocked("MISSING_EXACT_1M_BAR")
        return MinuteBar(at, D("100"), D("10000000"), "a" * 64)


def _mock_cohort(*, old=("W022",), lag=5):
    aliases = ["W022", "W028", "W019", "VS077"] + [f"X{i:02d}" for i in range(32)]
    rows = []
    for alias in aliases:
        for delay in (5, 15, 60):
            is_good = alias in old
            rows.append(
                {
                    "wallet": alias,
                    "latency_minutes": delay,
                    "oracle_hindsight": True,
                    "known_at": "UNKNOWN_VENDOR_HISTORICAL_ORACLE",
                    "status": (
                        "HISTORICAL_HINDSIGHT_SIMULATION_ONLY"
                        if is_good
                        else "BLOCKED_MARKET_OR_EXECUTION"
                    ),
                    "pnl": "1" if is_good else None,
                    "source_anchored_at": (
                        (datetime(2026, 9, 20, tzinfo=UTC)).isoformat() if is_good else None
                    ),
                }
            )
    return {
        "schema": "pm01_fill_only_replay_v2",
        "wallet_count": 36,
        "prospective_qualified_wallet_count": 0,
        "never_claim_prospective_alpha": True,
        "study_cutoff": "2026-10-29T17:22:16.142000+00:00",
        "rows": rows,
    }


def _minute(at, **wallet_pnl):
    return {
        "at": at.isoformat(),
        "delta_pnl_by_wallet": {k: str(v) for k, v in wallet_pnl.items()},
    }


def _trace(positions, flows, minutes=(0, 1)):
    snapshots = [
        {
            "at": (T0 + timedelta(minutes=minute)).isoformat(),
            "positions": positions,
            "flows": flows,
            "funding_accrued": "0",
        }
        for minute in minutes
    ]
    return {
        "status": "HISTORICAL_HINDSIGHT_SIMULATION_ONLY",
        "historical_book_snapshots": snapshots,
    }


def test_36_cohort_provenance_and_invented_clock_fail_closed():
    valid = _mock_cohort()
    chosen, counts = validate_source(valid, 5)
    assert len(chosen) == 36
    assert counts["HISTORICAL_HINDSIGHT_SIMULATION_ONLY"] == 1
    with pytest.raises(ValueError, match="INVENTED_FIRST_KNOWN_CLOCK"):
        changed = _mock_cohort()
        changed["rows"][0]["known_at"] = "2026-09-20T00:00:00+00:00"
        validate_source(changed, 5)
    with pytest.raises(ValueError, match="UNTRUSTED"):
        changed = _mock_cohort()
        changed["prospective_qualified_wallet_count"] = 1
        validate_source(changed, 5)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        changed = _mock_cohort()
        changed["rows"].pop()
        validate_source(changed, 5)
    with pytest.raises(ValueError, match="DUPLICATE"):
        changed = _mock_cohort()
        changed["rows"][1] = changed["rows"][0].copy()
        validate_source(changed, 5)


def test_30_day_gate_requires_multiple_actual_complete_wallets():
    single = opportunity_gate(_mock_cohort(old=("W022",)))
    by_count = {r["wallet_count"]: r for r in single["feasibility_by_wallet_count"]}
    assert by_count[1]["feasible_at_least_one_combination"]
    assert not by_count[2]["feasible_at_least_one_combination"]
    assert single["candidate_windows"]["W022"]["prospective_first_known"] is False

    paired = opportunity_gate(_mock_cohort(old=("W022", "W028")))
    pairs = {r["wallet_count"]: r for r in paired["feasibility_by_wallet_count"]}
    assert pairs[2]["feasible_at_least_one_combination"]
    assert not pairs[3]["feasible_at_least_one_combination"]
    assert paired["largest_completed_candidate_common_window_hours"] > 30 * 24
    assert paired["duration_only_preflight_not_1m_continuous_coverage"]
    with pytest.raises(ValueError, match="INVALID_REQUIRED_HISTORY"):
        opportunity_gate(_mock_cohort(), minimum_days=0)


def test_no_stale_book_forward_in_time_and_funding_is_positive_cost():
    model = Scenario("TEST", 5, D("100000"), D("0.001"))
    instrument = "hyperliquid:mainnet:perp:default:BTC"
    s = {
        "at": T0.isoformat(),
        "positions": {instrument: "1"},
        "flows": {instrument: "-100"},
        "funding_accrued": "0",
    }
    assert _pnl(s, T0, Market(), model) == 0
    assert _pnl(s, T0 + timedelta(hours=8), Market(), model) == D("-0.01")
    with pytest.raises(ValueError, match="FUTURE_BOOK"):
        _pnl(s, T0 - timedelta(minutes=1), Market(), model)
    with pytest.raises(ValueError, match="NONFINITE"):
        _pnl({**s, "positions": {instrument: "NaN"}}, T0, Market(), model)


def test_synchronized_minute_grid_marks_all_wallets_and_rejects_gaps():
    instrument = "hyperliquid:mainnet:perp:default:BTC"
    traces = {
        "A": _trace({instrument: "1"}, {instrument: "-100"}, (0, 2)),
        "B": _trace({instrument: "-1"}, {instrument: "100"}, (0, 2)),
    }
    points = synchronized_path(traces, Market(), lag=5, max_minutes=3)
    assert len(points) == 3
    assert set(points[0]["delta_pnl_by_wallet"]) == {"A", "B"}
    assert all(D(v) == 0 for v in points[0]["delta_pnl_by_wallet"].values())

    with pytest.raises(MarketDataBlocked, match="MISSING"):
        synchronized_path(
            traces,
            Market(missing={(instrument, T0 + timedelta(minutes=1))}),
            lag=5,
            max_minutes=3,
        )
    with pytest.raises(ValueError, match="NO_COMMON"):
        synchronized_path({"A": traces["A"], "B": _trace({}, {}, (5, 6))}, Market(), lag=5)
    with pytest.raises(ValueError, match="INVALID_SYNCHRONIZATION_REQUEST"):
        synchronized_path(traces, Market(), lag=5, max_minutes=100000)


def test_shared_losses_breach_account_while_individual_pods_survive():
    grid = [
        _minute(T0, A=0, B=0),
        _minute(T0 + timedelta(minutes=1), A=-1700, B=-1700),
    ]
    a = simulate_equity(grid, ("A",))
    b = simulate_equity(grid, ("B",))
    both = simulate_equity(grid, ("A", "B"))
    assert a["status"] == "OBSERVED_PATH_NOT_PASSED"
    assert b["status"] == "OBSERVED_PATH_NOT_PASSED"
    assert both["status"] == "SAMPLED_FLOOR_BREACH"
    assert D(both["end_equity"]) == D("96600")
    assert both["decision_at"] == grid[1]["at"]


def test_profit_touch_is_single_path_not_probability_and_scaling_matters():
    grid = [
        _minute(T0, A=0, B=0),
        _minute(T0 + timedelta(minutes=1), A=6000, B=6000),
    ]
    two = simulate_equity(grid, ("A", "B"))
    capped = simulate_equity(grid, ("A", "B"), per_wallet_scale=D("0.5"))
    assert two["status"] == "SAMPLED_PROFIT_TARGET_TOUCH"
    assert D(two["end_equity"]) == D("112000")
    assert capped["status"] == "OBSERVED_PATH_NOT_PASSED"
    assert two["not_a_pass_probability"] and two["time_window_excludes_intraminute_equity_extrema"]


def test_midnight_reset_and_missing_minutes_fail():
    grid = [
        _minute(datetime(2026, 10, 29, 23, 58, tzinfo=UTC), A=0),
        _minute(datetime(2026, 10, 29, 23, 59, tzinfo=UTC), A=2800),
        _minute(datetime(2026, 10, 30, 0, 0, tzinfo=UTC), A=2000),
        _minute(datetime(2026, 10, 30, 0, 1, tzinfo=UTC), A=-400),
    ]
    result = simulate_equity(grid, ("A",))
    # 23:59 equity 102800; new day's floor 99800; equity at 00:01 99600 -> breach.
    assert result["status"] == "SAMPLED_FLOOR_BREACH"
    assert result["decision_at"] == grid[-1]["at"]
    with pytest.raises(ValueError, match="MISSING_OR_DUPLICATE_MARK"):
        simulate_equity(grid[:1] + grid[2:], ("A",))
    with pytest.raises(ValueError, match="MISSING_WALLET"):
        simulate_equity(grid[:1] + [_minute(utc(grid[1]["at"]), B=3)], ("A",))
    with pytest.raises(ValueError, match="SELECTED_WALLET"):
        simulate_equity(grid[:1], ("B",))


def test_unknown_price_oracle_contract_and_private_reproducibility(tmp_path: Path):
    with pytest.raises(ValueError, match="NAIVE"):
        utc("2026-10-29T00:00:00")
    payload = {"schema": "test", "addresses": "not-used", "live_risk_authorized": False}
    path, sha = _save_private(tmp_path / "private", payload)
    assert sha.startswith(path.stem.removeprefix("pm36-sync-"))
    assert path.stat().st_mode & 0o077 == 0
    assert _save_private(tmp_path / "private", payload) == (path, sha)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="CONFLICTING"):
        _save_private(tmp_path / "private", payload)
