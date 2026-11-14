"""Catalog interface for the canonical wallet store SQLite database.

Maintains tables for datasets, partitions, and wallets.
Supports indexed partition lookups and registry coverage reconciliation.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from .schema import DATASET_SCHEMAS, DATASET_SHA256, SCHEMA_VERSION

DEFAULT_STORE_DIR = Path("/home/quant/dev/copytrade-pm/data/private/wallet_store")
DEFAULT_REGISTRY_DB = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")


def get_catalog_path(store_dir: Path = DEFAULT_STORE_DIR) -> Path:
    return store_dir / "catalog.sqlite"


def init_catalog(catalog_path: Path) -> sqlite3.Connection:
    """Initialize catalog SQLite tables with mode 600 permissions."""
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(catalog_path.parent, 0o700)

    con = sqlite3.connect(catalog_path, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    with con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS datasets(
                kind TEXT PRIMARY KEY,
                schema_version TEXT,
                schema_sha256 TEXT,
                description TEXT
            );
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS partitions(
                kind TEXT,
                wallet TEXT,
                day TEXT,
                path TEXT,
                rows INTEGER,
                bytes INTEGER,
                sha256 TEXT,
                fetched_at TEXT,
                source TEXT,
                source_cmd TEXT,
                PRIMARY KEY(kind, wallet, day, path)
            );
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS partitions_kind_day ON partitions(kind, day);
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS partitions_kind_wallet_day ON partitions(kind, wallet, day);
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS wallets(
                address TEXT PRIMARY KEY,
                first_ts TEXT,
                last_ts TEXT,
                fills INTEGER,
                positions INTEGER,
                sources TEXT
            );
        """)

        # Register datasets
        descriptions = {
            "fills": "Canonical wallet fill executions",
            "positions": "Canonical wallet open positions snapshots",
            "equity": "Canonical wallet total equity snapshots",
            "funding": "Canonical wallet funding payment cashflows",
            "ledger": "Canonical wallet deposits, withdrawals, and fee adjustments",
        }
        for kind in DATASET_SCHEMAS:
            sha = DATASET_SHA256.get(kind, "")
            desc = descriptions.get(kind, "")
            con.execute(
                """
                INSERT INTO datasets(kind, schema_version, schema_sha256, description)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(kind) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    schema_sha256 = excluded.schema_sha256,
                    description = excluded.description;
                """,
                (kind, SCHEMA_VERSION, sha, desc),
            )

    if catalog_path.exists():
        os.chmod(catalog_path, 0o600)
    return con


def record_partition(
    con: sqlite3.Connection,
    *,
    kind: str,
    wallet: str,
    day: str,
    path: str,
    rows: int,
    bytes_count: int,
    sha256_hex: str,
    fetched_at: str,
    source: str,
    source_cmd: str = "",
) -> None:
    """Record partition into catalog."""
    with con:
        con.execute(
            """
            INSERT INTO partitions(kind, wallet, day, path, rows, bytes, sha256, fetched_at, source, source_cmd)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, wallet, day, path) DO UPDATE SET
                rows = excluded.rows,
                bytes = excluded.bytes,
                sha256 = excluded.sha256,
                fetched_at = excluded.fetched_at,
                source = excluded.source,
                source_cmd = excluded.source_cmd;
            """,
            (
                kind,
                wallet,
                day,
                path,
                rows,
                bytes_count,
                sha256_hex,
                fetched_at,
                source,
                source_cmd,
            ),
        )


def refresh_wallet_summary(con: sqlite3.Connection, wallet: str) -> None:
    """Recompute summary statistics for a wallet in catalog."""
    cur = con.cursor()
    row = cur.execute(
        """
        SELECT
            sum(CASE WHEN kind = 'fills' THEN rows ELSE 0 END) as fills_count,
            sum(CASE WHEN kind = 'positions' THEN rows ELSE 0 END) as positions_count,
            group_concat(distinct source) as all_sources
        FROM partitions
        WHERE wallet = ?
        """,
        (wallet,),
    ).fetchone()

    fills_count = (row[0] if row else 0) or 0
    positions_count = (row[1] if row else 0) or 0
    sources_str = (row[2] if row else "") or ""

    # Fetch min and max day
    day_row = cur.execute(
        """
        SELECT min(day) as min_day, max(day) as max_day
        FROM partitions
        WHERE wallet = ?
        """,
        (wallet,),
    ).fetchone()
    first_ts = (day_row[0] if day_row else "") or ""
    last_ts = (day_row[1] if day_row else "") or ""

    with con:
        con.execute(
            """
            INSERT INTO wallets(address, first_ts, last_ts, fills, positions, sources)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                first_ts = excluded.first_ts,
                last_ts = excluded.last_ts,
                fills = excluded.fills,
                positions = excluded.positions,
                sources = excluded.sources;
            """,
            (wallet, first_ts, last_ts, fills_count, positions_count, sources_str),
        )


def query_uncovered_registry_wallets(
    con: sqlite3.Connection,
    registry_db_path: Path = DEFAULT_REGISTRY_DB,
) -> list[str]:
    """Return wallets present in registry that have 0 cached data in store catalog."""
    if not registry_db_path.exists():
        return []

    cur = con.cursor()
    cur.execute(f"ATTACH DATABASE '{registry_db_path.resolve()}' AS registry;")
    try:
        rows = cur.execute(
            """
            SELECT DISTINCT lower(address) as addr
            FROM registry.wallets
            WHERE lower(address) NOT IN (
                SELECT address FROM main.wallets WHERE fills > 0 OR positions > 0
            )
            ORDER BY addr;
            """
        ).fetchall()
        return [r["addr"] for r in rows]
    finally:
        cur.execute("DETACH DATABASE registry;")
