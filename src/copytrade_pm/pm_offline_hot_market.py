"""Read-only, SHA-pinned, memory-mapped native 1m Hyperliquid hot weekly panels.

A separate compile step uses Polars to project complete verified source day
Parquet into compact little-endian numeric arrays. Workers share the same
private immutable cache bytes via OS mmap, never mutable Python row copies.
No order execution, source NAV, signed receipt or financial certification.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import struct
from typing import Any

from .pm_offline_cache import ImmutableCache
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid
from .pm_offline_market import _file_sha, _verified_day
from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource

SCHEMA = "pm_offline_hot_native_week_v1"
MAGIC = b"PMHOTW1\x00"
WEEK_BARS = 7 * 1440
MAX_HEADER_BYTES = 65536
COLUMN_NAMES = (
    "timestamp_ms",
    "open_float_screen_only",
    "high_float_screen_only",
    "low_float_screen_only",
    "close_float_screen_only",
    "volume_base_screen_only",
)


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ManifestInvalid("INVALID_HOT_WEEK_CLOCK")
    date = value.astimezone(UTC)
    if date.hour or date.minute or date.second or date.microsecond or date.weekday():
        raise ManifestInvalid("HOT_WEEK_MUST_START_MONDAY_UTC")
    return date


def _identity(market: str, week: datetime, shas: list[dict]) -> dict[str, str]:
    frozen = json.dumps(shas, sort_keys=True, separators=(",", ":")).encode()
    return {
        "instrument": sha256(market.encode()).hexdigest(),
        "week": sha256(week.isoformat().encode()).hexdigest(),
        "source_days": sha256(frozen).hexdigest(),
        "software": sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def _header_bytes(header: dict) -> bytes:
    data = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    if not 0 < len(data) < MAX_HEADER_BYTES:
        raise ManifestInvalid("INVALID_HOT_WEEK_HEADER_SIZE")
    return MAGIC + struct.pack("<I", len(data)) + data


class HotNativeWeek:
    """Owner-private mmap, read-only and exclusively screening-level Float64."""

    def __init__(self, *, content_path: Path, cache_status: str):
        import numpy as np

        self.cache_status = cache_status
        self.content_path = content_path
        with content_path.open("rb") as stream:
            magic = stream.read(len(MAGIC))
            length = stream.read(4)
            if magic != MAGIC or len(length) != 4:
                raise ManifestBlocked("HOT_WEEK_MAGIC_MISMATCH")
            header_size = struct.unpack("<I", length)[0]
            if not 0 < header_size < MAX_HEADER_BYTES:
                raise ManifestBlocked("HOT_WEEK_HEADER_SIZE_INVALID")
            try:
                self.metadata = json.loads(stream.read(header_size))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ManifestBlocked("CORRUPT_HOT_WEEK_HEADER") from exc
        if (
            not isinstance(self.metadata, dict)
            or self.metadata.get("schema") != SCHEMA
            or self.metadata.get("rows") != WEEK_BARS
            or self.metadata.get("columns") != list(COLUMN_NAMES)
            or len(self.metadata.get("source_days", [])) != 7
        ):
            raise ManifestBlocked("HOT_WEEK_HEADER_CONTRACT_INVALID")
        self._dtype = np.dtype(
            [
                ("timestamp_ms", "<i8"),
                ("open_float_screen_only", "<f8"),
                ("high_float_screen_only", "<f8"),
                ("low_float_screen_only", "<f8"),
                ("close_float_screen_only", "<f8"),
                ("volume_base_screen_only", "<f8"),
            ]
        )
        self._offset = len(MAGIC) + 4 + header_size
        required = self._offset + WEEK_BARS * self._dtype.itemsize
        if content_path.stat().st_size != required:
            raise ManifestBlocked("HOT_WEEK_NUMERIC_SIZE_MISMATCH")
        self.rows = np.memmap(
            content_path,
            dtype=self._dtype,
            mode="r",
            offset=self._offset,
            shape=(WEEK_BARS,),
        )
        if self.rows.flags.writeable:
            raise ManifestBlocked("HOT_WEEK_NOT_READ_ONLY")
        begin = int(datetime.fromisoformat(self.metadata["week_start"]).timestamp() * 1000)
        if (
            int(self.rows["timestamp_ms"][0]) != begin
            or int(self.rows["timestamp_ms"][-1]) != begin + (WEEK_BARS - 1) * 60000
        ):
            raise ManifestBlocked("HOT_WEEK_TIME_RANGE_MISMATCH")
        self._start_ms = begin

    def sample(self, at: datetime) -> dict[str, float] | None:
        """Exact UTC minute only. No nearest-price fallback or true L2 claims."""
        when = at.astimezone(UTC) if at.tzinfo and at.utcoffset() is not None else None
        if when is None or when.second or when.microsecond:
            raise ManifestInvalid("NON_EXACT_HOT_WEEK_MINUTE")
        milliseconds = int(when.timestamp() * 1000)
        offset, remainder = divmod(milliseconds - self._start_ms, 60000)
        if remainder or offset < 0 or offset >= WEEK_BARS:
            return None
        bar = self.rows[offset]
        if int(bar["timestamp_ms"]) != milliseconds:
            raise ManifestBlocked("HOT_WEEK_MISSING_EXACT_BAR")
        return {name: float(bar[name]) for name in COLUMN_NAMES if name != "timestamp_ms"}

    def prior_volume(self, at: datetime) -> float | None:
        """Prior completed 1m base volume, NULL at the weekly boundary."""
        if at.tzinfo is None or at.utcoffset() is None:
            raise ManifestInvalid("NAIVE_HOT_WEEK_CLOCK")
        previous = at.astimezone(UTC) - timedelta(minutes=1)
        sampled = self.sample(previous)
        return None if sampled is None else sampled["volume_base_screen_only"]

    def close(self) -> None:
        """Release the read-only mapping explicitly when finished."""
        mm = getattr(self.rows, "_mmap", None)
        if mm is not None:
            mm.close()

    def __enter__(self) -> HotNativeWeek:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def open_verified_hot_week(
    *,
    market_root: Path,
    cache_root: Path,
    instrument: str,
    week_start: datetime,
) -> HotNativeWeek:
    """Seal and map one complete 7-day native week, or fail-closed."""
    import numpy as np
    import polars as pl

    first = _clock(week_start)
    root = Path(market_root)
    if root.is_symlink() or not root.is_dir():
        raise ManifestInvalid("INVALID_HOT_MARKET_ROOT")
    source_days = []
    locations = []
    try:
        family = VerifiedHyperliquidMinuteSource._family(instrument)
    except MarketDataBlocked as exc:
        raise ManifestInvalid("INVALID_HOT_NATIVE_MARKET") from exc
    for offset in range(7):
        day = first + timedelta(days=offset)
        folder = root / family / (f"year={day.year:04d}/month={day.month:02d}/day={day.day:02d}")
        path, sidecar = folder / "data.parquet", folder / "source.json"
        if any(
            part.is_symlink()
            for part in (folder, folder.parent, folder.parent.parent, root / family)
        ):
            raise ManifestBlocked("SYMLINK_HOT_NATIVE_DAY")
        if not path.is_file() or not sidecar.is_file():
            raise ManifestBlocked("INCOMPLETE_HOT_NATIVE_WEEK")
        if path.is_symlink() or sidecar.is_symlink():
            raise ManifestBlocked("SYMLINK_HOT_NATIVE_DAY")
        if sidecar.stat().st_size > 1024 * 1024:
            raise ManifestBlocked("OVERSIZED_HOT_NATIVE_SIDECAR")
        try:
            metadata = json.loads(sidecar.read_text())
        except (ValueError, UnicodeDecodeError) as exc:
            raise ManifestBlocked("MALFORMED_HOT_NATIVE_SIDECAR") from exc
        observed = metadata.get("sha256")
        if not isinstance(observed, str) or _file_sha(path) != observed:
            raise ManifestBlocked("HOT_NATIVE_SOURCE_SHA_MISMATCH")
        source_days.append(
            {
                "date": day.date().isoformat(),
                "data_sha256": observed,
                "metadata_sha256": _file_sha(sidecar),
            }
        )
        locations.append(path)
    cache = ImmutableCache(
        cache_root,
        max_object_bytes=8 * 1024 * 1024,
        min_free_bytes=1024 * 1024 * 1024,
    )
    dependency = _identity(instrument, first, source_days)
    existing = cache.load("hot_native_week", dependency, version=SCHEMA)
    if existing is None:
        frames = []
        for day in (first + timedelta(days=i) for i in range(7)):
            try:
                frame, expected_data, expected_meta = _verified_day(root, instrument, day)
            except ManifestBlocked as exc:
                raise ManifestBlocked("INVALID_COMPLETE_HOT_NATIVE_WEEK") from exc
            audit = source_days[(day - first).days]
            if (
                frame.height != 1440
                or expected_data != audit["data_sha256"]
                or expected_meta != audit["metadata_sha256"]
            ):
                raise ManifestBlocked("INCOMPLETE_HOT_NATIVE_WEEK")
            frames.append(frame)
        book = (
            pl.concat(frames)
            .sort("timestamp")
            .select("timestamp", "open", "high", "low", "close", "volume")
        )
        if book.height != WEEK_BARS or book["timestamp"].n_unique() != WEEK_BARS:
            raise ManifestBlocked("DUPLICATE_HOT_NATIVE_MINUTE")
        values = np.empty(
            WEEK_BARS,
            dtype=np.dtype(
                [
                    ("timestamp_ms", "<i8"),
                    ("open_float_screen_only", "<f8"),
                    ("high_float_screen_only", "<f8"),
                    ("low_float_screen_only", "<f8"),
                    ("close_float_screen_only", "<f8"),
                    ("volume_base_screen_only", "<f8"),
                ]
            ),
        )
        values["timestamp_ms"] = book["timestamp"].dt.epoch("ms").to_numpy()
        for source, field in (
            ("open", "open_float_screen_only"),
            ("high", "high_float_screen_only"),
            ("low", "low_float_screen_only"),
            ("close", "close_float_screen_only"),
            ("volume", "volume_base_screen_only"),
        ):
            values[field] = book[source].to_numpy()
        start_ms = int(first.timestamp() * 1000)
        if not np.array_equal(
            values["timestamp_ms"],
            np.arange(WEEK_BARS, dtype=np.int64) * 60000 + start_ms,
        ):
            raise ManifestBlocked("HOT_NATIVE_WEEK_HAS_GAP")
        for path, observed in zip(locations, source_days, strict=True):
            if _file_sha(path) != observed["data_sha256"]:
                raise ManifestBlocked("HOT_NATIVE_SOURCE_CHANGED_DURING_COMPILATION")
        header = {
            "schema": SCHEMA,
            "rows": WEEK_BARS,
            "week_start": first.isoformat(),
            "instrument": instrument,
            "columns": list(COLUMN_NAMES),
            "source_days": source_days,
            "numeric_dtype": "little_endian_i64_timestamp_5x_f64_screening",
            "scientifically_qualified": False,
            "execution_certified": False,
        }
        payload = _header_bytes(header) + values.tobytes(order="C")
        cache.publish("hot_native_week", dependency, version=SCHEMA, content=payload)
        status = "CACHE_CREATED"
    else:
        status = "CACHE_HIT"
    key = cache.identity("hot_native_week", dependency, version=SCHEMA)
    path, _ = cache._paths("hot_native_week", key)
    return HotNativeWeek(content_path=path, cache_status=status)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--week-start", required=True)
    args = parser.parse_args()
    try:
        at = datetime.fromisoformat(args.week_start)
    except ValueError as exc:
        parser.error(f"Invalid ISO week start: {exc}")
    try:
        with open_verified_hot_week(
            market_root=args.market_root,
            cache_root=args.cache_root,
            instrument=args.instrument,
            week_start=at,
        ) as view:
            print(
                json.dumps(
                    {
                        "schema": SCHEMA,
                        "status": "COMPLETE_HOT_WEEK_SCREEN_ONLY",
                        "instrument": args.instrument,
                        "week_start": at.astimezone(UTC).isoformat(),
                        "rows": int(view.rows.shape[0]),
                        "cache_status": view.cache_status,
                        "data_sha256": _file_sha(view.content_path),
                        "bytes": view.content_path.stat().st_size,
                        "read_only_mmap": not view.rows.flags.writeable,
                        "price_float_screen_only": True,
                        "execution_certified": False,
                        "scientifically_qualified": False,
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
    except (ManifestBlocked, ManifestInvalid) as exc:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": exc.status,
                    "reason": exc.code,
                    "execution_certified": False,
                    "scientifically_qualified": False,
                },
                sort_keys=True,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
