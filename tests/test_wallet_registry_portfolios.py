"""Frozen portfolio selection contracts, first-known boundaries and DB upgrades."""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil

import pytest

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_portfolios as contracts
from test_wallet_registry import address, fixture

REPO = Path(__file__).resolve().parents[1]
T = "2026-11-04T04:00:00+00:00"


def frozen() -> dict:
    return contracts.read_decisions(REPO, reg.PORTFOLIOS, observed_at=T)


def test_pinned_portfolio_documents_and_explicit_paper_research_contract() -> None:
    result = frozen()
    assert set(result) == set(reg.PORTFOLIOS)
    assert result["P1"]["payload"]["aliases"] == ["S035-ENA", "S051-BTC", "S053-HYPE"]
    assert result["P1"]["payload"]["status"] == "PAPER_RESEARCH_PRIMARY"
    assert result["P14"]["payload"]["status"] == "PAPER_RESEARCH_CHALLENGER"
    assert len(result["P14"]["payload"]["aliases"]) == 5
    assert result["P16"]["payload"]["status"] == "RESEARCH_OPTIONAL_CONTROL"
    for p in result.values():
        assert len(p["definition_sha256"]) == 64
        assert p["payload"]["order_route"] == "NONE"
        assert p["payload"]["source_identity_proven"] is False
        assert p["payload"]["selection_known_at"] <= T


def test_refuse_late_known_selection_and_modified_document(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not yet known"):
        contracts.read_decisions(REPO, reg.PORTFOLIOS, observed_at="2026-11-02T00:00:00+00:00")
    for record in contracts.DECISIONS.values():
        p = tmp_path / record["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / record["path"], p)
    assert contracts.read_decisions(tmp_path, reg.PORTFOLIOS, observed_at=T) == frozen()
    altered = tmp_path / contracts.DECISIONS["P14"]["path"]
    altered.write_bytes(altered.read_bytes() + b"\nPotentially unreviewed change\n")
    with pytest.raises(ValueError, match="document drift"):
        contracts.read_decisions(tmp_path, reg.PORTFOLIOS, observed_at=T)


def test_sealed_portfolios_asof_and_preserve_legacy_generation(
    tmp_path: Path,
) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    original = reg.apply(db, snapshot, T)
    assert "manifest_sha256" in original
    pinned = frozen()
    observed = "2026-11-04T05:00:00+00:00"
    enriched = {
        **snapshot,
        "portfolio_contracts": pinned,
        "sources": {
            **snapshot["sources"],
            **{
                f"portfolio_doc:{pid}": item["payload"]["source_doc_sha256"]
                for pid, item in pinned.items()
            },
        },
    }
    reg.apply(db, enriched, observed)
    with closing(reg.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM portfolio_seals").fetchone()[0] == 7
        assert (
            con.execute(
                "SELECT COUNT(*) FROM portfolio_versions WHERE portfolio_id='P1'"
            ).fetchone()[0]
            == 2
        )
        p1 = contracts.select_asof(con, "P1", "2026-11-03T00:00:00+00:00")
        assert p1["version"] == 2
        assert p1["state"] == "PAPER_RESEARCH_PRIMARY"
        assert p1["definition_sha256"] == pinned["P1"]["definition_sha256"]
        assert p1["source_identity_proven"] is False
        p14 = contracts.select_asof(con, "P14", T)
        assert p14["state"] == "PAPER_RESEARCH_CHALLENGER"
        assert len(p14["members"]) == 5
        assert p14["order_route"] == "NONE"
        assert p14["paper_running"] == "UNKNOWN"
        before = contracts.select_asof(con, "P14", "2026-11-01T00:00:00+00:00")
        assert before["state"] == "UNKNOWN_AT_ASOF"
    assert reg.apply(db, enriched, "2026-11-05T00:00:00+00:00")["unchanged"] is True
    with closing(reg.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM portfolio_seals").fetchone()[0] == 7
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_assigned_source_wallets_cannot_infer_missing_s_or_whale_identities(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    snapshot["portfolio_contracts"] = frozen()
    snapshot["sources"].update(
        {
            f"portfolio_doc:{name}": item["payload"]["source_doc_sha256"]
            for name, item in snapshot["portfolio_contracts"].items()
        }
    )
    snapshot["frozen_aliases"] = {"W028": address(1), "W042": address(2), "W030": address(3)}
    db = tmp_path / "private" / "registry.sqlite"
    reg.apply(db, snapshot, T)
    with closing(reg.connect(db, False)) as con:
        a = contracts.select_asof(con, "A", T)
        p = contracts.select_asof(con, "P1", T)
        assert a["alias_resolution_complete"] is True
        assert p["alias_resolution_complete"] is False
        assert a["source_identity_proven"] is False
        assert p["source_identity_proven"] is False
        assert a["definition_sha256"] is not None
        assert p["definition_sha256"] is not None
        assert a["trading_authorized"] is False


def test_reject_injected_proposal_status_and_hash_without_mutating_database(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    pinned = frozen()
    snapshot["portfolio_contracts"] = pinned
    snapshot["sources"].update(
        {
            f"portfolio_doc:{name}": item["payload"]["source_doc_sha256"]
            for name, item in pinned.items()
        }
    )
    reg.apply(db, snapshot, T)
    original = reg.db_status(db)
    forged = deepcopy(snapshot)
    forged["portfolio_contracts"]["P14"]["payload"]["status"] = "TRADING_AUTHORIZED"
    with pytest.raises(ValueError, match="changed since staging"):
        reg.apply(db, forged, "2026-11-05T00:00:00+00:00")
    assert reg.db_status(db) == original


def test_missing_portfolio_seal_fails_closed_on_query(tmp_path: Path) -> None:
    db = tmp_path / "private" / "registry.sqlite"
    _, snapshot = fixture(tmp_path)
    reg.apply(db, snapshot, T)
    with closing(reg.connect(db, False)) as con:
        p = contracts.select_asof(con, "P1", datetime.now(timezone.utc).isoformat())
        assert p["state"] == "UNKNOWN_AT_ASOF"
        assert p["definition_sha256"] is None
