"""Idempotent, reconciling migration into the day-partitioned :class:`FactStore`.

The unit of work is ``(kind, day)``. For each day the engine:

1. indexes every discovered input to the days its rows actually fall in;
2. fingerprints the day's exact input set (relative path + content SHA + rows);
3. no-ops when the manifest already records that fingerprint and the batch file
   still hashes to the recorded value;
4. otherwise rebuilds the day from **all** recorded inputs — deterministic
   priority order, dedupe by fact identity, intake-only same-ms repair — writes
   one immutable batch and commits the reconciliation in one transaction.

Every row is accounted for exactly once::

    sum(rows_read) == sum(rows_kept)        # written
                    + sum(rows_duplicate_within)
                    + sum(rows_duplicate_cross)
                    + sum(rows_null_key)
                    + sum(rows_rejected)

``rows_conflicting_values`` is an *of which* counter: a dropped duplicate whose
payload disagrees with the winner is already inside one of the duplicate buckets
and is never added twice.

and ``sum(rows_kept) == rows in the day batch``. A day that fails either
identity raises before anything is committed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

try:  # pragma: no cover - the core CI leg runs without the `market` extra
    import polars as pl  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    pl = None  # type: ignore[assignment]

from . import manifest as mf
from .repair import DEFAULT_TOLERANCE, RepairStats
from .schemas import (
    KNOWN_AT_BASIS_FETCH_CLOCK,
    KNOWN_AT_BASIS_UNRECORDED,
    IDENTITY_COLUMNS,
    column_names,
)
from .sources import (
    ADAPTERS,
    KINDS_BY_LAYER,
    InputFile,
    SourceLayer,
    SourceSpec,
    timestamp_to_ms,
    discover_inputs,
    empty_frame,
    file_sha256,
)
from .store import FactStore, PreparedDay, WriteReceipt

DAY_MS = 86_400_000


def _require_polars():
    if pl is None:  # pragma: no cover
        raise MigrationError("POLARS_REQUIRED: install the `market` extra")
    return pl


#: Columns that describe provenance rather than the fact itself; excluded from
#: conflict detection so a repeated fact from another source is not "conflict".
PROVENANCE_COLUMNS = frozenset(
    {
        "source_id",
        "source_rank",
        "arrival_seq",
        "batch_sha16",
        "first_known_at_ms",
        "known_at_basis",
        "dex_raw",
        "provider",
        "source_ts",
    }
)

INPUT_SEQ = "_input_seq"


class MigrationError(RuntimeError):
    """Fail-closed migration error naming the violated invariant."""


@dataclass(frozen=True, slots=True)
class PlannedInput:
    """One input file attributed to one ``(kind, day)``."""

    source: SourceSpec
    input_file: InputFile
    rows: int
    first_known_at_ms: int | None


@dataclass(frozen=True, slots=True)
class SourceRowTotals:
    """Per-source accounting for one kind."""

    source_id: str
    files_read: int = 0
    rows_read: int = 0
    rows_kept: int = 0
    rows_duplicate_within: int = 0
    rows_duplicate_cross: int = 0
    rows_conflicting_values: int = 0
    rows_rejected: int = 0
    rows_null_key: int = 0
    rows_quantized_to_zero: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "files_read": self.files_read,
            "rows_read": self.rows_read,
            "rows_kept": self.rows_kept,
            "rows_duplicate_within": self.rows_duplicate_within,
            "rows_duplicate_cross": self.rows_duplicate_cross,
            "rows_conflicting_values": self.rows_conflicting_values,
            "rows_rejected": self.rows_rejected,
            "rows_null_key": self.rows_null_key,
            "rows_quantized_to_zero": self.rows_quantized_to_zero,
        }


@dataclass(frozen=True, slots=True)
class DayOutcome:
    kind: str
    day: str
    status: str  # CREATED | REBUILT | UNCHANGED | DRY_RUN_*
    rows: int
    batch_sha16: str
    inputs_fingerprint: str
    repair: RepairStats = RepairStats()

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "day": self.day,
            "status": self.status,
            "rows": self.rows,
            "batch_sha16": self.batch_sha16,
            "inputs_fingerprint": self.inputs_fingerprint,
            "repair": self.repair.as_dict(),
        }


@dataclass(slots=True)
class MigrationReceipt:
    run_id: str
    started_at: str
    finished_at: str
    store_root: str
    kinds: tuple[str, ...]
    sources_used: tuple[str, ...]
    sources_not_supplied: tuple[str, ...]
    sources_empty: tuple[str, ...]
    unmigrated_kinds: tuple[str, ...]
    dry_run: bool = False
    days: list[DayOutcome] = field(default_factory=list)
    totals: dict[str, dict[str, int]] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        # ``receipt_sha256`` identifies the *store state* the run produced, so it
        # excludes the per-run status (CREATED vs UNCHANGED) and repair counters:
        # a correct rerun of the same inputs must reproduce it byte-for-byte.
        state_days = [
            {
                "kind": day.kind,
                "day": day.day,
                "rows": day.rows,
                "batch_sha16": day.batch_sha16,
                "inputs_fingerprint": day.inputs_fingerprint,
            }
            for day in self.days
        ]
        receipt_sha = hashlib.sha256(
            json.dumps(
                {
                    "kinds": list(self.kinds),
                    "sources_used": list(self.sources_used),
                    "totals": self.totals,
                    "days": state_days,
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "store_root": self.store_root,
            "dry_run": self.dry_run,
            "kinds": list(self.kinds),
            "sources_used": list(self.sources_used),
            "sources_not_supplied": list(self.sources_not_supplied),
            "sources_empty": list(self.sources_empty),
            "unmigrated_kinds": list(self.unmigrated_kinds),
            "days_total": len(self.days),
            "days_created": sum(1 for day in self.days if day.status == "CREATED"),
            "days_rebuilt": sum(1 for day in self.days if day.status == "REBUILT"),
            "days_unchanged": sum(1 for day in self.days if day.status == "UNCHANGED"),
            "days_dry_run": sum(1 for day in self.days if day.status.startswith("DRY_RUN")),
            "totals": self.totals,
            "reconciliation": self.reconciliation,
            "notes": self.notes,
            "receipt_sha256": receipt_sha,
        }


@dataclass(frozen=True, slots=True)
class DayAccounting:
    per_source: dict[str, SourceRowTotals]
    per_input: dict[tuple[str, str], int]
    rows_written: int


@dataclass(frozen=True, slots=True)
class DedupeResult:
    frame: Any
    kept_by_source: dict[str, int]
    kept_by_input: dict[str, int]
    duplicate_within: dict[str, int]
    duplicate_cross: dict[str, int]
    conflicts: dict[str, int]
    null_key: dict[str, int]


def source_totals(
    kind: str,
    source_ids: Iterable[str],
    *,
    per_source: Mapping[str, Mapping[str, int]],
) -> dict[tuple[str, str], SourceRowTotals]:
    out: dict[tuple[str, str], SourceRowTotals] = {}
    for source_id in source_ids:
        values = dict(per_source.get(source_id, {}))
        out[(kind, source_id)] = SourceRowTotals(source_id=source_id, **values)
    return out


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _fingerprint(inputs: Sequence[PlannedInput]) -> str:
    payload = "\n".join(
        f"{item.source.source_id}|{item.input_file.rel_path}|{item.input_file.sha256}|{item.rows}"
        for item in sorted(inputs, key=lambda it: (it.source.priority, it.input_file.rel_path))
    )
    return _sha256(payload)


def _timestamp_column(kind: str, schema: Mapping[str, Any]) -> str:
    candidates = (
        ("exchange_ts", "ts", "event_ts_ms", "time")
        if kind == "fills"
        else ("snapshot_ts", "ts", "event_ts_ms", "time")
    )
    for name in candidates:
        if name in schema:
            return name
    raise MigrationError(f"SOURCE_TIMESTAMP_COLUMN_MISSING:{kind}")


def day_from_rel_path(rel_path: str) -> str | None:
    """Read a ``day=YYYY-MM-DD`` hive segment out of a relative path, if any."""
    for part in rel_path.split("/"):
        if part.startswith("day=") and len(part) == 14:
            candidate = part[4:]
            try:
                datetime.fromisoformat(candidate)
            except ValueError:
                return None
            return candidate
    return None


def index_input_days(input_file: InputFile, kind: str) -> dict[str, int]:
    """Return ``{day: row_count}`` for every UTC day present in ``input_file``.

    A file with zero rows and a ``day=`` path segment is attributed to that day
    with a count of ``0``. That keeps "we read this day and it was empty"
    distinguishable from "we never had this day", so a research coverage gate can
    tell a quiet day from a truncated archive instead of treating both as absent.
    """
    if pl is None:  # pragma: no cover
        raise MigrationError("POLARS_REQUIRED: install the `market` extra")
    schema = pl.scan_parquet(input_file.path).collect_schema()
    timestamp = _timestamp_column(kind, schema)
    frame = pl.read_parquet(input_file.path, columns=[timestamp])
    if frame.height == 0:
        fallback = day_from_rel_path(input_file.rel_path)
        return {fallback: 0} if fallback else {}
    ms = timestamp_to_ms(frame, timestamp, source_id=input_file.source_id)
    counts = (
        pl.DataFrame({"day_index": (ms // DAY_MS).cast(pl.Int64)})
        .group_by("day_index")
        .agg(pl.len().alias("rows"))
        .sort("day_index")
    )
    return {
        datetime.fromtimestamp(int(day) * 86400, tz=UTC).date().isoformat(): int(rows)
        for day, rows in zip(counts["day_index"].to_list(), counts["rows"].to_list(), strict=True)
    }


def wallet_store_clocks(root: Path | str, *, catalog: Path | str | None = None) -> dict[str, int]:
    """Map legacy partition identity -> recorded ``fetched_at`` epoch ms.

    Wallet-store rows predate any per-row clock. The only recorded evidence is
    the catalog's per-partition ``fetched_at``; it is used verbatim, and a
    partition with no catalog row keeps ``first_known_at_ms = None`` (basis
    ``unrecorded``) rather than gaining an invented timestamp.
    """
    base = Path(root).expanduser()
    path = Path(catalog).expanduser() if catalog is not None else base / "catalog.sqlite"
    if not path.is_file():
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT kind, wallet, day, path, fetched_at FROM partitions").fetchall()
    except sqlite3.DatabaseError:
        return {}
    finally:
        con.close()
    clocks: dict[str, int] = {}
    for row in rows:
        try:
            stamp = datetime.fromisoformat(str(row["fetched_at"]))
        except TypeError, ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        ms = round(stamp.timestamp() * 1000)
        for key in (
            f"{row['kind']}|{str(row['wallet']).lower()}|{row['day']}",
            str(row["path"]),
        ):
            clocks[key] = min(ms, clocks.get(key, ms))
    return clocks


def _wallet_store_clock_for(clocks: Mapping[str, int], input_file: InputFile) -> int | None:
    direct = clocks.get(str(input_file.path)) or clocks.get(str(input_file.path.resolve()))
    if direct is not None:
        return direct
    parts = input_file.rel_path.split("/")
    try:
        kind = parts[0]
        wallet = next(part.split("=", 1)[1] for part in parts if part.startswith("wallet="))
        year = next(part.split("=", 1)[1] for part in parts if part.startswith("year="))
        month = next(part.split("=", 1)[1] for part in parts if part.startswith("month="))
        day = next(part.split("=", 1)[1] for part in parts if part.startswith("day="))
    except IndexError, StopIteration:
        return None
    return clocks.get(f"{kind}|{wallet.lower()}|{year}-{month}-{day}")


def _value_columns(kind: str) -> list[str]:
    return [name for name in column_names(kind) if name not in PROVENANCE_COLUMNS]


def _identity_expression(kind: str):
    if pl is None:  # pragma: no cover
        raise MigrationError("POLARS_REQUIRED: install the `market` extra")
    if kind == "fills":
        return (
            pl.when(pl.col("trade_id").is_not_null())
            .then(
                pl.concat_str(
                    [
                        pl.col("wallet"),
                        pl.lit("|"),
                        pl.col("coin"),
                        pl.lit("|"),
                        pl.col("trade_id"),
                    ]
                )
            )
            .otherwise(
                pl.concat_str(
                    [
                        pl.col("wallet"),
                        pl.lit("|"),
                        pl.col("coin"),
                        pl.lit("|"),
                        pl.col("event_ts_ms").cast(pl.String),
                        pl.lit("|"),
                        pl.col("side").cast(pl.String),
                        pl.lit("|"),
                        pl.col("size").cast(pl.String),
                        pl.lit("|"),
                        pl.col("price").cast(pl.String),
                    ]
                )
            )
        )
    if kind in IDENTITY_COLUMNS:
        keys = IDENTITY_COLUMNS[kind]
        return (
            pl.when(pl.all_horizontal([pl.col(name).is_not_null() for name in keys]))
            .then(pl.concat_str([pl.col(name).cast(pl.String) for name in keys], separator="|"))
            .otherwise(None)
        )
    return pl.concat_str(
        [
            pl.col("wallet"),
            pl.lit("|"),
            pl.col("symbol"),
            pl.lit("|"),
            pl.col("dex"),
            pl.lit("|"),
            pl.col("event_ts_ms").cast(pl.String),
        ]
    )


def _values_expression(kind: str):
    if pl is None:  # pragma: no cover
        raise MigrationError("POLARS_REQUIRED: install the `market` extra")
    return pl.concat_str(
        [
            pl.col(name).cast(pl.String, strict=False).fill_null("\\x00")
            for name in _value_columns(kind)
        ],
        separator="\\x1f",
    )


def _group_counts(frame, column: str) -> dict[str, int]:
    pl = _require_polars()
    return {
        str(row[column]): int(row["len"])
        for row in frame.group_by(column).agg(pl.len().alias("len")).iter_rows(named=True)
    }


def dedupe_day(frame, kind: str) -> DedupeResult:
    """Keep the highest-priority row per fact identity; count every drop."""
    if pl is None:  # pragma: no cover
        raise MigrationError("POLARS_REQUIRED: install the `market` extra")
    if frame.height == 0:
        return DedupeResult(frame, {}, {}, {}, {}, {}, {})

    keyed = frame.with_columns(
        _identity_expression(kind).alias("_identity"),
        _values_expression(kind).alias("_values"),
        pl.int_range(pl.len()).cast(pl.Int64).alias("_row"),
    )
    null_keyed = keyed.filter(pl.col("_identity").is_null())
    keyed = keyed.filter(pl.col("_identity").is_not_null())
    null_key = _group_counts(null_keyed, "source_id") if null_keyed.height else {}

    ordered = keyed.sort(["source_rank", "source_id", "_row"])
    winners = ordered.group_by("_identity").agg(pl.col("_row").min().alias("_row")).select("_row")
    kept_rows = ordered.join(winners, on="_row", how="semi")
    dropped = ordered.join(winners, on="_row", how="anti")

    kept_identity = kept_rows.select(
        "_identity",
        pl.col("_values").alias("_kept_values"),
        pl.col("source_id").alias("_kept_source"),
    )
    joined = dropped.join(kept_identity, on="_identity", how="inner")
    conflicts = _group_counts(
        joined.filter(pl.col("_values") != pl.col("_kept_values")), "source_id"
    )
    within: dict[str, int] = {}
    cross: dict[str, int] = {}
    for row in (
        joined.group_by("source_id", "_kept_source")
        .agg(pl.len().alias("len"))
        .iter_rows(named=True)
    ):
        source = str(row["source_id"])
        if source == str(row["_kept_source"]):
            within[source] = within.get(source, 0) + int(row["len"])
        else:
            cross[source] = cross.get(source, 0) + int(row["len"])

    kept = kept_rows.drop(["_identity", "_values", "_row"])
    return DedupeResult(
        frame=kept,
        kept_by_source=_group_counts(kept, "source_id"),
        kept_by_input=_group_counts(kept, INPUT_SEQ),
        duplicate_within=within,
        duplicate_cross=cross,
        conflicts=conflicts,
        null_key=null_key,
    )


class Migration:
    """Drives discovery, indexing, day rebuilds and reconciliation."""

    def __init__(
        self,
        *,
        store: FactStore,
        sources: Sequence[SourceSpec],
        kinds: Sequence[str] | None = None,
        tolerance=DEFAULT_TOLERANCE,
        dry_run: bool = False,
        pattern: str = "**/*.parquet",
        wallet_store_catalog: Path | str | None = None,
    ) -> None:
        self.store = store
        self.sources = tuple(sorted(sources, key=lambda spec: spec.priority))
        self.kinds = tuple(kinds) if kinds is not None else ("fills", "positions")
        self.tolerance = tolerance
        self.dry_run = dry_run
        self.pattern = pattern
        self.wallet_store_catalog = wallet_store_catalog
        self._clocks: dict[str, dict[str, int]] = {}

    # -- index -------------------------------------------------------------

    def build_plans(
        self,
    ) -> tuple[dict[tuple[str, str], list[PlannedInput]], list[str], list[str]]:
        """Return ``({(kind, day): [inputs]}, empty_sources, unmigrated_kinds)``."""
        plans: dict[tuple[str, str], list[PlannedInput]] = {}
        empty_sources: list[str] = []
        unmigrated: list[str] = []
        for spec in self.sources:
            for kind in self.kinds:
                if kind not in KINDS_BY_LAYER[spec.layer.value]:
                    continue
                inputs = discover_inputs(spec, kind, pattern=self.pattern)
                if not inputs:
                    empty_sources.append(f"{spec.source_id}:{kind}")
                    continue
                clocks: dict[str, int] = {}
                if spec.layer is SourceLayer.WALLET_STORE:
                    if spec.source_id not in self._clocks:
                        self._clocks[spec.source_id] = wallet_store_clocks(
                            spec.root, catalog=self.wallet_store_catalog
                        )
                    clocks = self._clocks[spec.source_id]
                for input_file in inputs:
                    days = index_input_days(input_file, kind)
                    if not days:
                        empty_sources.append(f"{spec.source_id}:{kind}:{input_file.rel_path}")
                        continue
                    first_known = (
                        _wallet_store_clock_for(clocks, input_file)
                        if spec.layer is SourceLayer.WALLET_STORE
                        else None
                    )
                    for day, rows in days.items():
                        plans.setdefault((kind, day), []).append(
                            PlannedInput(
                                source=spec,
                                input_file=input_file,
                                rows=rows,
                                first_known_at_ms=first_known,
                            )
                        )
            if spec.layer is SourceLayer.WALLET_STORE and spec.root.is_dir():
                for path in sorted(spec.root.iterdir()):
                    if (
                        path.is_dir()
                        and path.name not in KINDS_BY_LAYER["wallet_store"]
                        and path.name != ".metadata"
                        and any(path.rglob("*.parquet"))
                    ):
                        unmigrated.append(f"wallet_store:{path.name}")
        return plans, empty_sources, unmigrated

    # -- day ---------------------------------------------------------------

    def rebuild_day(
        self, kind: str, day: str, planned: Sequence[PlannedInput]
    ) -> tuple[DayAccounting, PreparedDay, WriteReceipt]:
        """Rebuild one day from all of its inputs and return exact accounting."""
        if pl is None:  # pragma: no cover
            raise MigrationError("POLARS_REQUIRED: install the `market` extra")
        ordered = sorted(planned, key=lambda it: (it.source.priority, it.input_file.rel_path))
        # Identity is (source_id, rel_path): two sources can publish the same
        # relative path (for example ``hyperliquid/fills/day=.../data.parquet``),
        # so a path-only key would attribute rows to the wrong source.
        input_ids = {
            (item.source.source_id, item.input_file.rel_path): index
            for index, item in enumerate(ordered)
        }
        frames = []
        accounting: dict[str, SourceRowTotals] = {}
        for item in ordered:
            accounting.setdefault(item.source.source_id, SourceRowTotals(item.source.source_id))
            frame = pl.read_parquet(item.input_file.path)
            adapter = ADAPTERS.get((item.source.layer, kind))
            if adapter is None:
                raise MigrationError(f"NO_ADAPTER:{item.source.layer.value}:{kind}")
            result = adapter(
                frame,
                source_id=item.source.source_id,
                source_rank=item.source.priority,
                first_known_at_ms=item.first_known_at_ms,
                known_at_basis=(
                    KNOWN_AT_BASIS_FETCH_CLOCK
                    if item.first_known_at_ms is not None
                    else KNOWN_AT_BASIS_UNRECORDED
                ),
            )
            current = accounting[item.source.source_id]
            accounting[item.source.source_id] = _bump(
                current,
                files_read=1,
                rows_read=result.rows_read,
                rows_quantized_to_zero=result.rows_quantized_to_zero,
            )
            valid = result.frame.filter(
                pl.col("wallet").is_not_null() & pl.col("event_ts_ms").is_not_null()
            )
            rejected = result.rows_read - valid.height
            if rejected:
                accounting[item.source.source_id] = _bump(
                    accounting[item.source.source_id], rows_rejected=rejected
                )
            if valid.height:
                frames.append(
                    valid.with_columns(
                        pl.lit(
                            input_ids[(item.source.source_id, item.input_file.rel_path)],
                            dtype=pl.UInt32,
                        ).alias(INPUT_SEQ)
                    )
                )

        rows_read_total = sum(totals.rows_read for totals in accounting.values())
        if not frames:
            if rows_read_total:
                raise MigrationError(f"NO_VALID_ROWS:{kind}:{day}:read={rows_read_total}")
            # Every input was read and empty: close the day with an explicit
            # zero-row batch so "read and empty" is never confused with "absent".
            empty = empty_frame(kind)
            prepared = self.store.prepare_day(kind, day, empty, tolerance=self.tolerance)
            write = self.store.write_day(prepared, dry_run=self.dry_run, allow_empty=True)
            return (
                DayAccounting(
                    per_source=accounting,
                    per_input={key: 0 for key in input_ids},
                    rows_written=0,
                ),
                prepared,
                write,
            )
        combined = pl.concat(frames, how="vertical_relaxed")
        deduped = dedupe_day(combined, kind)
        by_input_index = {
            int(key): value for key, value in _raw_group_counts(deduped.frame, INPUT_SEQ).items()
        }
        per_input = {
            (item.source.source_id, item.input_file.rel_path): by_input_index.get(index, 0)
            for index, item in enumerate(ordered)
        }
        for source_id, totals in list(accounting.items()):
            accounting[source_id] = _bump(
                totals,
                rows_kept=deduped.kept_by_source.get(source_id, 0),
                rows_duplicate_within=deduped.duplicate_within.get(source_id, 0),
                rows_duplicate_cross=deduped.duplicate_cross.get(source_id, 0),
                rows_conflicting_values=deduped.conflicts.get(source_id, 0),
                rows_null_key=deduped.null_key.get(source_id, 0),
            )
        prepared = self.store.prepare_day(kind, day, deduped.frame, tolerance=self.tolerance)
        write = self.store.write_day(prepared, dry_run=self.dry_run)
        self._assert_identities(kind, day, accounting, prepared.rows)
        return (
            DayAccounting(
                per_source=accounting,
                per_input=per_input,
                rows_written=prepared.rows,
            ),
            prepared,
            write,
        )

    @staticmethod
    def _assert_identities(
        kind: str,
        day: str,
        accounting: Mapping[str, SourceRowTotals],
        rows_written: int,
    ) -> None:
        read = sum(totals.rows_read for totals in accounting.values())
        accounted = sum(
            totals.rows_kept
            + totals.rows_duplicate_within
            + totals.rows_duplicate_cross
            + totals.rows_null_key
            + totals.rows_rejected
            for totals in accounting.values()
        )
        if read != accounted:
            raise MigrationError(
                f"ROW_ACCOUNTING_MISMATCH:{kind}:{day}:read={read}:accounted={accounted}:"
                f"detail={ {sid: totals.as_dict() for sid, totals in accounting.items()} }"
            )
        duplicate_rows = sum(
            totals.rows_duplicate_within + totals.rows_duplicate_cross
            for totals in accounting.values()
        )
        conflicting = sum(totals.rows_conflicting_values for totals in accounting.values())
        if conflicting > duplicate_rows:
            raise MigrationError(
                f"CONFLICT_COUNTER_NOT_A_SUBSET:{kind}:{day}:"
                f"conflicting={conflicting}:duplicates={duplicate_rows}"
            )
        kept = sum(totals.rows_kept for totals in accounting.values())
        if kept != rows_written:
            raise MigrationError(
                f"WRITTEN_ROW_MISMATCH:{kind}:{day}:kept={kept}:written={rows_written}"
            )

    # -- run ---------------------------------------------------------------

    def run(self, receipt: MigrationReceipt) -> MigrationReceipt:
        con = (
            None
            if self.dry_run and not self.store.manifest_path.is_file()
            else self.store.connect()
        )
        plans, empty_sources, unmigrated = self.build_plans()
        receipt.sources_empty = tuple(sorted(set(empty_sources) | set(receipt.sources_empty)))
        receipt.unmigrated_kinds = tuple(sorted(set(unmigrated)))
        totals: dict[tuple[str, str], dict[str, int]] = {}
        reconciliation: dict[str, dict[str, Any]] = {}
        for kind, day in sorted(plans):
            planned = plans[(kind, day)]
            fingerprint = _fingerprint(planned)
            existing = mf.day_batch(con, kind, day) if con is not None else None
            if (
                not self.dry_run
                and con is not None
                and existing is not None
                and existing.inputs_fingerprint == fingerprint
                and existing.exists()
                and file_sha256(Path(existing.path)) == existing.file_sha256
            ):
                receipt.days.append(
                    DayOutcome(
                        kind=kind,
                        day=day,
                        status="UNCHANGED",
                        rows=existing.rows,
                        batch_sha16=existing.batch_sha16,
                        inputs_fingerprint=fingerprint,
                    )
                )
                for record in mf.day_sources(con, kind, day):
                    source_id = str(record.pop("source_id"))
                    merge_into(totals.setdefault((kind, source_id), {}), record)
                summary = reconciliation.setdefault(kind, _empty_summary())
                summary["days_unchanged"] += 1
                summary["rows"] += existing.rows
                continue

            accounting, prepared, write = self.rebuild_day(kind, day, planned)
            status = ("DRY_RUN_" if self.dry_run else "") + (
                "REBUILT" if existing is not None else "CREATED"
            )
            if not self.dry_run:
                assert con is not None
                known = [
                    int(value)
                    for value in prepared.frame["first_known_at_ms"].to_list()
                    if value is not None
                ]
                mf.record_day(
                    con,
                    batch=mf.DayBatch(
                        kind=kind,
                        day=day,
                        batch_sha16=write.batch_sha16,
                        path=str(write.path),
                        rows=write.rows,
                        file_sha256=write.file_sha256,
                        inputs_fingerprint=fingerprint,
                    ),
                    source_ids=sorted(accounting.per_source),
                    bytes_count=write.bytes_count,
                    inputs=[
                        mf.InputRecord(
                            kind=kind,
                            day=day,
                            source_id=item.source.source_id,
                            rel_path=item.input_file.rel_path,
                            input_sha256=item.input_file.sha256,
                            rows_read=item.rows,
                            rows_kept=accounting.per_input.get(
                                (item.source.source_id, item.input_file.rel_path), 0
                            ),
                            rows_duplicate_within=0,
                            rows_duplicate_cross=0,
                            rows_conflicting_values=0,
                            rows_rejected=0,
                            rows_null_key=0,
                            first_known_at_ms=item.first_known_at_ms,
                        )
                        for item in sorted(
                            planned,
                            key=lambda it: (it.source.priority, it.input_file.rel_path),
                        )
                    ],
                    day_sources=[
                        {"source_id": totals.source_id, **totals.as_dict()}
                        for totals in accounting.per_source.values()
                    ],
                    first_known_min_ms=min(known) if known else None,
                    first_known_max_ms=max(known) if known else None,
                    closed_at=now_iso(),
                )
            receipt.days.append(
                DayOutcome(
                    kind=kind,
                    day=day,
                    status=status,
                    rows=accounting.rows_written,
                    batch_sha16=write.batch_sha16,
                    inputs_fingerprint=fingerprint,
                    repair=prepared.repair_stats,
                )
            )
            for source_id, source_totals_row in accounting.per_source.items():
                merge_into(totals.setdefault((kind, source_id), {}), source_totals_row.as_dict())
            summary = reconciliation.setdefault(kind, _empty_summary())
            summary["days_rebuilt"] += 1
            summary["rows"] += accounting.rows_written
            for key, value in prepared.repair_stats.as_dict().items():
                summary[f"repair_{key}"] += value

        receipt.totals = {
            f"{kind}:{source_id}": dict(values)
            for (kind, source_id), values in sorted(totals.items())
        }
        for kind, summary in reconciliation.items():
            scoped = [
                values for key, values in receipt.totals.items() if key.startswith(f"{kind}:")
            ]
            summary["rows_read"] = sum(values.get("rows_read", 0) for values in scoped)
            summary["rows_quantized_to_zero"] = sum(
                values.get("rows_quantized_to_zero", 0) for values in scoped
            )
            summary["rows_written"] = sum(values.get("rows_kept", 0) for values in scoped)
            accounted = sum(
                values.get("rows_kept", 0)
                + values.get("rows_duplicate_within", 0)
                + values.get("rows_duplicate_cross", 0)
                + values.get("rows_null_key", 0)
                + values.get("rows_rejected", 0)
                for values in scoped
            )
            summary["rows_accounted"] = accounted
            summary["identity_holds"] = summary["rows_read"] == accounted
        receipt.reconciliation = reconciliation
        return receipt


def _empty_summary() -> dict[str, Any]:
    return {
        "days_rebuilt": 0,
        "days_unchanged": 0,
        "rows": 0,
        "rows_read": 0,
        "rows_written": 0,
        "rows_accounted": 0,
        "rows_quantized_to_zero": 0,
        "identity_holds": True,
        "repair_bursts": 0,
        "repair_bursts_repaired": 0,
        "repair_bursts_left_broken": 0,
        "repair_bursts_skipped_missing_start_position": 0,
        "repair_rows_moved": 0,
    }


def merge_into(target: dict[str, int], values: Mapping[str, int]) -> None:
    for key, value in values.items():
        target[key] = target.get(key, 0) + int(value)


def _bump(totals: SourceRowTotals, **deltas: int) -> SourceRowTotals:
    merged = totals.as_dict()
    merge_into(merged, deltas)
    return SourceRowTotals(source_id=totals.source_id, **merged)


def _raw_group_counts(frame, column: str) -> dict[Any, int]:
    pl = _require_polars()
    return {
        row[column]: int(row["len"])
        for row in frame.group_by(column).agg(pl.len().alias("len")).iter_rows(named=True)
    }


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def new_receipt(
    *,
    store_root: Path | str,
    sources: Sequence[SourceSpec],
    not_supplied: Sequence[str],
    kinds: Sequence[str],
    dry_run: bool = False,
    notes: Iterable[str] = (),
) -> MigrationReceipt:
    digest = hashlib.sha256(str(store_root).encode()).hexdigest()[:8]
    return MigrationReceipt(
        run_id=f"run-{uuid4().hex}-{digest}",
        started_at=now_iso(),
        finished_at="",
        store_root=str(store_root),
        kinds=tuple(kinds),
        sources_used=tuple(spec.source_id for spec in sources),
        sources_not_supplied=tuple(not_supplied),
        sources_empty=(),
        unmigrated_kinds=(),
        dry_run=dry_run,
        notes=list(notes),
    )
