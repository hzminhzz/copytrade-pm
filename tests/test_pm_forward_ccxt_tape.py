"""CCXT Pro public quote private tape: atomic append, replay, and tamper checks."""

from contextlib import closing
import sqlite3

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_journal import PaperJournal
from test_pm_forward_ccxt_market import BTC, at, ccxt_market, orderbook


def quotes():
    native = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    one = parse_ccxt_book(native, orderbook(seconds=2), first_known_at=at(3)).payload()
    two = parse_ccxt_book(
        native, orderbook(seconds=4, bid=101, ask=102), first_known_at=at(5)
    ).payload()
    return one, two


def test_live_market_capture_durable_replay_idempotent_and_backup(tmp_path):
    store = PaperJournal(tmp_path / "private")
    first, second = quotes()
    a = store.append_market_quote(first)
    assert a["cursor"] == 1
    assert a["quote_sha"] == digest(first)
    assert a["status"] == "RECORDED_L2_ONLY_CAPACITY_UNKNOWN"
    assert store.append_market_quote(first)["status"] == "DUPLICATE_MARKET_QUOTE"
    b = store.append_market_quote(second)
    assert b["cursor"] == 2 and b["journal_head_sha"] != a["journal_head_sha"]
    reopened = PaperJournal(store.root)
    report = reopened.market_quote_status(BTC.key)
    assert report["cursor"] == 2
    assert report["journal_head_sha"] == b["journal_head_sha"]
    assert not report["trade_volume_complete"]
    assert not report["paper_observed"]
    backup = tmp_path / "snapshot"
    store.backup(backup)
    assert PaperJournal(backup).market_quote_status(BTC.key) == report


def test_market_quote_tamper_clock_regression_and_replayed_book_fails(tmp_path):
    store = PaperJournal(tmp_path / "private")
    first, second = quotes()
    store.append_market_quote(first)
    native = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    older = parse_ccxt_book(
        native, orderbook(seconds=1, bid=99, ask=99.5), first_known_at=at(4)
    ).payload()
    with pytest.raises(ValueError, match="PAPER_MARKET_QUOTE_CLOCK_REGRESSION"):
        store.append_market_quote(older)
    duplicate_book = {**first, "first_known_at": at(4)}
    with pytest.raises(ValueError, match="PAPER_MARKET_QUOTE_REPLAYED_BOOK"):
        store.append_market_quote(duplicate_book)
    assert store.market_quote_status(BTC.key)["cursor"] == 1
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute(
            "UPDATE market_quote_receipts SET quote_id='forged' WHERE instrument=? AND seq=1",
            (BTC.key,),
        )
    with pytest.raises(ValueError, match="PAPER_MARKET_QUOTE_CHAIN_DIVERGENCE"):
        PaperJournal(store.root).market_quote_status(BTC.key)


def test_market_quote_head_tamper_blocks_append_and_backup(tmp_path):
    store = PaperJournal(tmp_path / "private")
    first, second = quotes()
    store.append_market_quote(first)
    with closing(sqlite3.connect(store.path)) as db:
        with db:
            db.execute(
                "UPDATE market_quote_heads SET chain_sha=? WHERE instrument=?",
                ("a" * 64, BTC.key),
            )
    with pytest.raises(ValueError, match="PAPER_MARKET_QUOTE_HEAD_DIVERGENCE"):
        store.append_market_quote(second)
    with pytest.raises(ValueError, match="PAPER_MARKET_QUOTE_HEAD_DIVERGENCE"):
        store.market_quote_status(BTC.key)
    with pytest.raises(ValueError, match="PAPER_MARKET_QUOTE_HEAD_DIVERGENCE"):
        store.backup(tmp_path / "corrupt_copy")


def test_market_quote_requires_real_book_provenance_not_forged_volume(tmp_path):
    store = PaperJournal(tmp_path / "private")
    first, _ = quotes()
    forged = {**first, "volume_status": "COMPLETE_1M"}
    with pytest.raises(ValueError, match="PAPER_CCXT_QUOTE_INVALID"):
        store.append_market_quote(forged)
    no_source = {**first, "source": "HISTORICAL_BACKFILL"}
    with pytest.raises(ValueError, match="PAPER_CCXT_QUOTE_INVALID"):
        store.append_market_quote(no_source)
    assert store.market_quote_status(BTC.key)["cursor"] == 0
