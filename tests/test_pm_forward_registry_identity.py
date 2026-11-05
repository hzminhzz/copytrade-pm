"""Read-only registry identity resolution without promoting historical aliases."""

from contextlib import closing
import json
import re
import sqlite3

import pytest

from copytrade_pm.pm_forward_registry_identity import (
    P1,
    P14,
    audit_frozen_member_resolution,
    preview_prospective_reseal,
)


def prepare(tmp_path, *, resolved=False, late_known=False):
    primary = tmp_path / "wallet_fills_90d"
    secondary = tmp_path / "nansen_smart_money_fills_90d"
    primary.mkdir()
    secondary.mkdir()
    db = tmp_path / "registry.sqlite"
    addresses = {}
    for index, alias in enumerate(P14):
        addr = f"0x{index + 1:040x}"
        if alias == "Whale_0x5f94":
            addr = "0x5f94a519" + ("0" * 32)
            filename = "HL Perps Whale_0x5f94a519.json"
            folder = secondary
        else:
            filename = alias + "_" + addr + ".json"
            folder = primary
        (folder / filename).write_text(json.dumps({"address": addr, "fills": []}))
        addresses[alias] = addr
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(
                "CREATE TABLE portfolio_memberships("
                "portfolio_id TEXT,version INTEGER,member_alias TEXT,wallet_id INTEGER)"
            )
            conn.execute(
                "CREATE TABLE portfolio_seals("
                "portfolio_id TEXT,version INTEGER,definition_sha256 TEXT,"
                "doc_sha256 TEXT,selection_known_at TEXT)"
            )
            conn.execute("CREATE TABLE wallets(wallet_id INTEGER,venue TEXT,address TEXT)")
            conn.execute(
                "CREATE TABLE wallet_aliases(namespace TEXT,alias TEXT,"
                "wallet_id INTEGER,known_at TEXT)"
            )
            for i, alias in enumerate(P14, 1):
                conn.execute(
                    "INSERT INTO wallets VALUES (?,?,?)", (i, "hyperliquid", addresses[alias])
                )
            if resolved:
                for i, alias in enumerate(P14, 1):
                    conn.execute(
                        "INSERT INTO wallet_aliases VALUES (?,?,?,?)",
                        (
                            "research_v2",
                            alias,
                            i,
                            "2026-11-05T04:00:00+00:00"
                            if late_known
                            else "2026-11-04T03:00:00+00:00",
                        ),
                    )
            for portfolio, members in (("P1", P1), ("P14", P14)):
                conn.execute(
                    "INSERT INTO portfolio_seals VALUES (?,?,?,?,?)",
                    (portfolio, 2, "a" * 64, "b" * 64, "2026-11-04T04:00:00+00:00"),
                )
                for alias in members:
                    member_id = P14.index(alias) + 1 if resolved else None
                    conn.execute(
                        "INSERT INTO portfolio_memberships VALUES (?,?,?,?)",
                        (portfolio, 2, alias, member_id),
                    )
    return db, primary, secondary


def audit(db, primary, secondary, portfolio):
    return audit_frozen_member_resolution(
        registry_db=db,
        primary_dir=primary,
        secondary_dir=secondary,
        portfolio_id=portfolio,
    )


def test_registry_unresolved_remains_blocked_even_with_all_matching_local_files(tmp_path):
    db, primary, secondary = prepare(tmp_path)
    before = db.read_bytes()
    p1 = audit(db, primary, secondary, "P1")
    p14 = audit(db, primary, secondary, "P14")
    assert db.read_bytes() == before
    assert p1["member_count"] == 3
    assert p14["member_count"] == 5
    assert len(p1["unresolved_aliases"]) == 3
    assert len(p14["unresolved_aliases"]) == 5
    assert p1["status"] == p14["status"] == "BLOCKED"
    assert all(row["matched_registry_wallet"] for row in p14["members"])
    assert all(not row["frozen_wallet_id_resolved"] for row in p14["members"])
    assert all(row["historical_locator_not_first_known_admission"] for row in p14["members"])
    assert not p14["registry_mutated"]
    assert not p14["paper_admitted"]
    assert re.search(r"0x[0-9a-f]{40}", json.dumps(p14)) is None


def test_readonly_fully_resolved_identity_still_does_not_admit_trading(tmp_path):
    db, primary, secondary = prepare(tmp_path, resolved=True)
    p14 = audit(db, primary, secondary, "P14")
    assert p14["status"] == "PIT_IDENTITY_RESOLVED_ONLY"
    assert not p14["source_wallet_equity_attested"]
    assert not p14["paper_admitted"]
    assert p14["unresolved_aliases"] == []


def test_retroactive_v7_alias_backfill_must_not_reseal_historical_membership(tmp_path):
    db, primary, secondary = prepare(tmp_path, resolved=True, late_known=True)
    original = db.read_bytes()
    report = audit(db, primary, secondary, "P14")
    assert db.read_bytes() == original
    assert report["status"] == "BLOCKED"
    assert report["member_count"] == 5
    assert len(report["unresolved_aliases"]) == 5
    assert len(report["post_seal_binding_aliases"]) == 5
    assert all(member["status"] == "BLOCKED_POST_SEAL_BINDING" for member in report["members"])
    assert report["source_wallet_equity_attested"] is False
    assert report["paper_admitted"] is False


