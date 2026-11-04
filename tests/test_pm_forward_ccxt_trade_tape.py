"""Immutable prospective partial trade observations; never full executable capacity."""

from contextlib import closing
import sqlite3

import pytest

from copytrade_pm.pm_forward_ccxt_trades import TradeWindow
from copytrade_pm.pm_forward_journal import PaperJournal
from test_pm_forward_ccxt_trades import BTC, at, trade


def batches():
    window = TradeWindow(BTC, "BTC/USDC:USDC", max_cache=4)
    first = window.process([trade("a", 1)], first_known_at=at(2))
    second = window.process([trade("a", 1), trade("b", 3, amount="0.8")], first_known_at=at(4))
    return first, second


def test_partial_trades_replay_backup_and_idempotency(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    first, second = batches()
    assert journal.append_market_trade_batch(first)["cursor"] == 1
    assert journal.append_market_trade_batch(second)["cursor"] == 2
    assert journal.append_market_trade_batch(second)["status"] == (
        "DUPLICATE_PARTIAL_TRADE_OBSERVATION"
    )
    state = PaperJournal(journal.root).market_trade_status(BTC.key)
    assert state["cursor"] == 2
    assert state["stream_epochs"] == 1
    assert state["locally_observed_trade_count"] == 1
    assert state["executable_volume_base"] is None
    assert not state["trade_volume_complete"]
    journal.backup(tmp_path / "backup")
    assert PaperJournal(tmp_path / "backup").market_trade_status(BTC.key) == state


def test_trade_gap_epoch_change_requires_rebaseline(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    first, second = batches()
    with pytest.raises(ValueError, match="PAPER_CCXT_TRADE_EPOCH_NOT_BASELINED"):
        journal.append_market_trade_batch(second)
    journal.append_market_trade_batch(first)
    other = TradeWindow(BTC, "BTC/USDC:USDC")
    fresh = other.process([trade("c", 7)], first_known_at=at(8))
    assert journal.append_market_trade_batch(fresh)["cursor"] == 2
    assert journal.market_trade_status(BTC.key)["stream_epochs"] == 2


def test_trade_fake_executable_volume_and_corruption_fail_closed(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    first, second = batches()
    invalid = {**second, "executable_volume_base": "10"}
    with pytest.raises(ValueError, match="PAPER_CCXT_TRADE_EVIDENCE_UNTRUSTED"):
        journal.append_market_trade_batch(invalid)
    journal.append_market_trade_batch(first)
    journal.append_market_trade_batch(second)
    with closing(sqlite3.connect(journal.path)) as db:
        with db:
            db.execute(
                "UPDATE market_trade_batches SET payload=? WHERE instrument=? AND seq=2",
                ("{}", BTC.key),
            )
    with pytest.raises(ValueError, match="PAPER_CCXT_TRADE"):
        journal.market_trade_status(BTC.key)
    with pytest.raises(ValueError, match="PAPER_CCXT_TRADE"):
        journal.backup(tmp_path / "corrupt_copy")


def test_trade_receipt_must_keep_volume_sum_signed_identity(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    _, batch = batches()
    wrong = {**batch, "observed_volume_base": "999"}
    with pytest.raises(ValueError, match="PAPER_CCXT_TRADE_BATCH_INVALID"):
        journal.append_market_trade_batch(wrong)
