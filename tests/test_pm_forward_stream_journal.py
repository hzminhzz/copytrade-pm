"""Crash consistency of additive observer checkpoints, independent of finance."""

from contextlib import closing
from datetime import UTC, datetime
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_stream_journal import stream_event, verify_streams

T = "2026-10-29T12:00:00+00:00"


def receipt():
    return {
        "schema": "paper_first_known_source_v1",
        "source_id": "test",
        "source_event_at": T,
        "first_known_at": T,
        "captured_at": T,
    }


def event(cursor=0, kind="BASELINE"):
    return stream_event(
        stream_id="account:test",
        epoch="a" * 32,
        kind=kind,
        known_at=T,
        expected_cursor=cursor,
        checkpoint={"positions": {}},
        raw_sha=digest(receipt()),
    )


def test_atomic_receipt_checkpoint_reopen_and_replay(tmp_path):
    journal = PaperJournal(tmp_path / "new")
    payload, progress = receipt(), event()
    journal.append_source_receipt("test", None, "native-1", payload, stream_event=progress)
    before = verify_streams(journal.path)
    assert before["streams"]["account:test"]["cursor"] == 1
    assert before["streams"]["account:test"]["checkpoint"] == {"positions": {}}
    reopened = PaperJournal(journal.root)
    reopened.append_source_receipt("test", None, "native-1", payload, stream_event=progress)
    assert verify_streams(journal.path) == before
    with pytest.raises(ValueError, match="CONFLICTING_SOURCE"):
        reopened.append_source_receipt(
            "test", None, "native-1", {**payload, "extra": 1}, stream_event=progress
        )
    assert verify_streams(journal.path) == before
    assert reopened.source_status("test")["cursor"] == 1


def test_checkpoint_failure_rolls_back_legacy_receipt(tmp_path):
    journal = PaperJournal(tmp_path / "new")
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "CREATE TRIGGER injected_disk_failure BEFORE INSERT ON observer_stream_events "
            "BEGIN SELECT RAISE(ABORT, 'disk full injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="disk full"):
        journal.append_source_receipt("test", None, "n1", receipt(), stream_event=event())
    assert journal.source_status("test")["cursor"] == 0
    assert verify_streams(journal.path)["streams"] == {}
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute("DROP TRIGGER injected_disk_failure")
    journal.append_source_receipt("test", None, "n1", receipt(), stream_event=event())
    with pytest.raises(ValueError, match="STREAM_CURSOR_CONFLICT"):
        journal.append_source_receipt(
            "test", None, "n2", {**receipt(), "changed": True}, stream_event=event(0, "OBSERVATION")
        )
    assert journal.source_status("test")["cursor"] == 1


def test_tampered_head_and_payload_are_rejected(tmp_path):
    journal = PaperJournal(tmp_path / "new")
    journal.append_source_receipt("test", None, "n1", receipt(), stream_event=event())
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute("UPDATE observer_stream_heads SET chain_sha=?", ("f" * 64,))
        db.commit()
    with pytest.raises(ValueError, match="STREAM_HEAD_DIVERGENCE"):
        verify_streams(journal.path)
    with pytest.raises(ValueError, match="STREAM_HEAD_DIVERGENCE"):
        journal.append_stream_event(event(1, "TRANSPORT"))
    assert journal.source_status("test")["cursor"] == 1


@pytest.mark.parametrize("side,expected", [("before", 0), ("after", 1)])
def test_real_sigkill_on_both_sides_of_commit(tmp_path, side, expected):
    root = tmp_path / side
    PaperJournal(root)
    script = """
from contextlib import contextmanager
import os, signal, sys
from pathlib import Path
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_stream_journal import stream_event
class KilledJournal(PaperJournal):
    @contextmanager
    def _writer(self):
        with super()._writer() as connection:
            class Proxy:
                def __getattr__(self, key): return getattr(connection, key)
                def execute(self, sql, *args):
                    if sql == "COMMIT" and sys.argv[2] == "before":
                        os.kill(os.getpid(), signal.SIGKILL)
                    result = connection.execute(sql, *args)
                    if sql == "COMMIT" and sys.argv[2] == "after":
                        os.kill(os.getpid(), signal.SIGKILL)
                    return result
            yield Proxy()
j = KilledJournal(Path(sys.argv[1]))
t = "2026-10-29T12:00:00+00:00"
r = dict(schema="paper_first_known_source_v1", source_id="test",
         source_event_at=t, first_known_at=t, captured_at=t)
e = stream_event(stream_id="account:test", epoch="a"*32, kind="BASELINE",
                 known_at=t, expected_cursor=0, checkpoint={"positions": {}})
j.append_source_receipt("test", None, "n1", r, stream_event=e)
"""
    run = subprocess.run([sys.executable, "-c", script, str(root), side], check=False)
    assert run.returncode == -9
    journal = PaperJournal(root)
    assert journal.source_status("test")["cursor"] == expected
    result = verify_streams(journal.path)
    assert sum(row["cursor"] for row in result["streams"].values()) == expected
    assert result["integrity"] == "VERIFIED"


def test_checkpoint_causal_clock_and_private_writer(tmp_path):
    journal = PaperJournal(tmp_path / "new")
    with pytest.raises(ValueError, match="STREAM_CAUSAL_CLOCK"):
        stream_event(
            stream_id="account:test",
            epoch="a" * 32,
            kind="BASELINE",
            known_at=T,
            expected_cursor=0,
            checkpoint={},
            source_at="2026-10-29T12:00:01+00:00",
        )
    with journal._writer():
        with pytest.raises(ValueError, match="BUSY"):
            journal.append_stream_event(event())
    assert verify_streams(journal.path)["streams"] == {}
    assert os.stat(journal.path).st_mode & 0o077 == 0
    assert datetime.now(UTC).isoformat() > T
    assert json.dumps(receipt())  # Inputs remain serializable without special codecs.
