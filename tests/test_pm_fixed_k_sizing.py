"""NAV-free fixed-k risk-budget intents never bypass follower safety gates."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm_exposure_sizing import target_from_fixed_k

BTC = "hyperliquid/mainnet:perp:default/BTC"
ETH = "hyperliquid/mainnet:perp:default/ETH"


def intent(**overrides):
    payload = {
        "source_quantities": {BTC: D("2"), ETH: D("-8")},
        "k": D("0.04"),
        "source_marks": {BTC: D("1000"), ETH: D("100")},
        "follower_marks": {BTC: D("1000"), ETH: D("100")},
        "follower_equity_usd": D("10000"),
        "max_gross_notional_usd": D("300"),
        "max_market_notional_usd": D("200"),
        "pod_loss_budget_usd": D("200"),
    }
    payload.update(overrides)
    return target_from_fixed_k(**payload)


def test_signed_native_quantity_scaled_without_leader_nav():
    result = intent()
    assert result["target_quantities"] == {BTC: "0.08", ETH: "-0.32"}
    assert result["target_notionals_usd"] == {BTC: "80.00", ETH: "-32.00"}
    assert result["source_nav_required"] is False
    assert result["risk_supervisor_required"] is True
    assert result["order_route"] == "NONE"
    assert not result["trading_authorized"]


def test_different_follower_marks_keep_k_times_source_notional():
    result = intent(follower_marks={BTC: D("800"), ETH: D("80")})
    assert result["target_notionals_usd"] == {BTC: "80.00", ETH: "-32.00"}
    assert result["target_quantities"] == {BTC: "0.10", ETH: "-0.40"}


def test_held_positions_not_individual_trade_tickets():
    earlier = intent(source_quantities={BTC: D("2"), ETH: D("-8")})
    later = intent(source_quantities={BTC: D("3"), ETH: D("-8")})
    assert D(later["target_quantities"][BTC]) - D(earlier["target_quantities"][BTC]) == D("0.04")
    assert later["target_quantities"][ETH] == earlier["target_quantities"][ETH]


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"k": D("0")}, "nonpositive"),
        ({"k": D("NaN")}, "finite"),
        ({"k": D("11")}, "FIXED_K_POLICY_OUT_OF_BOUNDS"),
        ({"follower_equity_usd": D("0")}, "nonpositive"),
        ({"max_gross_notional_usd": D("40")}, "FIXED_K_GROSS_NOTIONAL_CAP"),
        ({"max_market_notional_usd": D("40")}, "FIXED_K_MARKET_NOTIONAL_CAP"),
        ({"pod_loss_budget_usd": D("11000")}, "POD_LOSS_BUDGET_EXCEEDS_FOLLOWER_EQUITY"),
        ({"follower_marks": {BTC: D("0"), ETH: D("100")}}, "nonpositive"),
        ({"source_marks": {BTC: D("0"), ETH: D("100")}}, "nonpositive"),
        ({"source_quantities": {"BTC": D("2")}}, "EXPOSURE_INVALID_NATIVE_INSTRUMENT"),
    ],
)
def test_no_risk_or_market_validation_bypass(changes, reason):
    with pytest.raises(ValueError):
        intent(**changes)


def test_dex_position_scope_is_not_collapsed_by_symbol():
    xyz = "hyperliquid/mainnet:perp:xyz/BTC"
    result = intent(
        source_quantities={BTC: D("2"), xyz: D("-2")},
        source_marks={BTC: D("1000"), xyz: D("1000")},
        follower_marks={BTC: D("1000"), xyz: D("1000")},
    )
    assert result["target_quantities"][BTC] == "0.08"
    assert result["target_quantities"][xyz] == "-0.08"


def test_flat_source_yields_empty_book_not_fabricated_nav():
    result = intent(source_quantities={}, source_marks={}, follower_marks={})
    assert result["target_quantities"] == {}
    assert result["source_nav_required"] is False
