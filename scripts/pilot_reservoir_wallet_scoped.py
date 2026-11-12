"""Read-only-source, wallet-scoped Reservoir seven-day acquisition pilot.

Writes ONLY immutable, private research artifacts outside Git. It does not mutate
the canonical store, registry, paper orders, PM-03/04, Guardian or qualification.
Historical exchange timestamps are not actual first-known receipts.

Use the quant-lab venv (DuckDB 2.0 and pyarrow), not the copytrade Python 3.14
runtime that currently lacks DuckDB.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
import fcntl
from hashlib import sha256
from itertools import groupby
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
import polars as pl

BUCKET = "hydromancer-reservoir"
REGION = "ap-northeast-1"
SELECTED_PORTFOLIOS = ("A", "B", "C", "Combo2", "regime.macro/TriadA", "regime.macro/TriadChop")
REGISTRY = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
CATALOG = Path("/home/quant/dev/copytrade-pm/data/private/wallet_store/catalog.sqlite")
OUTPUT = Path("/home/quant/.local/share/copytrade/research/reservoir-wallet-pilot-20261112")
CORE = (
    "address",
    "timestamp",
    "coin",
    "dex",
    "side",
    "size",
    "start_position",
    "trade_id",
    "direction",
    "is_liquidation",
)
ADDRESS = re.compile(r"0x[a-f0-9]{40}")
SNAPSHOT = re.compile(
    r"global/snapshots/perp/all/date=(\d{4}-\d{2}-\d{2})/"
    r"(\d+)_(\d+)\.parquet"
)
S3_PREFIX = f"s3://{BUCKET}"
SNAP_FIELDS = (
    "user",
    "market",
    "size",
    "notional",
    "entry_price",
    "liquidation_price",
    "leverage_type",
    "leverage",
    "funding_pnl",
    "account_value",
    "account_mode",
)


def jdump(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def sha(obj: Any) -> str:
    return sha256(jdump(obj).encode()).hexdigest()


@contextmanager
def private_lock(folder: Path) -> Iterator[None]:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    fd = os.open(folder / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def exclusive_bytes(path: Path, data: bytes) -> str:
    """No overwrite, symlink traversal or half-written logical replacement."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Existing immutable artifact requires verification")
    fd, tmp = tempfile.mkstemp(prefix=".stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as dst:
            dst.write(data)
            dst.flush()
            os.fsync(dst.fileno())
        os.link(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    os.chmod(path, 0o600)
    return sha256(data).hexdigest()


def exclusive_arrow(path: Path, table: pa.Table) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Existing immutable artifact requires verification")
    fd, tmp = tempfile.mkstemp(prefix=".stage-", dir=path.parent)
    os.close(fd)
    try:
        pq.write_table(table, tmp, compression="zstd", row_group_size=100_000)
        with open(tmp, "rb") as stream:
            digest = sha256(stream.read()).hexdigest()
            os.fsync(stream.fileno())
        os.link(tmp, path)
        os.chmod(path, 0o600)
        return digest
    finally:
        Path(tmp).unlink(missing_ok=True)


def registry_scope(path: Path = REGISTRY) -> tuple[list[str], dict[str, Any]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        check = con.execute("PRAGMA quick_check").fetchone()[0]
        if check != "ok":
            raise ValueError("PRIVATE_REGISTRY_INTEGRITY")
        placeholders = ",".join("?" for _ in SELECTED_PORTFOLIOS)
        sql = f"""
            SELECT s.portfolio_id, s.version, s.selection_known_at,
                   s.definition_sha256, lower(w.address) AS address
            FROM portfolio_seals s
            JOIN portfolio_memberships m
                ON m.portfolio_id=s.portfolio_id AND m.version=s.version
            JOIN wallets w ON w.wallet_id=m.wallet_id
            WHERE s.portfolio_id IN ({placeholders})
              AND s.version=(
                SELECT max(s2.version) FROM portfolio_seals s2
                WHERE s2.portfolio_id=s.portfolio_id
              )
            ORDER BY s.portfolio_id,m.member_alias
        """
        rows = con.execute(sql, SELECTED_PORTFOLIOS).fetchall()
        if len(rows) != 18 or len(set(x[0] for x in rows)) != 6:
            raise ValueError("MISSING_SELECTED_SEALED_MEMBERS")
        addresses = sorted({x[4] for x in rows})
        if len(addresses) != 14 or not all(ADDRESS.fullmatch(x) for x in addresses):
            raise ValueError("UNVERIFIED_SELECTED_IDENTITY")
        versions: dict[str, dict[str, Any]] = {}
        for pid, version, known_at, definition_sha, _ in rows:
            if not known_at or not re.fullmatch(r"[a-f0-9]{64}", definition_sha):
                raise ValueError("MISSING_PORTFOLIO_SEAL_PROVENANCE")
            item = {"version": version, "known_at": known_at, "definition_sha256": definition_sha}
            if pid in versions and versions[pid] != item:
                raise ValueError("AMBIGUOUS_SELECTED_SEAL")
            versions[pid] = item
        # Only identity hashes and non-sensitive counts leave this function.
        scope = {
            "wallet_count": len(addresses),
            "member_records": len(rows),
            "portfolio_count": len(versions),
            "portfolio_versions": versions,
            "wallet_set_sha256": sha256("\n".join(addresses).encode()).hexdigest(),
            "study_class": "RETROSPECTIVE_FIXED_COHORT_NOT_PIT_SELECTION",
        }
        return addresses, scope
    finally:
        con.close()


def aws_cli(args: list[str]) -> Any:
    cmd = [
        "aws",
        "s3api",
        *args,
        "--request-payer",
        "requester",
        "--region",
        REGION,
        "--profile",
        "default",
        "--output",
        "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    if result.returncode:
        # Deliberately do not expose AWS diagnostics or any credentials.
        raise RuntimeError(f"AWS_S3_REQUEST_FAILED exit={result.returncode}")
    return json.loads(result.stdout)


def s3_head(key: str) -> dict[str, Any]:
    record = aws_cli(["head-object", "--bucket", BUCKET, "--key", key])
    return {
        "key": key,
        "bytes": record["ContentLength"],
        "etag": record.get("ETag", ""),
        "last_modified": record.get("LastModified"),
    }


def source_keys(day: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fill = s3_head(f"by_dex/hyperliquid/fills/perp/all/date={day}/fills.parquet")
    objects = aws_cli(
        [
            "list-objects-v2",
            "--bucket",
            BUCKET,
            "--prefix",
            f"global/snapshots/perp/all/date={day}/",
            "--max-keys",
            "25",
        ]
    )
    contents = objects.get("Contents", [])
    if len(contents) != 1 or objects.get("IsTruncated"):
        raise ValueError(f"SNAPSHOT_MISSING_OR_MULTIPLE day={day}")
    key = contents[0]["Key"]
    match = SNAPSHOT.fullmatch(key)
    if match is None or match.group(1) != day:
        raise ValueError(f"BAD_SNAPSHOT_STATE_ID day={day}")
    snapshot = s3_head(key)
    snapshot["block"] = int(match.group(2))
    snapshot["state_ts_ms"] = int(match.group(3))
    state_day = datetime.fromtimestamp(snapshot["state_ts_ms"] / 1000, UTC).date()
    if str(state_day) != day:
        raise ValueError(f"SNAPSHOT_TIME_DAY_MISMATCH day={day}")
    return fill, snapshot


def remote_connection():
    sys.path.insert(0, "/home/quant/tmp")
    from reservoir_query import connect, load_credentials

    con = connect(load_credentials("default"))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET TimeZone='UTC'")
    return con


def column_budget(con, key: str, fields: tuple[str, ...]) -> dict[str, Any]:
    uri = f"{S3_PREFIX}/{key}"
    rows = con.execute(
        """
        SELECT path_in_schema, SUM(total_compressed_size),
               count(DISTINCT row_group_id),
               count(*) FILTER (WHERE stats_min IS NOT NULL
                                AND stats_max IS NOT NULL)
        FROM parquet_metadata(?)
        GROUP BY path_in_schema
    """,
        [uri],
    ).fetchall()
    values = {x[0]: x for x in rows}
    missing = sorted(set(fields) - values.keys())
    if missing:
        raise ValueError("SOURCE_SCHEMA_MISSING_FIELDS:" + ",".join(missing))
    return {
        "source_columns": len(values),
        "selected_columns": list(fields),
        "projected_compressed_bytes": sum(values[x][1] for x in fields),
        "row_groups": max(x[2] for x in rows),
        "address_or_user_stats_row_groups": values.get("address", values.get("user"))[3],
    }


def validate_fills(table: pa.Table, wallets: set[str], day: str) -> dict[str, Any]:
    required = (
        "wallet",
        "exchange_ts",
        "coin",
        "dex",
        "side",
        "size",
        "start_position",
        "trade_id",
        "direction",
        "is_liquidation",
    )
    if tuple(table.column_names) != required:
        raise ValueError("SOURCE_COLUMNS_CHANGED")
    schema = table.schema
    if (
        not pa.types.is_decimal(schema.field("size").type)
        or not pa.types.is_decimal(schema.field("start_position").type)
        or not pa.types.is_uint64(schema.field("trade_id").type)
        or not pa.types.is_timestamp(schema.field("exchange_ts").type)
    ):
        raise ValueError("LOSSLESS_FILL_TYPES_UNAVAILABLE")
    seen: set[tuple[str, int]] = set()
    per_wallet: Counter[str] = Counter()
    null_start = 0
    liquidation = 0
    for row in table.to_pylist():
        wallet = row["wallet"]
        if wallet not in wallets or row["dex"] != "hyperliquid":
            raise ValueError("SOURCE_SCOPE_MISMATCH")
        stamp = row["exchange_ts"]
        if stamp is None or str(stamp.astimezone(UTC).date()) != day:
            raise ValueError("SOURCE_TIMESTAMP_DAY_MISMATCH")
        if not isinstance(row["size"], Decimal) or row["size"] <= 0:
            raise ValueError("SOURCE_NONPOSITIVE_SIZE")
        if row["side"] not in ("buy", "sell") or not row["coin"]:
            raise ValueError("SOURCE_DIRECTION_OR_MARKET_INVALID")
        if row["start_position"] is None:
            null_start += 1
        trade_id = row["trade_id"]
        if trade_id is None:
            raise ValueError("SOURCE_MISSING_TRADE_ID")
        key = (wallet, trade_id)
        if key in seen:
            raise ValueError("SOURCE_DUPLICATE_TRADE_ID")
        seen.add(key)
        liquidation += row["is_liquidation"] is True
        per_wallet[wallet] += 1
    return {
        "rows": table.num_rows,
        "wallets_with_rows": len(per_wallet),
        "start_position_null": null_start,
        "liquidations": liquidation,
        "unique_wallet_trade_ids": len(seen),
    }


def fetch_fills(con, key: str, wallets: list[str], day: str) -> pa.Table:
    slots = ",".join("?" for _ in wallets)
    # Retain the entire DEX/day source scope for selected wallets, do NOT sort
    # vendor data on S3 or pretend same-ms trade IDs are a causal ordering.
    sql = f"""
        SELECT address AS wallet, timestamp AS exchange_ts,
               coin, dex, side, size, start_position, trade_id,
               direction, is_liquidation
        FROM read_parquet(?)
        WHERE address IN ({slots})
    """
    return con.sql(sql, params=[f"{S3_PREFIX}/{key}", *wallets]).to_arrow_table()


def fetch_snapshot(con, key: str, wallets: list[str], state: dict[str, Any]) -> pa.Table:
    slots = ",".join("?" for _ in wallets)
    sql = f"""
        SELECT user AS wallet, market,
               size AS signed_size, notional, entry_price, liquidation_price,
               leverage_type, leverage, funding_pnl, account_value, account_mode,
               ?::BIGINT AS state_block, ?::BIGINT AS state_ts_ms
        FROM read_parquet(?)
        WHERE user IN ({slots})
    """
    table = con.sql(
        sql, params=[state["block"], state["state_ts_ms"], f"{S3_PREFIX}/{key}", *wallets]
    ).to_arrow_table()
    if table.num_rows == 0:
        raise ValueError("SNAPSHOT_EMPTY_SELECTED_SCOPE_UNKNOWN")
    for row in table.to_pylist():
        if row["wallet"] not in wallets or not row["market"]:
            raise ValueError("SNAPSHOT_SCOPE_MISMATCH")
    return table


def verify_artifact(folder: Path, source_etag: str, scope_sha: str) -> dict[str, Any] | None:
    path = folder / "data.parquet"
    sidecar = folder / "provenance.json"
    if not path.exists() and not sidecar.exists():
        return None
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("BLOCKED_INCOMPLETE_ARTIFACT_PAIR")
    record = json.loads(sidecar.read_text())
    if record["source_etag"] != source_etag or record["wallet_set_sha256"] != scope_sha:
        raise ValueError("BLOCKED_SOURCE_VERSION_OR_SCOPE_DRIFT")
    if sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError("BLOCKED_STAGED_SHA_MISMATCH")
    pq.read_metadata(path)  # Parquet footer must be readable.
    return record


def publish_table(
    folder: Path,
    table: pa.Table,
    etag: str,
    scope_sha: str,
    source_key: str,
    day: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    old = verify_artifact(folder, etag, scope_sha)
    if old is not None:
        return old
    if table.num_rows == 0:
        # Zero rows is not proof of inactivity, never publish a zero-day tape.
        raise ValueError("NO_ROWS_SERVED_NOT_AN_INACTIVE_DAY")
    digest = exclusive_arrow(folder / "data.parquet", table)
    record = {
        "schema": "reservoir_wallet_scoped_pilot_v1",
        "day": day,
        "source_key": source_key,
        "source_etag": etag,
        "sha256": digest,
        "wallet_set_sha256": scope_sha,
        "rows": table.num_rows,
        "fields": list(table.column_names),
        "metrics": metrics,
        "historical_first_known": False,
        "scientifically_qualified": False,
        "attribution": "Data: Hydromancer Reservoir (reservoir.hydromancer.xyz), CC BY 4.0",
        "ingested_at_utc": datetime.now(UTC).isoformat(),
    }
    exclusive_bytes(folder / "provenance.json", (jdump(record) + "\n").encode())
    return record


def date_window(start: date, end: date) -> list[str]:
    from datetime import timedelta

    if end < start or (end - start).days > 6 or end >= datetime.now(UTC).date():
        raise ValueError("PILOT_REQUIRES_1_TO_7_COMPLETED_UTC_DAYS")
    return [str(start + timedelta(days=i)) for i in range((end - start).days + 1)]


def preflight(start: date, end: date, folder: Path, max_projected_bytes: int) -> dict[str, Any]:
    wallets, scope = registry_scope()
    if len(wallets) != 14:
        raise ValueError("UNEXPECTED_SELECTED_COHORT")
    days = date_window(start, end)
    conn = remote_connection()
    try:
        objects = []
        total_projection = 0
        for day in days:
            fill, snapshot = source_keys(day)
            fill["type"] = "fills"
            snapshot["type"] = "position_snapshot"
            fill["column_budget"] = column_budget(conn, fill["key"], CORE)
            snapshot["column_budget"] = column_budget(conn, snapshot["key"], SNAP_FIELDS)
            for item in (fill, snapshot):
                total_projection += item["column_budget"]["projected_compressed_bytes"]
                objects.append(item)
        if total_projection > max_projected_bytes:
            raise ValueError("COST_CAP_ESTIMATE_EXCEEDED")
        manifest = {
            "schema": "reservoir_pilot_preflight_v1",
            "created_utc": datetime.now(UTC).isoformat(),
            "days": days,
            "scope": scope,
            "objects": objects,
            "total_projected_compressed_bytes": total_projection,
            "max_projected_compressed_bytes": max_projected_bytes,
            "source_first_known": False,
            "status": "PREFLIGHT_ONLY",
        }
        private_lock_dir = folder
        result_path = private_lock_dir / "preflight.json"
        exclusive_bytes(result_path, (jdump(manifest) + "\n").encode())
        return {
            "days": len(days),
            "wallet_count": len(wallets),
            "object_count": len(objects),
            "total_projected_compressed_MB": round(total_projection / 1e6, 3),
            "max_projected_MB": round(max_projected_bytes / 1e6, 3),
            "preflight_sha256": sha256(result_path.read_bytes()).hexdigest(),
            "status": "PREFLIGHT_PROVISIONAL",
        }
    finally:
        conn.close()


def verify_manifest(folder: Path) -> tuple[list[str], dict[str, Any]]:
    path = folder / "preflight.json"
    pre = json.loads(path.read_text())
    wallets, scope = registry_scope()
    if pre["scope"]["wallet_set_sha256"] != scope["wallet_set_sha256"]:
        raise ValueError("SELECTED_SCOPE_CHANGED")
    if pre["scope"]["portfolio_versions"] != scope["portfolio_versions"]:
        raise ValueError("SEALED_PORTFOLIO_CHANGED")
    if pre["days"] != date_window(
        date.fromisoformat(pre["days"][0]), date.fromisoformat(pre["days"][-1])
    ):
        raise ValueError("NON_CONTIGUOUS_DATES")
    if len(pre["objects"]) != 2 * len(pre["days"]):
        raise ValueError("INCOMPLETE_OBJECT_MANIFEST")
    if (
        sum(obj["column_budget"]["projected_compressed_bytes"] for obj in pre["objects"])
        != pre["total_projected_compressed_bytes"]
    ):
        raise ValueError("MANIFEST_BUDGET_INCONSISTENT")
    return wallets, pre


def fetch(folder: Path, only_day: str | None = None) -> dict[str, Any]:
    wallets, pre = verify_manifest(folder)
    if only_day is not None and only_day not in pre["days"]:
        raise ValueError("FETCH_DAY_NOT_IN_FROZEN_PREFLIGHT")
    pending_days = [only_day] if only_day is not None else pre["days"]
    con = remote_connection()
    summary: list[dict[str, Any]] = []
    try:
        for day in pending_days:
            for kind in ("fills", "position_snapshot"):
                (item,) = (
                    x for x in pre["objects"] if x["type"] == kind and f"date={day}/" in x["key"]
                )
                # Refuse to query revised source ETags, no silent vendor revision.
                now = s3_head(item["key"])
                if now["etag"] != item["etag"] or now["bytes"] != item["bytes"]:
                    raise ValueError("S3_OBJECT_CHANGED_AFTER_PREFLIGHT")
                target = folder / kind / f"day={day}"
                existing = verify_artifact(target, item["etag"], pre["scope"]["wallet_set_sha256"])
                if existing:
                    summary.append(
                        {
                            "day": day,
                            "type": kind,
                            "status": "REUSED_VERIFIED",
                            "rows": existing["rows"],
                        }
                    )
                    continue
                started = time.monotonic()
                if kind == "fills":
                    table = fetch_fills(con, item["key"], wallets, day)
                    metrics = validate_fills(table, set(wallets), day)
                else:
                    table = fetch_snapshot(con, item["key"], wallets, item)
                    metrics = {
                        "rows": table.num_rows,
                        "wallets_with_positions": len(set(table.column("wallet").to_pylist())),
                        "native_main_market_rows": sum(
                            ":" not in row["market"] for row in table.to_pylist()
                        ),
                    }
                elapsed = round(time.monotonic() - started, 3)
                if table.num_rows == 0:
                    summary.append(
                        {
                            "day": day,
                            "type": kind,
                            "status": "NO_ROWS_SERVED_NOT_INACTIVITY",
                            "rows": 0,
                            "query_seconds": elapsed,
                        }
                    )
                    continue
                receipt = publish_table(
                    target,
                    table,
                    item["etag"],
                    pre["scope"]["wallet_set_sha256"],
                    item["key"],
                    day,
                    metrics,
                )
                summary.append(
                    {
                        "day": day,
                        "type": kind,
                        "status": "PUBLISHED",
                        "rows": receipt["rows"],
                        "query_seconds": elapsed,
                        "bytes_on_disk": (target / "data.parquet").stat().st_size,
                        "metrics": metrics,
                    }
                )
                # Check again to detect S3 file updates during retrieval.
                head_after = s3_head(item["key"])
                if head_after["etag"] != item["etag"]:
                    raise ValueError("S3_CHANGED_DURING_ACQUISITION")
        summary_path = folder / (
            f"fetch-summary-{only_day}.json" if only_day is not None else "fetch-summary.json"
        )
        result = {
            "asof_utc": datetime.now(UTC).isoformat(),
            "schema": "reservoir_wallet_pilot_run_v1",
            "study_class": "RETROSPECTIVE_FIXED_COHORT_NOT_PIT_SELECTION",
            "scope_sha": pre["scope"]["wallet_set_sha256"],
            "results": summary,
            "source_transport_bytes": None,  # Must not infer measured cost from column chunks.
            "scientifically_qualified": False,
            "trading_authorized": False,
        }
        if not summary_path.exists():
            exclusive_bytes(summary_path, (jdump(result) + "\n").encode())
        return {
            "status": "FETCH_FINISHED",
            "days": len(pending_days),
            "objects": len(summary),
            "published": sum(x["status"] == "PUBLISHED" for x in summary),
            "reused": sum(x["status"] == "REUSED_VERIFIED" for x in summary),
            "rows_fills": sum(x["rows"] for x in summary if x["type"] == "fills"),
            "rows_snapshot": sum(x["rows"] for x in summary if x["type"] == "position_snapshot"),
            "total_local_bytes": sum(x.get("bytes_on_disk", 0) for x in summary),
        }
    finally:
        con.close()


def read_local_ids(con: sqlite3.Connection, wallet: str, day: str) -> tuple[set[int], str]:
    # The immutable canonical store is another evidence provider, not overwritten.
    partitions = con.execute(
        "SELECT path,sha256 FROM partitions WHERE kind='fills' AND wallet=? AND day=?",
        (wallet, day),
    ).fetchall()
    if not partitions:
        return set(), "LOCAL_PARTITION_ABSENT"
    results: set[int] = set()
    for path_value, expected in partitions:
        path = Path(path_value)
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            return set(), "LOCAL_HASH_OR_PATH_BLOCKED"
        frame = pl.read_parquet(path, columns=["dex", "trade_id"])
        frame = frame.filter(pl.col("dex").is_in(["HL", "hyperliquid"]))
        for tid in frame.get_column("trade_id").to_list():
            if tid is not None:
                results.add(int(tid))
    return results, "LOCAL_PARTITION_PRESENT"


def report(folder: Path) -> dict[str, Any]:
    wallets, pre = verify_manifest(folder)
    catalog = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    group: Counter[str] = Counter()
    day_result: list[dict[str, Any]] = []
    all_fill_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    try:
        for day in pre["days"]:
            fill_path = folder / "fills" / f"day={day}" / "data.parquet"
            snap_path = folder / "position_snapshot" / f"day={day}" / "data.parquet"
            if not fill_path.is_file() or not snap_path.is_file():
                raise ValueError("PILOT_INCOMPLETE_REQUIRED_ARTIFACT")
            (f_item,) = (
                x for x in pre["objects"] if x["type"] == "fills" and f"date={day}/" in x["key"]
            )
            (s_item,) = (
                x
                for x in pre["objects"]
                if x["type"] == "position_snapshot" and f"date={day}/" in x["key"]
            )
            verify_artifact(fill_path.parent, f_item["etag"], pre["scope"]["wallet_set_sha256"])
            verify_artifact(snap_path.parent, s_item["etag"], pre["scope"]["wallet_set_sha256"])
            fill = pq.read_table(fill_path).to_pylist()
            book = pq.read_table(snap_path).to_pylist()
            all_fill_rows.extend(fill)
            snapshots.extend(book)
            per_wallet: dict[str, set[int]] = defaultdict(set)
            for row in fill:
                per_wallet[row["wallet"]].add(row["trade_id"])
            daily = Counter()
            for wallet in wallets:
                source_ids = per_wallet.get(wallet, set())
                local_ids, local_status = read_local_ids(catalog, wallet, day)
                if local_status != "LOCAL_PARTITION_PRESENT":
                    daily[local_status] += 1
                daily["source_rows"] += len(source_ids)
                daily["local_ids"] += len(local_ids)
                daily["matched_ids"] += len(source_ids & local_ids)
                daily["source_only_ids"] += len(source_ids - local_ids)
                daily["local_only_ids"] += len(local_ids - source_ids)
                if not source_ids and not local_ids:
                    daily["both_zero_unproven_inactivity"] += 1
                if source_ids and not local_ids:
                    daily["source_positive_local_empty"] += 1
                if local_ids and not source_ids:
                    daily["local_positive_source_empty"] += 1
            day_result.append({"day": day, **dict(daily)})
            group.update(daily)
    finally:
        catalog.close()

    # Source fill chain across day boundary. Same-millisecond ordering and
    # a missing earlier baseline are not silently reconstructed.
    per_market: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in all_fill_rows:
        per_market[(r["wallet"], r["coin"])].append(r)
    chains = Counter()
    for records in per_market.values():
        records.sort(key=lambda x: (x["exchange_ts"], x["trade_id"]))
        timestamp_groups = [
            list(group_rows) for _, group_rows in groupby(records, key=lambda r: r["exchange_ts"])
        ]
        chains["markets_seen"] += 1
        chains["multi_ms_groups"] += sum(len(g) > 1 for g in timestamp_groups)
        chains["rows_inside_multi_ms_groups"] += sum(len(g) for g in timestamp_groups if len(g) > 1)
        for left, right in zip(timestamp_groups, timestamp_groups[1:]):
            if len(left) != 1 or len(right) != 1:
                chains["adjacent_timestamp_group_pairs_unordered"] += 1
                continue
            earlier, later = left[0], right[0]
            if earlier["start_position"] is None or later["start_position"] is None:
                chains["single_pair_null_start"] += 1
                continue
            predicted = earlier["start_position"] + (
                earlier["size"] if earlier["side"] == "buy" else -earlier["size"]
            )
            if predicted == later["start_position"]:
                chains["single_event_pair_consistent"] += 1
            else:
                chains["single_event_pair_mismatch_unresolved"] += 1

    by_date: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    state_times: dict[str, int] = {}
    for row in snapshots:
        d = str(datetime.fromtimestamp(row["state_ts_ms"] / 1000, UTC).date())
        state_times[d] = row["state_ts_ms"]
        if ":" not in row["market"]:  # main-DEX only
            by_date[d][(row["wallet"], row["market"])] = row["signed_size"]
    anchor = Counter()
    days = pre["days"]
    for d0, d1 in zip(days, days[1:]):
        t0 = datetime.fromtimestamp(state_times[d0] / 1000, UTC)
        t1 = datetime.fromtimestamp(state_times[d1] / 1000, UTC)
        shared = set(by_date[d0]).intersection(by_date[d1])
        anchor["pairs_with_two_explicit_positions"] += len(shared)
        for key in shared:
            events = [r for r in per_market.get(key, []) if t0 < r["exchange_ts"] <= t1]
            anchor[
                "explicit_pairs_with_source_fills"
                if events
                else "explicit_pairs_without_source_fills"
            ] += 1
            delta = sum(
                (r["size"] if r["side"] == "buy" else -r["size"] for r in events),
                Decimal(0),
            )
            expected = by_date[d0][key] + float(delta)
            actual = by_date[d1][key]
            if abs(by_date[d0][key] - actual) > max(1e-7, 1e-9 * abs(actual)):
                anchor["explicit_pairs_with_position_change"] += 1
            if abs(expected - actual) <= max(1e-7, 1e-9 * abs(actual)):
                anchor["matching_endpoint_delta_pairs"] += 1
            else:
                anchor["mismatched_endpoint_delta_pairs"] += 1
        anchor["snapshot_pairs"] += 1
        anchor["positions_lacking_explicit_two_sided_anchor"] += len(
            set(by_date[d0]) ^ set(by_date[d1])
        )

    network = {}
    for d in days:
        trace = folder / f"network-{d}.strace"
        if not trace.is_file():
            network[d] = None
            continue
        received = 0
        matches = 0
        for line in trace.open(errors="ignore"):
            match = re.search(r"\b(recvfrom|recvmsg)\(.*\)\s+=\s+(\d+)", line)
            if match:
                received += int(match.group(2))
                matches += 1
        network[d] = {"received_bytes": received, "receive_calls": matches}

    result = {
        "asof_utc": datetime.now(UTC).isoformat(),
        "schema": "reservoir_wallet_pilot_parity_v2",
        "study_class": "RETROSPECTIVE_FIXED_COHORT_NOT_PIT_SELECTION",
        "days": days,
        "wallets": len(wallets),
        "summary": dict(group),
        "per_day": day_result,
        "fill_chain": dict(chains),
        "explicit_anchor_parity": dict(anchor),
        "network_receive_trace": network,
        "network_measurement_limit": (
            "Process recvfrom/recvmsg bytes incl TLS/other traffic, "
            "not measured billable S3 bytes; untraced days are null."
        ),
        "claim": "HISTORICAL_SOURCE_EVIDENCE_ONLY",
        "unknowns": [
            "historical_first_known_receipt",
            "complete_continuous_all_dex_position_books",
            "source-empty_days_versus_inactivity",
            "same_timestamp_ordering",
            "follower_executable_profit",
        ],
        "qualified": False,
    }
    path = folder / "parity-report-v2.json"
    if not path.exists():
        exclusive_bytes(path, (jdump(result) + "\n").encode())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "fetch", "report"))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 11, 5))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 11, 11))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--max-projected-mb", type=int, default=1300)
    parser.add_argument("--day", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    os.umask(0o077)
    with private_lock(args.out):
        if args.mode == "preflight":
            out = preflight(args.start, args.end, args.out, args.max_projected_mb * 1_000_000)
        elif args.mode == "fetch":
            out = fetch(args.out, str(args.day) if args.day else None)
        else:
            out = report(args.out)
    # Never print addresses; only aggregate research evidence.
    print(jdump(out))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Provider/SQL failures may contain private parameters or credentials.
        # The error type is safe to print; full private diagnostics stay local.
        print(
            jdump({"status": "BLOCKED", "error_type": type(exc).__name__}),
            file=sys.stderr,
        )
        sys.exit(2)
