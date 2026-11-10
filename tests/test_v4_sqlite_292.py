"""Issue #292: unchanged-source economics and indexed proof safety."""

from contextlib import closing
from datetime import timedelta
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm.pm_forward_stream_journal import (
    backfill_verified_source_locators,
    verify_official_position_transition,
    verify_streams,
)
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import _read_source, _readonly
from copytrade_pm.pm_v4_evidence import evidence_path, read_wire
from copytrade_pm.pm_v4_selected_positions import official_accounts
from copytrade_pm.pm_v4_sqlite_recovery import backup_and_verify
from test_pm_forward_persistent_source import account, shifted, T
from test_pm_forward_observed_paper import at
from test_pm_vike_paper_integration import official_frame


def test_ten_thousand_valid_unchanged_frames_do_not_append_economic_evidence(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "20"), T.isoformat())
    committed_cursor = journal.source_status("test")["cursor"]
    committed_head = source.progress.head["chain_sha"]
    for index in range(1, 10001):
        result = source.observe(shifted(index, "20.0"), (T + timedelta(seconds=index)).isoformat())
        assert result["classification"] in ("UNCHANGED_STATE", "DUPLICATE")
    assert journal.source_status("test")["cursor"] == committed_cursor
    assert source.progress.head["chain_sha"] == committed_head
    assert source.checkpoint["dex_clocks"] != source.progress.checkpoint["dex_clocks"]
    assert (
        source.observe(shifted(10001, "21"), (T + timedelta(seconds=10001)).isoformat())[
            "classification"
        ]
        == "OBSERVED_STATE_CHANGE"
    )
    assert journal.source_status("test")["cursor"] == committed_cursor + 1
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"


def test_source_locator_coverage_and_index_are_transactional(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    source.observe(shifted(1, "20"), (T + timedelta(seconds=1)).isoformat())
    with closing(sqlite3.connect(journal.path)) as db:
        coverage = db.execute(
            "SELECT verified_through FROM observer_source_locator_coverage "
            "WHERE stream_id='account:test'"
        ).fetchone()
        locator = db.execute(
            "SELECT source_id,receipt_id,receipt_sha,stream_id,event_seq "
            "FROM observer_source_locators"
        ).fetchall()
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT e.seq FROM observer_source_locators l "
            "JOIN observer_stream_events e ON e.stream_id=l.stream_id "
            "AND e.seq=l.event_seq WHERE l.stream_id=? AND l.source_id=? "
            "AND l.receipt_id=? AND l.receipt_sha=?",
            ("account:test", *locator[-1][:3]),
        ).fetchall()
    assert coverage == (source.progress.head["cursor"],)
    assert len(locator) == 2
    assert any("INDEX" in str(row).upper() for row in plan)


