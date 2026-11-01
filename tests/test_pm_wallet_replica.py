from decimal import Decimal as D

import pytest

from copytrade_pm.pm_wallet_replica import WalletBook, fidelity, replicate

AT = "2026-11-01T04:00:00+00:00"
SHA = "a" * 64
BTC = "hyperliquid/mainnet:perp:default/BTC"
ETH = "hyperliquid/mainnet:perp:default/ETH"


def book(**changes):
    data = dict(
        wallet="W028", account_scope="master/perp/all-dex",
        source_event_at="2026-11-01T03:59:00+00:00",
        first_known_at="2026-11-01T03:59:30+00:00",
        source_sha256=SHA, equity_usd=D("50000"),
        positions={BTC: D("2"), ETH: D("-5")},
        complete=True, capital_reconciled=True, continuous=True,
        receipts_prospective=True,
    )
    data.update(changes)
    return WalletBook(**data)


def test_e0_one_scalar_preserves_signed_long_short_and_delta():
    a = replicate(book(), decision_at=AT, pod_capital_usd=D("2000"))
    b = replicate(book(positions={BTC: D("3"), ETH: D("-1")}),
                  decision_at=AT, pod_capital_usd=D("2000"))
    assert a.scale == D("0.04")
    assert a.intended == {BTC: D(".08"), ETH: D("-.20")}
    assert b.intended[BTC] - a.intended[BTC] == D(".04")
    assert b.intended[ETH] - a.intended[ETH] == D(".16")


@pytest.mark.parametrize("changes", [
    {"complete": False}, {"continuous": False},
    {"capital_reconciled": False}, {"receipts_prospective": False},
    {"first_known_at": "2026-11-01T05:00:00+00:00"},
    {"equity_usd": D("0")}, {"positions": {"BTC": D("1")}},
])
def test_e0_fails_closed_without_whole_account_evidence(changes):
    with pytest.raises(ValueError):
        replicate(book(**changes), decision_at=AT, pod_capital_usd=D("2000"))


def test_e0_fidelity_attributes_risk_vs_execution_and_unapproved_hedge():
    a = replicate(book(), decision_at=AT, pod_capital_usd=D("2000"))
    result = fidelity(
        a, approved={BTC: D(".06")}, executed={BTC: D(".05")},
        marks={BTC: D("100000"), ETH: D("2000")},
    )
    assert result["intended_gross_usd"] == "8400.00"
    assert result["overlay_deviation_usd"] == "2400.00"
    assert result["execution_deviation_usd"] == "1000.00"
    assert result["tracking_deviation_usd"] == "3400.00"
    assert result["unapproved_source_legs"] == [ETH]
    assert result["economic_outcome_verified"] is False


def test_e0_fidelity_never_converts_flat_to_zero_error_score():
    a = replicate(book(positions={BTC: D("0")}), decision_at=AT,
                  pod_capital_usd=D("2000"))
    result = fidelity(a, approved={}, executed={}, marks={BTC: D("10")})
    assert result["tracking_deviation_fraction"] is None
    assert result["no_source_exposure"] is True


def test_e0_missing_market_mark_blocks():
    a = replicate(book(), decision_at=AT, pod_capital_usd=D("2000"))
    with pytest.raises(ValueError, match="E0_INCOMPLETE_FIDELITY_MARKS"):
        fidelity(a, approved=a.intended, executed=a.intended, marks={BTC: D("1")})
