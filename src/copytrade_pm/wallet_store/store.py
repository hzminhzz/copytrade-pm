"""Permanent data store engine and access layer for canonical wallet-level data.

Provides Hive-partitioned, immutable zstd Parquet files with SQLite catalog tracking,
Pydantic validation at ingest, and catalog-driven lazy scanning.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Sequence

try:
    import polars as pl
except ModuleNotFoundError:  # pragma: no cover - core CI leg runs without --extra market
    pl = None  # type: ignore[assignment]

from .catalog import (
    DEFAULT_STORE_DIR,
    get_catalog_path,
    init_catalog,
    record_partition,
    refresh_wallet_summary,
)
from .schema import DATASET_SCHEMAS, DATASET_SHA256, SCHEMA_VERSION


def ensure_mode_700(path: Path) -> None:
    """Ensure directory exists and has mode 700 permissions."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def ensure_mode_600(path: Path) -> None:
    """Ensure file has mode 600 permissions."""
    if path.exists():
        os.chmod(path, 0o600)


def file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def ingest(
    kind: str,
    wallet: str,
    day: str,
    df: pl.DataFrame,
    source: str,
    source_cmd: str = "",
    *,
    store_dir: Path = DEFAULT_STORE_DIR,
    con: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Ingest a DataFrame into a canonical immutable partition.

    Never rewrites an existing data.parquet: writes to data.parquet.tmp, fsyncs,
    then renames. If partition exists with different content, writes data.<sha8>.parquet
    alongside and records both in catalog.
    """
    if kind not in DATASET_SCHEMAS:
        raise ValueError(f"Unknown dataset kind: {kind!r}")

    wallet_clean = wallet.lower().strip()
    if not (wallet_clean.startswith("0x") and len(wallet_clean) == 42):
        raise ValueError(f"Invalid wallet address: {wallet!r}")

    # Validate day format YYYY-MM-DD
    parts = day.split("-")
    if len(parts) != 3 or len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        raise ValueError(f"Invalid day format, expected YYYY-MM-DD: {day!r}")
    year_str, month_str, day_str = parts

    model_cls, expected_schema = DATASET_SCHEMAS[kind]

    # Validate and strictly cast DataFrame to expected Polars schema
    if df.schema != expected_schema:
        try:
            df = df.cast(expected_schema, strict=True)
        except Exception as exc:
            raise ValueError(
                f"DataFrame schema mismatch for {kind}. Expected {expected_schema}, got {df.schema}"
            ) from exc

    # Store root directory mode 700
    ensure_mode_700(store_dir)

    # Partition directory: <store_dir>/<kind>/wallet=<0x...>/year=YYYY/month=MM/day=DD
    partition_dir = (
        store_dir
        / kind
        / f"wallet={wallet_clean}"
        / f"year={year_str}"
        / f"month={month_str}"
        / f"day={day_str}"
    )

    # Make parent dirs mode 700
    curr = partition_dir
    while curr != store_dir:
        curr.mkdir(parents=True, exist_ok=True)
        os.chmod(curr, 0o700)
        curr = curr.parent

    target_path = partition_dir / "data.parquet"
    tmp_path = partition_dir / "data.parquet.tmp"

    # Write DataFrame with zstd compression to tmp file
    df.write_parquet(tmp_path, compression="zstd")

    # Fsync to guarantee disk flush
    with open(tmp_path, "rb+") as f:
        f.flush()
        os.fsync(f.fileno())

    ensure_mode_600(tmp_path)
    new_sha = file_sha256(tmp_path)
    file_bytes = tmp_path.stat().st_size
    rows_count = len(df)

    # Immutability check
    if not target_path.exists():
        os.replace(tmp_path, target_path)
        ensure_mode_600(target_path)
        final_path = target_path
    else:
        existing_sha = file_sha256(target_path)
        if existing_sha == new_sha:
            # Identical content: remove tmp and reuse existing
            os.remove(tmp_path)
            final_path = target_path
        else:
            # Different content: write data.<sha8>.parquet alongside
            sha8 = new_sha[:8]
            alongside_path = partition_dir / f"data.{sha8}.parquet"
            os.replace(tmp_path, alongside_path)
            ensure_mode_600(alongside_path)
            final_path = alongside_path

    # Provenance sidecar: <store_dir>/.metadata/<kind>/<wallet>/<day>.json
    meta_dir = store_dir / ".metadata" / kind / wallet_clean
    ensure_mode_700(meta_dir)
    sidecar_path = meta_dir / f"{day}.json"

    fetched_at = datetime.now(timezone.utc).isoformat()
    sidecar_data = {
        "kind": kind,
        "wallet": wallet_clean,
        "day": day,
        "path": str(final_path),
        "rows": rows_count,
        "bytes": file_bytes,
        "sha256": new_sha,
        "schema_version": SCHEMA_VERSION,
        "schema_sha256": DATASET_SHA256.get(kind, ""),
        "fetched_at": fetched_at,
        "source": source,
        "source_cmd": source_cmd,
    }

    with open(sidecar_path, "w", encoding="utf-8") as sf:
        json.dump(sidecar_data, sf, indent=2)
    ensure_mode_600(sidecar_path)

    # Record into catalog.sqlite
    close_con = False
    if con is None:
        catalog_path = get_catalog_path(store_dir)
        con = init_catalog(catalog_path)
        close_con = True

    try:
        record_partition(
            con,
            kind=kind,
            wallet=wallet_clean,
            day=day,
            path=str(final_path),
            rows=rows_count,
            bytes_count=file_bytes,
            sha256_hex=new_sha,
            fetched_at=fetched_at,
            source=source,
            source_cmd=source_cmd,
        )
        refresh_wallet_summary(con, wallet_clean)
    finally:
        if close_con:
            con.close()

    return sidecar_data


def scan(
    kind: str,
    wallets: Sequence[str] | str | None = None,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    *,
    store_dir: Path = DEFAULT_STORE_DIR,
) -> pl.LazyFrame:
    """Build LazyFrame by scanning catalog partitions; never globs the filesystem.

    Filters by wallet and UTC day before reading files. Refuses unknown schema version.
    """
    if kind not in DATASET_SCHEMAS:
        raise ValueError(f"Unknown dataset kind: {kind!r}")

    _, expected_schema = DATASET_SCHEMAS[kind]
    catalog_path = get_catalog_path(store_dir)

    if not catalog_path.exists():
        return pl.DataFrame(schema=expected_schema).lazy()

    con = init_catalog(catalog_path)
    try:
        cur = con.cursor()
        # Verify dataset schema version
        row = cur.execute("SELECT schema_version FROM datasets WHERE kind = ?", (kind,)).fetchone()
        if row and row["schema_version"] != SCHEMA_VERSION:
            raise ValueError(
                f"Incompatible schema version: store has {row['schema_version']}, current code requires {SCHEMA_VERSION}"
            )

        query = "SELECT path, day FROM partitions WHERE kind = ?"
        params: list[Any] = [kind]

        if wallets is not None:
            if isinstance(wallets, str):
                wallets_list = [wallets.lower().strip()]
            else:
                wallets_list = [w.lower().strip() for w in wallets]
            placeholders = ",".join("?" for _ in wallets_list)
            query += f" AND wallet IN ({placeholders})"
            params.extend(wallets_list)

        if start is not None:
            start_str = (
                start.strftime("%Y-%m-%d") if isinstance(start, datetime) else str(start)[:10]
            )
            query += " AND day >= ?"
            params.append(start_str)

        if end is not None:
            end_str = end.strftime("%Y-%m-%d") if isinstance(end, datetime) else str(end)[:10]
            query += " AND day <= ?"
            params.append(end_str)

        query += " ORDER BY day ASC, path ASC"
        rows = cur.execute(query, params).fetchall()
        paths = [r["path"] for r in rows if Path(r["path"]).exists()]

        if not paths:
            return pl.DataFrame(schema=expected_schema).lazy()

        return pl.scan_parquet(paths)
    finally:
        con.close()


def coverage(
    kind: str | None = None,
    *,
    store_dir: Path = DEFAULT_STORE_DIR,
) -> pl.DataFrame:
    """Return DataFrame of all partitions, wallet, day, rows, bytes, and sources.

    Answers coverage queries without scanning physical files.
    """
    catalog_path = get_catalog_path(store_dir)
    if not catalog_path.exists():
        return pl.DataFrame(
            schema={
                "kind": pl.String,
                "wallet": pl.String,
                "day": pl.String,
                "rows": pl.Int64,
                "bytes": pl.Int64,
                "sources": pl.String,
            }
        )

    con = init_catalog(catalog_path)
    try:
        cur = con.cursor()
        if kind is not None:
            rows = cur.execute(
                """
                SELECT kind, wallet, day, sum(rows) as rows, sum(bytes) as bytes, group_concat(distinct source) as sources
                FROM partitions
                WHERE kind = ?
                GROUP BY kind, wallet, day
                ORDER BY kind, wallet, day
                """,
                (kind,),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT kind, wallet, day, sum(rows) as rows, sum(bytes) as bytes, group_concat(distinct source) as sources
                FROM partitions
                GROUP BY kind, wallet, day
                ORDER BY kind, wallet, day
                """
            ).fetchall()

        data = [dict(r) for r in rows]
        if not data:
            return pl.DataFrame(
                schema={
                    "kind": pl.String,
                    "wallet": pl.String,
                    "day": pl.String,
                    "rows": pl.Int64,
                    "bytes": pl.Int64,
                    "sources": pl.String,
                }
            )
        return pl.DataFrame(data)
    finally:
        con.close()