def test_independent_backup_restore_preserves_original_v1_proof(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    source.observe(shifted(1, "20"), (T + timedelta(seconds=1)).isoformat())
    destination = tmp_path / "independent-restore"
    with pytest.raises(ValueError, match="QUIESCENCE_NOT_VERIFIED"):
        backup_and_verify(journal.path, destination, quiescence_verified=False)
    result = backup_and_verify(journal.path, destination, quiescence_verified=True)
    assert result["status"] == "RESTORED_VERIFIED_SOURCE_ONLY"
    assert result["stream_head_sha"] == verify_streams(journal.path)["head_sha"]
    assert result["financial_ledger_verified"] is False
    with pytest.raises(FileExistsError, match="DESTINATION_EXISTS"):
        backup_and_verify(journal.path, destination, quiescence_verified=True)


def test_wal_checkpoint_reports_progress_only_after_reader_quiescence(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    with closing(sqlite3.connect(journal.path)) as pin:
        pin.execute("BEGIN")
        pin.execute("SELECT COUNT(*) FROM observer_stream_events").fetchone()
        # A concurrent writer is free to append under WAL while the reader
        # holds a historical snapshot, but checkpoint cannot consume it all.
        source.observe(shifted(1, "20"), (T + timedelta(seconds=1)).isoformat())
        with closing(sqlite3.connect(journal.path, timeout=0.5)) as checkpoint:
            passive = checkpoint.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            assert len(passive) == 3
            assert passive[1] >= passive[2]
        pin.execute("ROLLBACK")
    with closing(sqlite3.connect(journal.path, timeout=0.5)) as checkpoint:
        busy, log, checkpointed = checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        assert (busy, log, checkpointed) == (0, 0, 0)
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"


def test_legacy_v1_unindexed_proof_backfill_preserves_heads(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    source.observe(shifted(1, "20"), (T + timedelta(seconds=1)).isoformat())
    before = verify_streams(journal.path)["head_sha"]
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute("DROP TABLE observer_source_locators")
        db.execute("DROP TABLE observer_source_locator_coverage")
        db.commit()
    with closing(_readonly(journal.path)) as db:
        receipt = _read_source(db, "test", 2)
        assert receipt is not None
        assert verify_official_position_transition(
            db,
            alias="test",
            receipt_id=receipt["receipt_id"],
            receipt_sha=receipt["sha"],
            receipt=receipt["receipt"],
        )
    with pytest.raises(ValueError, match="REQUIRES_QUIESCENCE"):
        backfill_verified_source_locators(journal.path)
    result = backfill_verified_source_locators(journal.path, quiescence_verified=True)
    assert result["original_stream_head_sha"] == before
    assert result["indexed_receipts"] == 2
    assert verify_streams(journal.path)["head_sha"] == before
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "DELETE FROM observer_source_locators WHERE source_id=? AND receipt_id=?",
            ("test", receipt["receipt_id"]),
        )
        db.commit()
    with closing(_readonly(journal.path)) as db:
        assert not verify_official_position_transition(
            db,
            alias="test",
            receipt_id=receipt["receipt_id"],
            receipt_sha=receipt["sha"],
            receipt=receipt["receipt"],
        )


def test_volatile_clocks_reject_conflict_and_gap_forces_new_baseline(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "20"), T.isoformat())
    source.observe(shifted(1, "20.0"), (T + timedelta(seconds=1)).isoformat())
    with pytest.raises(ValueError, match="SAME_CLOCK_CONFLICTING_POSITIONS"):
        source.observe(shifted(1, "21"), (T + timedelta(seconds=2)).isoformat())
    # The rejection establishes a durable GAP, rather than a phantom entry.
    assert not source.checkpoint["baseline_valid"]
    recovered = source.observe(shifted(3, "21"), (T + timedelta(seconds=4)).isoformat())
    assert recovered["classification"] == "BASELINE"
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"


def test_compact_v2_original_evidence_and_missing_sidecar_fail_closed(tmp_path):
    journal = PaperJournal(tmp_path / "v4")
    address = official_frame(1, 0)["data"]["user"]

    def info(_):
        catalog = [None]
        raw = json.dumps(catalog, sort_keys=True).encode()
        return catalog, raw, sha256(raw).hexdigest()

    source = official_accounts(journal, {"S035": address}, info=info)["S035"]
    source.begin(at(0))
    for seconds, quantity in ((1, 0), (12, 20)):
        frame = official_frame(seconds, quantity)
        raw = json.dumps(frame, separators=(",", ":"))
        result = source.observe(frame, at(seconds + 1), raw_text=raw)
        assert result["classification"] in ("BASELINE", "OBSERVED_STATE_CHANGE")
    with closing(_readonly(journal.path)) as db:
        latest = _read_source(db, "S035", 2)
        assert latest is not None
        assert verify_official_position_transition(
            db,
            alias="S035",
            receipt_id=latest["receipt_id"],
            receipt_sha=latest["sha"],
            receipt=latest["receipt"],
            require_current_positions=True,
        )
        raw_event = db.execute(
            "SELECT payload FROM observer_stream_events WHERE stream_id=? ORDER BY seq DESC LIMIT 1",
            ("account:S035",),
        ).fetchone()[0]
    event = json.loads(raw_event)
    assert event["schema"] == "paper_observer_stream_event_v2"
    assert "native_wire" not in event["details"]
    assert "native_frame" not in event["details"]
    sha = event["raw_sha"]
    assert json.loads(read_wire(journal.path, sha))["channel"] == "allDexsClearinghouseState"
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"
    evidence_path(journal.path, sha).unlink()
    with closing(_readonly(journal.path)) as db:
        assert not verify_official_position_transition(
            db,
            alias="S035",
            receipt_id=latest["receipt_id"],
            receipt_sha=latest["sha"],
            receipt=latest["receipt"],
        )
    with pytest.raises(ValueError, match="SIDECAR_MISSING"):
        verify_streams(journal.path)
    evidence_path(journal.path, sha).write_bytes(b"not-a-valid-compressed-source")
    with pytest.raises(ValueError, match="SIDECAR_CORRUPT"):
        verify_streams(journal.path)
