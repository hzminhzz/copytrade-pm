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
)


def prepare(tmp_path, *, resolved=False):
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
            for i, alias in enumerate(P14, 1):
                conn.execute(
                    "INSERT INTO wallets VALUES (?,?,?)", (i, "hyperliquid", addresses[alias])
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
