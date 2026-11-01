"""The E0 full book must reach the existing PM04 engine without ghost targets."""

from dataclasses import replace
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_portfolio_e0 import PORTFOLIOS, prepare_portfolio
from copytrade_pm.pm_wallet_handoff import record_wallet_signal
from copytrade_pm.pm_wallet_replica import WalletBook
from copytrade_pm.pm03_account import digest
from test_pm04_shadow import BTC, BTC_KEY, at, engine, event, make_run, tick


def prepared(seconds, books):
    source = {
        pod: WalletBook(
            wallet=pod,
            account_scope="synthetic-complete-account",
            source_event_at=at(seconds),
            first_known_at=at(seconds),
            source_sha256=digest(
                {
                    "pod": pod,
                    "seconds": seconds,
                    "book": {k: str(v) for k, v in books.get(pod, {}).items()},
                }
            ),
            equity_usd=D("10000"),
            positions=books.get(pod, {}),
            complete=True,
            capital_reconciled=True,
            continuous=True,
            receipts_prospective=True,
        )
        for pod in PORTFOLIOS["A"]
    }
    return prepare_portfolio(
        "A", source_books=source, decision_at=at(seconds), pod_capital_usd=D("10000")
    )


def test_complete_book_partial_reduce_reverse_flat_and_replay(tmp_path):
    run = make_run(tmp_path)
    first = prepared(60, {"W028": {BTC_KEY: D("3")}, "W042": {BTC_KEY: D("-2")}})
    message = event("e0-first", "PM04_SIGNAL", engine(60), 60)
    record_wallet_signal(run, first, message)
    tick(run, "e0-due", 360)
    assert run.account.quantities[BTC] == D("1")
    reduced = prepared(420, {"W028": {BTC_KEY: D("1")}, "W042": {BTC_KEY: D("-2")}})
    record_wallet_signal(run, reduced, event("e0-reduce", "PM04_SIGNAL", engine(420), 420))
    assert run.account.pm04_state["pod_targets"]["W028"][BTC_KEY] == "1"
    flat = prepared(480, {})
    flat_event = event("e0-flat", "PM04_SIGNAL", engine(480), 480)
    result = record_wallet_signal(run, flat, flat_event)
    assert all(q == 0 for q in run.account.quantities.values())
    assert all(
        D(book.get(BTC_KEY, 0)) == 0 for book in run.account.pm04_state["pod_targets"].values()
    )
    assert record_wallet_signal(run, flat, flat_event) == result
    assert run.verify_checkpoint(run.checkpoint()) == result


def test_unsupported_hedge_rejects_entire_book_without_mutation(tmp_path):
    run = make_run(tmp_path)
    intent = prepared(
        60,
        {
            "W028": {
                BTC_KEY: D("3"),
                "hyperliquid/mainnet:perp:default/UNSUPPORTED": D("-1"),
            }
        },
    )
    prior = run.state()
    with pytest.raises(ValueError, match="UNSUPPORTED_INSTRUMENT"):
        record_wallet_signal(run, intent, event("unsupported", "PM04_SIGNAL", engine(60), 60))
    assert run.state() == prior


def test_changed_source_cannot_reuse_event_id(tmp_path):
    run = make_run(tmp_path)
    message = event("same", "PM04_SIGNAL", engine(60), 60)
    record_wallet_signal(run, prepared(60, {"W028": {BTC_KEY: D("1")}}), message)
    with pytest.raises(ValueError, match="CONFLICTING_E0"):
        record_wallet_signal(run, prepared(60, {"W028": {BTC_KEY: D("2")}}), message)


def test_compilation_preserves_independently_known_leverage_and_margin():
    intent = prepared(60, {"W028": {BTC_KEY: D("1")}})
    replica = intent.books["W028"]
    assert replica.source_leverage is None
    assert replica.source_margin_usd is None
    source = WalletBook(
        wallet="W028",
        account_scope="synthetic",
        source_event_at=at(60),
        first_known_at=at(60),
        source_sha256="a" * 64,
        equity_usd=D("10000"),
        positions={BTC_KEY: D("1")},
        complete=True,
        capital_reconciled=True,
        continuous=True,
        receipts_prospective=True,
        source_leverage={BTC_KEY: D("3")},
        source_margin_usd={BTC_KEY: D("100")},
    )
    from copytrade_pm.pm_wallet_replica import replicate

    known = replicate(source, decision_at=at(60), pod_capital_usd=D("2000"))
    assert known.source_leverage == {BTC_KEY: D("3")}
    assert known.source_margin_usd == {BTC_KEY: D("100")}
    assert known.scale == D(".2")
    with pytest.raises(ValueError, match="RISK_METADATA_SCOPE"):
        replicate(
            replace(source, source_leverage={"BTC": D("3")}),
            decision_at=at(60),
            pod_capital_usd=D("2000"),
        )
