"""FP-09 blocked-yet-independent P1 and P14 portfolio admission."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_paper import PaperCampaign
from copytrade_pm.pm_forward_portfolios import (
    P1,
    P14,
    FrozenPaperPortfolio,
    PaperPortfolioView,
    load_sealed_paper_portfolio,
)
from copytrade_pm.pm_forward_registry_identity import P1 as WR_P1
from copytrade_pm.pm_forward_registry_identity import P14 as WR_P14
from copytrade_pm.pm_forward_source_campaign import _ALIAS
from test_pm_forward_admission import _alter
from test_pm_forward_fill import _source_book
from test_pm_forward_journal import T, manifest


def test_two_frozen_10k_accounts_and_shared_source_fanout() -> None:
    assert P1.members == ("S035", "S051", "S053")
    assert len(P14.members) == 5 and "S064" in P14.members
    assert "Whale_0x5f94" in P14.members
    assert P1.nominal_risk_per_member == "200"
    assert P14.nominal_risk_per_member == "120"
    coordinator = PaperPortfolioView(PaperCampaign())
    coordinator.register(P1, replace(manifest("p1", "p1_account"), portfolio_sha=P1.sha))
    coordinator.register(P14, replace(manifest("p14", "p14_account"), portfolio_sha=P14.sha))
    for name in ("P1", "P14"):
        state = coordinator.status(name)
        assert state["account"]["cash"] == "10000"
        assert state["account"]["quantities"] == {}
        assert state["source_admission"] == "BLOCKED"
        assert state["order_route"] == "NONE"
    shared = admit_source_book(
        _source_book(), decision_at=T, fill_at=T, allow_synthetic_fixture=True
    )
    result = coordinator.observe("S035", shared)
    assert result == {"P1": "BLOCKED", "P14": "BLOCKED"}
    assert "S064" in coordinator.status("P14")["missing_members"]
    assert "S064" not in coordinator.status("P1")["missing_members"]
    broken = admit_source_book(
        _alter(_source_book(), source_equity=None),
        decision_at=T,
        fill_at=T,
        allow_synthetic_fixture=True,
    )
    coordinator.observe("S064", broken)
    assert "S064" in coordinator.status("P14")["rejected_members"]
    assert coordinator.status("P1")["rejected_members"] == {}
    assert coordinator.status("P1")["account"] == coordinator.campaign.status("p1")["account"]


def test_new_e6_e2_research_priorities_cannot_silently_register_as_legacy_fp09() -> None:
    v2 = Path(__file__).resolve().parents[1] / (
        "docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json"
    )
    assert sha256(v2.read_bytes()).hexdigest() == (
        "21f4e9406370fefcb0e38719c2a07bb57b68b073d70b3530034f7f5944c240fc"
    )
    study = json.loads(v2.read_text())
    assert study["scope"] == "NEW_FORWARD_PAPER_RESEARCH_ONLY"
    assert study["preservation"]["existing_FP09_P1_P14_trial_unchanged"] is True
    assert study["new_forward_paper_priority"][:2] == ["E6", "E2"]
    assert tuple(_ALIAS[alias] for alias in WR_P1) == P1.members
    assert tuple(_ALIAS[alias] for alias in WR_P14) == P14.members
    assert {entry["canonical_alias"] for entry in study["portfolios"]["P1"]["members"]} == set(
        WR_P1
    )
    assert {entry["canonical_alias"] for entry in study["portfolios"]["P14"]["members"]} == set(
        WR_P14
    )
    view = PaperPortfolioView(PaperCampaign())
    for name in ("E6", "E2"):
        candidate = FrozenPaperPortfolio(
            name,
            tuple(entry["canonical_alias"] for entry in study["portfolios"][name]["members"]),
        )
        with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
            view.register(
                candidate,
                replace(manifest(name, name + "_account"), portfolio_sha=candidate.sha),
            )
    rogue_baseline = FrozenPaperPortfolio("P1", ("S035", "S051", "ACT04"))
    with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
        view.register(
            rogue_baseline,
            replace(manifest("P1", "unapproved"), portfolio_sha=rogue_baseline.sha),
        )
    assert view.portfolios == {} and view.run_ids == {}


def test_resealing_or_cross_portfolio_manifest_fails() -> None:
    view = PaperPortfolioView(PaperCampaign())
    with pytest.raises(ValueError, match="PORTFOLIO_MANIFEST_SHA_MISMATCH"):
        view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P14.sha))
    view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P1.sha))
    with pytest.raises(ValueError, match="DUPLICATE_PORTFOLIO_RUN_ID"):
        view.register(P14, replace(manifest("p1", "other"), portfolio_sha=P14.sha))


def _fixture_registry(db_path: Path) -> Path:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE portfolio_versions (
            portfolio_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            source_doc TEXT NOT NULL,
            known_at TEXT NOT NULL,
            sizing_contract TEXT NOT NULL,
            PRIMARY KEY(portfolio_id, version)
        );
    """)
    conn.execute("""
        CREATE TABLE portfolio_seals (
            portfolio_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            definition_sha256 TEXT NOT NULL,
            doc_sha256 TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            selection_known_at TEXT NOT NULL,
            PRIMARY KEY(portfolio_id, version)
        );
    """)
    conn.execute("""
        INSERT INTO portfolio_versions VALUES
            ('gemini.phase4/E6', 1, 'RESEARCH_SELECTION_ONLY', 'docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json', '2026-11-04T09:06:33+00:00', 'GEMINI_REFERENCE_K_NOT_EXECUTABLE'),
            ('gemini.phase4/E2', 1, 'RESEARCH_SELECTION_ONLY', 'docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json', '2026-11-04T09:06:33+00:00', 'GEMINI_REFERENCE_K_NOT_EXECUTABLE')
    """)
    conn.execute("""
        CREATE TABLE portfolio_memberships (
            portfolio_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            member_alias TEXT NOT NULL,
            wallet_id INTEGER,
            PRIMARY KEY(portfolio_id, version, member_alias)
        );
    """)
    conn.execute(
        "INSERT INTO portfolio_seals VALUES ('gemini.phase4/E6', 1, 'sha_fixture_e6', 'doc_sha', 'rev', '2026-11-04T09:06:33+00:00'), ('gemini.phase4/E2', 1, 'sha_fixture_e2', 'doc_sha', 'rev', '2026-11-04T09:06:33+00:00')"
    )
    conn.execute("""
        INSERT INTO portfolio_memberships VALUES
            ('gemini.phase4/E6', 1, 'ACT04', 333),
            ('gemini.phase4/E6', 1, 'CM-002', 282),
            ('gemini.phase4/E6', 1, 'S051-BTC', 195),
            ('gemini.phase4/E6', 1, 'S053-HYPE', 37),
            ('gemini.phase4/E6', 1, 'Whale_0x5f94', 146),
            ('gemini.phase4/E2', 1, 'ACT04', 333),
            ('gemini.phase4/E2', 1, 'S051-BTC', 195),
            ('gemini.phase4/E2', 1, 'S053-HYPE', 37)
    """)
    conn.commit()
    conn.close()
    return db_path


