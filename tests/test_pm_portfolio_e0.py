from dataclasses import replace
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_portfolio_e0 import PORTFOLIOS, assess_portfolio, prepare_portfolio
from copytrade_pm.pm_wallet_replica import WalletBook

BTC = "hyperliquid/mainnet:perp:default/BTC"
HEDGE = "hyperliquid/mainnet:perp:xyz/CL"
AT = "2026-11-01T06:30:00+00:00"


def sources(name):
    return {
        pod: WalletBook(
            wallet=pod, account_scope="master/all-perp-dex",
            source_event_at="2026-11-01T06:29:00+00:00",
            first_known_at="2026-11-01T06:29:10+00:00",
            source_sha256="a" * 64, equity_usd=D("50000"),
            positions={BTC: D("2"), HEDGE: D("-1")},
            complete=True, capital_reconciled=True, continuous=True,
            receipts_prospective=True,
        )
        for pod in PORTFOLIOS[name]
    }


@pytest.mark.parametrize("name", ("A", "B", "C"))
def test_all_portfolios_replicate_all_legs_without_episodic_sizing(name):
    p = prepare_portfolio(name, source_books=sources(name), decision_at=AT)
    assert p.status == "SOURCE_INTENT_READY_NOT_AUTHORIZED"
    assert len(p.books) == 3
    for pod in PORTFOLIOS[name]:
        assert p.books[pod].intended == {BTC: D(".08"), HEDGE: D("-.04")}


@pytest.mark.parametrize("name", ("A", "B", "C"))
def test_any_missing_complete_wallet_book_blocks_entire_portfolio(name):
    books = sources(name)
    pod = PORTFOLIOS[name][1]
    books[pod] = replace(books[pod], capital_reconciled=False)
    p = prepare_portfolio(name, source_books=books, decision_at=AT)
    assert p.status == "BLOCKED_EVIDENCE"
    assert not p.books
    assert p.blocked[pod] == "E0_INCOMPLETE_SOURCE_ACCOUNT"


@pytest.mark.parametrize("name", ("A", "B", "C"))
def test_partial_or_hindsight_roster_never_trades(name):
    books = sources(name)
    books.pop(PORTFOLIOS[name][0])
    with pytest.raises(ValueError, match="ROSTER_MISMATCH"):
        prepare_portfolio(name, source_books=books, decision_at=AT)


def test_fidelity_is_per_pod_not_hypothetical_pnl():
    p = prepare_portfolio("A", source_books=sources("A"), decision_at=AT)
    approved = {k: dict(v.intended) for k, v in p.books.items()}
    executed = {k: dict(v.intended) for k, v in p.books.items()}
    result = assess_portfolio(
        p, risk_approved=approved, executed=executed,
        marks={BTC: D("100000"), HEDGE: D("50")},
    )
    assert set(result["pods"]) == set(PORTFOLIOS["A"])
    assert result["realized_follower_pnl_verified"] is False
    assert result["authorized"] is False