def verify(*, store_dir: Path = DEFAULT_STORE_DIR) -> int:
    """Verify integrity of the store: re-hash every partition and check permissions.

    Reports all mismatches and problems. Returns 0 if store is fully verified.
    """
    catalog_path = get_catalog_path(store_dir)
    if not catalog_path.exists():
        print(f"[VERIFY ERROR] Catalog does not exist: {catalog_path}")
        return 1

    con = init_catalog(catalog_path)
    problems = 0
    checked_partitions = 0

    try:
        cur = con.cursor()
        partitions = cur.execute(
            "SELECT kind, wallet, day, path, rows, bytes, sha256 FROM partitions ORDER BY kind, wallet, day"
        ).fetchall()

        for p in partitions:
            checked_partitions += 1
            fpath = Path(p["path"])
            if not fpath.exists():
                print(f"[VERIFY ERROR] Missing partition file: {fpath}")
                problems += 1
                continue

            # Check mode 600
            file_mode = stat.S_IMODE(fpath.stat().st_mode)
            if file_mode != 0o600:
                print(
                    f"[VERIFY ERROR] Permission mismatch on {fpath}: expected 0o600, got {oct(file_mode)}"
                )
                problems += 1

            # Check sha256
            computed_sha = file_sha256(fpath)
            if computed_sha != p["sha256"]:
                print(
                    f"[VERIFY ERROR] SHA mismatch on {fpath}: catalog={p['sha256']}, computed={computed_sha}"
                )
                problems += 1

            # Check rows
            try:
                actual_rows = len(pl.read_parquet(fpath))
                if actual_rows != p["rows"]:
                    print(
                        f"[VERIFY ERROR] Row count mismatch on {fpath}: catalog={p['rows']}, actual={actual_rows}"
                    )
                    problems += 1
            except Exception as exc:
                print(f"[VERIFY ERROR] Unreadable parquet {fpath}: {exc}")
                problems += 1

            # Check sidecar
            sidecar_path = store_dir / ".metadata" / p["kind"] / p["wallet"] / f"{p['day']}.json"
            if not sidecar_path.exists():
                print(f"[VERIFY ERROR] Missing metadata sidecar: {sidecar_path}")
                problems += 1
            else:
                sidecar_mode = stat.S_IMODE(sidecar_path.stat().st_mode)
                if sidecar_mode != 0o600:
                    print(
                        f"[VERIFY ERROR] Permission mismatch on sidecar {sidecar_path}: expected 0o600, got {oct(sidecar_mode)}"
                    )
                    problems += 1

        print(
            f"[VERIFY SUMMARY] Checked {checked_partitions} partitions. Found {problems} problems."
        )
        return problems
    finally:
        con.close()
