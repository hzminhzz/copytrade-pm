"""Tests for CWSA Chapter 2 six-portfolio paper campaign."""

from decimal import Decimal


from copytrade_pm.pm_cwsa_paper import (
    PaperConsumer,
    load_selections,
)
from cwsa_fixture_registry import PORTFOLIO_CONFIGS

from cwsa_fixture_registry import make_registry
from test_cwsa_chapter2_ingestion import ALL, BASE, add_source, make_source


def test_load_selections(tmp_path, configs=PORTFOLIO_CONFIGS):
    seals = load_selections(make_registry(tmp_path), configs=PORTFOLIO_CONFIGS)
    assert len(seals) == 6
    assert set(seals.keys()) == set(PORTFOLIO_CONFIGS.keys())
    for pid, s in seals.items():
        # The roster book generation is the pin; the legacy seal version is gone.
        assert s["version"] == 1
        assert len(s["definition_sha256"]) == 64
        assert s["members"] == tuple(sorted(PORTFOLIO_CONFIGS[pid]["members"]))


def test_supervisor_initializes_six_clean_isolated_journals(tmp_path):
    state_root = tmp_path / "paper_root"
    source = tmp_path / "source.sqlite"
    make_source(source)
    supervisor = PaperConsumer(
        configs=PORTFOLIO_CONFIGS,
        run_label="cwsa_chapter2_20261112",
        state_root=state_root,
        source_db=source,
        roster_db=make_registry(tmp_path),
        publication_grace_override_ms=180_000,
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
    source = tmp_path / "source.sqlite"
    make_source(source)
    add_source(source, BASE, ALL)
    registry = make_registry(tmp_path)
    supervisor = PaperConsumer(
        configs=PORTFOLIO_CONFIGS,
        run_label="cwsa_chapter2_20261112",
        state_root=state_root,
        source_db=source,
        roster_db=registry,
        publication_grace_override_ms=180_000,
    )
    assert supervisor.poll_once(now_ms=BASE + 2_000) == 1
    assert supervisor.last_processed_checkpoint_ms == BASE

    # Verify status snapshot
    status_file = state_root / "status.json"
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
    reopened = PaperConsumer(
        configs=PORTFOLIO_CONFIGS,
        run_label="cwsa_chapter2_20261112",
        state_root=state_root,
        source_db=source,
        roster_db=registry,
        publication_grace_override_ms=180_000,
    )
    assert reopened.last_processed_checkpoint_ms == supervisor.last_processed_checkpoint_ms
    # Durable observation cursor prevents duplicate checkpoint effects on restart.
    assert reopened.poll_once(now_ms=BASE + 3_000) == 0
