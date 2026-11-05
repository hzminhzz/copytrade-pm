"""Test conditional shock & event-delay screens without real or fabricated NAV."""

from __future__ import annotations

import pytest

pytest.importorskip("polars")
pytest.importorskip("numpy")

import numpy as np

from scripts.phase7_conditional_stress import (
    SCALES,
    STUDY_MINUTES,
    evaluate,
    max_loss,
    port_exposure,
)
from scripts.phase7_delay_cost_screen import batch_orders, study_one_source
from scripts.phase7_native_exposure import END_MS, START_MS


def test_frozen_coefficients_keep_budget_scope_separate() -> None:
    assert set(SCALES["E2"]) == {"ACT04", "S051-BTC", "S053-HYPE"}
    assert set(SCALES["E6"]) == {*SCALES["E2"], "CM-002", "Whale_0x5f94"}
    assert SCALES["E2"]["ACT04"] > SCALES["E6"]["ACT04"]


def test_first_event_batch_window_does_not_reset() -> None:
    events = [
        (START_MS + 1000, 2.0, 100.0),
        (START_MS + 60_000, 1.0, 110.0),
        (START_MS + 290_000, -2.0, 120.0),
        (START_MS + 302_000, -1.0, 130.0),
        (START_MS + 340_000, 2.0, 140.0),
    ]
    observed = batch_orders(events, 300)
    assert len(observed) == 2
    assert observed[0] == (START_MS + 301_000, 1.0, 120.0, 3)
    assert observed[1] == (START_MS + 602_000, 1.0, 140.0, 2)
    assert len(batch_orders(events, 0)) == 5


def test_cancelled_net_zero_batch_not_counted() -> None:
    events = [(START_MS + 1000, 2.0, 100.0), (START_MS + 2000, -2.0, 101.0)]
    assert batch_orders(events, 300) == []


def test_window_right_censors_at_end_of_study() -> None:
    assert batch_orders([(END_MS - 1000, 1.0, 50.0)], 300) == []
    assert len(batch_orders([(END_MS - 1000, 1.0, 50.0)], 0)) == 1


def test_study_never_certifies_follower_price_or_pnl() -> None:
    def fill(ms, side, tid):
        return {"time": ms, "coin": "BTC", "px": "100", "sz": "2", "side": side, "tid": tid}

    stats = study_one_source(
        [
            fill(START_MS + 1000, "B", 1),
            fill(START_MS + 2000, "A", 2),
            fill(START_MS + 1000, "B", 1),
        ]
    )
    assert stats["valid_events"] == 2
    assert stats["duplicates"] == 1
    assert stats["0"]["orders"] == 2
    assert stats["5"]["orders"] == 0


def test_adversarial_shock_distinguishes_net_and_gross() -> None:
    long = np.zeros(STUDY_MINUTES, dtype=np.float32)
    short = np.zeros(STUDY_MINUTES, dtype=np.float32)
    long[123] = 1000
    short[123] = -600
    by_coin, by_wallet = port_exposure({("A", "BTC"): long, ("B", "BTC"): short}, {"A": 1, "B": 1})
    assert by_coin["BTC"][123] == 400
    assert by_wallet["A"][123] == 1000
    assert by_wallet["B"][123] == 600
    shock = max_loss(by_coin["BTC"] * -0.10, np.abs(by_coin["BTC"]) > 0)
    assert shock["worst_model_loss_usd"] == 40.0
    result = evaluate({("ACT04", "BTC"): long, ("S051-BTC", "BTC"): short}, {})
    e2 = result["portfolios"]["E2"]
    assert e2["account_equity_drawdown"] is None
    assert e2["breach_certified"] is None
    assert e2["observed_minutes_at_least_one_source_leg"] == 1
