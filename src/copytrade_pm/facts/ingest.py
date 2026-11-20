"""Append-only ingest of captured observations into the day-partitioned store.

The capture path (:mod:`copytrade_pm.wallet_health_official`) normalises provider
replies into ``equity`` / ``funding`` / ``ledger`` rows. This module is its only
writer, and it owns four rules:

* **Merge, never replace.** A day is rebuilt from the rows already committed for
  that day *plus* the rows offered now, so a capture that re-observes a narrower
  window can never drop an earlier fact.
* **Fact identity, not row identity.** Rows dedupe on
  :data:`~copytrade_pm.facts.schemas.IDENTITY_COLUMNS` and the survivor keeps the
  earliest recorded ``first_known_at_ms`` — the first time the fact was seen,
  never the latest fetch.
* **Conflicts fail closed.** One identity carrying two different payloads is an
  integrity failure, not a row to prefer silently.
* **Idempotent.** Identical content yields the same content-addressed batch name,
  so re-ingesting the same observation writes nothing and reports
  ``created=False``.

Nothing here invents a clock, a price, or a roster: a row with no recorded clock
stays ``RETROSPECTIVE`` and invisible to strict ``as_of`` reads.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # pragma: no cover - the core CI leg runs without the `market` extra
    import polars as pl  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    pl = None  # type: ignore[assignment]

from . import manifest as mf
from .schemas import (
    IDENTITY_COLUMNS,
    KNOWN_AT_BASIS_FETCH_CLOCK,
    KNOWN_AT_BASIS_UNRECORDED,
    SCHEMA_VERSION,
    column_names,
    schema_for,
    schema_sha,
)
from .store import FactStore, FactStoreError

#: Columns that describe provenance rather than the fact itself; a repeated
#: observation from another source is not a conflicting payload.
PROVENANCE_COLUMNS = frozenset(
    {
        "arrival_seq",
        "batch_sha16",
        "first_known_at_ms",
        "known_at_basis",
        "source_id",
        "source_rank",
    }
)


def _require_polars():
    if pl is None:  # pragma: no cover
        raise FactStoreError("POLARS_REQUIRED: install the `market` extra")
    return pl


@dataclass(frozen=True, slots=True)
class IngestReceipt:
    """What one ``(kind, day)`` ingest did, with exact row accounting."""

    kind: str
    day: str
    rows_offered: int
    rows_new: int
    rows_duplicate: int
    rows_preserved: int
    rows_written: int
    batch_sha16: str
    path: Path
    file_sha256: str
    created: bool
    dry_run: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "day": self.day,
            "rows_offered": self.rows_offered,
            "rows_new": self.rows_new,
            "rows_duplicate": self.rows_duplicate,
            "rows_preserved": self.rows_preserved,
            "rows_written": self.rows_written,
            "batch_sha16": self.batch_sha16,
            "created": self.created,
            "dry_run": self.dry_run,
        }


def frame_from_rows(kind: str, rows: Sequence[Mapping[str, Any]]):
    """Build a canonical frame from plain mappings, or an empty typed frame."""
    pl = _require_polars()
    schema = schema_for(kind)
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame([dict(row) for row in rows], schema=schema)


class FactIngestor:
    """Merge captured rows into one :class:`FactStore`."""

    def __init__(self, store: FactStore, *, dry_run: bool = False) -> None:
        self.store = store
        self.dry_run = dry_run

    # -- public ------------------------------------------------------------

    def ingest_rows(
        self,
        kind: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        source_id: str,
        source_rank: int,
        first_known_at_ms: int | None,
        input_label: str | None = None,
    ) -> tuple[IngestReceipt, ...]:
        """Convenience wrapper: normalise mappings, then :meth:`ingest_frame`."""
        return self.ingest_frame(
            kind,
            frame_from_rows(kind, rows),
            source_id=source_id,
            source_rank=source_rank,
            first_known_at_ms=first_known_at_ms,
            input_label=input_label,
        )

    def ingest_frame(
        self,
        kind: str,
        frame,
        *,
        source_id: str,
        source_rank: int,
        first_known_at_ms: int | None,
        input_label: str | None = None,
    ) -> tuple[IngestReceipt, ...]:
        """Ingest ``frame`` for ``kind``; returns one receipt per touched day."""
        pl = _require_polars()
        if kind not in IDENTITY_COLUMNS:
            raise FactStoreError(f"INGEST_UNSUPPORTED_KIND:{kind}")
        canonical = _canonicalise(
            kind,
            frame,
            source_id=source_id,
            source_rank=source_rank,
            first_known_at_ms=first_known_at_ms,
        )
        if canonical.height == 0:
            return ()
        per_day = canonical.group_by("_day").agg(pl.len().alias("rows")).sort("_day")
        receipts: list[IngestReceipt] = []
        for row in per_day.iter_rows(named=True):
            day = str(row["_day"])
            receipts.append(
                self._ingest_day(
                    kind,
                    day,
                    canonical.filter(pl.col("_day") == day).drop("_day"),
                    rows_offered=int(row["rows"]),
                    source_id=source_id,
                    source_rank=source_rank,
                    input_label=input_label or source_id,
                )
            )
        return tuple(receipts)

    # -- internals ---------------------------------------------------------

    def _ingest_day(
        self,
        kind: str,
        day: str,
        offered,
        *,
        rows_offered: int,
        source_id: str,
        source_rank: int,
        input_label: str,
    ) -> IngestReceipt:
        pl = _require_polars()
        existing = self.store.read_day(kind, day)
        combined = (
            offered if existing is None else pl.concat([existing, offered], how="vertical_relaxed")
        )
        merged, duplicates, conflicts = _dedupe(combined, kind)
        if conflicts:
            raise FactStoreError(f"INGEST_CONFLICTING_VALUES:{kind}:{day}:{conflicts}")
        prepared = self.store.prepare_day(kind, day, merged)
        write = self.store.write_day(prepared, dry_run=self.dry_run)
        preserved = 0 if existing is None else int(existing.height)
        rows_new = int(prepared.rows) - preserved
        if not self.dry_run:
            self._record(
                kind=kind,
                day=day,
                prepared=prepared,
                write=write,
                offered=offered,
                rows_offered=rows_offered,
                rows_new=rows_new,
                duplicates=duplicates,
                source_id=source_id,
                source_rank=source_rank,
                input_label=input_label,
            )
        return IngestReceipt(
            kind=kind,
            day=day,
            rows_offered=rows_offered,
            rows_new=rows_new,
            rows_duplicate=duplicates,
            rows_preserved=preserved,
            rows_written=int(prepared.rows),
            batch_sha16=write.batch_sha16,
            path=write.path,
            file_sha256=write.file_sha256,
            created=write.created,
            dry_run=self.dry_run,
        )

    def _record(
        self,
        *,
        kind: str,
        day: str,
        prepared,
        write,
        offered,
        rows_offered: int,
        rows_new: int,
        duplicates: int,
        source_id: str,
        source_rank: int,
        input_label: str,
    ) -> None:
        con = self.store.connect()
        if mf.dataset_schema_sha(con, kind) is None:
            mf.register_dataset(
                con,
                kind=kind,
                schema_version=SCHEMA_VERSION,
                schema_sha256=schema_sha(kind),
                columns=column_names(kind),
                description=f"canonical {kind} facts (Decimal(38,12))",
            )
        prior_inputs = mf.day_inputs(con, kind, day)
        record = mf.InputRecord(
            kind=kind,
            day=day,
            source_id=source_id,
            rel_path=f"capture/{input_label}/{kind}",
            input_sha256=_frame_sha(kind, offered),
            rows_read=rows_offered,
            rows_kept=rows_new,
            rows_duplicate_within=max(duplicates, 0),
            rows_duplicate_cross=0,
            rows_conflicting_values=0,
            rows_rejected=0,
            rows_null_key=0,
            first_known_at_ms=_first_known(offered),
        )
        inputs = {(item.source_id, item.rel_path): item for item in prior_inputs}
        # Re-running the same capture label for a day replaces its own input row
        # instead of colliding with the manifest's (source_id, rel_path) key.
        inputs[(source_id, record.rel_path)] = record
        ordered_inputs = [inputs[key] for key in sorted(inputs)]
        fingerprint = hashlib.sha256(
            json.dumps(
                sorted(
                    (item.source_id, item.rel_path, item.input_sha256) for item in ordered_inputs
                ),
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        prior_sources = [str(item["source_id"]) for item in mf.day_sources(con, kind, day)]
        day_sources = [
            {
                "source_id": name,
                "files_read": 1,
                "rows_read": sum(
                    item.rows_read for item in ordered_inputs if item.source_id == name
                ),
                "rows_kept": sum(
                    item.rows_kept for item in ordered_inputs if item.source_id == name
                ),
                "rows_duplicate_within": 0,
                "rows_duplicate_cross": 0,
                "rows_conflicting_values": 0,
                "rows_rejected": 0,
                "rows_null_key": 0,
                "rows_quantized_to_zero": 0,
            }
            for name in dict.fromkeys([*prior_sources, source_id])
        ]
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
            source_ids=sorted({item.source_id for item in ordered_inputs}),
            bytes_count=write.bytes_count,
            inputs=ordered_inputs,
            day_sources=day_sources,
            first_known_min_ms=min(known) if known else None,
            first_known_max_ms=max(known) if known else None,
            closed_at=_now_iso(),
        )


def _canonicalise(
    kind: str,
    frame,
    *,
    source_id: str,
    source_rank: int,
    first_known_at_ms: int | None,
):
    """Enforce the canonical schema, clocks and identity keys before any write."""
    pl = _require_polars()
    schema = schema_for(kind)
    missing = [name for name in schema.names() if name not in frame.columns]
    if missing:
        raise FactStoreError(f"INGEST_MISSING_COLUMNS:{kind}:{','.join(missing)}")
    try:
        canonical = frame.select(list(column_names(kind))).cast(schema, strict=True)
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed fail-closed error
        raise FactStoreError(f"INGEST_CAST_FAILED:{kind}:{type(exc).__name__}") from exc

    if first_known_at_ms is not None:
        canonical = canonical.with_columns(
            pl.col("first_known_at_ms").fill_null(int(first_known_at_ms))
        )
    canonical = canonical.with_columns(
        pl.coalesce(
            [
                pl.col("known_at_basis"),
                pl.when(pl.col("first_known_at_ms").is_not_null())
                .then(pl.lit(KNOWN_AT_BASIS_FETCH_CLOCK))
                .otherwise(pl.lit(KNOWN_AT_BASIS_UNRECORDED)),
            ]
        ).alias("known_at_basis"),
        pl.col("source_id").fill_null(source_id),
        pl.col("source_rank").fill_null(int(source_rank)),
        pl.col("arrival_seq").fill_null(0),
    )

    base_keys = ("wallet", "event_ts_ms") if "wallet" in column_names(kind) else ("event_ts_ms",)
    keys = tuple(dict.fromkeys((*base_keys, *IDENTITY_COLUMNS[kind])))
    nulls = canonical.filter(pl.any_horizontal([pl.col(name).is_null() for name in keys]))
    if nulls.height:
        raise FactStoreError(f"INGEST_NULL_IDENTITY:{kind}:{nulls.height}")

    if kind == "bars_1m":
        canonical = canonical.with_columns(
            pl.col("venue").str.strip_chars().str.to_lowercase(),
            pl.col("coin").str.strip_chars().str.to_uppercase(),
        )
        if canonical.filter((pl.col("venue") == "") | (pl.col("coin") == "")).height:
            raise FactStoreError("INGEST_EMPTY_IDENTITY:bars_1m")
        if canonical.filter((pl.col("event_ts_ms") % 60_000) != 0).height:
            raise FactStoreError("BARS_1M_NOT_ON_MINUTE_GRID")
        if canonical.filter((pl.col("volume") < 0) | (pl.col("quote_volume_usd") < 0)).height:
            raise FactStoreError("BARS_1M_NEGATIVE_VOLUME")

    causality_violations = canonical.filter(
        pl.col("first_known_at_ms").is_not_null()
        & (pl.col("first_known_at_ms") < pl.col("event_ts_ms"))
    )
    if causality_violations.height:
        raise FactStoreError(f"BITEMPORAL_CAUSALITY_VIOLATION:{kind}")

    return canonical.with_columns(
        pl.from_epoch(pl.col("event_ts_ms"), time_unit="ms").dt.date().cast(pl.String).alias("_day")
    )


def _dedupe(frame, kind: str) -> tuple[Any, int, int]:
    """Keep one row per fact identity: earliest clock, then best source rank.

    Returns ``(kept, duplicates, conflicts)``; ``conflicts`` counts dropped rows
    whose payload disagrees with the surviving row, which is an integrity error
    the caller must fail on rather than resolve.
    """
    pl = _require_polars()
    if frame.height == 0:
        return frame, 0, 0
    keys = IDENTITY_COLUMNS[kind]
    values = [name for name in column_names(kind) if name not in PROVENANCE_COLUMNS]
    keyed = frame.with_columns(
        pl.concat_str([pl.col(name).cast(pl.String) for name in keys], separator="|").alias(
            "_identity"
        ),
        pl.concat_str(
            [pl.col(name).cast(pl.String, strict=False).fill_null("\\x00") for name in values],
            separator="\\x1f",
        ).alias("_values"),
        pl.int_range(pl.len()).cast(pl.Int64).alias("_row"),
    )
    ordered = keyed.sort(["first_known_at_ms", "source_rank", "_row"], nulls_last=True)
    winners = ordered.group_by("_identity").agg(pl.col("_row").min().alias("_row")).select("_row")
    kept = ordered.join(winners, on="_row", how="semi")
    dropped = ordered.join(winners, on="_row", how="anti")
    conflicts = 0
    if dropped.height:
        joined = dropped.join(
            kept.select("_identity", pl.col("_values").alias("_kept")), on="_identity", how="inner"
        )
        conflicts = int(joined.filter(pl.col("_values") != pl.col("_kept")).height)
    return (
        kept.drop(["_identity", "_values", "_row"]).sort(list(keys)),
        int(dropped.height),
        conflicts,
    )


def _frame_sha(kind: str, frame) -> str:
    payload = frame.select(list(column_names(kind))).sort(list(IDENTITY_COLUMNS[kind]))
    return hashlib.sha256(payload.write_json().encode()).hexdigest()


def _first_known(frame) -> int | None:
    values = [value for value in frame["first_known_at_ms"].to_list() if value is not None]
    return min(values) if values else None


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()
