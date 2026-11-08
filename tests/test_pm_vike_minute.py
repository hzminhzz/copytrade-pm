"""Vike minute observations must never become fictitious L2 fills."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_vike_minute import (
    EstimatedMinuteExecutionModel, minute_latest, minute_observation,
)


T = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def row(*, ts=None, symbol="BTC", dex="HL", kind="perp", volume=20.0):
    return {
        "ts": int((ts or T).timestamp() * 1000),
        "symbol": symbol, "dex": dex, "kind": kind,
        "open": 100, "high": 102, "low": 99, "close": 101,
        "volume": volume, "volume_usd": volume * 101,
        "n_trades": 4 if volume else 0,
    }


def observed(r=None, *, seconds=30):
    return minute_observation(r or row(), received_at=(T + timedelta(seconds=seconds)).isoformat())


def test_forming_bar_is_last_trade_known_at_receipt_not_final_future_close():
    result = observed()
    assert result["forming"] is True
    assert result["price_semantics"] == "LAST_OBSERVED_TRADE_AS_OF_RECEIPT"
    assert result["first_known_at"] == (T + timedelta(seconds=30)).isoformat()


def test_completed_bar_is_final_only_when_its_end_has_passed():
    result = observed(seconds=70)
    assert result["forming"] is False
    assert result["price_semantics"] == "FINAL_BAR_CLOSE"


def test_provider_future_and_stale_candles_fail_closed():
    for delta in (-1, 121):
        with pytest.raises(ValueError, match="FUTURE_OR_STALE"):
            observed(seconds=delta)


def test_hip3_native_name_does_not_collapse_to_main_dex():
    prices = minute_latest(
        {"market": "perp", "interval": "1m",
         "candles": [row(), row(symbol="BRENTOIL", dex="xyz")]},
        received_at=(T + timedelta(seconds=30)).isoformat(),
    )
    assert set(prices) == {"BTC", "xyz:BRENTOIL"}
    prefixed = minute_latest(
        {"market": "perp", "interval": "1m",
         "candles": [row(symbol="xyz:AAOI", dex="XYZ")]},
        received_at=(T + timedelta(seconds=30)).isoformat(),
    )
    assert set(prefixed) == {"xyz:AAOI"}
    assert prefixed["xyz:AAOI"]["native_symbol"] == "xyz:AAOI"


def test_provider_outcome_and_zero_price_not_accepted_as_perp():
    assert minute_latest(
        {"market": "perp", "interval": "1m", "candles": [row(symbol="#123", kind="outcome")]},
        received_at=(T + timedelta(seconds=30)).isoformat(),
    ) == {}
    with pytest.raises(ValueError, match="PRICE_INVALID"):
        observed({**row(), "close": 0})


def test_one_estimated_market_order_with_bounded_volume_and_fee():
    estimate = EstimatedMinuteExecutionModel().price(
        D("1"), observed(), step=D("0.001"),
        minimum_notional=D("10"), decision_at=(T + timedelta(seconds=31)).isoformat(),
    )
    assert estimate["status"] == "FILLED"
    assert estimate["execution_evidence"] == "ESTIMATED_EXECUTION"
    assert estimate["single_market_intent"] is True
    assert estimate["real_order_count"] == 0
    assert D(estimate["fee"]) > 0
    assert D(estimate["vwap"]) > D("101")


def test_sell_estimate_costs_move_against_seller():
    estimate = EstimatedMinuteExecutionModel().price(
        D("-1"), observed(), step=D("0.001"),
        minimum_notional=D("10"), decision_at=(T + timedelta(seconds=31)).isoformat(),
    )
    assert estimate["status"] == "FILLED"
    assert D(estimate["vwap"]) < D("101")


def test_unproven_liquidity_and_amount_step_do_not_generate_synthetic_partial_fills():
    model = EstimatedMinuteExecutionModel()
    prices = observed()
    kwargs = {"step": D("0.001"), "minimum_notional": D("10"),
              "decision_at": (T + timedelta(seconds=31)).isoformat()}
    assert model.price(D("3"), prices, **kwargs)["status"] == "UNPRICEABLE_CAPACITY_NOT_VERIFIED"
    assert model.price(D("1.0005"), prices, **kwargs)["status"] == "REJECTED_NATIVE_STEP"
    assert model.price(D("1"), observed(row(volume=0)), **kwargs)["status"] == "UNPRICEABLE_CAPACITY_NOT_VERIFIED"


def test_stale_or_lookahead_decision_cannot_fill():
    model = EstimatedMinuteExecutionModel()
    prices = observed()
    for seconds in (29, 160):
        assert model.price(
            D("1"), prices, step=D("0.001"), minimum_notional=D("10"),
            decision_at=(T + timedelta(seconds=seconds)).isoformat(),
        )["status"] == "UNPRICEABLE_STALE_OR_FUTURE"


def test_corrupt_observation_hash_is_rejected():
    model = EstimatedMinuteExecutionModel()
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        model.price(
            D("1"), {**observed(), "price": "200"}, step=D("0.001"),
            minimum_notional=D("10"), decision_at=(T + timedelta(seconds=31)).isoformat(),
        )


def test_minute_response_requires_exact_perp_1m_contract():
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        minute_latest({"market": "spot", "interval": "1m", "candles": [row()]},
                      received_at=(T + timedelta(seconds=31)).isoformat())
