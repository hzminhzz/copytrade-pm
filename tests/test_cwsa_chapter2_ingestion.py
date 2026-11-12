"""CWSA Chapter 2: independent partial-wave, replay and consumer-safety tests."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_cwsa_six_paper import (
    PORTFOLIO_CONFIGS,
    Chapter2PaperSupervisor,
)
from copytrade_pm.pm_checkpoint_journal import CheckpointOutcome

REGISTRY = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
GRID = 300_000
BASE = 1_794_470_200_000
ALL = sorted({member for cfg in PORTFOLIO_CONFIGS.values() for member in cfg["members"]})


def make_source(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE cwsa_outcomes (stream TEXT NOT NULL, checkpoint_ms INTEGER NOT NULL, "
            "candidate_sha TEXT NOT NULL, outcome TEXT NOT NULL, PRIMARY KEY(stream,checkpoint_ms))"
        )


def add_source(path: Path, checkpoint: int, aliases: tuple[str, ...] | list[str], kind="BASELINE"):
    with closing(sqlite3.connect(path)) as db, db:
        for alias in aliases:
            stream = digest(["fixture-stream", alias])
            outcome = CheckpointOutcome(
                source_id=alias,
                scope_generation="a" * 64,
                policy_epoch="b" * 64,
                checkpoint_ms=checkpoint,
                outcome_id=digest(["cwsa_outcome_v3", stream, checkpoint]),
                kind=kind,
                economic_sha=None,
                signal_id=None,
                positions=(),
                sample=None,
                published_ms=checkpoint + 1000,
                reasons=(),
            )
            db.execute(
                "INSERT INTO cwsa_outcomes VALUES (?,?,?,?)",
                (stream, checkpoint, "c" * 64, outcome.model_dump_json()),
            )


def new_supervisor(tmp_path: Path) -> Chapter2PaperSupervisor:
    return Chapter2PaperSupervisor(
        state_root=tmp_path / "paper",
        source_db=tmp_path / "source.sqlite",
        registry_db=REGISTRY,
        publication_grace_override_ms=180_000,
    )


def test_healthy_portfolio_does_not_wait_for_unrelated_missing_wallets(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    a_members = PORTFOLIO_CONFIGS["A"]["members"]
    add_source(source, BASE, a_members)
    supervisor = new_supervisor(tmp_path)
    assert supervisor.poll_once(now_ms=BASE + 2000) == 1
    a = json.loads((tmp_path / "paper" / "A" / "status.json").read_text())
    assert a["coverage_complete"] is True
    assert a["source_checkpoint_cursor_ms"] == BASE
    b = json.loads((tmp_path / "paper" / "B" / "status.json").read_text())
    assert b["coverage_complete"] is False
    assert b["source_checkpoint_cursor_ms"] == 0
    assert b["source_wave_state"] == "WAITING_SOURCE_WAVE"
    assert b["financial_admission"] == "BLOCKED_EVIDENCE"
    add_source(source, BASE, sorted(set(ALL) - set(a_members)))
    assert supervisor.poll_once(now_ms=BASE + 4000) == 1
    assert all(ledger.last_checkpoint_ms == BASE for ledger in supervisor.wave_ledgers.values())
    assert supervisor.last_processed_checkpoint_ms == BASE
    assert supervisor.poll_once(now_ms=BASE + 5000) == 0


def test_crash_after_commit_before_status_publish_recovers_from_journal(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL)
    original = new_supervisor(tmp_path)
    assert original.poll_once(now_ms=BASE + 1000) == 1
    statuses = [tmp_path / "paper" / "cwsa_chapter2_status.json"]
    statuses.extend(
        tmp_path / "paper" / cfg["folder"] / "status.json" for cfg in PORTFOLIO_CONFIGS.values()
    )
    for path in statuses:
        path.unlink()
    recovered = new_supervisor(tmp_path)
    assert recovered.last_processed_checkpoint_ms == BASE
    for path in statuses:
        assert path.is_file(), f"missing recovered status: {path}"
    assert recovered.poll_once(now_ms=BASE + 1100) == 0
    for ledger in recovered.wave_ledgers.values():
        with closing(sqlite3.connect(ledger.journal.path)) as db:
            assert db.execute("SELECT count(*) FROM chapter2_wave_receipts").fetchone()[0] == 1


def test_partial_wave_waits_for_all_wallets_then_commits_once(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL[:1])
    supervisor = new_supervisor(tmp_path)
    assert supervisor.poll_once(now_ms=BASE + 2000) == 0
    assert supervisor.last_processed_checkpoint_ms == 0
    add_source(source, BASE, ALL[1:])
    assert supervisor.poll_once(now_ms=BASE + 2500) == 1
    status = json.loads((tmp_path / "paper" / "A" / "status.json").read_text())
    assert status["coverage_complete"] is True
    assert set(status["source_kinds"]) == set(PORTFOLIO_CONFIGS["A"]["members"])
    assert status["source_checkpoint_cursor_ms"] == BASE
    assert supervisor.poll_once(now_ms=BASE + 3000) == 0
    reopened = new_supervisor(tmp_path)
    assert reopened.last_processed_checkpoint_ms == BASE
    assert reopened.poll_once(now_ms=BASE + 3500) == 0
    with closing(sqlite3.connect(reopened.journals["A"].path)) as db, db:
        assert db.execute("SELECT count(*) FROM chapter2_wave_receipts").fetchone()[0] == 1


def test_missing_wallet_expires_to_explicit_gap_then_next_wave_progresses(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL[:1])
    supervisor = new_supervisor(tmp_path)
    assert supervisor.poll_once(now_ms=BASE + 180_000 + 1000) == 1
    first = json.loads((tmp_path / "paper" / "A" / "status.json").read_text())
    assert first["coverage_complete"] is False
    assert first["source_checkpoint_cursor_ms"] == BASE
    add_source(source, BASE, ALL[1:])
    assert supervisor.poll_once(now_ms=BASE + 181_000) == 0
    add_source(source, BASE + GRID, ALL, kind="UNCHANGED")
    assert supervisor.poll_once(now_ms=BASE + GRID + 1000) == 1
    current = json.loads((tmp_path / "paper" / "A" / "status.json").read_text())
    assert current["coverage_complete"] is True
    assert current["source_checkpoint_cursor_ms"] == BASE + GRID
    with closing(sqlite3.connect(supervisor.journals["A"].path)) as db, db:
        assert db.execute("SELECT COUNT(*) FROM chapter2_wave_receipts").fetchone()[0] == 2


def test_explicit_unavailable_is_not_complete_and_mandate_count_cannot_promote(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL, kind="UNAVAILABLE")
    supervisor = new_supervisor(tmp_path)
    assert supervisor.poll_once(now_ms=BASE + 3000) == 1
    data = json.loads((tmp_path / "paper" / "A" / "status.json").read_text())
    assert data["coverage_complete"] is False
    assert data["financial_admission"] == "BLOCKED_EVIDENCE"
    assert data["cursor"] == 0
    assert "UNAVAILABLE" in set(data["source_kinds"].values())


def test_conflicting_existing_wave_receipt_fails_closed(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL)
    supervisor = new_supervisor(tmp_path)
    assert supervisor.poll_once(now_ms=BASE + 5000) == 1
    with closing(sqlite3.connect(supervisor.journals["A"].path)) as db, db:
        db.execute(
            "UPDATE chapter2_wave_receipts SET receipt_sha=? WHERE checkpoint_ms=?",
            ("f" * 64, BASE),
        )
    with pytest.raises(ValueError, match="CHAPTER2_WAVE_RECEIPT"):
        new_supervisor(tmp_path)


def test_distinct_portfolios_preserve_independent_observation_cursors(tmp_path):
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL)
    supervisor = new_supervisor(tmp_path)
    assert supervisor.poll_once(now_ms=BASE + 1000) == 1
    with closing(sqlite3.connect(supervisor.journals["A"].path)) as db, db:
        db.execute("DELETE FROM chapter2_wave_receipts WHERE checkpoint_ms=?", (BASE,))
    reopened = new_supervisor(tmp_path)
    assert reopened.last_processed_checkpoint_ms == 0
    assert reopened.poll_once(now_ms=BASE + 2000) == 1
    for journal in reopened.journals.values():
        with closing(sqlite3.connect(journal.path)) as db, db:
            assert db.execute("SELECT count(*) FROM chapter2_wave_receipts").fetchone()[0] == 1
