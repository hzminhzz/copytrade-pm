"""Day-partitioned, immutable, bi-temporal :class:`FactStore`.

Physical layout::

    <root>/<kind>/day=YYYY-MM-DD/<batch_sha16>.parquet      zstd
    <root>/facts.sqlite                                     manifest

Invariants this module owns:

* **Exact decimal money.** Every financial column is ``Decimal(38, 12)`` in
  Parquet; no ``Float64`` write path exists here.
* **Immutable day batches.** A batch file name is its content identity. A day is
  either unchanged (same input fingerprint -> no write) or rebuilt into one new
  batch; a day never holds two competing files.
* **Intake-only ordering repair.** ``arrival_seq`` is assigned once, at ingest,
  after :func:`copytrade_pm.facts.repair.repair_same_ms_order`. Readers sort by
  ``(wallet, coin, event_ts_ms, arrival_seq)`` and never re-derive order.
* **Strict point-in-time reads.** ``scan(as_of=...)`` returns only rows whose
  ``first_known_at_ms`` is recorded and ``<= as_of``. Rows whose clock was never
  recorded stay invisible and are counted, never back-filled with a guess.
* **No roster imports.** This package owns raw facts only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import io
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Iterable, Sequence

try:  # pragma: no cover - the core CI leg runs without the `market` extra
    import polars as pl  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    pl = None  # type: ignore[assignment]

from . import manifest as mf
from .repair import DEFAULT_TOLERANCE, FillLink, RepairStats, repair_same_ms_order
from .schemas import (
    KIND_COLUMNS,
    SCHEMA_VERSION,
    ProvenanceTier,
    column_names,
    money_columns,
    schema_for,
    schema_sha,
)

SORT_KEYS: dict[str, tuple[str, ...]] = {
    "fills": ("wallet", "coin", "event_ts_ms", "source_rank", "arrival_seq"),
    "positions": ("wallet", "symbol", "event_ts_ms", "source_rank", "arrival_seq"),
    # Captured kinds sort on their full fact identity so the intake order (and
    # therefore the content-addressed batch name) is total, not tie-dependent.
    "equity": ("wallet", "account_scope", "event_ts_ms"),
    "funding": ("wallet", "coin", "event_ts_ms", "hash"),
    "ledger": ("wallet", "event_ts_ms", "hash", "kind"),
    "bars_1m": ("venue", "coin", "event_ts_ms"),
}
CHAIN_KEYS: dict[str, tuple[str, ...]] = {
    "fills": ("wallet", "coin"),
    "positions": ("wallet", "symbol"),
    "equity": ("wallet", "account_scope"),
    "funding": ("wallet", "coin"),
    "ledger": ("wallet",),
    "bars_1m": ("venue", "coin"),
}


class FactStoreError(RuntimeError):
    """Fail-closed store error; the message always names the violated rule."""


@dataclass(frozen=True, slots=True)
class Weighted:
    """One weighted sample from a coverage or reconciliation report."""

    label: str
    rows: int


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """What the store actually holds for a kind and window."""

    kind: str
    days_present: tuple[str, ...]
    rows_by_day: tuple[tuple[str, int], ...]
    missing_days: tuple[str, ...]
    rows: int
    files: int
    observed_fetch_rows: int
    retrospective_rows: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "days_present": len(self.days_present),
            "first_day": self.days_present[0] if self.days_present else None,
            "last_day": self.days_present[-1] if self.days_present else None,
            "missing_days": len(self.missing_days),
            "missing_days_sample": list(self.missing_days[:10]),
            "rows": self.rows,
            "files": self.files,
            "observed_fetch_rows": self.observed_fetch_rows,
            "retrospective_rows": self.retrospective_rows,
        }


@dataclass(frozen=True, slots=True)
class FactSlice:
    """A lazy, PIT-filtered view returned by :meth:`FactStore.scan`."""

    kind: str
    frame: Any
    as_of_ms: int | None
    tiers: tuple[ProvenanceTier, ...]
    allow_unknown_known_at: bool
    days: tuple[str, ...]
    files: int
    manifest_rows: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def collect(self):
        return self.frame.collect()

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "as_of_ms": self.as_of_ms,
            "tiers": [tier.value for tier in self.tiers],
            "allow_unknown_known_at": self.allow_unknown_known_at,
            "days": len(self.days),
            "files": self.files,
            "manifest_rows": self.manifest_rows,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    """Outcome of one immutable day write."""

    kind: str
    day: str
    batch_sha16: str
    path: Path
    rows: int
    bytes_count: int
    file_sha256: str
    created: bool


@dataclass(frozen=True, slots=True)
class PreparedDay:
    """Canonical rows for one day after ordering repair."""

    kind: str
    day: str
    frame: Any
    repair_stats: RepairStats

    @property
    def rows(self) -> int:
        return int(self.frame.height)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _require_polars():
    """Return the Polars module or fail closed when the extra is absent."""
    if pl is None:  # pragma: no cover
        raise FactStoreError("POLARS_REQUIRED: install the `market` extra")
    return pl


class FactStore:
    """Reader/writer for one fact-store root."""

    def __init__(self, root: Path | str, *, create: bool = False) -> None:
        self.root = Path(root).expanduser()
        self._con: sqlite3.Connection | None = None
        self._create = create
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
            _chmod(self.root, 0o700)

    # -- lifecycle ---------------------------------------------------------

    @property
    def manifest_path(self) -> Path:
        return mf.manifest_path(self.root)

    def connect(self) -> sqlite3.Connection:
        if self._con is None:
            self._con = mf.connect(self.root, create=self._create)
            if self._create:
                mf.set_meta(self._con, "store_root", str(self.root))
                mf.set_meta(self._con, "schema_version", SCHEMA_VERSION)
                for kind in KIND_COLUMNS:
                    mf.register_dataset(
                        self._con,
                        kind=kind,
                        schema_version=SCHEMA_VERSION,
                        schema_sha256=schema_sha(kind),
                        columns=column_names(kind),
                        description=f"canonical {kind} facts (Decimal(38,12))",
                    )
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> FactStore:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- paths -------------------------------------------------------------

    def day_dir(self, kind: str, day: str) -> Path:
        return self.root / kind / f"day={day}"

    # -- write -------------------------------------------------------------

    def prepare_day(
        self,
        kind: str,
        day: str,
        frame,
        *,
        tolerance=DEFAULT_TOLERANCE,
    ) -> PreparedDay:
        """Canonicalise row order for one day and assign ``arrival_seq`` once."""
        pl = _require_polars()
        if kind not in KIND_COLUMNS:
            raise FactStoreError(f"UNKNOWN_FACT_KIND:{kind}")
        if frame.height == 0:
            return PreparedDay(
                kind=kind, day=day, frame=empty_canonical(kind), repair_stats=RepairStats()
            )

        ordered = frame.sort(list(SORT_KEYS[kind]))
        if kind == "fills":
            ordered, stats = _repair_fills(ordered, tolerance=tolerance)
        else:
            stats = RepairStats()
            ordered = ordered.drop("arrival_seq").with_columns(
                pl.int_range(pl.len())
                .over(list(CHAIN_KEYS[kind]))
                .cast(pl.Int64)
                .alias("arrival_seq")
            )
        return PreparedDay(kind=kind, day=day, frame=ordered, repair_stats=stats)

    def write_day(
        self, prepared: PreparedDay, *, dry_run: bool = False, allow_empty: bool = False
    ) -> WriteReceipt:
        """Write one immutable day batch and return its receipt.

        The batch name is the SHA-256 prefix of the canonical Parquet payload
        computed with an empty ``batch_sha16`` placeholder, so identical content
        always lands on the same path and is never rewritten.
        """
        pl = _require_polars()
        kind, day = prepared.kind, prepared.day
        # Enforce the canonical schema at the write boundary: an adapter that
        # left an all-null column or an Int64 counter cannot change the Parquet
        # contract, and a schema drift can never reach a reader.
        frame = prepared.frame.select(column_names(kind)).cast(schema_for(kind), strict=False)
        if frame.height == 0 and not allow_empty:
            raise FactStoreError(f"EMPTY_DAY_BATCH:{kind}:{day}")

        # The day is part of the batch identity: two empty days would otherwise
        # share a content hash and collide in the manifest's primary key.
        identity_payload = _parquet_bytes(frame.with_columns(pl.lit("").alias("batch_sha16")))
        batch_sha16 = _sha256(day.encode() + identity_payload)[:16]
        final = frame.with_columns(pl.lit(batch_sha16).alias("batch_sha16"))
        expected = _parquet_bytes(final)

        directory = self.day_dir(kind, day)
        target = directory / f"{batch_sha16}.parquet"
        if dry_run:
            return WriteReceipt(
                kind=kind,
                day=day,
                batch_sha16=batch_sha16,
                path=target,
                rows=int(frame.height),
                bytes_count=len(expected),
                file_sha256=_sha256(expected),
                created=not target.exists(),
            )
        directory.mkdir(parents=True, exist_ok=True)
        _chmod(directory, 0o700)
        created = False
        if target.exists():
            if _sha256(target.read_bytes()) != _sha256(expected):
                raise FactStoreError(f"BATCH_CONTENT_CONFLICT:{kind}:{day}:{batch_sha16}")
        else:
            tmp = directory / f".{uuid.uuid4().hex}.tmp"
            tmp.write_bytes(expected)
            _fsync(tmp)
            _chmod(tmp, 0o600)
            os.replace(tmp, target)
            created = True
        file_sha256 = _sha256(target.read_bytes())
        self._remove_other_batches(directory, keep=target.name)
        return WriteReceipt(
            kind=kind,
            day=day,
            batch_sha16=batch_sha16,
            path=target,
            rows=int(frame.height),
            bytes_count=target.stat().st_size,
            file_sha256=file_sha256,
            created=created,
        )

    @staticmethod
    def _remove_other_batches(directory: Path, *, keep: str) -> None:
        for candidate in directory.glob("*.parquet"):
            if candidate.name != keep:
                candidate.unlink()

    # -- read --------------------------------------------------------------

    def scan(
        self,
        kind: str,
        *,
        wallets: Sequence[str] | str | None = None,
        coins: Sequence[str] | str | None = None,
        start_day: str | None = None,
        end_day: str | None = None,
        as_of_ms: int | None = None,
        tiers: Iterable[ProvenanceTier] | None = None,
        allow_unknown_known_at: bool = False,
    ) -> FactSlice:
        """Return a lazy slice, strictly filtered by the known-at clock.

        ``as_of_ms`` is a *known-at* bound: a row is visible only when the store
        recorded a first-seen clock and that clock is ``<= as_of_ms``. Rows with
        no recorded clock are excluded unless ``allow_unknown_known_at`` is set
        explicitly — they must never be treated as if they were known earlier.
        """
        pl = _require_polars()
        if kind not in KIND_COLUMNS:
            raise FactStoreError(f"UNKNOWN_FACT_KIND:{kind}")
        cols = column_names(kind)
        if wallets is not None and "wallet" not in cols:
            raise FactStoreError(f"KIND_HAS_NO_WALLET_COLUMN:{kind}")
        if coins is not None and "coin" not in cols:
            raise FactStoreError(f"KIND_HAS_NO_COIN_COLUMN:{kind}")
        requested_tiers = (
            tuple(tiers)
            if tiers is not None
            else (
                ProvenanceTier.OBSERVED_FETCH,
                ProvenanceTier.RETROSPECTIVE,
            )
        )
        if any(not isinstance(tier, ProvenanceTier) for tier in requested_tiers):
            raise FactStoreError("INVALID_PROVENANCE_TIER")
        con = self.connect()
        batches = mf.day_batches(con, kind, start_day=start_day, end_day=end_day)
        notes: list[str] = []
        if not batches:
            return FactSlice(
                kind=kind,
                frame=empty_canonical(kind).lazy(),
                as_of_ms=as_of_ms,
                tiers=requested_tiers,
                allow_unknown_known_at=allow_unknown_known_at,
                days=(),
                files=0,
                manifest_rows=0,
                notes=("NO_PARTITIONS",),
            )
        paths = [batch.path for batch in batches if batch.exists()]
        if len(paths) != len(batches):
            notes.append(f"MISSING_PARTITION_FILES:{len(batches) - len(paths)}")
        frame = pl.scan_parquet(paths)
        if wallets is not None:
            selected = [wallets] if isinstance(wallets, str) else list(wallets)
            frame = frame.filter(pl.col("wallet").is_in([w.lower() for w in selected]))
        if coins is not None:
            selected_coins = [coins] if isinstance(coins, str) else list(coins)
            frame = frame.filter(
                pl.col("coin").is_in([coin.strip().upper() for coin in selected_coins])
            )
        if not requested_tiers:
            frame = frame.limit(0)
        elif requested_tiers != (ProvenanceTier.OBSERVED_FETCH, ProvenanceTier.RETROSPECTIVE):
            tier_expr = None
            for tier in requested_tiers:
                branch = (
                    pl.col("first_known_at_ms").is_not_null()
                    if tier is ProvenanceTier.OBSERVED_FETCH
                    else pl.col("first_known_at_ms").is_null()
                )
                tier_expr = branch if tier_expr is None else (tier_expr | branch)
            if tier_expr is not None:
                frame = frame.filter(tier_expr)
        if as_of_ms is not None:
            if allow_unknown_known_at:
                frame = frame.filter(
                    pl.col("first_known_at_ms").is_null()
                    | (pl.col("first_known_at_ms") <= as_of_ms)
                )
                notes.append("UNKNOWN_KNOWN_AT_INCLUDED")
            else:
                frame = frame.filter(
                    pl.col("first_known_at_ms").is_not_null()
                    & (pl.col("first_known_at_ms") <= as_of_ms)
                )
                notes.append("UNKNOWN_KNOWN_AT_EXCLUDED")
        return FactSlice(
            kind=kind,
            frame=frame,
            as_of_ms=as_of_ms,
            tiers=requested_tiers,
            allow_unknown_known_at=allow_unknown_known_at,
            days=tuple(batch.day for batch in batches),
            files=len(paths),
            manifest_rows=sum(batch.rows for batch in batches),
            notes=tuple(notes),
        )

    def coverage(
        self,
        kind: str,
        *,
        start_day: str | None = None,
        end_day: str | None = None,
    ) -> CoverageReport:
        con = self.connect()
        rows = mf.day_coverage(con, kind)
        if start_day is not None:
            rows = [row for row in rows if row[0] >= start_day]
        if end_day is not None:
            rows = [row for row in rows if row[0] <= end_day]
        present = tuple(day for day, _ in rows)
        missing: tuple[str, ...] = ()
        if start_day is not None and end_day is not None and present:
            from .sources import day_range

            missing = tuple(day for day in day_range(start_day, end_day) if day not in set(present))
        tier_counts = {
            str(row["tier"]): int(row["rows"])
            for row in con.execute(
                """
                SELECT CASE WHEN first_known_at_ms IS NULL THEN 'RETROSPECTIVE'
                            ELSE 'OBSERVED_FETCH' END AS tier, sum(rows_kept) AS rows
                FROM inputs WHERE kind = ? GROUP BY tier
                """,
                (kind,),
            )
        }
        return CoverageReport(
            kind=kind,
            days_present=present,
            rows_by_day=tuple(rows),
            missing_days=missing,
            rows=sum(count for _, count in rows),
            files=len(present),
            observed_fetch_rows=tier_counts.get("OBSERVED_FETCH", 0),
            retrospective_rows=tier_counts.get("RETROSPECTIVE", 0),
        )

    def read_day(self, kind: str, day: str):
        """Return the single committed batch for ``(kind, day)``, or ``None``.

        Ingest merges onto the existing day so a later capture can never drop an
        earlier fact that this run did not re-observe. A day whose recorded file
        is missing or whose bytes no longer match the manifest fails closed: the
        ingest path must not silently rebuild a partition from partial evidence.
        """
        polars = _require_polars()
        if kind not in KIND_COLUMNS:
            raise FactStoreError(f"UNKNOWN_FACT_KIND:{kind}")
        con = self.connect()
        batch = mf.day_batch(con, kind, day)
        if batch is None:
            return None
        path = Path(batch.path)
        if not path.is_file():
            raise FactStoreError(f"DAY_BATCH_MISSING:{kind}:{day}")
        if _sha256(path.read_bytes()) != batch.file_sha256:
            raise FactStoreError(f"DAY_BATCH_SHA_MISMATCH:{kind}:{day}")
        return polars.read_parquet(path)

    def distinct_wallets(
        self,
        kinds: Sequence[str] = ("positions", "equity"),
        *,
        start_day: str | None = None,
        end_day: str | None = None,
    ) -> tuple[str, ...]:
        """Distinct wallets already present for ``kinds`` (a read-only union).

        Used by the wallet-health capture to keep refreshing wallets the store
        already tracks, without opening a retired registry.
        """
        polars = _require_polars()
        found: set[str] = set()
        for kind in kinds:
            if kind not in KIND_COLUMNS:
                raise FactStoreError(f"UNKNOWN_FACT_KIND:{kind}")
            if "wallet" not in column_names(kind):
                continue
            slice_ = self.scan(kind, start_day=start_day, end_day=end_day)
            if slice_.files == 0:
                continue
            frame = slice_.frame.select(polars.col("wallet").unique()).collect()
            found.update(str(wallet) for wallet in frame["wallet"].to_list())
        return tuple(sorted(found))

    def verify(self) -> dict[str, Any]:
        """Re-hash every batch, compare with the manifest, report orphans."""
        pl = _require_polars()
        con = self.connect()
        problems: list[str] = []
        batches = [batch for kind in sorted(KIND_COLUMNS) for batch in mf.day_batches(con, kind)]
        checked = 0
        for batch in batches:
            checked += 1
            path = Path(batch.path)
            if not path.is_file():
                problems.append(f"MISSING_FILE:{batch.kind}:{batch.day}")
                continue
            if _sha256(path.read_bytes()) != batch.file_sha256:
                problems.append(f"FILE_SHA_MISMATCH:{batch.kind}:{batch.day}")
            try:
                height = pl.scan_parquet(path).select(pl.len()).collect().item()
            except Exception as exc:
                problems.append(f"UNREADABLE:{batch.kind}:{batch.day}:{type(exc).__name__}")
                continue
            if height != batch.rows:
                problems.append(f"ROW_COUNT_MISMATCH:{batch.kind}:{batch.day}")
            schema = pl.scan_parquet(path).collect_schema()
            expected = schema_for(batch.kind)
            if dict(schema) != dict(expected):
                problems.append(f"SCHEMA_MISMATCH:{batch.kind}:{batch.day}")
            if path.name != f"{batch.batch_sha16}.parquet":
                problems.append(f"BATCH_NAME_MISMATCH:{batch.kind}:{batch.day}")
        orphans = [str(path) for path in mf.orphan_batches(con)]
        return {
            "batches_checked": checked,
            "problems": problems,
            "orphan_files": orphans,
            "ok": not problems and not orphans,
        }


def empty_canonical(kind: str):
    pl = _require_polars()
    if kind not in KIND_COLUMNS:
        raise FactStoreError(f"UNKNOWN_FACT_KIND:{kind}")
    return pl.DataFrame(schema=schema_for(kind))


def _repair_fills(frame, *, tolerance=DEFAULT_TOLERANCE):
    """Apply intake-only same-ms repair to every affected ``(wallet, coin)`` chain."""
    pl = _require_polars()
    if frame.height == 0:
        return frame, RepairStats()
    chains = list(CHAIN_KEYS["fills"])
    needs_repair = frame.group_by(chains).agg(
        pl.col("event_ts_ms").is_duplicated().any().alias("_repair")
    )
    # A join does not promise row order; re-establish the intake sort explicitly
    # so repaired ordering never depends on the join implementation.
    flagged = frame.join(needs_repair, on=chains, how="left").sort(list(SORT_KEYS["fills"]))
    burst_rows = flagged.filter(pl.col("_repair")).drop("_repair")
    quiet = flagged.filter(~pl.col("_repair")).drop("_repair")
    if burst_rows.height == 0:
        quiet = quiet.drop("arrival_seq").with_columns(
            pl.int_range(pl.len()).over(chains).cast(pl.Int64).alias("arrival_seq")
        )
        return quiet.sort(list(SORT_KEYS["fills"])), RepairStats()

    totals = {
        "bursts": 0,
        "bursts_repaired": 0,
        "bursts_left_broken": 0,
        "bursts_skipped_missing_start_position": 0,
        "rows_moved": 0,
    }
    fixed_parts = []
    for part in burst_rows.partition_by(chains, maintain_order=True):
        links = [
            FillLink(
                ts_ms=int(ts),
                start_position=pre,
                sign=_sign_of(side),
                size=size,
            )
            for ts, pre, side, size in zip(
                part["event_ts_ms"].to_list(),
                part["start_position"].to_list(),
                part["side"].to_list(),
                part["size"].to_list(),
                strict=True,
            )
        ]
        result = repair_same_ms_order(links, tolerance=tolerance)
        for key, value in result.stats.as_dict().items():
            totals[key] += value
        part = part[list(result.order)]
        part = part.drop("arrival_seq").with_columns(
            pl.int_range(pl.len()).cast(pl.Int64).alias("arrival_seq")
        )
        fixed_parts.append(part)

    quiet = quiet.drop("arrival_seq").with_columns(
        pl.int_range(pl.len()).over(chains).cast(pl.Int64).alias("arrival_seq")
    )
    combined = pl.concat([quiet, *fixed_parts], how="vertical_relaxed")
    return combined.sort(list(SORT_KEYS["fills"])), RepairStats(**totals)


def _sign_of(side: str | None) -> int:
    if side == "buy":
        return 1
    if side == "sell":
        return -1
    return 0


def _parquet_bytes(frame) -> bytes:
    buffer = io.BytesIO()
    frame.write_parquet(buffer, compression="zstd")
    return buffer.getvalue()


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _fsync(path: Path) -> None:
    with open(path, "rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:  # pragma: no cover - non-POSIX or read-only mount
        pass


def money_columns_for(kind: str) -> tuple[str, ...]:
    return money_columns(kind)
