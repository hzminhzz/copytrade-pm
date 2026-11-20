"""Historical-data fixture for the read-only legacy identity audit.

The legacy wallet registry is archived read-only and is never an admission
authority. These helpers build a synthetic archive copy so the read-only audit
(`audit_frozen_member_resolution`) and the observers it feeds stay testable.
"""

from contextlib import closing
import json
import sqlite3

from copytrade_pm.pm_forward_registry_identity import (
    P1 as P1,
    P14 as P14,
    audit_frozen_member_resolution,
)


def prepare(tmp_path, *, resolved=False, late_known=False):
    primary = tmp_path / "wallet_fills_90d"
    secondary = tmp_path / "nansen_smart_money_fills_90d"
    primary.mkdir(exist_ok=True)
    secondary.mkdir(exist_ok=True)
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
