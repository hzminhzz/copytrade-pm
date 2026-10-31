from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm36_e3 import size

T = datetime(2026, 10, 1, tzinfo=UTC)


def history(recent_step: D = D("0.02"), reference_step: D = D("0.01")):
    """Return exactly 840 hourly returns ending one hour before decision."""
    prices = []
    price = D("100")
    for offset in range(-841, 0):
        if offset < -168:
            step = reference_step if (offset + 841) % 2 == 0 else -reference_step
        else:
            step = recent_step if (offset + 169) % 2 == 0 else -recent_step
        price *= step.exp()
        prices.append((T + timedelta(hours=offset), price))
    return prices


def test_realized_vol_ratio_scales_permitted_target_and_caps_at_one():
    targets = {"BTC": D("10")}
    scaled = size(targets, {"BTC": D("10")}, {"BTC": history()}, T)["BTC"]
    assert abs(scaled - D("5")) < D("1e-20")
    assert size(targets, {"BTC": D("10")}, {"BTC": history(D("0.005"))}, T) == targets


def test_zero_reference_volatility_blocks_new_risk():
    data = history(reference_step=D("0"))
    assert size({"BTC": D("10")}, {"BTC": D("2")}, {"BTC": data}, T) == {"BTC": D("2")}


def test_insufficient_history_preserves_exposure_and_only_honors_reduction():
    targets = {"BTC": D("10"), "ETH": D("-8"), "SOL": D("-5")}
    current = {"BTC": D("4"), "ETH": D("-10"), "SOL": D("5")}
    histories = {key: [] for key in targets}
    assert size(targets, current, histories, T) == {
        "BTC": D("4"),  # new risk blocked
        "ETH": D("-8"),  # same-side reduction allowed
        "SOL": D("0"),  # reversal can flatten but not open opposite risk
    }


def test_decision_and_future_prices_are_never_used():
    data = history()
    data.extend([(T, D("1")), (T + timedelta(hours=1), D("999999"))])
    result = size({"BTC": D("10")}, {"BTC": D("10")}, {"BTC": data}, T)["BTC"]
    assert abs(result - D("5")) < D("1e-20")


def test_missing_hourly_observation_blocks_new_risk():
    data = history()
    data.pop(400)
    assert size({"BTC": D("10")}, {"BTC": D("3")}, {"BTC": data}, T) == {"BTC": D("3")}


def test_incomplete_target_universe_fails_closed():
    with pytest.raises(ValueError, match="UNIVERSES_MUST_MATCH"):
        size({"BTC": D("10")}, {}, {}, T)


def test_invalid_price_is_rejected():
    with pytest.raises(ValueError, match="POSITIVE_AND_FINITE"):
        size({"BTC": D("1")}, {"BTC": D("0")}, {"BTC": [(T - timedelta(hours=1), D("0"))]}, T)
