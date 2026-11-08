"""Observed top-of-book paper execution never substitutes depth for traded volume."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import Instrument, Rulebook, Account
from copytrade_pm.pm03_execution import CostModel, MarketObservation, execute_targets

INST = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
AT = "2026-11-07T11:00:00+00:00"


def quote(**override):
    props = {
        "instrument": INST,
        "event_at": AT,
        "first_known_at": AT,
        "mark": D("100"),
        "volume_base": None,
        "quality": "VERIFIED_QUOTE",
        "supported": True,
        "capacity_basis": "DISPLAYED_L2_TOP_LEVEL",
        "best_bid": D("99"),
        "best_ask": D("101"),
        "bid_size": D("1"),
        "ask_size": D("2"),
        "quantity_step": D("0.1"),
        "minimum_notional": D("1"),
    }
    props.update(override)
    return MarketObservation(**props)


def account():
    rb = Rulebook(
        program="paper",
        stage="virtual",
        source="test-only",
        observed_at=AT,
        version="1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=None,
        daily_loss=D("500"),
        static_loss=D("1000"),
        trailing_loss=None,
        confirmed=True,
        permitted=(INST,),
    )
    return Account.start(rb, AT)


def costs():
    return CostModel(
        fee_bps=D("5"),
        full_spread_bps=D("0"),
        slippage_bps=D("2"),
        impact_bps_at_full_participation=D("0"),
        max_participation=D("0.5"),
        max_age_seconds=30,
        latency_seconds=0,
    )


def test_displayed_depth_prices_buy_at_ask_without_double_spread():
    paper = account()
    result = execute_targets(
        paper,
        {"pod": {INST: D("2")}},
        {INST: quote()},
        costs(),
        decision_at=AT,
        hypothetical_fill_at=AT,
        permitted=True,
    )
    assert result["status"] == "PARTIAL"
    assert D(result["fills"][0]["quantity"]) == D("1")
    assert D(result["fills"][0]["execution_price"]) > D("101")
    assert result["fills"][0]["capacity_basis"] == "DISPLAYED_L2_TOP_LEVEL"
    assert result["fills"][0]["hypothetical_only"] is True
    assert paper.quantities[INST] == D("1")
    assert paper.pm_quantities["pod"][INST] == D("1")
    assert paper.equity < D("10000")


def test_displayed_depth_prices_sells_at_bid_and_enforces_side_size():
    paper = account()
    result = execute_targets(
        paper,
        {"pod": {INST: D("-2")}},
        {INST: quote()},
        costs(),
        decision_at=AT,
        hypothetical_fill_at=AT,
        permitted=True,
    )
    assert D(result["fills"][0]["quantity"]) == D("-0.5")
    assert D(result["fills"][0]["execution_price"]) < D("99")
    assert paper.quantities[INST] == D("-0.5")


@pytest.mark.parametrize(
    "changes",
    [
        {"volume_base": D("1000")},
        {"quality": "OHLCV_1M_PROXY"},
        {"best_bid": D("102")},
        {"ask_size": D("0")},
        {"best_ask": None},
        {"quantity_step": None},
    ],
)
def test_l2_depth_contract_never_fabricates_traded_volume(changes):
    with pytest.raises(ValueError):
        quote(**changes).validate(AT)


def test_old_volume_based_model_is_unchanged():
    classic = MarketObservation(INST, AT, AT, D("100"), D("1000"), "SYNTHETIC", True)
    classic.validate(AT)
    price, _, report = costs().price_and_fee(D("1"), classic)
    assert price > D("100")
    assert report["quality"] == "SYNTHETIC"
