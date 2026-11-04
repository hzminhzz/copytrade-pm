"""P0 research-catalog integration: independently pinned V2 and PIT aliases."""

from __future__ import annotations

import csv
from contextlib import closing
from copy import deepcopy
from pathlib import Path

import pytest

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_catalog as cat
from copytrade_pm import wallet_registry_portfolios as contracts
from test_wallet_registry import address, fixture

REPO = Path(__file__).resolve().parents[1]
AFTER = "2026-11-05T00:00:00+00:00"
BEFORE = "2026-11-04T08:00:00+00:00"
WHALE = "0x5f94" + "0" * 36


def _private_file(path: Path) -> Path:
    records = {
        "ACT04": address(11),
        "W083": address(12),
        "W080": address(13),
        "CM-002": address(14),
        "HL Perps Whale": WHALE,
        "W016": address(16),
        "W100": address(17),
    }
    with path.open("w", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=["alias", "address"])
        out.writeheader()
        for alias, addr in records.items():
            out.writerow({"alias": alias, "address": addr})
    return path


def _v2_snapshot(tmp_path: Path, *, aliases: bool = True) -> tuple[Path, dict]:
    _, snap = fixture(tmp_path)
    v2 = cat.read_v2(REPO, observed_at=AFTER)
    old = contracts.read_decisions(REPO, reg.PORTFOLIOS, observed_at=AFTER)
    sources = {
        **snap["sources"],
        **{
            f"portfolio_doc:{name}": item["payload"]["source_doc_sha256"]
            for name, item in old.items()
        },
        "portfolio_doc:gemini_v2": v2["source_sha256"],
    }
    source_paths = {"portfolio_doc:gemini_v2": REPO / cat.V2_FILE}
    identities = {}
    if aliases:
        private = _private_file(tmp_path / "phase4-identity.csv")
        identities = cat.read_private_identities(private, v2)
        sources["phase4_private_aliases"] = reg.digest(private)
        source_paths["phase4_private_aliases"] = private
    snap.update(
        {
            "sources": sources,
            "source_paths": source_paths,
            "portfolio_contracts": old,
            "decision_repo": REPO,
            "catalog_v2": v2,
            "catalog_aliases": identities,
        }
    )
    return tmp_path / "private" / "inventory.sqlite", snap


