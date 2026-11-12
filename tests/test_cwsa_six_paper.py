"""Tests for CWSA Chapter 2 six-portfolio paper campaign."""

from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3


from copytrade_pm.pm_cwsa_six_paper import (
    PORTFOLIO_CONFIGS,
    Chapter2PaperSupervisor,
    load_registry_seals,
)

REGISTRY_PATH = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
SOURCE_PATH = Path(
    "/home/quant/.local/share/copytrade/prospective/cwsa-5m-source-chapter2-20261112/paper-events.sqlite3"
)


def test_load_registry_seals():
    seals = load_registry_seals(REGISTRY_PATH)
    assert len(seals) == 6
    assert set(seals.keys()) == set(PORTFOLIO_CONFIGS.keys())
    for pid, s in seals.items():
        assert s["version"] == 2
        assert len(s["definition_sha256"]) == 64
        assert s["members"] == tuple(sorted(PORTFOLIO_CONFIGS[pid]["members"]))


def test_supervisor_initializes_six_clean_isolated_journals(tmp_path):
    state_root = tmp_path / "paper_root"
    supervisor = Chapter2PaperSupervisor(
        state_root=state_root,
        source_db=SOURCE_PATH,
        registry_db=REGISTRY_PATH,
    )
    assert len(supervisor.journals) == 6
    for pid, cfg in PORTFOLIO_CONFIGS.items():
        folder = cfg["folder"]
        j_dir = state_root / folder
        assert j_dir.is_dir()
        journal = supervisor.journals[pid]
        restored = journal.restore(cfg["folder"])
        acct = restored["account"]
        assert Decimal(str(acct["cash"])) == cfg["starting_balance"]
        assert not acct.get("quantities")
        assert not acct.get("fills")
        assert Decimal(str(acct.get("fees", "0"))) == Decimal("0")
        assert restored["cursor"] == 0


def test_supervisor_evaluates_checkpoint_wave(tmp_path):
    state_root = tmp_path / "paper_root"
    # Freeze the live, continuously progressing source as a consistent SQLite
    # snapshot. A new real checkpoint arriving during restart is not a replay.
    source_copy = tmp_path / "source_snapshot.sqlite3"
    with closing(sqlite3.connect(f"file:{SOURCE_PATH}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(source_copy)) as target:
            src.backup(target)
    supervisor = Chapter2PaperSupervisor(
        state_root=state_root,
        source_db=source_copy,
        registry_db=REGISTRY_PATH,
    )
    # Process checkpoints from actual source database
    processed = supervisor.poll_once()
    assert processed > 0
    assert supervisor.last_processed_checkpoint_ms >= 1794460200000

    # Verify status snapshot
    status_file = state_root / "cwsa_chapter2_status.json"
    assert status_file.is_file()

    # Verify each journal remained clean at initial cash with 0 positions
    for pid, cfg in PORTFOLIO_CONFIGS.items():
        journal = supervisor.journals[pid]
        restored = journal.restore(cfg["folder"])
        assert restored["cursor"] == 0
        acct = restored["account"]
        assert Decimal(str(acct["cash"])) == cfg["starting_balance"]
        assert not acct.get("quantities")
        assert not acct.get("fills")
        port_status = state_root / cfg["folder"] / "status.json"
        assert port_status.is_file()

    # Restart supervisor and verify clean recovery
    reopened = Chapter2PaperSupervisor(
        state_root=state_root,
        source_db=source_copy,
        registry_db=REGISTRY_PATH,
    )
    assert reopened.last_processed_checkpoint_ms == supervisor.last_processed_checkpoint_ms
    # Durable observation cursor prevents duplicate checkpoint effects on restart.
    assert reopened.poll_once() == 0
