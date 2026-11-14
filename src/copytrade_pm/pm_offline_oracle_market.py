"""SHA-verified native market alignment for real *historical-oracle* batches.

This produces a screening context only: exact next-minute opens and prior
completed-minute base volume. It is NOT an executable order book and does not
calculate PM-03 equity, funding, leverage, margin, pass probability or P&L.
Missing days, incomplete bars and wrong DEX scopes remain explicit rejects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import resource
from time import perf_counter

from .pm_offline_cache import ImmutableCache
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid
from .pm_offline_market import _file_sha, _verified_day
from .pm_offline_oracle import (
    MAX_PARQUET_BYTES,
    _json_bytes,
    compile_real_historical_oracle,
    load_real_oracle_batches,
)
from .pm_offline_repository import _market_day, native_instrument
from .pm_shadow import VerifiedHyperliquidMinuteSource

SCHEMA = "pm_offline_real_native_oracle_context_v1"
DAY_MS = 86_400_000
MAX_MARKET_DAYS = 6000


def _day_clock(day_number: int) -> datetime:
    return datetime.fromtimestamp(day_number * 86400, tz=UTC)


def _day_record(root: Path, instrument: str, day_number: int) -> dict:
    day = _day_clock(day_number)
    status, bars = _market_day(root, instrument, day, verify_sha=True)
    family = VerifiedHyperliquidMinuteSource.family(instrument)
    folder = root / family / (f"year={day.year:04d}/month={day.month:02d}/day={day.day:02d}")
    sidecar = folder / "source.json"
    meta_sha = None
    data_sha = None
    if sidecar.is_file() and not sidecar.is_symlink():
        raw = sidecar.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ManifestBlocked("OVERSIZED_NATIVE_DAY_METADATA")
        meta_sha = sha256(raw).hexdigest()
        try:
            metadata = json.loads(raw)
            data_sha = metadata.get("sha256")
        except ValueError, TypeError:
            pass
    return {
        "status": status,
        "bars": bars,
        "data_sha256": data_sha,
        "metadata_sha256": meta_sha,
    }


def _missing(frame, status: str):
    import polars as pl

    return frame.with_columns(
        pl.lit(None).cast(pl.Float64).alias("next_open_float_screen_only"),
        pl.lit(None).cast(pl.Float64).alias("prior_base_volume_screen_only"),
        pl.lit(status).alias("match_status"),
    )


def _validated_day(root: Path, instrument: str, day_number: int, pinned: dict):
    from .pm_offline_manifest import ManifestBlocked

    day = _day_clock(day_number)
    frame, data_sha, metadata_sha = _verified_day(root, instrument, day)
    if data_sha != pinned["data_sha256"] or metadata_sha != pinned["metadata_sha256"]:
        raise ManifestBlocked("NATIVE_DAY_CHANGED_DURING_JOIN")
    if frame.height != pinned["bars"] or frame.height != 1440:
        raise ManifestBlocked("NATIVE_BAR_COUNT_MISMATCH_WITH_SIDECAR")
    return frame


def _join_day(
    root: Path,
    instrument: str,
    day_number: int,
    group,
    pinned: dict[tuple[str, int], dict],
):
    import polars as pl

    metadata = pinned[(instrument, day_number)]
    if metadata["status"] != "VERIFIED_NATIVE_DAY":
        return _missing(group, metadata["status"])
    try:
        bars = _validated_day(root, instrument, day_number, metadata)
    except ManifestBlocked as exc:
        if exc.code == "NATIVE_DAY_CHANGED_DURING_JOIN":
            raise
        return _missing(group, "INVALID_NATIVE_1M_DAY")
    # At t=00:00 the prior *completed* minute lies in the previous day.
    need_previous = group.filter(pl.col("execute_ms") % DAY_MS == 0).height > 0
    prev = bars
    if need_previous:
        before = pinned.get((instrument, day_number - 1))
        if before and before["status"] == "VERIFIED_NATIVE_DAY":
            try:
                prior_day = _validated_day(root, instrument, day_number - 1, before)
                prev = pl.concat([prior_day, bars])
            except ManifestBlocked as exc:
                if exc.code == "NATIVE_DAY_CHANGED_DURING_JOIN":
                    raise
        # Missing predecessor is explicit NULL on the 00:00 action.
    # Exact UTC minute equality; no as-of nearest or future-bar substitution.
    current = bars.lazy().select(
        pl.col("timestamp").dt.epoch("ms").alias("execute_ms"),
        pl.col("open").alias("next_open_float_screen_only"),
    )
    prior = prev.lazy().select(
        pl.col("timestamp").dt.epoch("ms").alias("prior_ms"),
        pl.col("volume").alias("prior_base_volume_screen_only"),
    )
    return (
        group.lazy()
        .with_columns((pl.col("execute_ms") - 60_000).alias("prior_ms"))
        .join(current, how="left", on="execute_ms")
        .join(prior, how="left", on="prior_ms")
        .with_columns(
            pl.when(pl.col("next_open_float_screen_only").is_null())
            .then(pl.lit("MISSING_EXACT_OPEN"))
            .when(pl.col("prior_base_volume_screen_only").is_null())
            .then(pl.lit("MISSING_COMPLETED_PRIOR_VOLUME"))
            .otherwise(pl.lit("MATCHED_SCREEN_ONLY"))
            .alias("match_status"),
        )
        .drop("prior_ms")
        .collect(engine="streaming")
    )


def _join_instrument(root: Path, instrument: str, candidate, pinned):
    """One bounded Polars projection/join per instrument, never per minute/day.

    Every included market Parquet was independently SHA-checked in the
    preflight fingerprint. Validate 1,440 rows/UTC day, uniqueness and all
    OHLC invariants before accepting any exact-open match for the instrument.
    """
    import polars as pl

    days = sorted(
        day
        for (market, day), metadata in pinned.items()
        if market == instrument and metadata["status"] == "VERIFIED_NATIVE_DAY"
    )
    status_days = sorted(set(candidate["day_number"].to_list()))
    statuses = pl.DataFrame(
        {
            "day_number": status_days,
            "market_status": [pinned[(instrument, day)]["status"] for day in status_days],
        }
    )
    joined = candidate.join(statuses, on="day_number", how="left").with_columns(
        (pl.col("execute_ms") - 60_000).alias("prior_ms")
    )
    if not days:
        result = _missing(joined, "MISSING_NATIVE_DAY")
        return result.with_columns(pl.col("market_status").alias("match_status")).drop(
            "market_status", "prior_ms", "day_number"
        )
    family = VerifiedHyperliquidMinuteSource.family(instrument)
    locations = []
    for number in days:
        at = _day_clock(number)
        path = (
            root
            / family
            / (f"year={at.year:04d}/month={at.month:02d}/day={at.day:02d}/data.parquet")
        )
        if not path.is_file() or path.is_symlink():
            raise ManifestBlocked("VERIFIED_NATIVE_DAY_CHANGED_DURING_JOIN")
        locations.append(path)
    try:
        query = pl.scan_parquet(locations, extra_columns="ignore", missing_columns="insert")
        schema = query.collect_schema()
        required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
        if not required.issubset(schema):
            raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
        timestamp_dtype = schema["timestamp"]
        if not isinstance(timestamp_dtype, pl.Datetime) or timestamp_dtype.time_zone != "UTC":
            raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
        market = (
            query.select(sorted(required))
            .with_columns(pl.col("timestamp").dt.cast_time_unit("us"))
            .collect(engine="streaming")
        )
    except pl.exceptions.ComputeError, pl.exceptions.SchemaError:
        # Optional vendor columns and timestamp precision can differ across
        # day generations. Project and normalize each day before concatenating
        # lazily, rather than coercing incompatible data or inventing bars.
        try:
            parts = []
            for path in locations:
                scan = pl.scan_parquet(path)
                columns = scan.collect_schema()
                if not required.issubset(columns):
                    raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
                dtype = columns["timestamp"]
                if not isinstance(dtype, pl.Datetime) or dtype.time_zone != "UTC":
                    raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
                parts.append(
                    scan.select(sorted(required)).with_columns(
                        pl.col("timestamp").dt.cast_time_unit("us")
                    )
                )
            market = pl.concat(parts).collect(engine="streaming")
        except pl.exceptions.ComputeError, pl.exceptions.SchemaError, OSError:
            raise ManifestBlocked("INVALID_NATIVE_1M_DAY") from None
    except OSError:
        raise ManifestBlocked("INVALID_NATIVE_1M_DAY") from None
    # A file could be replaced between the initial cache fingerprint and
    # the Polars multi-file scan. Bind the observed result to the preflight
    # source bytes; never publish a market tape from changed inputs.
    for number, path in zip(days, locations, strict=True):
        if _file_sha(path) != pinned[(instrument, number)]["data_sha256"]:
            raise ManifestBlocked("NATIVE_DAY_CHANGED_DURING_JOIN")
    if market.height != len(days) * 1440:
        raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
    market = market.with_columns(
        (pl.col("timestamp").dt.epoch("ms") // DAY_MS).alias("market_day_number"),
    )
    observed = {
        item["market_day_number"]: item["len"]
        for item in market.group_by("market_day_number").len().to_dicts()
    }
    if observed != {day: 1440 for day in days} or (market["timestamp"].n_unique() != market.height):
        raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
    symbol = instrument.split(":")[-1]
    bad = market.filter(
        (pl.col("symbol") != symbol)
        | (pl.col("timestamp").dt.epoch("ms") % 60_000 != 0)
        | ~pl.all_horizontal(pl.col("open", "high", "low", "close", "volume").is_finite())
        | (pl.col("open") <= 0)
        | (pl.col("low") <= 0)
        | (pl.col("high") < pl.col("open"))
        | (pl.col("high") < pl.col("close"))
        | (pl.col("low") > pl.col("open"))
        | (pl.col("low") > pl.col("close"))
        | (pl.col("volume") < 0)
    )
    if not bad.is_empty():
        raise ManifestBlocked("INVALID_NATIVE_1M_DAY")
    current = market.lazy().select(
        pl.col("timestamp").dt.epoch("ms").alias("execute_ms"),
        pl.col("open").alias("next_open_float_screen_only"),
    )
    previous = market.lazy().select(
        pl.col("timestamp").dt.epoch("ms").alias("prior_ms"),
        pl.col("volume").alias("prior_base_volume_screen_only"),
    )
    result = (
        joined.lazy()
        .join(current, on="execute_ms", how="left")
        .join(previous, on="prior_ms", how="left")
        .with_columns(
            pl.when(pl.col("market_status") != "VERIFIED_NATIVE_DAY")
            .then(pl.col("market_status"))
            .when(pl.col("next_open_float_screen_only").is_null())
            .then(pl.lit("MISSING_EXACT_OPEN"))
            .when(pl.col("prior_base_volume_screen_only").is_null())
            .then(pl.lit("MISSING_COMPLETED_PRIOR_VOLUME"))
            .otherwise(pl.lit("MATCHED_SCREEN_ONLY"))
            .alias("match_status")
        )
        .collect(engine="streaming")
    )
    return result.select(
        "delay_minutes",
        "account_sha256",
        "instrument",
        "execute_ms",
        "source_fill_count",
        "first_event_ms",
        "last_event_ms",
        "next_open_float_screen_only",
        "prior_base_volume_screen_only",
        "match_status",
    )


def match_real_oracle_native(
    *,
    source_root: Path,
    market_root: Path,
    cache_root: Path,
    start: str,
    end: str,
    instruments: tuple[str, ...] = (),
    max_market_days: int = MAX_MARKET_DAYS,
) -> dict:
    """Join sealed real source batches to verified native Parquet days."""
    if type(max_market_days) is not int or not 1 <= max_market_days <= MAX_MARKET_DAYS:
        raise ManifestInvalid("INVALID_NATIVE_DAY_BUDGET")
    market_root = Path(market_root)
    if not market_root.is_dir() or market_root.is_symlink():
        raise ManifestInvalid("UNSAFE_OR_MISSING_NATIVE_MARKET_ROOT")
    for instrument in instruments:
        if instrument != native_instrument(":".join(instrument.split(":")[3:])):
            raise ManifestInvalid("UNSUPPORTED_NATIVE_FILTER")
    t0 = perf_counter()
    source_report = compile_real_historical_oracle(source_root, cache_root, start=start, end=end)
    batches, source_tape_sha = load_real_oracle_batches(
        cache_root,
        start=start,
        end=end,
        source_sha256=source_report["source_collection_sha256"],
    )
    import polars as pl

    all_instruments = set(batches["instrument"].unique().to_list())
    if instruments:
        scope = set(instruments)
        if not scope <= all_instruments:
            raise ManifestInvalid("UNKNOWN_NATIVE_FILTER_IN_SOURCE")
        batches = batches.filter(pl.col("instrument").is_in(sorted(scope)))
    if batches.is_empty():
        raise ManifestBlocked("NO_NATIVE_EXECUTION_CANDIDATES")
    candidates = batches.with_columns((pl.col("execute_ms") // DAY_MS).alias("day_number"))
    required = {
        (row["instrument"], row["day_number"])
        for row in candidates.select(["instrument", "day_number"]).unique().to_dicts()
    }
    predecessor = {
        (row["instrument"], row["day_number"] - 1)
        for row in candidates.filter(pl.col("execute_ms") % DAY_MS == 0)
        .select(["instrument", "day_number"])
        .unique()
        .to_dicts()
    }
    needed = sorted(required | predecessor)
    if len(needed) > max_market_days:
        raise ManifestBlocked("EXCEEDS_BOUNDED_NATIVE_DAY_SCAN")
    fingerprints = {key: _day_record(market_root, *key) for key in needed}
    market_fingerprint = sha256(
        _json_bytes({f"{inst}@{day}": fingerprints[(inst, day)] for inst, day in needed})
    ).hexdigest()
    software_fingerprint = sha256(
        _json_bytes(
            {
                name: sha256((Path(__file__).resolve().parent / name).read_bytes()).hexdigest()
                for name in (
                    "pm_offline_oracle_market.py",
                    "pm_offline_market.py",
                    "pm_offline_repository.py",
                    "pm_shadow.py",
                )
            }
        )
    ).hexdigest()
    store = ImmutableCache(
        cache_root,
        max_object_bytes=MAX_PARQUET_BYTES,
        min_free_bytes=1024 * 1024 * 1024,
    )
    key = {
        "source": source_tape_sha,
        "market": market_fingerprint,
        "software": software_fingerprint,
        "scope": sha256(_json_bytes({"instruments": sorted(instruments)})).hexdigest(),
    }
    checked_seconds = perf_counter() - t0
    cached = store.load("oracle_native", key, version=SCHEMA)
    if cached is not None:
        output = pl.read_parquet(BytesIO(cached))
        cache_state = "CACHE_HIT"
        encoded = cached
    else:
        results = []
        for label, group in candidates.partition_by(
            ["instrument"], as_dict=True, maintain_order=False
        ).items():
            (instrument,) = label
            try:
                result = _join_instrument(market_root, instrument, group, fingerprints)
            except ManifestBlocked as exc:
                if exc.code != "INVALID_NATIVE_1M_DAY":
                    raise
                # A single malformed day must not hide unrelated source
                # markets/days. Isolate that instrument and use the original
                # SHA-verifying day adapter to mark each day explicitly.
                fragments = []
                for day_label, piece in group.partition_by(
                    ["day_number"], as_dict=True, maintain_order=False
                ).items():
                    (day_number,) = day_label
                    part = _join_day(market_root, instrument, day_number, piece, fingerprints)
                    fragments.append(part.drop("day_number"))
                result = pl.concat(fragments)
            results.append(result)
        output = (
            pl.concat(results)
            .sort(["delay_minutes", "instrument", "execute_ms", "account_sha256"])
            .rechunk()
        )
        byte_stream = BytesIO()
        output.write_parquet(byte_stream, statistics=False, compression="zstd")
        encoded = byte_stream.getvalue()
        if len(encoded) > MAX_PARQUET_BYTES:
            raise ManifestBlocked("NATIVE_CONTEXT_EXCEEDS_DISK_BUDGET")
        store.publish("oracle_native", key, version=SCHEMA, content=encoded)
        cache_state = "CACHE_CREATED"
    joined_seconds = perf_counter() - t0 - checked_seconds
    counts = (
        output.lazy()
        .group_by(["delay_minutes", "match_status"])
        .agg(
            pl.len().alias("batches"),
            pl.col("source_fill_count").sum().alias("source_fills"),
        )
        .sort(["delay_minutes", "match_status"])
        .collect(engine="streaming")
        .to_dicts()
    )
    matched = sum(row["batches"] for row in counts if row["match_status"] == "MATCHED_SCREEN_ONLY")
    checked_source_fills = int(output["source_fill_count"].sum())
    result_logic = {
        "schema": SCHEMA,
        "batch_parquet_sha256": source_tape_sha,
        "market_fingerprint_sha256": market_fingerprint,
        "context_tape_sha256": sha256(encoded).hexdigest(),
        "candidate_batches": output.height,
        "candidate_source_fill_observations_across_delays": checked_source_fills,
        "matched_batches": matched,
        "status_counts_by_delay": counts,
    }
    return {
        **result_logic,
        "status": "HISTORICAL_ORACLE_NATIVE_SCREEN_ONLY",
        "scope": "FILTERED" if instruments else "ALL_VALID_PERP_SOURCE",
        "market_input_days": len(needed),
        "verified_complete_native_days": sum(
            item["status"] == "VERIFIED_NATIVE_DAY" for item in fingerprints.values()
        ),
        "declared_partial_or_missing_days": sum(
            item["status"] != "VERIFIED_NATIVE_DAY" for item in fingerprints.values()
        ),
        "cache_status": cache_state,
        "preflight_seconds": round(checked_seconds, 6),
        "market_join_seconds": round(joined_seconds, 6),
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "price_float_screen_only": True,
        "volume_capacity_proxy": "PRIOR_COMPLETED_BASE_VOLUME_NOT_L2",
        "contractual_pass_or_breach": "UNKNOWN",
        "scientifically_qualified": False,
        "logical_sha256": sha256(_json_bytes(result_logic)).hexdigest(),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--instrument", action="append", default=[])
    parser.add_argument("--max-market-days", type=int, default=MAX_MARKET_DAYS)
    args = parser.parse_args()
    print(
        json.dumps(
            match_real_oracle_native(
                source_root=args.source_root,
                market_root=args.market_root,
                cache_root=args.cache_root,
                start=args.start,
                end=args.end,
                instruments=tuple(sorted(set(args.instrument))),
                max_market_days=args.max_market_days,
            ),
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