def test_new_prospective_preflight_keeps_historical_seals_and_emits_unsigned_research_only(
    tmp_path,
):
    db, primary, secondary = prepare(tmp_path, resolved=True, late_known=True)
    before = db.read_bytes()
    earlier = preview_prospective_reseal(
        registry_db=db,
        primary_dir=primary,
        secondary_dir=secondary,
        portfolio_id="P14",
        as_of="2026-11-04T12:00:00+00:00",
    )
    assert earlier["status"] == "BLOCKED_IDENTITY_INCOMPLETE"
    assert earlier["unsigned_candidate"] is None
    assert not earlier["identity_asof_complete"]
    assert len(earlier["original_aliases_post_seal"]) == 5

    prospective = preview_prospective_reseal(
        registry_db=db,
        primary_dir=primary,
        secondary_dir=secondary,
        portfolio_id="P14",
    )
    assert prospective["status"] == "SIGNER_REVIEW_REQUIRED"
    assert prospective["identity_asof_complete"] is True
    assert len(prospective["members"]) == 5
    assert prospective["unsigned_candidate"]["schema"] == "copytrade_signed_research_selection_v1"
    assert prospective["unsigned_candidate"]["trading_authorized"] is False
    assert set(prospective["unsigned_candidate"]["definitions"]) == {
        "paper.prospective/P14-" + prospective["as_of"][:10].replace("-", "")
    }
    assert all(row["alias_known_by_asof"] for row in prospective["members"])
    assert not prospective["signed_proof_provided"]
    assert not prospective["operator_approved_new_selection"]
    assert not prospective["paper_admitted"]
    assert not prospective["registry_mutated"]
    assert prospective["order_route"] == "NONE"
    assert db.read_bytes() == before
    assert not re.search(r"0x[0-9a-f]{40}", json.dumps(prospective))
    assert audit(db, primary, secondary, "P14")["status"] == "BLOCKED"


def test_prospective_identity_conflict_and_cross_alias_duplicate_refused(tmp_path):
    db, primary, secondary = prepare(tmp_path, resolved=True, late_known=True)
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(
                "INSERT INTO wallet_aliases VALUES (?,?,?,?)",
                ("other", "S035-ENA", 2, "2026-11-05T05:00:00+00:00"),
            )
    with pytest.raises(ValueError, match="PROSPECTIVE_ALIAS_IDENTITY_CONFLICT"):
        preview_prospective_reseal(
            registry_db=db,
            primary_dir=primary,
            secondary_dir=secondary,
            portfolio_id="P1",
        )
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute("DELETE FROM wallet_aliases WHERE namespace='other'")
            conn.execute("UPDATE wallet_aliases SET wallet_id=1 WHERE alias='S051-BTC'")
    with pytest.raises(ValueError, match="PROSPECTIVE_ALIAS_ADDRESS_OR_DUPLICATE_WALLET"):
        preview_prospective_reseal(
            registry_db=db,
            primary_dir=primary,
            secondary_dir=secondary,
            portfolio_id="P1",
        )


def test_prospective_refuses_future_or_naive_clocks(tmp_path):
    from datetime import UTC, datetime, timedelta

    db, primary, secondary = prepare(tmp_path, resolved=True, late_known=True)
    common = dict(registry_db=db, primary_dir=primary, secondary_dir=secondary, portfolio_id="P1")
    with pytest.raises(ValueError, match="PROSPECTIVE_PREVIEW_CLOCK_INVALID"):
        preview_prospective_reseal(**common, as_of="2026-11-05T05:00:00")
    with pytest.raises(ValueError, match="PROSPECTIVE_PREVIEW_CLOCK_INVALID"):
        preview_prospective_reseal(
            **common, as_of=(datetime.now(UTC) + timedelta(hours=1)).isoformat()
        )


def test_prospective_preview_normalizes_date_to_utc_and_enforces_original_known_at(tmp_path):
    db, primary, secondary = prepare(tmp_path, resolved=True)
    common = dict(registry_db=db, primary_dir=primary, secondary_dir=secondary, portfolio_id="P1")
    with pytest.raises(ValueError, match="PROSPECTIVE_CUTOFF_PRECEDES_ORIGINAL_SELECTION"):
        preview_prospective_reseal(**common, as_of="2026-11-04T03:59:00+00:00")
    report = preview_prospective_reseal(**common, as_of="2026-11-05T06:00:00+07:00")
    assert report["status"] == "SIGNER_REVIEW_REQUIRED"
    assert report["as_of"] == "2026-11-04T23:00:00+00:00"
    assert set(report["unsigned_candidate"]["definitions"]) == {"paper.prospective/P1-20261104"}


def test_conflicting_wallet_link_or_bad_whale_file_fails_closed(tmp_path):
    db, primary, secondary = prepare(tmp_path, resolved=True)
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(
                "UPDATE portfolio_memberships SET wallet_id=999 "
                "WHERE portfolio_id='P14' AND member_alias='S035-ENA'"
            )
    with pytest.raises(ValueError, match="FROZEN_WALLET_ID_CONFLICT"):
        audit(db, primary, secondary, "P14")
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(
                "UPDATE portfolio_memberships SET wallet_id=1 "
                "WHERE portfolio_id='P14' AND member_alias='S035-ENA'"
            )
    whale = secondary / "HL Perps Whale_0x5f94a519.json"
    whale.write_text(json.dumps({"address": "0x" + "7" * 40}))
    with pytest.raises(ValueError, match="PRIVATE_WHALE_ADDRESS_PREFIX_MISMATCH"):
        audit(db, primary, secondary, "P14")
