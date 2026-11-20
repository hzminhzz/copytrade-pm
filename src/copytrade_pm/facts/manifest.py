"""SQLite manifest for the day-partitioned fact store (stdlib only).

The manifest is deliberately importable without Polars so that read-only
clients (research studies, ops tooling) can route to Parquet files without
pulling the writer stack — and without globbing a private filesystem.

Layout (``<root>/facts.sqlite``)::

    meta(key, value)
    datasets(kind, schema_version, schema_sha256, columns_json, description)
    sources(source_id, layer, priority, pinned_prefix, first_seen_at)
    days(kind, day, inputs_fingerprint, batch_sha16, rows, file_sha256,
         first_known_min_ms, first_known_max_ms, closed_at)      PK (kind, day)
    batches(batch_sha16, kind, day, path, rows, bytes, file_sha256,
            source_ids, created_at)                              PK (batch_sha16)
    inputs(kind, day, source_id, rel_path, input_sha256, rows_read,
           rows_kept, rows_duplicate_within, rows_duplicate_cross,
           rows_conflicting_values, rows_rejected, rows_null_key,
           first_known_at_ms)                     PK (kind, day, source_id, rel_path)
    runs(run_id, started_at, finished_at, status, totals_json)
    run_sources(run_id, kind, source_id, files_read, rows_read, rows_kept,
                rows_duplicate_within, rows_duplicate_cross,
                rows_conflicting_values, rows_rejected, rows_null_key)

A day row is the unit of idempotence: ``inputs_fingerprint`` is the SHA-256 of
the exact set of input files (relative path + content SHA + row count) that
produced ``batch_sha16``. Re-presenting the same inputs is a no-op; presenting a
different input set rebuilds the day from *all* recorded inputs, so a day can
never hold two competing batches.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

MANIFEST_NAME = "facts.sqlite"
MANIFEST_SCHEMA_VERSION = "facts-manifest-1.0.0"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets(
    kind TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    schema_sha256 TEXT NOT NULL,
    columns_json TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sources(
    source_id TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    priority INTEGER NOT NULL,
    pinned_prefix TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS days(
    kind TEXT NOT NULL,
    day TEXT NOT NULL,
    inputs_fingerprint TEXT NOT NULL,
    batch_sha16 TEXT NOT NULL,
    rows INTEGER NOT NULL,
    file_sha256 TEXT NOT NULL,
    first_known_min_ms INTEGER,
    first_known_max_ms INTEGER,
    closed_at TEXT NOT NULL,
    PRIMARY KEY(kind, day)
);
CREATE TABLE IF NOT EXISTS batches(
    batch_sha16 TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    day TEXT NOT NULL,
    path TEXT NOT NULL,
    rows INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    file_sha256 TEXT NOT NULL,
    source_ids TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS batches_kind_day ON batches(kind, day);
CREATE TABLE IF NOT EXISTS inputs(
    kind TEXT NOT NULL,
    day TEXT NOT NULL,
    source_id TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    rows_read INTEGER NOT NULL,
    rows_kept INTEGER NOT NULL,
    rows_duplicate_within INTEGER NOT NULL,
    rows_duplicate_cross INTEGER NOT NULL,
    rows_conflicting_values INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL,
    rows_null_key INTEGER NOT NULL,
    first_known_at_ms INTEGER,
    PRIMARY KEY(kind, day, source_id, rel_path)
);
CREATE INDEX IF NOT EXISTS inputs_kind_day ON inputs(kind, day);
CREATE TABLE IF NOT EXISTS day_sources(
    kind TEXT NOT NULL,
    day TEXT NOT NULL,
    source_id TEXT NOT NULL,
    files_read INTEGER NOT NULL,
    rows_read INTEGER NOT NULL,
    rows_kept INTEGER NOT NULL,
    rows_duplicate_within INTEGER NOT NULL,
    rows_duplicate_cross INTEGER NOT NULL,
    rows_conflicting_values INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL,
    rows_null_key INTEGER NOT NULL,
    rows_quantized_to_zero INTEGER NOT NULL,
    PRIMARY KEY(kind, day, source_id)
);
CREATE TABLE IF NOT EXISTS runs(
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    totals_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS run_sources(
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    files_read INTEGER NOT NULL,
    rows_read INTEGER NOT NULL,
    rows_kept INTEGER NOT NULL,
    rows_duplicate_within INTEGER NOT NULL,
    rows_duplicate_cross INTEGER NOT NULL,
    rows_conflicting_values INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL,
    rows_null_key INTEGER NOT NULL,
    PRIMARY KEY(run_id, kind, source_id)
);
"""


