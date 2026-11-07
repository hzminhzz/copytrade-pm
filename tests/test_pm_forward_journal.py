"""Forward paper WAL crash/recovery, isolation, and tamper contracts."""

from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import fcntl
import os
import sqlite3
import threading

import pytest

from copytrade_pm.pm03_rules import propr_rulebook
from copytrade_pm.pm_forward_paper import PaperCampaign, PaperManifest
from copytrade_pm.pm_forward_journal import PaperJournal


T = "2026-11-04T04:00:00+00:00"
LATER = "2026-11-04T04:01:00+00:00"


def manifest(run: str, account: str) -> PaperManifest:
    return PaperManifest(
        run_id=run,
        account_id=account,
        portfolio_sha="a" * 64,
        market_manifest_sha="b" * 64,
        release_sha="c" * 64,
        policy_sha="d" * 64,
        selected_at=T,
        started_at=T,
        rulebook=propr_rulebook("classic_1step", "evaluation", Decimal("10000"), observed_at=T),
    )


def test_wal_restart_idempotency_and_run_isolation(tmp_path) -> None:
    store = PaperJournal(tmp_path / "paper")
    first = store.register(manifest("run_1", "acct_1"))
    store.register(manifest("run_2", "acct_2"))
    event = {"kind": "HALT", "event_at": LATER, "reason": "manual"}
    committed = store.append("run_1", "evt_1", event)
    assert committed["cursor"] == 1
    assert committed["account"]["risk"] == "HALT"
    assert committed["account"]["halt_reason"] == "manual"
    reopened = PaperJournal(tmp_path / "paper")
    assert reopened.restore("run_1") == committed
    assert reopened.append("run_1", "evt_1", event) == committed
    with pytest.raises(ValueError, match="CONFLICTING_PAPER_EVENT"):
        reopened.append("run_1", "evt_1", {**event, "reason": "different"})
    assert reopened.restore("run_1") == committed
    assert reopened.restore("run_2")["account"]["risk"] == "GREEN"
    assert first["account"]["cash"] == committed["account"]["cash"] == "10000"
    with pytest.raises(ValueError, match="CONFLICTING_PAPER_RUN_MANIFEST"):
        reopened.register(replace(manifest("run_1", "acct_1"), policy_sha="e" * 64))
    with pytest.raises(sqlite3.IntegrityError):
        reopened.register(manifest("run_3", "acct_2"))


def test_public_campaign_wal_integration(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    campaign = PaperCampaign(journal=journal)
    first = campaign.register(manifest("run_1", "acct_1"))
    assert first["cursor"] == 0
    updated = campaign.record_event(
        "run_1", "halt", {"kind": "HALT", "event_at": LATER, "reason": "test"}
    )
    assert updated["cursor"] == 1
    assert updated["account"]["risk"] == "HALT"
    assert PaperJournal(journal.root).restore("run_1")["account"] == updated["account"]


def test_refused_event_does_not_commit_and_late_event_refused(tmp_path) -> None:
    j = PaperJournal(tmp_path / "paper")
    j.register(manifest("run_1", "acct_1"))
    with pytest.raises(ValueError, match="PAPER_EVENT_NOT_SUPPORTED"):
        j.append("run_1", "bad", {"kind": "BROKER_ORDER", "event_at": LATER})
    assert j.restore("run_1")["cursor"] == 0
    j.append("run_1", "mark", {"kind": "MARK", "event_at": LATER, "state_known": False})
    with pytest.raises(ValueError, match="PAPER_EVENT_OUT_OF_ORDER"):
        j.append("run_1", "old", {"kind": "HALT", "event_at": T})
    assert j.restore("run_1")["cursor"] == 1


def test_verified_online_backup_restore_and_exclusive_destination(tmp_path) -> None:
    original = PaperJournal(tmp_path / "paper")
    original.register(manifest("run_1", "acct_1"))
    event = {"kind": "HALT", "event_at": LATER, "reason": "backup"}
    original.append("run_1", "halt", event)
    heads = original.backup(tmp_path / "backup")
    copied = PaperJournal(tmp_path / "backup")
    assert heads["run_1"] == original.restore("run_1")["journal_head_sha"]
    assert copied.restore("run_1") == original.restore("run_1")
    with pytest.raises(FileExistsError):
        original.backup(tmp_path / "backup")
    with pytest.raises(ValueError, match="PAPER_BACKUP_SELF_OVERWRITE"):
        original.backup(original.root)


def test_second_writer_refused_without_partial_effect(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    journal.register(manifest("run_1", "acct_1"))
    fd = os.open(journal.root / "paper-events.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="PAPER_JOURNAL_BUSY_OR_UNAVAILABLE"):
            journal.append("run_1", "blocked", {"kind": "HALT", "event_at": LATER})
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert journal.restore("run_1")["cursor"] == 0


def test_opt_in_public_source_writer_waits_before_any_transaction(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper", lease_wait_seconds=0.6)
    journal.register(manifest("run_1", "acct_1"))
    fd = os.open(journal.root / "paper-events.lock", os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    release = threading.Timer(0.1, fcntl.flock, args=(fd, fcntl.LOCK_UN))
    release.start()
    try:
        journal.append("run_1", "single", {"kind": "HALT", "event_at": LATER})
    finally:
        release.join(timeout=2)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert journal.restore("run_1")["cursor"] == 1
    assert journal.restore("run_1")["account"]["risk"] == "HALT"
    with pytest.raises(ValueError, match="PAPER_JOURNAL_LEASE_WAIT_INVALID"):
        PaperJournal(tmp_path / "invalid", lease_wait_seconds=3)


def test_opt_in_public_source_wait_expires_without_side_effect(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper", lease_wait_seconds=0.05)
    journal.register(manifest("run_1", "acct_1"))
    fd = os.open(journal.root / "paper-events.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="PAPER_JOURNAL_BUSY_OR_UNAVAILABLE"):
            journal.append("run_1", "denied", {"kind": "HALT", "event_at": LATER})
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert journal.restore("run_1")["cursor"] == 0


def test_50_account_isolation_and_reopen(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    for index in range(50):
        journal.register(manifest(f"run_{index}", f"acct_{index}"))
    for index in range(0, 50, 2):
        journal.append(f"run_{index}", "halt", {"kind": "HALT", "event_at": LATER})
    reopened = PaperJournal(journal.root)
    for index in range(50):
        state = reopened.restore(f"run_{index}")
        assert state["account"]["cash"] == "10000"
        assert state["cursor"] == (1 if index % 2 == 0 else 0)
        assert state["account"]["risk"] == ("HALT" if index % 2 == 0 else "GREEN")


def test_tampering_detected_and_dir_private(tmp_path) -> None:
    j = PaperJournal(tmp_path / "paper")
    j.register(manifest("run_1", "acct_1"))
    j.append("run_1", "halt", {"kind": "HALT", "event_at": LATER})
    with closing(sqlite3.connect(j.path)) as db:
        with db:
            db.execute("UPDATE runs SET cursor=100 WHERE run_id='run_1'")
    with pytest.raises(ValueError, match="PAPER_CHECKPOINT_DIVERGENCE"):
        PaperJournal(j.root).restore("run_1")
    assert j.path.stat().st_mode & 0o077 == 0
    assert j.root.stat().st_mode & 0o077 == 0
