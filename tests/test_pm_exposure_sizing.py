"""Equity-normalized wallet exposure: size, skip, catch-up, audit gates."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm_exposure_sizing import (
    build_intent,
    calculate_weights,
    reconcile_actual,
    target_from_weights,
)
from copytrade_pm.pm_wallet_replica import WalletBook, replicate

BTC = "hyperliquid/mainnet:perp:default/BTC"
ETH = "hyperliquid/mainnet:perp:default/ETH"
BTC_XYZ = "hyperliquid/mainnet:perp:xyz/BTC"
AT = "2026-11-02T03:01:00+00:00"
SHA = "a" * 64


def source(**changes):
    data = dict(
        wallet="W028",
        account_scope="master:all-dex",
        source_event_at="2026-11-02T03:00:00+00:00",
        first_known_at="2026-11-02T03:00:30+00:00",
        source_sha256=SHA,
        equity_usd=D("100000"),
        positions={BTC: D("3")},
        complete=True,
        capital_reconciled=True,
        continuous=True,
        receipts_prospective=True,
    )
    data.update(changes)
    return WalletBook(**data)


def test_user_example_300pct_btc_exposure_from_equity_not_margin_or_ticket():
    book = source(source_leverage={BTC: D("10")}, source_margin_usd={BTC: D("30000")})
    plan = build_intent(
        book,
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000")},
        follower_marks={BTC: D("100000")},
    )
    assert plan.source_weights == {BTC: D("3")}
    assert plan.target_notionals_usd == {BTC: D("6000")}
    assert plan.target_quantities == {BTC: D(".06")}
    assert plan.source_gross_exposure_multiple == D("3")
    assert plan.source_net_exposure_multiple == D("3")
    assert (
        plan.target_quantities
        == replicate(book, decision_at=AT, pod_capital_usd=D("2000")).intended
    )


def test_multiasset_long_short_preserves_signed_weights_and_hedges():
    plan = build_intent(
        source(positions={BTC: D("3"), ETH: D("-100")}),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000"), ETH: D("2000")},
        follower_marks={BTC: D("100000"), ETH: D("2000")},
    )
    assert plan.source_weights == {BTC: D("3"), ETH: D("-2")}
    assert plan.target_notionals_usd == {BTC: D("6000"), ETH: D("-4000")}
    assert plan.target_quantities == {BTC: D(".06"), ETH: D("-2")}
    assert plan.source_gross_exposure_multiple == D("5")
    assert plan.source_net_exposure_multiple == D("1")


def test_skipped_one_or_two_follower_trades_are_catchup_deltas_not_flat_source():
    plan = build_intent(
        source(),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000")},
        follower_marks={BTC: D("100000")},
    )
    skipped_open = reconcile_actual(plan, actual_quantities={}, follower_marks={BTC: D("100000")})
    assert skipped_open["catch_up_deltas"] == {BTC: "0.06"}
    assert D(skipped_open["tracking_deviation_fraction"]) == 1
    missed_second_trade = reconcile_actual(
        plan, actual_quantities={BTC: D(".04")}, follower_marks={BTC: D("100000")}
    )
    assert missed_second_trade["catch_up_deltas"] == {BTC: "0.02"}
    assert D(missed_second_trade["tracking_deviation_fraction"]) == D("1") / D("3")
    caught_up = reconcile_actual(
        plan, actual_quantities={BTC: D(".06")}, follower_marks={BTC: D("100000")}
    )
    assert caught_up["catch_up_deltas"] == {}
    assert D(caught_up["tracking_deviation_fraction"]) == 0


def test_equity_change_resizes_wallet_position_without_new_source_trade():
    earlier = calculate_weights(
        source_quantities={BTC: D("3")},
        source_equity_usd=D("100000"),
        source_marks={BTC: D("100000")},
    )
    later = calculate_weights(
        source_quantities={BTC: D("3")},
        source_equity_usd=D("120000"),
        source_marks={BTC: D("100000")},
    )
    assert earlier[BTC] == D("3")
    assert later[BTC] == D("2.5")
    notionals, quantities = target_from_weights(
        weights=later, pod_capital_usd=D("2000"), follower_marks={BTC: D("100000")}
    )
    assert notionals[BTC] == D("5000")
    assert quantities[BTC] == D(".05")


def test_source_and_follower_mark_difference_keeps_dollar_weight():
    plan = build_intent(
        source(),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000")},
        follower_marks={BTC: D("99000")},
    )
    assert plan.source_weights[BTC] == D("3")
    assert plan.target_quantities[BTC] * D("99000") == D("6000")


def test_native_dex_identity_cannot_collapse_to_same_symbol():
    plan = build_intent(
        source(positions={BTC: D("3"), BTC_XYZ: D("-3")}),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000"), BTC_XYZ: D("100000")},
        follower_marks={BTC: D("100000"), BTC_XYZ: D("100000")},
    )
    assert set(plan.target_quantities) == {BTC, BTC_XYZ}
    assert plan.source_gross_exposure_multiple == D("6")


def test_flat_zero_quantity_market_with_existing_marks_is_valid():
    plan = build_intent(
        source(positions={BTC: D("0")}),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000")},
        follower_marks={BTC: D("100000")},
    )
    assert plan.source_weights == {}
    assert plan.target_quantities == {}
    assert plan.source_gross_exposure_multiple == 0


def test_verified_flat_source_means_close_actual_but_unaudited_missing_does_not():
    flat = build_intent(
        source(positions={}),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={},
        follower_marks={},
    )
    result = reconcile_actual(
        flat, actual_quantities={BTC: D(".03")}, follower_marks={BTC: D("100000")}
    )
    assert result["catch_up_deltas"] == {BTC: "-0.03"}
    assert result["tracking_deviation_fraction"] is None
    with pytest.raises(ValueError, match="E0_INCOMPLETE_SOURCE_ACCOUNT"):
        build_intent(
            source(positions={}, complete=False),
            decision_at=AT,
            pod_capital_usd=D("2000"),
            source_marks={},
            follower_marks={},
        )


@pytest.mark.parametrize(
    "update",
    [
        {"equity_usd": D("0")},
        {"equity_usd": D("-1000")},
        {"capital_reconciled": False},
        {"complete": False},
        {"continuous": False},
        {"receipts_prospective": False},
        {"source_event_at": "2026-11-01T23:00:00+00:00"},
        {"first_known_at": "2026-11-02T04:00:00+00:00"},
    ],
)
def test_source_book_fail_closed(update):
    with pytest.raises(ValueError):
        build_intent(
            source(**update),
            decision_at=AT,
            pod_capital_usd=D("2000"),
            source_marks={BTC: D("100000")},
            follower_marks={BTC: D("100000")},
        )


@pytest.mark.parametrize(
    "field,values",
    [
        ("source_marks", {}),
        ("follower_marks", {}),
        ("source_marks", {BTC: D("0")}),
        ("follower_marks", {BTC: D("-1")}),
        ("source_marks", {"BTC": D("100000")}),
        ("follower_marks", {"BTC": D("100000")}),
        ("source_marks", {BTC: D("NaN")}),
    ],
)
def test_mark_quality_cannot_silently_drop_or_price_wrong_leg(field, values):
    kwargs = {
        "source_marks": {BTC: D("100000")},
        "follower_marks": {BTC: D("100000")},
    }
    kwargs[field] = values
    with pytest.raises(ValueError):
        build_intent(source(), decision_at=AT, pod_capital_usd=D("2000"), **kwargs)


def test_executed_unexpected_position_must_have_mark_before_catchup():
    plan = build_intent(
        source(),
        decision_at=AT,
        pod_capital_usd=D("2000"),
        source_marks={BTC: D("100000")},
        follower_marks={BTC: D("100000")},
    )
    with pytest.raises(ValueError, match="EXPOSURE_MISSING_MARK"):
        reconcile_actual(plan, actual_quantities={ETH: D("1")}, follower_marks={BTC: D("100000")})
    result = reconcile_actual(
        plan,
        actual_quantities={BTC: D(".06"), ETH: D("-1")},
        follower_marks={BTC: D("100000"), ETH: D("2000")},
    )
    assert result["catch_up_deltas"][ETH] == "1"
    assert D(result["tracking_deviation_usd"]) == D("2000")


def test_missing_hedge_quote_refuses_whole_intent_instead_of_skipping():
    with pytest.raises(ValueError, match="EXPOSURE_MISSING_MARK"):
        build_intent(
            source(positions={BTC: D("3"), ETH: D("-100")}),
            decision_at=AT,
            pod_capital_usd=D("2000"),
            source_marks={BTC: D("100000"), ETH: D("2000")},
            follower_marks={BTC: D("100000")},
        )


def test_no_unbounded_margin_promotion_or_silent_leverage_cap():
    weights = calculate_weights(
        source_quantities={BTC: D("3")},
        source_equity_usd=D("100000"),
        source_marks={BTC: D("100000")},
    )
    notionals, qty = target_from_weights(
        weights=weights,
        pod_capital_usd=D("2000"),
        follower_marks={BTC: D("100000")},
    )
    assert notionals[BTC] == D("6000")  # $3000 PM04 cap is downstream
    assert qty[BTC] == D(".06")
