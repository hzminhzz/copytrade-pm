"""Named migration sources and their fail-closed adapters to canonical facts.

Sources are never globbed by guesswork. Each source is named, has a fixed
priority, and is supplied explicitly by the caller. The five sources of the
Slice 2 migration are:

==============================  ========  =======================================
``source_id``                   priority  layout
==============================  ========  =======================================
``wallet_store``                0        ``<root>/<kind>/**/*.parquet``
``reservoir:full-history``      1        ``<root>/**/*.parquet``
``reservoir:monitored-plus-six`` 2       ``<root>/**/*.parquet``
``reservoir:roster-daily``      3        ``<root>/**/*.parquet``
``reservoir:liquid12-discovery`` 4       ``<root>/**/*.parquet``
==============================  ========  =======================================

Priority decides who wins when the same fact appears in more than one source.
It is fixed here, not derived from argument order, so a migration is
reproducible regardless of how the CLI was invoked.

Discovery reads every ``*.parquet`` under a supplied root (sorted, relative
paths recorded). Nothing is skipped silently: a source that yields no rows, or a
kind that a root contains but the migration does not ingest, is reported in the
run receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:  # pragma: no cover - the core CI leg runs without the `market` extra
    import polars as pl  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    pl = None  # type: ignore[assignment]

from .schemas import (
    KNOWN_AT_BASIS_FETCH_CLOCK,
    KNOWN_AT_BASIS_UNRECORDED,
    MONEY_PRECISION,
    MONEY_SCALE,
    normalise_dex,
)

DAY_MS = 86_400_000

WALLET_STORE_SOURCE = "wallet_store"
RESERVOIR_FULL_HISTORY = "reservoir:full-history"
RESERVOIR_MONITORED_PLUS_SIX = "reservoir:monitored-plus-six"
RESERVOIR_ROSTER_DAILY = "reservoir:roster-daily"
RESERVOIR_LIQUID12_DISCOVERY = "reservoir:liquid12-discovery"

#: The complete, ordered source catalogue. ``priority`` is authoritative.
SOURCE_CATALOGUE: dict[str, tuple[int, str]] = {
    WALLET_STORE_SOURCE: (0, "wallet_store"),
    RESERVOIR_FULL_HISTORY: (1, "reservoir"),
    RESERVOIR_MONITORED_PLUS_SIX: (2, "reservoir"),
    RESERVOIR_ROSTER_DAILY: (3, "reservoir"),
    RESERVOIR_LIQUID12_DISCOVERY: (4, "reservoir"),
}

#: Reservoir prefix name accepted by the CLI -> canonical ``source_id``.
RESERVOIR_PREFIX_ALIASES: dict[str, str] = {
    "full-history": RESERVOIR_FULL_HISTORY,
    "monitored-plus-six": RESERVOIR_MONITORED_PLUS_SIX,
    "roster-daily": RESERVOIR_ROSTER_DAILY,
    "liquid12-discovery": RESERVOIR_LIQUID12_DISCOVERY,
}

#: Kinds this migration ingests, per source layer.
KINDS_BY_LAYER: dict[str, tuple[str, ...]] = {
    "wallet_store": ("fills", "positions"),
    "reservoir": ("fills",),
}

#: Source timestamp column per kind.
TIMESTAMP_BY_KIND: dict[str, str] = {"fills": "exchange_ts", "positions": "snapshot_ts"}


class SourceLayer(StrEnum):
    WALLET_STORE = "wallet_store"
    RESERVOIR = "reservoir"


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """One named migration source rooted at an explicit path."""

    source_id: str
    layer: SourceLayer
    root: Path
    priority: int
    kinds: tuple[str, ...]

    @property
    def pinned_prefix(self) -> str:
        """Stable, non-absolute label recorded in the manifest."""
        return self.source_id


@dataclass(frozen=True, slots=True)
class InputFile:
    """One discovered Parquet input, addressed relatively for the manifest."""

    source_id: str
    kind: str
    rel_path: str
    path: Path
    bytes_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Canonical rows of one input file plus its fail-closed counters."""

    frame: Any
    rows_read: int
    rows_rejected: int
    rows_quantized_to_zero: int
    first_known_at_ms: int | None
    known_at_basis: str