@dataclass(frozen=True, slots=True)
class DayBatch:
    """One closed day partition as recorded in the manifest."""

    kind: str
    day: str
    batch_sha16: str
    path: str
    rows: int
    file_sha256: str
    inputs_fingerprint: str

    def exists(self) -> bool:
        return Path(self.path).is_file()


@dataclass(frozen=True, slots=True)
class InputRecord:
    """One raw input file that contributed to a day partition."""

    kind: str
    day: str
    source_id: str
    rel_path: str
    input_sha256: str
    rows_read: int
    rows_kept: int
    rows_duplicate_within: int
    rows_duplicate_cross: int
    rows_conflicting_values: int
    rows_rejected: int
    rows_null_key: int
    first_known_at_ms: int | None = None


def manifest_path(root: Path | str) -> Path:
    return Path(root) / MANIFEST_NAME


def connect(root: Path | str, *, create: bool = False) -> sqlite3.Connection:
    """Open the manifest. ``create=False`` refuses to materialise a new store."""
    path = manifest_path(root)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        _chmod(path.parent, 0o700)
    elif not path.is_file():
        raise FileNotFoundError(f"FACTS_MANIFEST_MISSING:{path}")
    con = sqlite3.connect(path, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    if create:
        with con:
            con.executescript(_SCHEMA_SQL)
            con.execute(
                "INSERT INTO meta(key, value) VALUES('manifest_schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (MANIFEST_SCHEMA_VERSION,),
            )
        _chmod(path, 0o600)
    else:
        version = con.execute(
            "SELECT value FROM meta WHERE key = 'manifest_schema_version'"
        ).fetchone()
        if version is None or version["value"] != MANIFEST_SCHEMA_VERSION:
            con.close()
            raise ValueError(
                "FACTS_MANIFEST_SCHEMA_UNSUPPORTED:"
                f"{version['value'] if version else 'missing'} != {MANIFEST_SCHEMA_VERSION}"
            )
    return con


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:  # pragma: no cover - non-POSIX or read-only mount
        pass


def register_dataset(
    con: sqlite3.Connection,
    *,
    kind: str,
    schema_version: str,
    schema_sha256: str,
    columns: Sequence[str],
    description: str = "",
) -> None:
    with con:
        con.execute(
            """
            INSERT INTO datasets(kind, schema_version, schema_sha256, columns_json, description)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(kind) DO UPDATE SET
                schema_version = excluded.schema_version,
                schema_sha256 = excluded.schema_sha256,
                columns_json = excluded.columns_json,
                description = excluded.description
            """,
            (kind, schema_version, schema_sha256, json.dumps(list(columns)), description),
        )


def dataset_schema_sha(con: sqlite3.Connection, kind: str) -> str | None:
    row = con.execute("SELECT schema_sha256 FROM datasets WHERE kind = ?", (kind,)).fetchone()
    return None if row is None else str(row["schema_sha256"])


def register_source(
    con: sqlite3.Connection,
    *,
    source_id: str,
    layer: str,
    priority: int,
    pinned_prefix: str,
    first_seen_at: str,
) -> None:
    with con:
        con.execute(
            """
            INSERT INTO sources(source_id, layer, priority, pinned_prefix, first_seen_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                layer = excluded.layer,
                priority = excluded.priority,
                pinned_prefix = excluded.pinned_prefix
            """,
            (source_id, layer, priority, pinned_prefix, first_seen_at),
        )


def source_priorities(con: sqlite3.Connection) -> dict[str, int]:
    return {
        str(row["source_id"]): int(row["priority"])
        for row in con.execute("SELECT source_id, priority FROM sources")
    }


def day_batch(con: sqlite3.Connection, kind: str, day: str) -> DayBatch | None:
    row = con.execute(
        """
        SELECT d.kind, d.day, d.batch_sha16, d.rows, d.file_sha256, d.inputs_fingerprint,
               b.path
        FROM days d JOIN batches b ON b.batch_sha16 = d.batch_sha16
        WHERE d.kind = ? AND d.day = ?
        """,
        (kind, day),
    ).fetchone()
    if row is None:
        return None
    return DayBatch(
        kind=str(row["kind"]),
        day=str(row["day"]),
        batch_sha16=str(row["batch_sha16"]),
        path=str(row["path"]),
        rows=int(row["rows"]),
        file_sha256=str(row["file_sha256"]),
        inputs_fingerprint=str(row["inputs_fingerprint"]),
    )


def day_batches(
    con: sqlite3.Connection,
    kind: str,
    *,
    start_day: str | None = None,
    end_day: str | None = None,
) -> list[DayBatch]:
    query = (
        "SELECT d.kind, d.day, d.batch_sha16, d.rows, d.file_sha256, d.inputs_fingerprint, "
        "b.path FROM days d JOIN batches b ON b.batch_sha16 = d.batch_sha16 WHERE d.kind = ?"
    )
    params: list[Any] = [kind]
    if start_day is not None:
        query += " AND d.day >= ?"
        params.append(start_day)
    if end_day is not None:
        query += " AND d.day <= ?"
        params.append(end_day)
    query += " ORDER BY d.day ASC"
    return [
        DayBatch(
            kind=str(row["kind"]),
            day=str(row["day"]),
            batch_sha16=str(row["batch_sha16"]),
            path=str(row["path"]),
            rows=int(row["rows"]),
            file_sha256=str(row["file_sha256"]),
            inputs_fingerprint=str(row["inputs_fingerprint"]),
        )
        for row in con.execute(query, params)
    ]


def day_coverage(con: sqlite3.Connection, kind: str) -> list[tuple[str, int]]:
    return [
        (str(row["day"]), int(row["rows"]))
        for row in con.execute(
            "SELECT day, rows FROM days WHERE kind = ? ORDER BY day ASC", (kind,)
        )
    ]


def record_day(
    con: sqlite3.Connection,
    *,
    batch: DayBatch,
    source_ids: Sequence[str],
    bytes_count: int,
    inputs: Iterable[InputRecord],
    day_sources: Sequence[Mapping[str, Any]] = (),
    first_known_min_ms: int | None,
    first_known_max_ms: int | None,
    closed_at: str,
) -> None:
    """Commit one day atomically: day row, batch row, per-source and per-input accounting."""
    with con:
        con.execute(
            """
            INSERT INTO batches(batch_sha16, kind, day, path, rows, bytes, file_sha256,
                                source_ids, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(batch_sha16) DO UPDATE SET
                path = excluded.path,
                rows = excluded.rows,
                bytes = excluded.bytes,
                file_sha256 = excluded.file_sha256,
                source_ids = excluded.source_ids
            """,
            (
                batch.batch_sha16,
                batch.kind,
                batch.day,
                batch.path,
                batch.rows,
                bytes_count,
                batch.file_sha256,
                ",".join(sorted(source_ids)),
                closed_at,
            ),
        )
        con.execute(
            """
            INSERT INTO days(kind, day, inputs_fingerprint, batch_sha16, rows, file_sha256,
                             first_known_min_ms, first_known_max_ms, closed_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, day) DO UPDATE SET
                inputs_fingerprint = excluded.inputs_fingerprint,
                batch_sha16 = excluded.batch_sha16,
                rows = excluded.rows,
                file_sha256 = excluded.file_sha256,
                first_known_min_ms = excluded.first_known_min_ms,
                first_known_max_ms = excluded.first_known_max_ms,
                closed_at = excluded.closed_at
            """,
            (
                batch.kind,
                batch.day,
                batch.inputs_fingerprint,
                batch.batch_sha16,
                batch.rows,
                batch.file_sha256,
                first_known_min_ms,
                first_known_max_ms,
                closed_at,
            ),
        )
        con.execute("DELETE FROM inputs WHERE kind = ? AND day = ?", (batch.kind, batch.day))
        con.executemany(
            """
            INSERT INTO inputs(kind, day, source_id, rel_path, input_sha256, rows_read,
                               rows_kept, rows_duplicate_within, rows_duplicate_cross,
                               rows_conflicting_values, rows_rejected, rows_null_key,
                               first_known_at_ms)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    rec.kind,
                    rec.day,
                    rec.source_id,
                    rec.rel_path,
                    rec.input_sha256,
                    rec.rows_read,
                    rec.rows_kept,
                    rec.rows_duplicate_within,
                    rec.rows_duplicate_cross,
                    rec.rows_conflicting_values,
                    rec.rows_rejected,
                    rec.rows_null_key,
                    rec.first_known_at_ms,
                )
                for rec in inputs
            ],
        )
        con.execute("DELETE FROM day_sources WHERE kind = ? AND day = ?", (batch.kind, batch.day))
        con.executemany(
            """
            INSERT INTO day_sources(kind, day, source_id, files_read, rows_read, rows_kept,
                                    rows_duplicate_within, rows_duplicate_cross,
                                    rows_conflicting_values, rows_rejected, rows_null_key,
                                    rows_quantized_to_zero)
            VALUES(:kind, :day, :source_id, :files_read, :rows_read, :rows_kept,
                   :rows_duplicate_within, :rows_duplicate_cross, :rows_conflicting_values,
                   :rows_rejected, :rows_null_key, :rows_quantized_to_zero)
            """,
            [
                {
                    "kind": batch.kind,
                    "day": batch.day,
                    "source_id": row["source_id"],
                    "files_read": row.get("files_read", 0),
                    "rows_read": row.get("rows_read", 0),
                    "rows_kept": row.get("rows_kept", 0),
                    "rows_duplicate_within": row.get("rows_duplicate_within", 0),
                    "rows_duplicate_cross": row.get("rows_duplicate_cross", 0),
                    "rows_conflicting_values": row.get("rows_conflicting_values", 0),
                    "rows_rejected": row.get("rows_rejected", 0),
                    "rows_null_key": row.get("rows_null_key", 0),
                    "rows_quantized_to_zero": row.get("rows_quantized_to_zero", 0),
                }
                for row in day_sources
            ],
        )


def day_inputs(con: sqlite3.Connection, kind: str, day: str) -> list[InputRecord]:
    return [
        InputRecord(
            kind=str(row["kind"]),
            day=str(row["day"]),
            source_id=str(row["source_id"]),
            rel_path=str(row["rel_path"]),
            input_sha256=str(row["input_sha256"]),
            rows_read=int(row["rows_read"]),
            rows_kept=int(row["rows_kept"]),
            rows_duplicate_within=int(row["rows_duplicate_within"]),
            rows_duplicate_cross=int(row["rows_duplicate_cross"]),
            rows_conflicting_values=int(row["rows_conflicting_values"]),
            rows_rejected=int(row["rows_rejected"]),
            rows_null_key=int(row["rows_null_key"]),
            first_known_at_ms=None
            if row["first_known_at_ms"] is None
            else int(row["first_known_at_ms"]),
        )
        for row in con.execute(
            "SELECT * FROM inputs WHERE kind = ? AND day = ? ORDER BY source_id, rel_path",
            (kind, day),
        )
    ]


def day_sources(con: sqlite3.Connection, kind: str, day: str) -> list[dict[str, Any]]:
    """Authoritative per-source reconciliation for one closed day."""
    return [
        {
            "source_id": str(row["source_id"]),
            "files_read": int(row["files_read"]),
            "rows_read": int(row["rows_read"]),
            "rows_kept": int(row["rows_kept"]),
            "rows_duplicate_within": int(row["rows_duplicate_within"]),
            "rows_duplicate_cross": int(row["rows_duplicate_cross"]),
            "rows_conflicting_values": int(row["rows_conflicting_values"]),
            "rows_rejected": int(row["rows_rejected"]),
            "rows_null_key": int(row["rows_null_key"]),
            "rows_quantized_to_zero": int(row["rows_quantized_to_zero"]),
        }
        for row in con.execute(
            "SELECT * FROM day_sources WHERE kind = ? AND day = ? ORDER BY source_id",
            (kind, day),
        )
    ]


def orphan_batches(con: sqlite3.Connection) -> list[Path]:
    """Batch files on disk the manifest does not reference."""
    referenced = {Path(str(row["path"])) for row in con.execute("SELECT path FROM batches")}
    root_row = con.execute("SELECT value FROM meta WHERE key = 'store_root'").fetchone()
    if root_row is None:
        return []
    root = Path(str(root_row["value"]))
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.parquet") if p not in referenced)


def start_run(con: sqlite3.Connection, *, run_id: str, started_at: str) -> None:
    with con:
        con.execute(
            "INSERT INTO runs(run_id, started_at, status) VALUES(?, ?, 'RUNNING')",
            (run_id, started_at),
        )


def finish_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    finished_at: str,
    status: str,
    totals: dict[str, Any],
    sources: Sequence[dict[str, Any]] = (),
) -> None:
    with con:
        con.execute(
            "UPDATE runs SET finished_at = ?, status = ?, totals_json = ? WHERE run_id = ?",
            (finished_at, status, json.dumps(totals, sort_keys=True, default=str), run_id),
        )
        con.execute("DELETE FROM run_sources WHERE run_id = ?", (run_id,))
        con.executemany(
            """
            INSERT INTO run_sources(run_id, kind, source_id, files_read, rows_read, rows_kept,
                                    rows_duplicate_within, rows_duplicate_cross,
                                    rows_conflicting_values, rows_rejected, rows_null_key)
            VALUES(:run_id, :kind, :source_id, :files_read, :rows_read, :rows_kept,
                   :rows_duplicate_within, :rows_duplicate_cross, :rows_conflicting_values,
                   :rows_rejected, :rows_null_key)
            """,
            [{"run_id": run_id, **row} for row in sources],
        )


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    with con:
        con.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_meta(con: sqlite3.Connection, key: str) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def runs(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {
            "run_id": str(row["run_id"]),
            "started_at": str(row["started_at"]),
            "finished_at": None if row["finished_at"] is None else str(row["finished_at"]),
            "status": str(row["status"]),
            "totals": json.loads(str(row["totals_json"])),
        }
        for row in con.execute("SELECT * FROM runs ORDER BY started_at ASC")
    ]