def test_dynamic_sealed_portfolio_loading_with_isolated_fixture(tmp_path: Path) -> None:
    test_db = _fixture_registry(tmp_path / "test_reg.sqlite")
    e6 = load_sealed_paper_portfolio("gemini.phase4/E6", test_db)
    assert e6.name == "gemini.phase4/E6"
    assert e6.members == ("ACT04", "CM-002", "S051-BTC", "S053-HYPE", "Whale_0x5f94")
    assert e6.nominal_risk_per_member == "120"

    e2 = load_sealed_paper_portfolio("gemini.phase4/E2", test_db)
    assert e2.name == "gemini.phase4/E2"
    assert e2.members == ("ACT04", "S051-BTC", "S053-HYPE")
    assert e2.nominal_risk_per_member == "200"

    with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
        load_sealed_paper_portfolio("non_existent_portfolio", test_db)


def test_dynamic_view_registration_and_status_with_fixture(tmp_path: Path) -> None:
    test_db = _fixture_registry(tmp_path / "test_reg.sqlite")
    view = PaperPortfolioView(PaperCampaign(), registry_db=test_db)
    e6 = load_sealed_paper_portfolio("gemini.phase4/E6", test_db)
    e6_manifest = replace(manifest("e6_run", "e6_acct"), portfolio_sha=e6.sha)
    view.register(e6, e6_manifest)

    status = view.status("gemini.phase4/E6")
    assert status["portfolio_name"] == "gemini.phase4/E6"
    assert status["source_admission"] == "BLOCKED"
    assert "ACT04" in status["missing_members"]
    assert "CM-002" in status["missing_members"]


def test_tampered_sealed_portfolio_fails_closed(tmp_path: Path) -> None:
    test_db = _fixture_registry(tmp_path / "tampered_reg.sqlite")
    # Deliberately tamper with the membership of gemini.phase4/E6 in DB
    conn = sqlite3.connect(test_db)
    conn.execute(
        "UPDATE portfolio_seals SET definition_sha256 = 'stale_tampered_sha' WHERE portfolio_id = 'gemini.phase4/E6'"
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
        load_sealed_paper_portfolio("gemini.phase4/E6", test_db)
