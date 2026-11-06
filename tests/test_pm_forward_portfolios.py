"""FP-09 blocked-yet-independent P1 and P14 portfolio admission."""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_catalog as catalog
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
from test_wallet_registry_catalog import AFTER, WHALE, _v2_snapshot


def test_two_frozen_10k_accounts_and_shared_source_fanout(tmp_path: Path) -> None:
    assert P1.members == ("S035", "S051", "S053")
    assert len(P14.members) == 5 and "S064" in P14.members
    assert "Whale_0x5f94" in P14.members
    assert P1.nominal_risk_per_member == "200"
    assert P14.nominal_risk_per_member == "120"
    coordinator = PaperPortfolioView(
        PaperCampaign(), registry_db=_fixture_registry(tmp_path / "registry.sqlite")
    )
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


def test_new_e6_e2_research_priorities_cannot_silently_register_as_legacy_fp09(
    tmp_path: Path,
) -> None:
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
    view = PaperPortfolioView(
        PaperCampaign(), registry_db=_fixture_registry(tmp_path / "registry.sqlite")
    )
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


def test_resealing_or_cross_portfolio_manifest_fails(tmp_path: Path) -> None:
    view = PaperPortfolioView(
        PaperCampaign(), registry_db=_fixture_registry(tmp_path / "registry.sqlite")
    )
    with pytest.raises(ValueError, match="PORTFOLIO_MANIFEST_SHA_MISMATCH"):
        view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P14.sha))
    view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P1.sha))
    with pytest.raises(ValueError, match="DUPLICATE_PORTFOLIO_RUN_ID"):
        view.register(P14, replace(manifest("p1", "other"), portfolio_sha=P14.sha))


@pytest.fixture(autouse=True)
def _synthetic_registry_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())


def _fixture_registry(db_path: Path) -> Path:
    db, snapshot = _v2_snapshot(db_path.parent)
    reg.apply(db, snapshot, AFTER)
    return db


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


@pytest.mark.parametrize("tamper", ["fixture_prefix", "member", "document_bytes"])
def test_sealed_portfolio_rejects_unverified_fixture_or_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    test_db = _fixture_registry(tmp_path / "registry.sqlite")
    with closing(sqlite3.connect(test_db)) as conn, conn:
        if tamper == "fixture_prefix":
            conn.execute(
                "UPDATE portfolio_seals SET definition_sha256 = 'sha_fixture_forged' "
                "WHERE portfolio_id = 'gemini.phase4/E6'"
            )
        elif tamper == "member":
            # Simulate damaged bytes after bypassing only this isolated fixture's
            # write guards; the independent read verifier must still reject it.
            triggers = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'trigger' AND tbl_name = 'portfolio_memberships'"
            ).fetchall()
            for (name,) in triggers:
                conn.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            conn.execute(
                "UPDATE portfolio_memberships SET member_alias = 'UNSEALED_MEMBER' "
                "WHERE portfolio_id = 'gemini.phase4/E6' AND member_alias = 'ACT04'"
            )
        else:
            source = Path(__file__).resolve().parents[1] / catalog.V2_FILE
            changed = tmp_path / "changed.json"
            changed.write_bytes(source.read_bytes() + b"\n")
            monkeypatch.setattr(catalog, "V2_FILE", str(changed))
    with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
        load_sealed_paper_portfolio("gemini.phase4/E6", test_db)