def build_catalogue(
    *,
    wallet_store: Path | str | None = None,
    reservoir: Mapping[str, Path | str] | None = None,
) -> tuple[tuple[SourceSpec, ...], tuple[str, ...]]:
    """Return ``(sources, not_supplied)`` ordered by fixed priority.

    ``not_supplied`` names every catalogue source the caller did not supply, so
    a partial migration is visible in the receipt instead of looking complete.
    Unknown or duplicated reservoir prefix names fail closed.
    """
    supplied: dict[str, SourceSpec] = {}
    if wallet_store is not None:
        supplied[WALLET_STORE_SOURCE] = SourceSpec(
            source_id=WALLET_STORE_SOURCE,
            layer=SourceLayer.WALLET_STORE,
            root=Path(wallet_store).expanduser(),
            priority=SOURCE_CATALOGUE[WALLET_STORE_SOURCE][0],
            kinds=KINDS_BY_LAYER["wallet_store"],
        )
    for name, path in dict(reservoir or {}).items():
        source_id = RESERVOIR_PREFIX_ALIASES.get(name)
        if source_id is None:
            raise ValueError(
                "UNKNOWN_RESERVOIR_PREFIX:"
                f"{name}: expected one of {sorted(RESERVOIR_PREFIX_ALIASES)}"
            )
        if source_id in supplied:
            raise ValueError(f"DUPLICATE_RESERVOIR_PREFIX:{name}")
        supplied[source_id] = SourceSpec(
            source_id=source_id,
            layer=SourceLayer.RESERVOIR,
            root=Path(path).expanduser(),
            priority=SOURCE_CATALOGUE[source_id][0],
            kinds=KINDS_BY_LAYER["reservoir"],
        )
    ordered = tuple(sorted(supplied.values(), key=lambda spec: spec.priority))
    absent = tuple(source_id for source_id in SOURCE_CATALOGUE if source_id not in supplied)
    return ordered, absent


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:  # pragma: no cover - discovery is always rooted
        return PurePosixPath(path).as_posix()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_inputs(
    spec: SourceSpec, kind: str, *, pattern: str = "**/*.parquet"
) -> list[InputFile]:
    """List every Parquet input of ``kind`` under ``spec.root``, sorted.

    The same physical file reached through two relative paths is collapsed by
    resolved path and keeps the lexicographically first relative path, so
    discovery is deterministic.
    """
    if not spec.root.is_dir():
        raise FileNotFoundError(f"SOURCE_ROOT_MISSING:{spec.source_id}:{spec.root}")
    base = spec.root if spec.layer is SourceLayer.RESERVOIR else spec.root / kind
    if not base.is_dir():
        return []
    seen: dict[Path, Path] = {}
    for candidate in sorted(base.glob(pattern)):
        if not candidate.is_file() or candidate.suffix != ".parquet":
            continue
        resolved = candidate.resolve()
        if any(part == ".metadata" for part in resolved.parts):
            continue
        seen.setdefault(resolved, candidate)
    inputs: list[InputFile] = []
    for candidate in sorted(seen.values(), key=lambda path: _relative(path, spec.root)):
        inputs.append(
            InputFile(
                source_id=spec.source_id,
                kind=kind,
                rel_path=_relative(candidate, spec.root),
                path=candidate,
                bytes_count=candidate.stat().st_size,
                sha256=file_sha256(candidate),
            )
        )
    return inputs


def day_of_ms(event_ts_ms: int) -> str:
    return datetime.fromtimestamp(event_ts_ms / 1000.0, tz=timezone.utc).date().isoformat()


def day_range(start_day: str, end_day: str) -> list[str]:
    current = date.fromisoformat(start_day)
    final = date.fromisoformat(end_day)
    days: list[str] = []
    while current <= final:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def _require_polars():
    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    return pl


def _require(frame, columns: Sequence[str], *, source_id: str, kind: str) -> None:
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"SOURCE_SCHEMA_UNSUPPORTED:{source_id}:{kind}:missing={missing}")


def timestamp_to_ms(frame, column: str, *, source_id: str):
    """Normalise a source timestamp column to epoch milliseconds (Int64)."""
    pl = _require_polars()
    dtype = frame.schema[column]
    if isinstance(dtype, pl.Datetime):
        return frame[column].dt.epoch("ms").cast(pl.Int64)
    if dtype in (pl.Int64, pl.Int32):
        return frame[column].cast(pl.Int64)
    if dtype == pl.String:
        parsed = frame[column].str.to_datetime(time_zone="UTC", strict=False)
        if parsed.null_count() > frame[column].null_count():
            raise ValueError(f"SOURCE_TIMESTAMP_UNSUPPORTED:{source_id}:{column}")
        return parsed.dt.epoch("ms").cast(pl.Int64)
    raise ValueError(f"SOURCE_TIMESTAMP_UNSUPPORTED:{source_id}:{column}:{dtype}")