def test_v2_public_source_is_pinned_and_has_no_order_authority(tmp_path: Path) -> None:
    v2 = cat.read_v2(REPO, observed_at=AFTER)
    assert set(v2["definitions"]) == {
        "gemini.phase4/E6",
        "gemini.phase4/E2",
        "gemini.phase4/E3",
        "gemini.phase5/B",
    }
    assert len(v2["definitions"]["gemini.phase4/E6"]["members"]) == 5
    assert all(d["payload"]["order_route"] == "NONE" for d in v2["definitions"].values())
    assert [x["priority"] for x in v2["selections"]] == [1, 2, 3, None, 4, 5]
    with pytest.raises(ValueError, match="not yet known"):
        cat.read_v2(REPO, observed_at=BEFORE)

    copy = tmp_path / cat.V2_FILE
    copy.parent.mkdir(parents=True)
    copy.write_bytes((REPO / cat.V2_FILE).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source drift"):
        cat.read_v2(tmp_path, observed_at=AFTER)


def test_new_portfolios_are_queryable_without_overwriting_legacy_versions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db, snap = _v2_snapshot(tmp_path)
    reg.apply(db, snap, AFTER)
    with closing(reg.connect(db, False)) as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            con.execute("SELECT COUNT(DISTINCT portfolio_id) FROM portfolio_seals").fetchone()[0]
            == 11
        )
        assert con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 7
        current = cat.list_selection(con, AFTER)
        assert current["selection_state"] == "OWNER_APPROVED_RESEARCH_ONLY"
        assert current["portfolios"][0]["portfolio_id"] == "gemini.phase4/E6"
        assert current["portfolios"][0]["alias_resolution_complete"] is True
        assert current["portfolios"][1]["portfolio_id"] == "gemini.phase4/E2"
        assert current["portfolios"][1]["alias_resolution_complete"] is True
        p1 = contracts.select_asof(con, "P1", AFTER)
        assert p1["state"] == "PAPER_RESEARCH_PRIMARY"
        assert p1["alias_resolution_complete"] is True
        assert p1["source_doc_sha256"] == contracts.DECISIONS["P1"]["sha256"]
        assert current["portfolios"][-1]["role"] == "ARCHIVED_PREVIOUS_FIVE_POD_CHALLENGER"
        assert cat.list_selection(con, BEFORE)["selection_state"] == "NOT_REGISTERED_AT_ASOF"
        assert (
            contracts.select_asof(con, "P1", "2026-11-03T00:00:00+00:00")[
                "alias_resolution_complete"
            ]
            is False
        )
        assert cat.resolve_portfolio(con, "E6", AFTER) == "gemini.phase4/E6"
        assert cat.resolve_portfolio(con, "q3/B", AFTER) == "B"
        assert cat.resolve_portfolio(con, "gemini.phase5/B", AFTER) == "gemini.phase5/B"
        with pytest.raises(ValueError, match="ambiguous portfolio alias"):
            cat.resolve_portfolio(con, "B", AFTER)
        assert cat.resolve_alias(con, "W083", AFTER) == cat.resolve_alias(con, "S053-HYPE", AFTER)
        assert cat.resolve_alias(con, "HL Perps Whale", AFTER) is None
        assert cat.resolve_alias(con, "W083", BEFORE) is None
    assert reg.cli(["--db", str(db), "portfolio", "E6", "--asof", AFTER]) == 0
    assert "gemini.phase4/E6" in capsys.readouterr().out
    assert reg.cli(["--db", str(db), "portfolio", "--current", "--asof", AFTER]) == 0
    assert '"selection_state": "OWNER_APPROVED_RESEARCH_ONLY"' in capsys.readouterr().out
    assert reg.cli(["--db", str(db), "wallet", "--alias", "W083", "--asof", AFTER]) == 0
    assert "gemini.phase4/E2" in capsys.readouterr().out
    assert reg.apply(db, snap, AFTER)["unchanged"] is True


def test_late_alias_import_preserves_frozen_p1_p14_membership_and_asof(tmp_path: Path) -> None:
    """V7 aliases are later first-known evidence, not a retroactive v2 source seal."""
    db, snapshot = _v2_snapshot(tmp_path)
    baseline = deepcopy(snapshot)
    baseline.pop("portfolio_contracts")
    baseline.pop("catalog_v2")
    baseline.pop("catalog_aliases")
    for key in ("portfolio_doc:gemini_v2", "phase4_private_aliases"):
        baseline["sources"].pop(key, None)
        baseline["source_paths"].pop(key, None)
    reg.apply(db, baseline, BEFORE)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, False)) as con:
        for name, size in (("P1", 3), ("P14", 5)):
            frozen = con.execute(
                "SELECT wallet_id FROM portfolio_memberships WHERE portfolio_id=? AND version=2",
                (name,),
            ).fetchall()
            assert len(frozen) == size
            assert all(row[0] is None for row in frozen)
            selected = contracts.select_asof(con, name, AFTER)
            assert selected["alias_resolution_complete"] is True
            assert selected["source_identity_proven"] is False
            assert contracts.select_asof(con, name, BEFORE)["alias_resolution_complete"] is False
    assert reg.apply(db, snapshot, AFTER)["unchanged"] is True
    with closing(reg.connect(db, False)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM portfolio_memberships WHERE portfolio_id IN ('P1','P14') "
                "AND version=2 AND wallet_id IS NOT NULL"
            ).fetchone()[0]
            == 0
        )


