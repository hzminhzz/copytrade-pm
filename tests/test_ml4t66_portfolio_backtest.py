"""ML4T-66 historical-oracle portfolio accounting and fail-closed regression."""

from datetime import UTC, datetime

import numpy as np
import polars as pl

from scripts import ml4t66_portfolio_backtest as bt


def test_sha_verified_partial_market_day_prices_only_exact_observed_minutes(monkeypatch, tmp_path):
    monkeypatch.setattr(bt, "DAYS", 1)
    monkeypatch.setattr(bt, "MINUTES", 1440)
    monkeypatch.setattr(bt, "START_MS", 0)
    monkeypatch.setattr(bt, "START", datetime(1970, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(bt, "native_instrument", lambda coin: "native-test")
    # A partial day starting at 03:50 is valid after that timestamp,
    # but cannot be silently backfilled during the 230 absent minutes.
    stamps = [datetime(1970, 1, 1, 3, 50, tzinfo=UTC), datetime(1970, 1, 1, 3, 51, tzinfo=UTC)]
    frame = pl.DataFrame(
        {
            "timestamp": stamps,
            "open": [100.0, 101.0],
            "close": [100.0, 102.0],
            "low": [99.0, 100.0],
            "high": [102.0, 103.0],
            "volume": [10.0, 11.0],
        }
    )
    monkeypatch.setattr(bt, "_verified_day", lambda root, inst, day: (frame, "sha", "meta"))
    panels, audit = bt.load_native_panels(tmp_path, {"PONS": 0})
    assert np.isnan(panels["PONS"]["open"][229])
    assert panels["PONS"]["open"][230] == 100.0
    assert panels["PONS"]["open"][231] == 101.0
    assert np.isnan(panels["PONS"]["open"][232])
    assert audit["PONS"]["verified_partial_native_days"] == 1
    assert audit["PONS"]["verified_complete_native_days"] == 0
    assert audit["PONS"]["sha_verified_missing_minutes_in_partial_days"] == 1438


def test_observed_flat_anchor_censors_earlier_source_activity():
    rows = [
        {"alias": "A", "coin": "BTC", "time": 10, "start_zero_observed": False},
        {"alias": "A", "coin": "BTC", "time": 20, "start_zero_observed": True},
        {"alias": "A", "coin": "BTC", "time": 30, "start_zero_observed": False},
        {"alias": "A", "coin": "ETH", "time": 20, "start_zero_observed": False},
    ]
    cleaned, diag = bt.source_zero_cut(rows)
    assert [x["time"] for x in cleaned] == [20, 30]
    assert diag["pre_zero_source_fills_skipped"] == 2
    assert diag["no_observed_flat_anchor_coins"] == ["A/ETH"]


def test_inventory_double_entry_cash_and_next_bar_cost(monkeypatch):
    monkeypatch.setattr(bt, "MINUTES", 1440)
    monkeypatch.setattr(bt, "DAYS", 1)
    monkeypatch.setattr(bt, "START_MS", 0)
    monkeypatch.setattr(bt, "START", datetime(1970, 1, 1, tzinfo=UTC))
    # This pod's static k=1/3*0.35, with a bought and then sold source unit.
    orders = pl.DataFrame(
        {
            "alias": ["A", "A"],
            "coin": ["BTC", "BTC"],
            "execute_ms": [60_000, 120_000],
            "net_qty": [1.0, -1.0],
            "fill_count": [1, 1],
        }
    )
    p = np.full(1440, 110.0)
    p[:2] = 100.0
    prices = {"BTC": {"open": p, "close": p, "low": p, "high": p}}
    account, worst, gross, bad, detail = bt.simulate_inventory(
        orders, ("A",), {"A": {"static_equity_scalar": "10000"}}, prices, cost_bps=6.0
    )
    k = 0.35
    gross_trade = k * 100 + k * 110
    expected_profit = k * (110 - 100) - gross_trade * 0.0006
    assert not bad.any()
    assert abs(account[-1] - 10000 - expected_profit) < 1e-7
    assert np.allclose(account, worst)
    assert np.max(gross) > 0
    assert detail["pod_results"]["A"]["scenario_trades_executed"] == 2
    assert (
        abs(
            detail["pod_results"]["A"]["scenario_fixed_fee_plus_slippage_usd"]
            - round(gross_trade * 0.0006, 2)
        )
        < 1e-7
    )
    assert detail["first_follower_path_unknown_at"] is None


def test_missing_execution_blocks_full_passage_without_pretending_zero(monkeypatch):
    monkeypatch.setattr(bt, "MINUTES", 1440)
    monkeypatch.setattr(bt, "DAYS", 1)
    monkeypatch.setattr(bt, "START_MS", 0)
    monkeypatch.setattr(bt, "START", datetime(1970, 1, 1, tzinfo=UTC))
    orders = pl.DataFrame(
        {
            "alias": ["A", "A"],
            "coin": ["BTC", "BTC"],
            "execute_ms": [60_000, 120_000],
            "net_qty": [1.0, -1.0],
            "fill_count": [1, 1],
        }
    )
    p = np.full(1440, 110.0)
    p[0] = 100.0
    p[1] = np.nan
    prices = {
        "BTC": {
            "open": p,
            "close": p,
            "low": np.where(np.isfinite(p), p - 1, np.nan),
            "high": np.where(np.isfinite(p), p + 1, np.nan),
        }
    }
    equity, adverse, _, bad, diag = bt.simulate_inventory(
        orders, ("A",), {"A": {"static_equity_scalar": "10000"}}, prices, cost_bps=6.0
    )
    assert diag["order_failures"]["MISSING_NATIVE_EXECUTION_BAR"] == 1
    assert diag["first_follower_path_unknown_at"] == "1970-01-01T00:01:00+00:00"
    assert diag["failure_index_or_none"] == 1
    hard = bad.copy()
    hard[1] = True
    result = bt.challenge_first_passage(
        equity,
        hard,
        {
            "targets": (100.0,),
            "trailing": 100.0,
            "daily": 100.0,
            "eod_trailing": True,
        },
    )
    assert result["status"] == "BLOCKED_BY_FIRST_UNKNOWN_EXECUTION_OR_MARK"
    assert result["challenge_pass"] is None


def test_drawdown_percentage_uses_prior_peak_not_initial_account(monkeypatch):
    monkeypatch.setattr(bt, "DAYS", 1)
    # A $6k peak-to-trough loss is 40% of $15k, not 60% of $10k.
    equity = np.full(1440, 10_000.0)
    equity[1] = 15_000.0
    equity[2] = 9_000.0
    result = bt.metrics(equity, np.zeros(1440, dtype=bool))
    assert result["observed_only_max_drawdown_usd_lower_bound"] == 6000.0
    assert result["observed_only_max_drawdown_pct_prior_peak"] == 40.0
    assert result["observed_only_max_drawdown_pct_initial_10k"] == 60.0


def test_barrier_first_passage_blocks_before_future_target(monkeypatch):
    monkeypatch.setattr(bt, "MINUTES", 5)
    monkeypatch.setattr(bt, "DAYS", 1)
    monkeypatch.setattr(bt, "START", datetime(1970, 1, 1, tzinfo=UTC))
    equity = np.array([10000.0, 10040.0, 9990.0, 10200.0, 10500.0])
    result = bt.challenge_first_passage(
        equity,
        np.zeros(5, dtype=bool),
        {"daily": 200.0, "trailing": 40.0, "eod_trailing": False, "targets": (100.0,)},
    )
    assert result["status"] == "MODELED_BREACH_BEFORE_ANY_MARK_GAP"
    assert result["at"].endswith("00:02:00+00:00")
    assert result["challenge_pass"] is False