def _decimal_series(frame, column: str):
    """Exact decimal widening through the shortest round-trip string form.

    ``Float64`` sources are already lossy; ``Decimal(str(float))`` reproduces
    exactly the stored float without introducing further error, and the cast to
    scale 12 truncates anything below 1e-12 (counted by the caller).
    """
    pl = _require_polars()
    return (
        frame[column]
        .cast(pl.String, strict=False)
        .cast(pl.Decimal(MONEY_PRECISION, MONEY_SCALE), strict=False)
    )


def _null_series(count: int, dtype):
    pl = _require_polars()
    return pl.Series("value", [None] * count, dtype=dtype)


def _money_null(count: int):
    pl = _require_polars()
    return _null_series(count, pl.Decimal(MONEY_PRECISION, MONEY_SCALE))


def _string_or_null(frame, column: str):
    pl = _require_polars()
    if column not in frame.columns:
        return _null_series(frame.height, pl.String)
    return frame[column].cast(pl.String, strict=False)


def _decimal_or_null(frame, column: str):
    if column not in frame.columns:
        return _money_null(frame.height)
    return _decimal_series(frame, column)


def _bool_or_null(frame, column: str):
    pl = _require_polars()
    if column not in frame.columns:
        return _null_series(frame.height, pl.Boolean)
    return frame[column].cast(pl.Boolean, strict=False)


SIDE_NORMALISATION = {
    "buy": "buy",
    "b": "buy",
    "long": "buy",
    "sell": "sell",
    "a": "sell",
    "s": "sell",
    "short": "sell",
}


def _side_series(frame):
    pl = _require_polars()
    lowered = frame["side"].cast(pl.String, strict=False).str.to_lowercase()
    return lowered.replace_strict(SIDE_NORMALISATION, default=None).cast(pl.String)


def _quantized_to_zero(frame, raw_column: str, canonical) -> int:
    """Rows where a non-zero source value became ``0`` at scale 12."""
    pl = _require_polars()
    if raw_column not in frame.columns:
        return 0
    raw_abs = frame[raw_column].cast(pl.String, strict=False).cast(pl.Float64, strict=False)
    lost = (raw_abs.abs() > 0) & (canonical.cast(pl.Float64, strict=False) == 0)
    return int(lost.sum())


def _rejected_rows(frame) -> int:
    return int(frame["wallet"].is_null().sum() + frame["event_ts_ms"].is_null().sum())


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def adapt_reservoir_fills(
    frame,
    *,
    source_id: str,
    source_rank: int,
    first_known_at_ms: int | None = None,
    known_at_basis: str = KNOWN_AT_BASIS_UNRECORDED,
) -> AdapterResult:
    """Adapt a Reservoir fills frame to the canonical fills schema.

    Required columns are exactly what the archive publishes: ``wallet``,
    ``exchange_ts``, ``coin``, ``dex``, ``side``, ``size``, ``start_position``,
    ``trade_id``. ``direction``, ``is_liquidation``, ``price``, ``fee`` and
    ``day`` are optional and stay null when absent — never zero-invented.
    """
    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    _require(
        frame,
        ("wallet", "exchange_ts", "coin", "dex", "side", "size", "start_position", "trade_id"),
        source_id=source_id,
        kind="fills",
    )
    rows = frame.height
    event_ts_ms = timestamp_to_ms(frame, "exchange_ts", source_id=source_id)
    size = _decimal_series(frame, "size")
    start_position = _decimal_series(frame, "start_position")

    out = pl.DataFrame(
        {
            "wallet": frame["wallet"].cast(pl.String).str.to_lowercase(),
            "coin": frame["coin"].cast(pl.String),
            "dex": normalise_dex(frame["dex"]),
            "dex_raw": frame["dex"].cast(pl.String, strict=False),
            "provider": _null_series(rows, pl.String),
            "side": _side_series(frame),
            "size": size,
            "price": _decimal_or_null(frame, "price"),
            "fee": _decimal_or_null(frame, "fee"),
            "fee_token": _null_series(rows, pl.String),
            "size_usd": _money_null(rows),
            "start_position": start_position,
            "closed_pnl": _money_null(rows),
            "trade_id": frame["trade_id"].cast(pl.String, strict=False),
            "order_id": _null_series(rows, pl.String),
            "direction": _string_or_null(frame, "direction"),
            "is_liquidation": _bool_or_null(frame, "is_liquidation"),
            "is_maker": _null_series(rows, pl.Boolean),
            "crossed": _null_series(rows, pl.Boolean),
            "exchange_ts": event_ts_ms.cast(pl.Datetime("ms", "UTC")),
            "event_ts_ms": event_ts_ms,
            "source_ts": frame["exchange_ts"].cast(pl.String, strict=False),
            "first_known_at_ms": pl.Series(
                "first_known_at_ms", [first_known_at_ms] * rows, dtype=pl.Int64
            ),
            "known_at_basis": pl.Series(
                "known_at_basis",
                [known_at_basis if first_known_at_ms is not None else KNOWN_AT_BASIS_UNRECORDED]
                * rows,
                dtype=pl.String,
            ),
            "arrival_seq": pl.Series("arrival_seq", list(range(rows)), dtype=pl.Int64),
            "source_id": pl.Series("source_id", [source_id] * rows, dtype=pl.String),
            "source_rank": pl.Series("source_rank", [source_rank] * rows, dtype=pl.UInt8),
            "batch_sha16": pl.Series("batch_sha16", [""] * rows, dtype=pl.String),
        }
    )
    quantized = _quantized_to_zero(frame, "size", size)
    quantized += _quantized_to_zero(frame, "start_position", start_position)
    return AdapterResult(
        frame=out,
        rows_read=rows,
        rows_rejected=_rejected_rows(out),
        rows_quantized_to_zero=quantized,
        first_known_at_ms=first_known_at_ms,
        known_at_basis=out["known_at_basis"][0] if rows else known_at_basis,
    )