def test_already_retrofilled_membership_never_backdates_alias_first_known(tmp_path: Path) -> None:
    """Existing v7 mutations in a database cannot become retrospective PIT evidence."""
    db, snapshot = _v2_snapshot(tmp_path)
    baseline = deepcopy(snapshot)
    baseline.pop("portfolio_contracts")
    baseline.pop("catalog_v2")
    baseline.pop("catalog_aliases")
    for key in ("portfolio_doc:gemini_v2", "phase4_private_aliases"):
        baseline["sources"].pop(key, None)
        baseline["source_paths"].pop(key, None)
    reg.apply(db, baseline, BEFORE)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, True)) as con, con:
        for name in ("P1", "P14"):
            aliases = con.execute(
                "SELECT member_alias FROM portfolio_memberships WHERE portfolio_id=? AND version=2",
                (name,),
            ).fetchall()
            for (alias,) in aliases:
                ident = cat.resolve_alias(con, alias, AFTER)
                assert ident is not None
                # Simulate a database modified by the old v7 importer.
                con.execute(
                    "UPDATE portfolio_memberships SET wallet_id=? "
                    "WHERE portfolio_id=? AND version=2 AND member_alias=?",
                    (ident, name, alias),
                )
    with closing(reg.connect(db, False)) as con:
        for name in ("P1", "P14"):
            assert contracts.select_asof(con, name, BEFORE)["alias_resolution_complete"] is False
            current = contracts.select_asof(con, name, AFTER)
            assert current["alias_resolution_complete"] is True
            assert current["source_identity_proven"] is False
            assert current["trading_authorized"] is False


def test_missing_private_alias_evidence_is_explicit_unknown(tmp_path: Path) -> None:
    db, snap = _v2_snapshot(tmp_path, aliases=False)
    reg.apply(db, snap, AFTER)
    with closing(reg.connect(db, False)) as con:
        e6 = contracts.select_asof(con, "gemini.phase4/E6", AFTER)
        assert len(e6["members"]) == 5
        assert e6["alias_resolution_complete"] is False
        assert cat.resolve_alias(con, "W083", AFTER) is None
        assert cat.list_selection(con, AFTER)["portfolios"][0]["alias_resolution_complete"] is False


def test_alias_collision_is_rejected_without_rewriting_source(tmp_path: Path) -> None:
    db, snap = _v2_snapshot(tmp_path)
    bad = deepcopy(snap)
    bad["catalog_aliases"]["S053-HYPE"] = address(99)
    with pytest.raises(ValueError, match="identities changed"):
        reg.apply(db, bad, AFTER)
    assert not db.exists()

    reg.apply(db, snap, AFTER)
    with closing(reg.connect(db, True)) as con, con:
        con.execute(
            "INSERT INTO wallet_aliases VALUES(?,?,?,?)",
            ("tampered", "W083", 1, AFTER),
        )
    with closing(reg.connect(db, False)) as con:
        with pytest.raises(ValueError, match="ambiguous canonical wallet alias"):
            cat.resolve_alias(con, "W083", AFTER)


def test_modified_research_role_is_never_reported_as_approved(tmp_path: Path) -> None:
    db, snap = _v2_snapshot(tmp_path)
    reg.apply(db, snap, AFTER)
    with closing(reg.connect(db, True)) as con, con:
        con.execute(
            "UPDATE research_selections SET role='TRADING_AUTHORIZED' "
            "WHERE portfolio_id='gemini.phase4/E6'"
        )
    with closing(reg.connect(db, False)) as con:
        with pytest.raises(ValueError, match="immutable research selection history drift"):
            cat.list_selection(con, AFTER)
    with pytest.raises(ValueError, match="immutable research selection history drift"):
        reg.db_status(db)


def test_new_source_drift_does_not_promote_an_existing_registry(tmp_path: Path) -> None:
    db, snap = _v2_snapshot(tmp_path)
    reg.apply(db, snap, AFTER)
    before = reg.db_status(db)
    drift = deepcopy(snap)
    drift["sources"]["portfolio_doc:gemini_v2"] = "f" * 64
    with pytest.raises(ValueError, match="source changed"):
        reg.apply(db, drift, AFTER)
    assert reg.db_status(db) == before
