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


def test_model_rejects_invalid_risk_budget():
    with pytest.raises(ValueError, match="INVALID_POD_STOP_BUDGET"):
        policy.protected(
            _batch([("A", "BTC", 60000, 2.0, 1)]),
            ("A",),
            {"A": {"static_equity_scalar": "10000"}},
            {},
            budget_usd=0,
        )