def adapt_wallet_store_fills(
    frame,
    *,
    source_id: str,
    source_rank: int,
    first_known_at_ms: int | None,
    known_at_basis: str = KNOWN_AT_BASIS_FETCH_CLOCK,
) -> AdapterResult:
    """Adapt a legacy wallet-store fills frame (``ts``/``symbol``/``size_token``)."""
    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    _require(
        frame,
        ("ts", "wallet", "symbol", "dex", "side", "size_token"),
        source_id=source_id,
        kind="fills",
    )
    rows = frame.height
    event_ts_ms = timestamp_to_ms(frame, "ts", source_id=source_id)
    size = _decimal_series(frame, "size_token")

    out = pl.DataFrame(
        {
            "wallet": frame["wallet"].cast(pl.String).str.to_lowercase(),
            "coin": frame["symbol"].cast(pl.String),
            "dex": normalise_dex(frame["dex"]),
            "dex_raw": frame["dex"].cast(pl.String, strict=False),
            "provider": _string_or_null(frame, "source"),
            "side": _side_series(frame),
            "size": size,
            "price": _decimal_or_null(frame, "price"),
            "fee": _decimal_or_null(frame, "fee"),
            "fee_token": _string_or_null(frame, "fee_token"),
            "size_usd": _decimal_or_null(frame, "size_usd"),
            "start_position": _decimal_or_null(frame, "start_position"),
            "closed_pnl": _decimal_or_null(frame, "closed_pnl"),
            "trade_id": _string_or_null(frame, "trade_id"),
            "order_id": _string_or_null(frame, "order_id"),
            "direction": _null_series(rows, pl.String),
            "is_liquidation": _null_series(rows, pl.Boolean),
            "is_maker": _bool_or_null(frame, "is_maker"),
            "crossed": _bool_or_null(frame, "crossed"),
            "exchange_ts": event_ts_ms.cast(pl.Datetime("ms", "UTC")),
            "event_ts_ms": event_ts_ms,
            "source_ts": _string_or_null(frame, "source_ts"),
            "first_known_at_ms": pl.Series(
                "first_known_at_ms", [first_known_at_ms] * rows, dtype=pl.Int64
            ),
            "known_at_basis": pl.Series(
                "known_at_basis",
                [known_at_basis if first_known_at_ms is not None else KNOWN_AT_BASIS_UNRECORDED]
                * rows,
                dtype=pl.String,
            ),
            "arrival_seq": pl.Series("arrival_seq", list(range(rows)), dtype=pl.Int64),
            "source_id": pl.Series("source_id", [source_id] * rows, dtype=pl.String),
            "source_rank": pl.Series("source_rank", [source_rank] * rows, dtype=pl.UInt8),
            "batch_sha16": pl.Series("batch_sha16", [""] * rows, dtype=pl.String),
        }
    )
    quantized = _quantized_to_zero(frame, "size_token", size)
    if "start_position" in frame.columns:
        quantized += _quantized_to_zero(frame, "start_position", out["start_position"])
    return AdapterResult(
        frame=out,
        rows_read=rows,
        rows_rejected=_rejected_rows(out),
        rows_quantized_to_zero=quantized,
        first_known_at_ms=first_known_at_ms,
        known_at_basis=out["known_at_basis"][0] if rows else known_at_basis,
    )


