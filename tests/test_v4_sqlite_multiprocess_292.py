"""Adversarial multi-process SQLite, proof, checkpoint and crash tests for #292."""

from contextlib import closing
from datetime import timedelta
import multiprocessing as mp
import os
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm_forward_observed_paper import _read_source, _readonly
from copytrade_pm.pm_forward_stream_journal import verify_streams
from copytrade_pm.pm_v4_sqlite_recovery import (
    active_source_handles,
    backup_and_verify,
    checkpoint_verified_backup,
)
from test_pm_forward_persistent_source import T, account, shifted


def _pin_reader(path: str, ready, release) -> None:
    with closing(sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        db.execute("SELECT COUNT(*) FROM observer_stream_events").fetchone()
        ready.send(os.getpid())
        release.recv()
        db.execute("ROLLBACK")


def _crash_source(source, frame, seconds: int, code: int, *, after_commit: bool) -> None:
    original = source.progress.commit

    def fail(*args, **kwargs):
        if after_commit:
            original(*args, **kwargs)
        os._exit(code)

    source.progress.commit = fail
    source.observe(frame, (T + timedelta(seconds=seconds)).isoformat())
    os._exit(99)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process and leases")
def test_rogue_reader_prevents_recovery_checkpoint_but_not_writer(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    backup_dir = tmp_path / "restored-proof"
    verified = backup_and_verify(journal.path, backup_dir, quiescence_verified=True)
    before = journal.source_status("test")["cursor"]
    ctx = mp.get_context("fork")
    ready_parent, ready_child = ctx.Pipe()
    release_parent, release_child = ctx.Pipe()
    reader = ctx.Process(
        target=_pin_reader,
        args=(str(journal.path), ready_child, release_child),
    )
    reader.start()
    try:
        pid = ready_parent.recv()
        assert pid == reader.pid
        assert any(row["pid"] == pid for row in active_source_handles(journal.path))
        # Reader holds a WAL snapshot, but writer still advances and can
        # persist a subsequent, genuine position change.
        source.observe(shifted(1, "20"), (T + timedelta(seconds=1)).isoformat())
        assert journal.source_status("test")["cursor"] == before + 1
        with closing(sqlite3.connect(journal.path, timeout=0.1)) as db:
            busy, log, checked = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            assert log >= checked
        with pytest.raises(ValueError, match="ACTIVE_HANDLES"):
            checkpoint_verified_backup(
                journal.path,
                backup_dir,
                quiescence_verified=True,
                expected_head_sha=verified["stream_head_sha"],
            )
    finally:
        if reader.is_alive():
            release_parent.send(True)
        reader.join(timeout=5)
        if reader.is_alive():
            reader.terminate()
            reader.join(timeout=5)
    assert reader.exitcode == 0
    # Backup was taken before a new source receipt, so it cannot authorize
    # checkpoint after a changed head even when the rogue reader is gone.
    with pytest.raises(ValueError, match="LIVE_DB_CHANGED_SINCE_BACKUP"):
        checkpoint_verified_backup(
            journal.path,
            backup_dir,
            quiescence_verified=True,
            expected_head_sha=verified["stream_head_sha"],
        )


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process crashes")
@pytest.mark.parametrize("after_commit,code", [(False, 81), (True, 82)])
def test_crash_before_or_after_source_commit_fences_reentry(
    tmp_path,
    after_commit,
    code,
):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    old_head = source.progress.head["chain_sha"]
    candidate = shifted(1, "20")
    ctx = mp.get_context("fork")
    child = ctx.Process(
        target=_crash_source,
        args=(source, candidate, 1, code),
        kwargs={"after_commit": after_commit},
    )
    child.start()
    child.join(timeout=5)
    if child.is_alive():
        child.terminate()
        child.join(timeout=5)
    assert child.exitcode == code
    rows = journal.source_status("test")["cursor"]
    assert rows == (2 if after_commit else 1)
    with closing(_readonly(journal.path)) as db:
        receipt = _read_source(db, "test", rows)
        assert receipt is not None
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"
    # A new runtime must never mistake a pre-crash observation for an entry.
    restarted, _ = account_existing(journal)
    assert restarted.progress.head["chain_sha"] != old_head or not after_commit
    restarted.begin((T + timedelta(seconds=2)).isoformat(), reason="RESTART")
    baseline = restarted.observe(shifted(3, "20"), (T + timedelta(seconds=3)).isoformat())
    assert baseline["classification"] == "BASELINE"
    assert baseline["position_changes"] == {}
    assert baseline["signal_eligible"] is False


def account_existing(journal):
    # Reuse the same exact native selected scope, never a new DB.
    from copytrade_pm.pm_forward_source_stream import PersistentAccount
    from test_pm_e4_prospective import WALLET

    return PersistentAccount(
        journal=journal,
        alias="test",
        address=WALLET,
        dex_catalog=[None, {"name": "xyz"}],
        subaccounts=None,
        parent_alias="test",
        scope_sha="a" * 64,
    ), journal


def test_quiescent_verified_backup_permits_wal_only_checkpoint(tmp_path):
    source, journal = account(tmp_path)
    source.observe(shifted(0, "0"), T.isoformat())
    backup_dir = tmp_path / "source-backup"
    receipt = backup_and_verify(journal.path, backup_dir, quiescence_verified=True)
    result = checkpoint_verified_backup(
        journal.path,
        backup_dir,
        quiescence_verified=True,
        expected_head_sha=receipt["stream_head_sha"],
    )
    assert result["checkpoint"] == {"busy": 0, "log": 0, "checkpointed": 0}
    assert result["source_head_sha"] == receipt["stream_head_sha"]
    assert result["main_db_unpruned"] is True
