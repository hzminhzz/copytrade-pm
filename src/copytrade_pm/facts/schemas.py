"""Canonical bi-temporal schemas for :mod:`copytrade_pm.facts`.

Every financial column is an explicit ``Decimal(38, 12)`` Parquet type. The
legacy wallet store wrote ``Float64``; this module is the single place that
defines the replacement, so no writer can drift back.

Two scalar-typed rules are deliberate and documented rather than "cleaned up":

* ``Decimal(38, 12)`` cannot represent ``|x| < 1e-12``. Values below that scale
  are truncated to zero by the cast. This module does not hide that: callers
  count quantised-to-zero cells through :func:`quantized_to_zero_mask` and the
  migration receipt reports them.
* Source data that is *already* ``Float64`` is not re-derived. It is widened
  through the shortest round-trip decimal repr of the stored float, so no new
  error is introduced and no precision is invented.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from enum import StrEnum

try:  # pragma: no cover - the core CI leg runs without the `market` extra
    import polars as pl  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    pl = None  # type: ignore[assignment]

MONEY_SCALE = 12
MONEY_PRECISION = 38
SCHEMA_VERSION = "facts-1.0.0"

#: Orders in which a ``known_at`` value may have been established. Only the
#: first is evidence; the second is an explicit "we do not know".
KNOWN_AT_BASIS_FETCH_CLOCK = "partition_fetch_clock"
KNOWN_AT_BASIS_UNRECORDED = "unrecorded"
KNOWN_AT_BASES = (KNOWN_AT_BASIS_FETCH_CLOCK, KNOWN_AT_BASIS_UNRECORDED)


class ProvenanceTier(StrEnum):
    """What kind of clock evidence a row carries.

    ``OBSERVED_FETCH`` rows have a recorded fetch/observation clock, so strict
    point-in-time filtering can bound them. ``RETROSPECTIVE`` rows have no
    historical clock at all: they are invisible to ``as_of`` scans unless the
    caller explicitly opts in, and they never gain an invented timestamp.
    """

    OBSERVED_FETCH = "OBSERVED_FETCH"
    RETROSPECTIVE = "RETROSPECTIVE"


TIER_BY_BASIS = {
    KNOWN_AT_BASIS_FETCH_CLOCK: ProvenanceTier.OBSERVED_FETCH,
    KNOWN_AT_BASIS_UNRECORDED: ProvenanceTier.RETROSPECTIVE,
}

#: Verbatim DEX labels normalised to one canonical vocabulary. Only the label
#: changes; no financial value is touched. The raw label is retained in
#: ``dex_raw`` so nothing is lost.
DEX_NORMALISATION = {
    "hl": "hyperliquid",
    "hyperliquid": "hyperliquid",
    "xyz": "xyz",
    "spot": "spot",
}
DEX_UNKNOWN = "unknown"

FILLS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("wallet", "String"),
    ("coin", "String"),
    ("dex", "String"),
    ("dex_raw", "String"),
    ("provider", "String"),
    ("side", "String"),
    ("size", "Decimal"),
    ("price", "Decimal"),
    ("fee", "Decimal"),
    ("fee_token", "String"),
    ("size_usd", "Decimal"),
    ("start_position", "Decimal"),
    ("closed_pnl", "Decimal"),
    ("trade_id", "String"),
    ("order_id", "String"),
    ("direction", "String"),
    ("is_liquidation", "Boolean"),
    ("is_maker", "Boolean"),
    ("crossed", "Boolean"),
    ("exchange_ts", "Datetime"),
    ("event_ts_ms", "Int64"),
    ("source_ts", "String"),
    ("first_known_at_ms", "Int64"),
    ("known_at_basis", "String"),
    ("arrival_seq", "Int64"),
    ("source_id", "String"),
    ("source_rank", "UInt8"),
    ("batch_sha16", "String"),
)

POSITIONS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("wallet", "String"),
    ("symbol", "String"),
    ("dex", "String"),
    ("dex_raw", "String"),
    ("provider", "String"),
    ("direction", "String"),
    ("size_token", "Decimal"),
    ("size_usd", "Decimal"),
    ("entry_price", "Decimal"),
    ("mark_price", "Decimal"),
    ("liquidation_price", "Decimal"),
    ("unrealized_pnl", "Decimal"),
    ("leverage", "Decimal"),
    ("leverage_type", "String"),
    ("margin_used", "Decimal"),
    ("opened_at", "Datetime"),
    ("pnl_cohort", "String"),
    ("size_cohort", "String"),
    ("liq_progress", "Decimal"),
    ("snapshot_ts", "Datetime"),
    ("event_ts_ms", "Int64"),
    ("first_known_at_ms", "Int64"),
    ("known_at_basis", "String"),
    ("arrival_seq", "Int64"),
    ("source_id", "String"),
    ("source_rank", "UInt8"),
    ("batch_sha16", "String"),
)

EQUITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("wallet", "String"),
    ("account_scope", "String"),
    ("abstraction_mode", "String"),
    ("equity_usd", "Decimal"),
    ("withdrawable_usd", "Decimal"),
    ("margin_used_usd", "Decimal"),
    ("observed_at", "Datetime"),
    ("event_ts_ms", "Int64"),
    ("first_known_at_ms", "Int64"),
    ("known_at_basis", "String"),
    ("arrival_seq", "Int64"),
    ("source_id", "String"),
    ("source_rank", "UInt8"),
    ("batch_sha16", "String"),
)

FUNDING_COLUMNS: tuple[tuple[str, str], ...] = (
    ("wallet", "String"),
    ("coin", "String"),
    ("payment_usd", "Decimal"),
    ("funding_rate", "Decimal"),
    ("size", "Decimal"),
    ("hash", "String"),
    ("event_ts", "Datetime"),
    ("event_ts_ms", "Int64"),
    ("first_known_at_ms", "Int64"),
    ("known_at_basis", "String"),
    ("arrival_seq", "Int64"),
    ("source_id", "String"),
    ("source_rank", "UInt8"),
    ("batch_sha16", "String"),
)

LEDGER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("wallet", "String"),
    ("kind", "String"),
    ("amount_usd", "Decimal"),
    ("token", "String"),
    ("hash", "String"),
    ("event_ts", "Datetime"),
    ("event_ts_ms", "Int64"),
    ("first_known_at_ms", "Int64"),
    ("known_at_basis", "String"),
    ("arrival_seq", "Int64"),
    ("source_id", "String"),
    ("source_rank", "UInt8"),
    ("batch_sha16", "String"),
)

BARS_1M_COLUMNS: tuple[tuple[str, str], ...] = (
    ("venue", "String"),
    ("coin", "String"),
    ("open", "Decimal"),
    ("high", "Decimal"),
    ("low", "Decimal"),
    ("close", "Decimal"),
    ("volume", "Decimal"),
    ("quote_volume_usd", "Decimal"),
    ("bar_ts", "Datetime"),
    ("event_ts_ms", "Int64"),
    ("first_known_at_ms", "Int64"),
    ("known_at_basis", "String"),
    ("arrival_seq", "Int64"),
    ("source_id", "String"),
    ("source_rank", "UInt8"),
    ("batch_sha16", "String"),
)

KIND_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "fills": FILLS_COLUMNS,
    "positions": POSITIONS_COLUMNS,
    "equity": EQUITY_COLUMNS,
    "funding": FUNDING_COLUMNS,
    "ledger": LEDGER_COLUMNS,
    "bars_1m": BARS_1M_COLUMNS,
}

#: Numeric columns that must be exact decimals, per kind.
MONEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "fills": ("size", "price", "fee", "size_usd", "start_position", "closed_pnl"),
    "positions": (
        "size_token",
        "size_usd",
        "entry_price",
        "mark_price",
        "liquidation_price",
        "unrealized_pnl",
        "leverage",
        "margin_used",
        "liq_progress",
    ),
    "equity": ("equity_usd", "withdrawable_usd", "margin_used_usd"),
    "funding": ("payment_usd", "funding_rate", "size"),
    "ledger": ("amount_usd",),
    "bars_1m": ("open", "high", "low", "close", "volume", "quote_volume_usd"),
}

TIMESTAMP_COLUMNS: dict[str, str] = {
    "fills": "exchange_ts",
    "positions": "snapshot_ts",
    "equity": "observed_at",
    "funding": "event_ts",
    "ledger": "event_ts",
    "bars_1m": "bar_ts",
}

#: Columns that identify *one* fact for the kinds ingested by capture. Two rows
#: with the same identity are the same observation; a differing payload under one
#: identity is a conflict, never a second fact. ``fills`` and ``positions`` keep
#: their own richer expressions in :mod:`copytrade_pm.facts.migrate`.
IDENTITY_COLUMNS: dict[str, tuple[str, ...]] = {
    "equity": ("wallet", "account_scope", "event_ts_ms"),
    "funding": ("wallet", "coin", "event_ts_ms", "hash"),
    "ledger": ("wallet", "event_ts_ms", "hash", "kind"),
    "bars_1m": ("venue", "coin", "event_ts_ms"),
}


def _require_polars():
    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    return pl


def _dtype(name: str):
    pl = _require_polars()
    if name == "String":
        return pl.String
    if name == "Int64":
        return pl.Int64
    if name == "UInt8":
        return pl.UInt8
    if name == "Boolean":
        return pl.Boolean
    if name == "Datetime":
        return pl.Datetime("ms", "UTC")
    if name == "Decimal":
        return pl.Decimal(MONEY_PRECISION, MONEY_SCALE)
    raise ValueError(f"UNKNOWN_CANONICAL_DTYPE:{name}")


def schema_for(kind: str):
    """Return the canonical Parquet write schema for ``kind``."""
    pl = _require_polars()
    if kind not in KIND_COLUMNS:
        raise ValueError(f"UNKNOWN_FACT_KIND:{kind}")
    return pl.Schema({name: _dtype(dtype) for name, dtype in KIND_COLUMNS[kind]})


def schema_sha(kind: str) -> str:
    """Stable identifier of the canonical schema (name, type) pairs."""
    if kind not in KIND_COLUMNS:
        raise ValueError(f"UNKNOWN_FACT_KIND:{kind}")
    payload = "|".join(f"{name}:{dtype}" for name, dtype in KIND_COLUMNS[kind])
    return hashlib.sha256(f"{SCHEMA_VERSION}|{payload}".encode()).hexdigest()


def column_names(kind: str) -> tuple[str, ...]:
    if kind not in KIND_COLUMNS:
        raise ValueError(f"UNKNOWN_FACT_KIND:{kind}")
    return tuple(name for name, _ in KIND_COLUMNS[kind])


def money_columns(kind: str) -> tuple[str, ...]:
    if kind not in MONEY_COLUMNS:
        raise ValueError(f"UNKNOWN_FACT_KIND:{kind}")
    return MONEY_COLUMNS[kind]


def quantized_to_zero_mask(frame, kind: str, raw_columns: dict[str, str]) -> int:
    """Count cells that a non-zero source value lost to the 1e-12 scale floor.

    ``raw_columns`` maps canonical decimal column -> the raw source column still
    present in ``frame``. Only used on the ingest path, where both exist.
    """
    _require_polars()
    total = 0
    for canonical, raw in raw_columns.items():
        if canonical not in frame.columns or raw not in frame.columns:
            continue
        total += int(((frame[canonical] == 0) & (frame[raw].abs() > 0)).sum())
    return total


def normalise_dex(series):
    """Map raw DEX labels to the canonical vocabulary, keeping unknowns visible."""
    pl = _require_polars()
    lowered = series.cast(pl.String, strict=False).str.to_lowercase()
    return lowered.replace_strict(DEX_NORMALISATION, default=DEX_UNKNOWN).cast(pl.String)


@dataclass(frozen=True, slots=True)
class KindSpec:
    """Static description of one fact kind for callers and docs."""

    kind: str
    schema_version: str
    schema_sha256: str
    timestamp_column: str
    decimal_columns: tuple[str, ...]

    @classmethod
    def for_kind(cls, kind: str) -> KindSpec:
        return cls(
            kind=kind,
            schema_version=SCHEMA_VERSION,
            schema_sha256=schema_sha(kind),
            timestamp_column=TIMESTAMP_COLUMNS[kind],
            decimal_columns=MONEY_COLUMNS[kind],
        )
