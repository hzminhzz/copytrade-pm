"""Persistent market projections preserve native identity and transactional caches."""

from copy import deepcopy

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_ccxt_market import PersistentMarket, parse_ccxt_market
from copytrade_pm.pm_forward_public_trades import PersistentPublicMarket
from copytrade_pm.pm_forward_stream_journal import verify_streams
from test_pm_forward_ccxt_market import BTC, at, ccxt_market, orderbook
from test_pm_forward_ccxt_trades import trade
from test_pm_forward_public_trades import BUYER, SELLER, trade as raw_trade, known


def market(tmp_path):
    journal = PaperJournal(tmp_path / "journal")
    parsed = parse_ccxt_market(ccxt_market(), first_known_at=at(0), expected=BTC)
    capture = PersistentMarket(journal, parsed, scope_sha="a" * 64, max_cache=4)
    capture.begin("quote", at(1))
    capture.begin("trades", at(1))
    return capture, journal


def test_persistent_quotes_and_trade_cache_across_former_epoch(tmp_path):
    capture, journal = market(tmp_path)
    capture.quote(orderbook(2), at(3))
    initial = capture.trades([trade("a", 2)], at(3))
    assert initial["new_local_trade_count"] == 0
    old_epoch = capture.window.epoch
    capture.quote(orderbook(140), at(141))
    nxt = capture.trades([trade("a", 2), trade("b", 140)], at(141))
    assert nxt["new_local_trade_count"] == 1
    assert capture.window.epoch == old_epoch
    assert journal.market_quote_status(BTC.key)["cursor"] == 2
    assert journal.market_trade_status(BTC.key)["locally_observed_trade_count"] == 1
    audit = verify_streams(journal.path)
    assert len(audit["streams"]) == 2


def test_trade_state_not_advanced_before_commit_and_channel_fault_isolated(tmp_path, monkeypatch):
    capture, journal = market(tmp_path)
    capture.trades([trade("a", 2)], at(3))
    before = deepcopy(capture.window._seen)
    real = journal.append_market_trade_batch

    def fail(*args, **kwargs):
        raise OSError("injected unavailable storage")

    monkeypatch.setattr(journal, "append_market_trade_batch", fail)
    with pytest.raises(OSError):
        capture.trades([trade("a", 2), trade("b", 4)], at(5))
    assert capture.window._seen == before
    monkeypatch.setattr(journal, "append_market_trade_batch", real)
    assert capture.trades([trade("a", 2), trade("b", 4)], at(5))["new_local_trade_count"] == 1
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        capture.trades([trade("a", 2, price="999")], at(6))
    capture.gap("trades", at(6), "CACHE_CONFLICT")
    capture.quote(orderbook(7), at(8))
    assert journal.market_quote_status(BTC.key)["cursor"] == 1
    capture.begin("trades", at(9))
    assert capture.trades([trade("b", 4), trade("c", 9)], at(10))["new_local_trade_count"] == 0


def test_raw_observed_trade_missing_from_ccxt_cache_is_an_explicit_gap(tmp_path):
    capture, journal = market(tmp_path)
    capture.trades([trade("a", 2)], at(3))
    before = verify_streams(journal.path)
    missing = trade("missing", 4)
    with pytest.raises(ValueError, match="CACHE_DROPPED_OBSERVED_TRADE"):
        capture.trades(
            [trade("a", 2), trade("b", 5)],
            at(6),
            first_known_by_id={
                "missing@" + str(missing["timestamp"]): at(5),
            },
        )
    assert verify_streams(journal.path) == before


def test_public_baseline_dedupe_wrong_dex_and_restart(tmp_path):
    journal = PaperJournal(tmp_path / "public")
    feed = PersistentPublicMarket(
        journal, BTC, {BUYER: "wallet:17", SELLER: "wallet:18"}, scope_sha="b" * 64
    )
    feed.begin(known(1))
    first = raw_trade(1, 1)
    assert feed.observe([first], known(2))["new_receipts"] == 0
    event = raw_trade(2, 3)
    assert feed.observe([event], known(4))["new_receipts"] == 2
    assert feed.observe([event], known(5))["new_receipts"] == 0
    with pytest.raises(ValueError, match="COIN_IDENTITY"):
        feed.observe([{**raw_trade(3, 5), "coin": "xyz:BTC"}], known(6))
    before = journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)
    reopened = PersistentPublicMarket(
        journal, BTC, {BUYER: "wallet:17", SELLER: "wallet:18"}, scope_sha="b" * 64
    )
    reopened.begin(known(8))
    assert reopened.observe([event], known(9))["new_receipts"] == 0
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key) == before
    assert verify_streams(journal.path)["streams"]["public:" + BTC.key]["gap_count"] == 2
