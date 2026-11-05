"""Regression checks for extended ML4T-66 protected barbell research."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest

from scripts import ml4t66_barbell_protected_oos as extended
from scripts import ml4t66_protected_portfolio_replay as protected


def test_portfolio_universe_has_unique_members_and_expected_roles():
    rows = extended.portfolio_universe()
    assert len(rows) == 66
    assert len({name for name, _, _ in rows}) == 66
    assert {len(members) for _, members, _ in rows} == {3, 4, 5}
    for _, members, roles in rows:
        assert len(members) == len(set(members))
        assert len(roles) == len(members)
        assert roles.count("anchor") in (2, 3)
        assert roles.count("runner") in (1, 2)


def test_training_budget_caps_and_hindsight_distinction():
    stats = {
        a: {
            "base_k": 0.1,
            "training_daily_adverse_usd": 500.,
            "training_lifetime_adverse_usd": 700.,
            "full_daily_adverse_usd": 1000.,
        } for a in ("A", "B", "C")
    }
    ks, daily, lifetime, training, full = extended.calculate_k(
        ("A", "B", "C"), ("anchor", "anchor", "runner"), stats
    )
    assert set(ks) == {"A", "B", "C"}
    assert training <= 400.
    assert full >= training
    assert sum(daily.values()) == 340.
    assert sum(lifetime.values()) == 550.
    assert all(0 < k <= 0.1 for k in ks.values())


def _short(monkeypatch):
    monkeypatch.setattr(protected.base, "MINUTES", 6)
    monkeypatch.setattr(protected.base, "START_MS", 0)
    monkeypatch.setattr(protected.base, "START", datetime(1970, 1, 1, tzinfo=UTC))


def _batch(aliases):
    n = len(aliases)
    qty = 100. / (.35/n)
    return pl.DataFrame({
        "alias": list(aliases),
        "coin": ["BTC"]*n,
        "execute_ms": [60_000]*n,
        "net_qty": [qty]*n,
    })


def test_per_pod_limit_stops_only_its_own_book(monkeypatch):
    _short(monkeypatch)
    bar = {
        "open": np.array([100., 100., 100., 98.8, 98.8, 98.8]),
        "close": np.array([100., 100., 98.9, 98.9, 98.9, 98.9]),
        "low": np.array([100., 100., 98.9, 98.9, 98.9, 98.9]),
        "high": np.array([100., 100., 98.9, 98.9, 98.9, 98.9]),
    }
    report = protected.protected(
        _batch(("A", "B")),
        ("A", "B"),
        {"A": {"static_equity_scalar": "10000"},
         "B": {"static_equity_scalar": "10000"}},
        {"BTC": bar},
        pod_budgets_usd={"A": 100., "B": 200.},
        pod_daily_limits_usd={"A": 100., "B": 200.},
    )
    assert report["pods"]["A"]["state"] == "SUSPENDED_FLAT"
    assert report["pods"]["A"]["exit_complete_at"] == "1970-01-01T00:03:00+00:00"
    assert report["pods"]["B"]["state"] == "ACTIVE"
    assert report["pods"]["B"]["exit_orders_executed"] == 0


def test_partial_per_pod_policy_is_rejected(monkeypatch):
    _short(monkeypatch)
    with pytest.raises(ValueError, match="INVALID_PER_POD_BUDGETS"):
        protected.protected(
            _batch(("A", "B")),
            ("A", "B"),
            {"A": {"static_equity_scalar": "10000"},
             "B": {"static_equity_scalar": "10000"}},
            {},
            pod_budgets_usd={"A": 100.},
        )


def test_no_green_day_requirement_for_custom_single_stage_contract(monkeypatch):
    _short(monkeypatch)
    bar = {
        "open": np.full(6, 100.),
        "close": np.array([100., 100., 111., 111., 111., 111.]),
        "low": np.array([100., 100., 111., 111., 111., 111.]),
        "high": np.array([100., 100., 111., 111., 111., 111.]),
    }
    report = protected.protected(
        pl.DataFrame({
            "alias": ["A"], "coin": ["BTC"], "execute_ms": [60_000],
            "net_qty": [100/.35],
        }),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bar},
        budget_usd=2000.,
        contract_rule={
            "daily": 500., "trailing": 1000.,
            "eod_trailing": False, "targets": (1000.,),
            "minimum_green_days": 0,
        },
    )
    assert report["target_at"] == "1970-01-01T00:02:00+00:00"
    assert report["status"] == "CHALLENGE_TARGET_REACHED"


def test_account_daily_hwm_stress_does_not_invent_ohlc_order(monkeypatch):
    _short(monkeypatch)
    bar = {
        "open": np.full(6, 100.),
        "close": np.array([100., 110., 108., 108., 108., 108.]),
        "low": np.array([100., 100., 103., 108., 108., 108.]),
        "high": np.array([100., 110., 110., 108., 108., 108.]),
    }
    output = protected.protected(
        pl.DataFrame({
            "alias": ["A"], "coin": ["BTC"], "execute_ms": [60_000],
            "net_qty": [100/.35],
        }),
        ("A",),
        {"A": {"static_equity_scalar": "10000"}},
        {"BTC": bar},
        budget_usd=3000.,
        mark_mode="close",
        contract_rule={
            "daily": 500., "trailing": 1000., "eod_trailing": False,
            "daily_hwm": True, "account_adverse_ohlc": True,
            "targets": (2000.,), "minimum_green_days": 0,
        },
    )
    assert output["status"] == "CONTRACT_FLOOR_BREACH"
    assert output["status_at"] == "1970-01-01T00:02:00+00:00"
