"""Contract regressions: pod $200 loss -> latch + next-open liquidation."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest

from scripts import ml4t66_protected_portfolio_replay as policy


def _reset_short_window(monkeypatch):
    monkeypatch.setattr(policy.base, "MINUTES", 8)
    monkeypatch.setattr(policy.base, "START_MS", 0)
    monkeypatch.setattr(policy.base, "START", datetime(1970, 1, 1, tzinfo=UTC))


def _bars(*, initial=100, next_drop=98, exit_open=97):
    op = np.full(8, 100.0)
    close = np.full(8, 100.0)
    low = np.full(8, 100.0)
    high = np.full(8, 100.0)
    close[2:] = next_drop
    low[2:] = next_drop
    high[2:] = next_drop
    op[3:] = exit_open
    return {"open": op, "close": close, "low": low, "high": high}


def _batch(rows):
    return pl.DataFrame(
        rows,
        orient="row",
        schema={
            "alias": pl.String,
            "coin": pl.String,
            "execute_ms": pl.Int64,
            "net_qty": pl.Float64,
            "fill_count": pl.Int64,
        },
    )


def test_only_breaching_pod_is_frozen_and_flat_next_open(monkeypatch):
    _reset_short_window(monkeypatch)
    # Two pods, each static scale k=0.175. Pod A's 100 effective BTC
    # shares lose >$200 on minute 2; pod B retains ETH unaffected.
    qty = 100.0 / 0.175
    rows = _batch(
        [
            ("A", "BTC", 60000, qty, 1),
            ("B", "ETH", 60000, qty / 10, 1),
            ("A", "BTC", 4 * 60000, qty, 1),
        ]
    )
    panel = {"BTC": _bars(next_drop=97.99, exit_open=97.97)}
    panel["ETH"] = {field: np.full(8, 100.0) for field in ("open", "close", "low", "high")}
    result = policy.protected(
        rows,
        ("A", "B"),
        {"A": {"static_equity_scalar": "10000"}, "B": {"static_equity_scalar": "10000"}},
        panel,
        cost_bps=6.0,
        budget_usd=200.0,
    )
    a = result["pods"]["A"]
    b = result["pods"]["B"]
    assert a["stopped_at"] == "1970-01-01T00:02:00+00:00"
    assert a["exit_complete_at"] == "1970-01-01T00:03:00+00:00"
    assert a["state"] == "SUSPENDED_FLAT"
    assert a["remaining_coin_qty"] == {}
    assert a["source_orders_ignored_after_stop"] == 1
    assert a["exit_orders_executed"] == 1
    assert a["pnl_after_flat_usd"] < -200
    assert b["state"] == "ACTIVE"
    assert b["stopped_at"] is None
    assert b["source_fills_executed"] == 1
    assert result["status"] == "STUDY_WINDOW_END"
    assert result["valid_complete_path"] is True
    assert result["max_drawdown_usd_observed"] > 200


def test_next_open_exit_gap_never_marks_flat_without_executable_bar(monkeypatch):
    _reset_short_window(monkeypatch)
    qty = 100.0 / 0.35
    panels = {"BTC": _bars(next_drop=97.99, exit_open=97.97)}
    panels["BTC"]["open"][3] = np.nan
    result = policy.protected(
        _batch([("A", "BTC", 60000, qty, 1)]),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        panels,
        budget_usd=200.0,
    )
    assert result["status"] == "BLOCKED_UNKNOWN_EXECUTION_OR_MARK"
    assert result["first_follower_unknown"]["reason"] == "UNPRICED_POD_FORCED_EXIT"
    assert result["pods"]["A"]["state"] == "SUSPENDED_PENDING_EXIT"
    assert result["pods"]["A"]["remaining_coin_qty"]
    assert result["net_pnl_usd"] is None


def test_per_pod_stop_is_from_marked_pnl_high_water_not_zero(monkeypatch):
    _reset_short_window(monkeypatch)
    # A buys 100 effective shares at 100, peaks at 110 (+~$994 net),
    # then falls to 107.9: peak-trough >$200, still profitable vs 0.
    qty = 100 / 0.35
    bars = _bars()
    bars["close"][1] = 110
    bars["low"][1] = 110
    bars["high"][1] = 110
    bars["open"][2] = 107.9
    bars["close"][2:] = 107.9
    bars["low"][2:] = 107.9
    bars["high"][2:] = 107.9
    bars["open"][3:] = 107.8
    result = policy.protected(
        _batch([("A", "BTC", 60000, qty, 1)]),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bars},
        budget_usd=200.0,
    )
    a = result["pods"]["A"]
    assert a["reason"] == "POD_TRAILING_DD"
    assert a["pnl_when_triggered_usd"] > 0
    assert a["pnl_after_flat_usd"] > 0


def test_optional_daily_stop_is_separate_from_long_term_two_percent(monkeypatch):
    _reset_short_window(monkeypatch)
    qty = 100 / 0.35
    bars = _bars(next_drop=98.9, exit_open=98.8)
    result = policy.protected(
        _batch([("A", "BTC", 60000, qty, 1)]),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bars},
        budget_usd=200,
        pod_daily_limit=100,
    )
    a = result["pods"]["A"]
    assert a["reason"] == "POD_DAILY_LOSS"
    assert a["exit_complete_at"] == "1970-01-01T00:03:00+00:00"


def test_open_gap_freezes_pod_before_same_minute_source_increase(monkeypatch):
    _reset_short_window(monkeypatch)
    raw_qty = 100.0 / 0.35
    bars = _bars(next_drop=97.0, exit_open=97.0)
    bars["open"][2] = 97.0
    result = policy.protected(
        _batch(
            [
                ("A", "BTC", 60_000, raw_qty, 1),
                ("A", "BTC", 120_000, raw_qty, 1),
            ]
        ),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bars},
        budget_usd=200,
    )
    pod = result["pods"]["A"]
    assert pod["stopped_at"] == "1970-01-01T00:02:00+00:00"
    assert pod["exit_complete_at"] == "1970-01-01T00:03:00+00:00"
    assert pod["source_orders_ignored_after_stop"] == 1
    assert result["fills_executed_by_type"]["source_delta"] == 1


def test_skipped_subminimum_source_deltas_catch_up_to_target_no_ghost_short(monkeypatch):
    _reset_short_window(monkeypatch)
    source_delta = 0.06 / 0.35
    prices = {"BTC": {field: np.full(8, 100.0) for field in ("open", "close", "low", "high")}}
    result = policy.protected(
        _batch(
            [
                ("A", "BTC", 60_000, source_delta, 1),
                ("A", "BTC", 120_000, source_delta, 1),
                ("A", "BTC", 180_000, -2 * source_delta, 1),
            ]
        ),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        prices,
        budget_usd=200,
    )
    assert result["status"] == "STUDY_WINDOW_END"
    assert result["fills_executed_by_type"]["source_delta"] == 2
    assert result["pods"]["A"]["remaining_coin_qty"] == {}
    assert result["pods"]["A"]["final_marked_pnl_usd"] < 0
    assert result["blocked_orders"]["BELOW_10USD"] == 1


def test_pretrade_gross_cap_blocks_increase_but_allows_full_reduction(monkeypatch):
    _reset_short_window(monkeypatch)
    raw_90 = 90 / 0.35
    raw_50 = 50 / 0.35
    bars = {"BTC": {field: np.full(8, 100.0) for field in ("open", "close", "low", "high")}}
    result = policy.protected(
        _batch(
            [
                ("A", "BTC", 60_000, raw_90, 1),
                ("A", "BTC", 120_000, raw_50, 1),
                ("A", "BTC", 180_000, -raw_90 - raw_50, 1),
            ]
        ),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        bars,
        budget_usd=200,
        max_gross_usd=10_000,
    )
    assert result["status"] == "STUDY_WINDOW_END"
    assert result["blocked_orders"]["PRETRADE_GROSS_CAP"] == 1
    assert result["peak_gross_usd"] <= 10_000
    assert result["pods"]["A"]["remaining_coin_qty"] == {}
    assert result["fills_executed_by_type"]["source_delta"] == 2


def test_source_reversal_closes_to_flat_without_automatic_reopen(monkeypatch):
    _reset_short_window(monkeypatch)
    raw_qty = 100 / 0.35
    bars = {"BTC": {field: np.full(8, 100.0) for field in ("open", "close", "low", "high")}}
    result = policy.protected(
        _batch(
            [
                ("A", "BTC", 60_000, raw_qty, 1),
                ("A", "BTC", 120_000, -2 * raw_qty, 1),
            ]
        ),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        bars,
        budget_usd=200,
    )
    assert result["status"] == "STUDY_WINDOW_END"
    assert result["fills_executed_by_type"]["source_delta"] == 1
    assert result["fills_executed_by_type"]["reversal_close"] == 1
    assert result["fills_executed_by_type"].get("reversal_open", 0) == 0
    assert result["pods"]["A"]["remaining_coin_qty"] == {}
    assert result["outstanding_source_reversals"][0]["pod"] == "A"


def test_nonfinite_risk_controls_rejected():
    for cap in [float("nan"), float("inf"), -10.0, 0.0]:
        with pytest.raises(ValueError, match="INVALID_PRETRADE_GROSS_CAP"):
            policy.protected(
                _batch([("A", "BTC", 60000, 2.0, 1)]),
                ("A",),
                {"A": {"static_equity_scalar": "10000"}},
                {},
                max_gross_usd=cap,
            )


def test_volume_participation_cap_blocks_new_risk_without_inventing_fill(monkeypatch):
    _reset_short_window(monkeypatch)
    panels = {"BTC": {field: np.full(8, 100.0) for field in ("open", "close", "low", "high")}}
    panels["BTC"]["volume"] = np.full(8, 10.0)
    result = policy.protected(
        _batch([("A", "BTC", 60_000, 100 / 0.35, 1)]),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        panels,
        max_participation=0.10,
    )
    assert result["blocked_orders"]["PRETRADE_VOLUME_CAP"] == 1
    assert result["pods"]["A"]["remaining_coin_qty"] == {}
    assert result["fills_executed_by_type"].get("source_delta", 0) == 0


def test_volume_cap_inability_to_flat_is_unknown_not_completed(monkeypatch):
    _reset_short_window(monkeypatch)
    qty = 100.0 / 0.35
    bars = _bars(next_drop=97.99, exit_open=97.97)
    bars["volume"] = np.full(8, 1000.0)
    bars["volume"][2] = 0.0  # previous completed minute for exit at index 3
    result = policy.protected(
        _batch([("A", "BTC", 60_000, qty, 1)]),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bars},
        max_participation=0.15,
        budget_usd=200,
    )
    assert result["status"] == "BLOCKED_UNKNOWN_EXECUTION_OR_MARK"
    assert result["first_follower_unknown"]["reason"] == "UNVERIFIED_FORCED_EXIT_CAPACITY"
    assert result["pods"]["A"]["remaining_coin_qty"]
    assert result["net_pnl_usd"] is None


def test_invalid_volume_participation_rejected():
    for rate in (0, -0.1, float("nan"), float("inf"), 1.1):
        with pytest.raises(ValueError, match="INVALID_PARTICIPATION_LIMIT"):
            policy.protected(
                _batch([("A", "BTC", 60_000, 2, 1)]),
                ("A",),
                {"A": {"static_equity_scalar": "10000"}},
                {},
                max_participation=rate,
            )


def test_account_stop_blocks_next_source_trade_and_flattens(monkeypatch):
    _reset_short_window(monkeypatch)
    raw_qty = 100 / 0.35
    bars = _bars(next_drop=98, exit_open=97.9)
    bars["open"][2] = 98
    result = policy.protected(
        _batch(
            [
                ("A", "BTC", 60_000, raw_qty, 1),
                ("A", "BTC", 120_000, raw_qty, 1),
            ]
        ),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bars},
        budget_usd=1000,
        contract_rule={
            "daily": 100,
            "trailing": 500,
            "eod_trailing": False,
            "targets": (1000,),
        },
    )
    assert result["status"] == "CONTRACT_FLOOR_BREACH_AT_OPEN"
    assert result["fills_executed_by_type"]["source_delta"] == 1
    assert result["pods"]["A"]["remaining_coin_qty"] == {}
    assert result["account_halt"] is True


def test_sprint_eod_ratcheting_does_not_use_intraday_peak(monkeypatch):
    _reset_short_window(monkeypatch)
    bars = {"BTC": {field: np.full(8, 100.0) for field in ("open", "close", "low", "high")}}
    bars["BTC"]["close"][1] = 104  # $400 peak
    bars["BTC"]["close"][2:] = 102  # $200 fall vs peak, still > initial
    bars["BTC"]["low"][1] = 100
    bars["BTC"]["high"][1] = 104
    bars["BTC"]["low"][2:] = 100
    bars["BTC"]["high"][2:] = 104
    orders = _batch([("A", "BTC", 60_000, 100 / 0.35, 1)])
    eq = {"A": {"static_equity_scalar": "10000"}}
    eod = policy.protected(
        orders,
        ("A",),
        eq,
        bars,
        budget_usd=1000,
        contract_rule={
            "daily": 500,
            "trailing": 100,
            "eod_trailing": True,
            "targets": (10000,),
        },
    )
    continuous = policy.protected(
        orders,
        ("A",),
        eq,
        bars,
        budget_usd=1000,
        contract_rule={
            "daily": 500,
            "trailing": 100,
            "eod_trailing": False,
            "targets": (10000,),
        },
    )
    assert eod["status"] == "STUDY_WINDOW_END"
    assert eod["account_halt"] is False
    assert continuous["status"].startswith("CONTRACT_FLOOR_BREACH")
    assert continuous["account_halt"] is True


def test_invalid_portfolio_identifiers_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_OR_EMPTY_POD_IDS"):
        policy.protected(
            _batch([("A", "BTC", 60000, 1, 1)]),
            ("A", "A"),
            {"A": {"static_equity_scalar": "10000"}},
            {},
        )


def test_target_records_only_actually_traded_pods(monkeypatch):
    _reset_short_window(monkeypatch)
    prices = {
        "BTC": {
            "open": np.full(8, 100.0),
            "close": np.array([100, 101, 101, 101, 101, 101, 101, 101], dtype=float),
            "low": np.full(8, 100.0),
            "high": np.full(8, 102.0),
        }
    }
    result = policy.protected(
        _batch([("A", "BTC", 60_000, 100 / 0.175, 1)]),
        ("A", "B"),
        {"A": {"static_equity_scalar": "10000"}, "B": {"static_equity_scalar": "10000"}},
        prices,
        contract_rule={
            "daily": 500,
            "trailing": 800,
            "eod_trailing": False,
            "targets": (50, 25),
        },
    )
    assert result["status"] == "PHASE1_TARGET_REACHED_STAGE2_NOT_SIMULATED"
    assert result["traded_pods_before_target"] == ["A"]
    assert result["all_members_traded_before_target"] is False
    assert result["source_trading_pods"] == ["A"]
    assert result["max_simultaneously_nonflat_pods"] == 1
    assert result["pods"]["B"]["source_fills_executed"] == 0


def test_cash_and_inventory_match_pm03_financial_authority_on_exact_simple_fills():
    from copytrade_pm.pm03_account import Account, Instrument, Rulebook
    from decimal import Decimal as D

    at = "2026-09-01T00:00:00+00:00"
    inst = Instrument("hyperliquid", "perp", "BTC")
    book = Rulebook(
        program="synthetic-parity",
        stage="evaluation",
        source="hypothetical-unit-test",
        observed_at=at,
        version="test-v1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=None,
        daily_loss=D("5000"),
        static_loss=None,
        trailing_loss=None,
        confirmed=True,
        permitted=(inst,),
    )
    pm = Account.start(book, at)
    pod = policy.Pod(alias="A", k=1.0)
    for delta, opened, close, at_mark in (
        (1.0, 100.0, 102.0, "2026-09-01T00:01:00+00:00"),
        (-1.0, 102.0, 103.0, "2026-09-01T00:02:00+00:00"),
    ):
        policy.execute(pod, "BTC", delta, opened, cost_bps=6.0)
        px = opened * (1 + (1 if delta > 0 else -1) * 0.00025)
        fee = abs(delta * opened) * 0.00035
        pm.simulate_fill(
            inst,
            D(str(delta)),
            D(str(px)),
            D(str(fee)),
            accepted=True,
            allocated={"A": D(str(delta))},
        )
        pm.mark({inst: D(str(close))}, at_mark)
        pm.verify()
        marked = pod.cash + pod.holdings.get("BTC", 0.0) * close
        assert abs(float(pm.equity) - 10000 - marked) < 1e-8
        assert abs(float(pm.pm_equity_pnl()["A"]) - marked) < 1e-8


def test_model_rejects_invalid_risk_budget():
    with pytest.raises(ValueError, match="INVALID_POD_STOP_BUDGET"):
        policy.protected(
            _batch([("A", "BTC", 60000, 2.0, 1)]),
            ("A",),
            {"A": {"static_equity_scalar": "10000"}},
            {},
            budget_usd=0,
        )
