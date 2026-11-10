"""V4 startup checks only current immutable heads; full history remains offline."""

from contextlib import closing
from datetime import timedelta
import sqlite3

import pytest

from copytrade_pm.pm_forward_stream_journal import (
    verify_stream_heads_fast,
    verify_streams,
)
from test_pm_forward_persistent_source import T, account, shifted


def _source(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    source.observe(shifted(1, "20"), (T + timedelta(seconds=1)).isoformat())
    return source, journal


def test_startup_heads_accept_valid_v1_and_admit_no_trade(tmp_path):
    _, journal = _source(tmp_path)
    quick = verify_stream_heads_fast(journal.path)
    assert quick["status"] == "TAILS_VERIFIED_HISTORICAL_AUDIT_PENDING"
    assert quick["complete_historical_integrity_verified"] is False
    assert quick["stream_count"] == 1
    assert quick["paper_admitted"] is False
    assert quick["order_route"] == "NONE"
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"


def test_startup_fails_on_corrupt_tail_stream_chain(tmp_path):
    _, journal = _source(tmp_path)
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "UPDATE observer_stream_events SET chain_sha=? "
            "WHERE stream_id=? AND seq=(SELECT cursor FROM observer_stream_heads WHERE stream_id=?)",
            ("f" * 64, "account:test", "account:test"),
        )
        db.commit()
    with pytest.raises(ValueError, match="STREAM_HEAD_DIVERGENCE"):
        verify_stream_heads_fast(journal.path)


def test_startup_fails_on_tampered_tail_source_receipt(tmp_path):
    _, journal = _source(tmp_path)
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "UPDATE source_receipts SET receipt_sha=? WHERE source_id=? AND seq=2",
            ("f" * 64, "test"),
        )
        db.commit()
    with pytest.raises(ValueError, match="STREAM_RECEIPT_DIVERGENCE"):
        verify_stream_heads_fast(journal.path)


def test_startup_fails_on_missing_immediate_predecessor(tmp_path):
    _, journal = _source(tmp_path)
    with closing(sqlite3.connect(journal.path)) as db:
        cursor = db.execute(
            "SELECT cursor FROM observer_stream_heads WHERE stream_id=?",
            ("account:test",),
        ).fetchone()[0]
        db.execute(
            "DELETE FROM observer_stream_events WHERE stream_id=? AND seq=?",
            ("account:test", cursor - 1),
        )
        db.commit()
    with pytest.raises(ValueError, match="STREAM_TAIL_PREDECESSOR_DIVERGENCE"):
        verify_stream_heads_fast(journal.path)


def test_history_corruption_is_detected_by_full_offline_verifier_not_fast_check(tmp_path):
    _, journal = _source(tmp_path)
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "UPDATE observer_stream_events SET event_sha=? WHERE stream_id=? AND seq=1",
            ("f" * 64, "account:test"),
        )
        db.commit()
    # This is not a full audit and must never claim it is.
    assert verify_stream_heads_fast(journal.path)["complete_historical_integrity_verified"] is False
    with pytest.raises(ValueError, match="STREAM_CHAIN_DIVERGENCE"):
        verify_streams(journal.path)