def adapt_wallet_store_positions(
    frame,
    *,
    source_id: str,
    source_rank: int,
    first_known_at_ms: int | None,
    known_at_basis: str = KNOWN_AT_BASIS_FETCH_CLOCK,
) -> AdapterResult:
    """Adapt a legacy wallet-store positions frame (``snapshot_ts``/``symbol``)."""
    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    _require(
        frame,
        ("snapshot_ts", "wallet", "symbol", "dex", "direction", "size_token"),
        source_id=source_id,
        kind="positions",
    )
    rows = frame.height
    event_ts_ms = timestamp_to_ms(frame, "snapshot_ts", source_id=source_id)

    out = pl.DataFrame(
        {
            "wallet": frame["wallet"].cast(pl.String).str.to_lowercase(),
            "symbol": frame["symbol"].cast(pl.String),
            "dex": normalise_dex(frame["dex"]),
            "dex_raw": frame["dex"].cast(pl.String, strict=False),
            "provider": _string_or_null(frame, "source"),
            "direction": _string_or_null(frame, "direction"),
            "size_token": _decimal_series(frame, "size_token"),
            "size_usd": _decimal_or_null(frame, "size_usd"),
            "entry_price": _decimal_or_null(frame, "entry_price"),
            "mark_price": _decimal_or_null(frame, "mark_price"),
            "liquidation_price": _decimal_or_null(frame, "liquidation_price"),
            "unrealized_pnl": _decimal_or_null(frame, "unrealized_pnl"),
            "leverage": _decimal_or_null(frame, "leverage"),
            "leverage_type": _string_or_null(frame, "leverage_type"),
            "margin_used": _decimal_or_null(frame, "margin_used"),
            "opened_at": (
                frame["opened_at"].cast(pl.Datetime("ms", "UTC"), strict=False)
                if "opened_at" in frame.columns
                else _null_series(rows, pl.Datetime("ms", "UTC"))
            ),
            "pnl_cohort": _string_or_null(frame, "pnl_cohort"),
            "size_cohort": _string_or_null(frame, "size_cohort"),
            "liq_progress": _decimal_or_null(frame, "liq_progress"),
            "snapshot_ts": event_ts_ms.cast(pl.Datetime("ms", "UTC")),
            "event_ts_ms": event_ts_ms,
            "first_known_at_ms": pl.Series(
                "first_known_at_ms", [first_known_at_ms] * rows, dtype=pl.Int64
            ),
            "known_at_basis": pl.Series(
                "known_at_basis",
                [known_at_basis if first_known_at_ms is not None else KNOWN_AT_BASIS_UNRECORDED]
                * rows,
                dtype=pl.String,
            ),
            "arrival_seq": pl.Series("arrival_seq", list(range(rows)), dtype=pl.Int64),
            "source_id": pl.Series("source_id", [source_id] * rows, dtype=pl.String),
            "source_rank": pl.Series("source_rank", [source_rank] * rows, dtype=pl.UInt8),
            "batch_sha16": pl.Series("batch_sha16", [""] * rows, dtype=pl.String),
        }
    )
    return AdapterResult(
        frame=out,
        rows_read=rows,
        rows_rejected=_rejected_rows(out),
        rows_quantized_to_zero=0,
        first_known_at_ms=first_known_at_ms,
        known_at_basis=out["known_at_basis"][0] if rows else known_at_basis,
    )


#: Which adapter to use for ``(layer, kind)``.
ADAPTERS: dict[tuple[SourceLayer, str], Any] = {
    (SourceLayer.RESERVOIR, "fills"): adapt_reservoir_fills,
    (SourceLayer.WALLET_STORE, "fills"): adapt_wallet_store_fills,
    (SourceLayer.WALLET_STORE, "positions"): adapt_wallet_store_positions,
}


def empty_frame(kind: str):
    """An empty canonical frame carrying the exact write schema."""
    from .schemas import schema_for

    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    return pl.DataFrame(schema=schema_for(kind))
