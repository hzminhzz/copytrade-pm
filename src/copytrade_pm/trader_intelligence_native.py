"""Time-bounded SHA-verified native 1m OHLCV for TI hypothetical replay.

Uses the pre-existing PM-01 Hyperliquid day adapter, its family/sidecar
integrity checks, and the existing ml4t-data Parquet. No provider requests,
order transport, replacement market store or execution attestation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource
from .trader_intelligence import digest, norm_clock, utc
from .trader_intelligence_research import MinuteBar


def lake_instrument(instrument: str) -> str:
    """Translate an *exact* TI-native market ID to the existing PM-01 scope."""
    parts = instrument.split("/")
    if len(parts) != 3 or parts[0] != "hyperliquid":
        raise ValueError("UNKNOWN_NATIVE_MINUTE_INSTRUMENT")
    scope = parts[1].split(":")
    if len(scope) != 3 or scope[:2] != ["mainnet", "perp"]:
        raise ValueError("UNKNOWN_NATIVE_MINUTE_INSTRUMENT")
    if not parts[2] or ":" in parts[2]:
        raise ValueError("UNKNOWN_NATIVE_MINUTE_INSTRUMENT")
    return ":".join(("hyperliquid", *scope, parts[2]))


@dataclass(frozen=True)
class VerifiedNativeWindow:
    instrument: str
    first_minute_at: str
    final_minute_at: str
    day_source_shas: tuple[tuple[str, str], ...]
    bars: tuple[MinuteBar, ...]
    research_only_status: str
    window_sha256: str

    def as_wire(self) -> dict:
        return asdict(self)


def read_native_minutes(
    *,
    root: Path,
    instrument: str,
    first_minute_at: str,
    final_minute_at: str,
    known_asof: str,
) -> VerifiedNativeWindow:
    """Return only fully closed, SHA-verified exact native minutes.

    A missing minute, missing day, mismatched sidecar or as-of future bar
    terminates the entire window. Price OHLC does not prove executable fills,
    bid/ask, funding, balance, order-size capacity or source book continuity.
    """
    start, end, cut = utc(first_minute_at), utc(final_minute_at), utc(known_asof)
    if (
        start > end
        or end - start > timedelta(days=3)
        or (start.second, start.microsecond, end.second, end.microsecond) != (0, 0, 0, 0)
    ):
        raise ValueError("INVALID_BOUND_NATIVE_WINDOW")
    if end + timedelta(minutes=1) > cut:
        raise ValueError("UNMATURED_NATIVE_WINDOW")
    native = lake_instrument(instrument)
    adapter = VerifiedHyperliquidMinuteSource(root)
    family = adapter._family(native)
    days: list[tuple[str, str]] = []
    bars: list[MinuteBar] = []
    moment = start
    import polars as pl

    while moment.date() <= end.date():
        day = moment.date()
        first = max(moment, start)
        directory = (
            root / family / f"year={day.year:04d}" / f"month={day.month:02d}" / f"day={day.day:02d}"
        )
        path = directory / "data.parquet"
        # Check using the already-owned native day adapter *first*.
        verified = adapter.get(native, first)
        raw = path.read_bytes()
        fingerprint = sha256(raw).hexdigest()
        if fingerprint != verified.source_sha256:
            raise MarketDataBlocked("MARKET_PARQUET_HASH_CHANGED_DURING_READ")
        df = pl.read_parquet(
            BytesIO(raw),
            columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        )
        day_end = min(end, datetime.combine(day, time(23, 59), tzinfo=UTC))
        for row in df.iter_rows(named=True):
            dt = utc(row["timestamp"])
            if first <= dt <= day_end:
                bars.append(
                    MinuteBar(
                        instrument=instrument,
                        start_at=norm_clock(dt),
                        open_px=str(row["open"]),
                        high_px=str(row["high"]),
                        low_px=str(row["low"]),
                        close_px=str(row["close"]),
                        base_volume=str(row["volume"]),
                    )
                )
        days.append((day.isoformat(), fingerprint))
        moment = datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC)
    expected = int((end - start).total_seconds() // 60) + 1
    if len(bars) != expected or any(
        utc(bar.start_at) != start + timedelta(minutes=i) for i, bar in enumerate(bars)
    ):
        raise MarketDataBlocked("NATIVE_MINUTE_GAP_OR_DUPLICATE")
    body = {
        "schema": "ti_sha_verified_native_minute_window_v1",
        "instrument": instrument,
        "start_at": norm_clock(start),
        "end_at": norm_clock(end),
        "day_shas": days,
        "bars": [asdict(row) for row in bars],
    }
    return VerifiedNativeWindow(
        instrument=instrument,
        first_minute_at=norm_clock(start),
        final_minute_at=norm_clock(end),
        day_source_shas=tuple(days),
        bars=tuple(bars),
        research_only_status="SHA_VERIFIED_1M_NOT_EXECUTION_QUALIFIED",
        window_sha256=digest(body),
    )
