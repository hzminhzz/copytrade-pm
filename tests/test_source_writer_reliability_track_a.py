"""Track A: independent reader interference and fail-closed source persistence."""

import asyncio
from contextlib import closing
import sqlite3

import pytest

from copytrade_pm.pm_forward_continuous_transport import SerialWriter
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_stream_journal import stream_event, verify_streams


T = "2026-11-09T00:00:00+00:00"


def _event(cursor: int, kind: str):
    return stream_event(
        stream_id="account:source",
        epoch="a" * 32,
        kind=kind,
        known_at=T,
        expected_cursor=cursor,
        checkpoint={"baseline_valid": kind == "BASELINE", "positions": {}},
    )


def test_serial_writer_records_actual_latency_and_queue_metrics():
    async def run():
        async with SerialWriter(max_pending=2) as writer:
            assert await writer.submit(lambda: "durable") == "durable"
            assert writer.write_count == 1
            assert writer.write_failures == 0
            assert writer.write_total_ms >= writer.write_max_ms >= 0
            assert writer.high_water == 1

    asyncio.run(run())


def test_pinned_read_snapshot_does_not_block_wal_receipt_commit(tmp_path):
    journal = PaperJournal(tmp_path / "source")
    with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as reader:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM observer_stream_events").fetchone() == (0,)
        journal.append_stream_event(_event(0, "GAP"))
        journal.append_stream_event(_event(1, "BASELINE"))
        # The original reader may legitimately remain on its old snapshot.
        assert reader.execute("SELECT count(*) FROM observer_stream_events").fetchone() == (0,)
        assert journal.path.stat().st_size > 0
    head = verify_streams(journal.path)["streams"]["account:source"]
    assert head["cursor"] == 2
    assert head["gap_count"] == 1
    assert head["baseline_count"] == 1


def test_writer_does_not_request_journal_mode_change_per_transaction(tmp_path, monkeypatch):
    journal = PaperJournal(tmp_path / "source")
    real_connect = sqlite3.connect
    statements = []

    class TracedConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            statements.append(sql)
            return self.connection.execute(sql, *args)

        def __getattr__(self, key):
            return getattr(self.connection, key)

    monkeypatch.setattr(
        sqlite3, "connect", lambda *args, **kwargs: TracedConnection(real_connect(*args, **kwargs))
    )
    # An existing WAL database must not renegotiate mode on restart either.
    reopened = PaperJournal(journal.root)
    reopened.append_stream_event(_event(0, "GAP"))
    assert not any("journal_mode=WAL" in sql for sql in statements)
    assert any(sql == "BEGIN IMMEDIATE" for sql in statements)
    assert any(sql == "COMMIT" for sql in statements)


def test_sqlite_busy_during_begin_never_replays_uncommitted_receipt(tmp_path):
    journal = PaperJournal(tmp_path / "source")
    with closing(sqlite3.connect(journal.path, timeout=0)) as competitor:
        competitor.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            journal.append_stream_event(_event(0, "GAP"))
        competitor.execute("ROLLBACK")
    assert verify_streams(journal.path)["streams"] == {}
    # A future valid observation uses a new persisted GAP, then baseline.
    journal.append_stream_event(_event(0, "GAP"))
    journal.append_stream_event(_event(1, "BASELINE"))
    assert verify_streams(journal.path)["streams"]["account:source"]["cursor"] == 2


def test_nontransient_open_error_is_not_retried_or_recast_as_busy(tmp_path, monkeypatch):
    journal = PaperJournal(tmp_path / "source")
    calls = []

    def failed_connect(*args, **kwargs):
        calls.append(1)
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(sqlite3, "connect", failed_connect)
    with pytest.raises(ValueError, match="PAPER_JOURNAL_SQLITE_PERMANENT"):
        journal.append_stream_event(_event(0, "GAP"))
    assert len(calls) == 1
