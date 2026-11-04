"""Large-input retrospective-only Polars event batching with immutable caches.

This compiles *timing and order-count diagnostics* from local historical fills.
Historical exchange timestamps are not first-known receipt times. With no
complete opening book and PIT equity, no PM-03 account or contractual P&L
is created here. All printed results omit raw addresses and filenames.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import resource
from time import perf_counter

from .pm_offline_cache import ImmutableCache
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid
from .pm_offline_repository import (
    ADDRESS,
    _clock,
    _hash_file,
    _source_files,
    native_instrument,
)

SCHEMA = "pm_offline_real_oracle_batches_v1"
POLICY = "STRICT_NEXT_OPEN_PER_FILL_ORACLE"
DELAYS = (0, 1, 2, 5, 10)
SOURCE_FIELDS = (
    "account_sha256",
    "instrument",
    "source_ms",
    "event_id",
)
MAX_SOURCE_EVENTS = 1_000_000
MAX_PARQUET_BYTES = 192 * 1024 * 1024


def _json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _safe_positive_number(value: object) -> bool:
    try:
        amount = Decimal(str(value))
    except InvalidOperation, ValueError, TypeError:
        return False
    return amount.is_finite() and amount > 0


def _event_frame(source_root: Path, *, begin_ms: int, end_ms: int) -> tuple:
    import polars as pl

    events: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    reasons: Counter[str] = Counter()
    source_shas = []
    seen_accounts = set()
    for path in _source_files(source_root):
        # Hash the exact bytes we parsed; no separate TOCTOU read.
        raw = path.read_bytes()
        source_shas.append(sha256(raw).hexdigest())
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ManifestBlocked("MALFORMED_SOURCE_JSON") from exc
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("fills"), list)
            or not isinstance(payload.get("address"), str)
            or not ADDRESS.fullmatch(payload["address"])
        ):
            raise ManifestBlocked("INVALID_SOURCE_FILE_SCHEMA")
        address = payload["address"].lower()
        account_sha = sha256(address.encode()).hexdigest()
        if account_sha in seen_accounts:
            raise ManifestBlocked("DUPLICATE_SOURCE_ACCOUNT_FILES")
        seen_accounts.add(account_sha)
        for event in payload["fills"]:
            if not isinstance(event, dict):
                reasons["INVALID_SOURCE_EVENT_SCHEMA"] += 1
                continue
            ts = event.get("time")
            if type(ts) is not int or not begin_ms <= ts < end_ms:
                continue
            try:
                market = native_instrument(event.get("coin"))
            except ManifestInvalid:
                reasons["UNSUPPORTED_SCOPE"] += 1
                continue
            tid = event.get("tid")
            if not isinstance(tid, int | str) or isinstance(tid, bool):
                reasons["UNKNOWN_TID"] += 1
                continue
            identity = (account_sha, market, str(tid))
            if identity in seen:
                reasons["DUPLICATE_TID"] += 1
                continue
            seen.add(identity)
            if event.get("side") not in {"A", "B"}:
                reasons["INVALID_SIDE"] += 1
                continue
            if not _safe_positive_number(event.get("px")) or not _safe_positive_number(
                event.get("sz")
            ):
                reasons["INVALID_SIZE_OR_PRICE"] += 1
                continue
            if event.get("startPosition", event.get("start_position")) is None:
                reasons["UNKNOWN_POSITION_BEFORE"] += 1
            events.append(
                {
                    "account_sha256": account_sha,
                    "instrument": market,
                    "source_ms": ts,
                    "event_id": str(tid),
                }
            )
            if len(events) > MAX_SOURCE_EVENTS:
                raise ManifestBlocked("REAL_ORACLE_SOURCE_EVENT_LIMIT")
    if not events:
        raise ManifestBlocked("NO_HISTORICAL_ORACLE_EVENTS_IN_WINDOW")
    # Stable typed columns, no direct file path, address or current equity.
    frame = pl.DataFrame(events).select(
        pl.col("account_sha256").cast(pl.String),
        pl.col("instrument").cast(pl.String),
        pl.col("source_ms").cast(pl.Int64),
        pl.col("event_id").cast(pl.String),
    )
    source_hash = sha256(
        json.dumps(sorted(source_shas), separators=(",", ":")).encode()
    ).hexdigest()
    return frame, source_hash, dict(sorted(reasons.items()))


def _batches(source, *, end_ms: int, engine: str):
    import polars as pl

    parts = []
    for delay in DELAYS:
        chunks = (
            source.lazy()
            .with_columns(
                ((pl.col("source_ms") + delay * 60_000) // 60_000 + 1)
                .mul(60_000)
                .alias("execute_ms"),
            )
            .filter(pl.col("execute_ms") < end_ms)
            .group_by(["account_sha256", "instrument", "execute_ms"])
            .agg(
                pl.len().alias("source_fill_count"),
                pl.col("source_ms").min().alias("first_event_ms"),
                pl.col("source_ms").max().alias("last_event_ms"),
            )
            .with_columns(pl.lit(delay).cast(pl.Int64).alias("delay_minutes"))
        )
        parts.append(chunks)
    out = (
        pl.concat(parts)
        .sort(["delay_minutes", "instrument", "execute_ms", "account_sha256"])
        .collect(engine=engine)
    )
    # Streaming and in-memory plans may produce different chunk boundaries.
    # Normalize those boundaries before serializing immutable Parquet bytes.
    return out.select(
        "delay_minutes",
        "account_sha256",
        "instrument",
        "execute_ms",
        "source_fill_count",
        "first_event_ms",
        "last_event_ms",
    ).rechunk()


def _source_digest(source_root: Path) -> str:
    """Bind every source file byte, without loading or parsing cached JSON."""
    hashes = sorted(_hash_file(file) for file in _source_files(source_root))
    return sha256(json.dumps(hashes, separators=(",", ":")).encode()).hexdigest()


def _as_parquet_bytes(frame) -> bytes:
    stream = BytesIO()
    frame.rechunk().write_parquet(stream, compression="zstd", statistics=False)
    output = stream.getvalue()
    if len(output) > MAX_PARQUET_BYTES:
        raise ManifestBlocked("ORACLE_TAPE_EXCEEDS_DISK_BUDGET")
    return output


def _source_cache(
    store: ImmutableCache, root: Path, *, sha: str, key: dict, begin_ms: int, end_ms: int
):
    """Immutable normalized source tape; reparse only on a cache miss."""
    import polars as pl

    source_bytes = store.load("oracle_source", key, version=SCHEMA)
    meta_bytes = store.load("oracle_source_meta", key, version=SCHEMA)
    start = perf_counter()
    if source_bytes is not None and meta_bytes is not None:
        meta = json.loads(meta_bytes)
        if meta.get("source_sha256") != sha or type(meta.get("event_count")) is not int:
            raise ManifestBlocked("SOURCE_META_SHA_OR_COUNT_MISMATCH")
        frame = pl.read_parquet(BytesIO(source_bytes))
        if frame.height != meta["event_count"]:
            raise ManifestBlocked("NORMALIZED_SOURCE_ROW_COUNT_MISMATCH")
        return frame, meta["ignored"], "CACHE_HIT", perf_counter() - start
    # A crash after one sealed object is safe: re-create both, while the
    # exclusive publisher refuses to overwrite any existing different bytes.
    frame, parsed_sha, ignored = _event_frame(root, begin_ms=begin_ms, end_ms=end_ms)
    if parsed_sha != sha:
        raise ManifestBlocked("SOURCE_CHANGED_DURING_COMPILATION")
    data = _as_parquet_bytes(frame.sort(["instrument", "source_ms", "account_sha256", "event_id"]))
    meta = _json_bytes(
        {
            "source_sha256": sha,
            "event_count": frame.height,
            "ignored": ignored,
            "clock_basis": "HISTORICAL_ORACLE",
        }
    )
    store.publish("oracle_source", key, version=SCHEMA, content=data)
    store.publish("oracle_source_meta", key, version=SCHEMA, content=meta)
    return frame, ignored, "CACHE_CREATED", perf_counter() - start


def compile_real_historical_oracle(
    source_root: Path,
    cache_root: Path,
    *,
    start: str,
    end: str,
    engine: str = "streaming",
) -> dict:
    """Compile exactly five strict next-open delays without financial P&L."""
    if engine not in {"streaming", "in-memory"}:
        raise ManifestInvalid("INVALID_POLARS_ENGINE")
    begin, finish = _clock(start), _clock(end)
    if (
        begin >= finish
        or begin.time() != datetime.min.time()
        or finish.time() != datetime.min.time()
        or not 1 <= (finish - begin).total_seconds() / 86400 <= 120
    ):
        raise ManifestInvalid("INVALID_ORACLE_STUDY_WINDOW")
    import polars as pl

    start_clock = perf_counter()
    input_root_sha = _source_digest(source_root)
    source_hash_seconds = perf_counter() - start_clock
    store = ImmutableCache(
        cache_root,
        max_object_bytes=MAX_PARQUET_BYTES,
        min_free_bytes=1024 * 1024 * 1024,
    )
    software_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    source_key = {
        "inputs": input_root_sha,
        "software": software_sha,
        "period": sha256(f"{start}/{end}".encode()).hexdigest(),
        "policy": sha256(b"HISTORICAL_ORACLE_SOURCE_EVENTS_V1").hexdigest(),
    }
    source, ignored, source_cache_status, decode_seconds = _source_cache(
        store,
        source_root,
        sha=input_root_sha,
        key=source_key,
        begin_ms=int(begin.timestamp() * 1000),
        end_ms=int(finish.timestamp() * 1000),
    )
    t1 = perf_counter()
    batch_key = {
        **source_key,
        "policy": sha256(POLICY.encode()).hexdigest(),
    }
    cached = store.load("oracle_batches", batch_key, version=SCHEMA)
    if cached is None:
        batch_frame = _batches(source, end_ms=int(finish.timestamp() * 1000), engine=engine)
        data = _as_parquet_bytes(batch_frame)
        store.publish("oracle_batches", batch_key, version=SCHEMA, content=data)
        cache_status = "CACHE_CREATED"
    else:
        data = cached
        batch_frame = pl.read_parquet(BytesIO(data))
        cache_status = "CACHE_HIT"
    output_sha = sha256(data).hexdigest()
    compile_seconds = perf_counter() - t1
    counts = (
        batch_frame.lazy()
        .group_by("delay_minutes")
        .agg(
            pl.len().alias("batches"),
            pl.sum("source_fill_count").alias("eligible_fills"),
        )
        .sort("delay_minutes")
        .collect(engine="streaming")
        .to_dicts()
    )
    accepted = source.height
    trial_rows = [
        {
            "delay_minutes": row["delay_minutes"],
            "batches": row["batches"],
            "eligible_fills": row["eligible_fills"],
            "merged_orders": row["eligible_fills"] - row["batches"],
            "right_censored_fills": accepted - row["eligible_fills"],
        }
        for row in counts
    ]
    if len(trial_rows) != len(DELAYS):
        raise ManifestBlocked("NOT_ALL_DELAY_SCENARIOS_REPRESENTED")
    logical = {
        "schema": SCHEMA,
        "source_collection_sha256": input_root_sha,
        "batch_parquet_sha256": output_sha,
        "input_fills_in_window": accepted,
        "per_delay": trial_rows,
    }
    return {
        **logical,
        "status": "HISTORICAL_ORACLE_BATCH_SCREEN_ONLY",
        "clock_basis": "HISTORICAL_ORACLE",
        "first_known_receipts_verified": False,
        "account_equity_pit_verified": False,
        "whole_book_verified": False,
        "contractual_pass_or_breach": "UNKNOWN",
        "scientifically_qualified": False,
        "unsupported_or_invalid_events": ignored,
        "source_hash_seconds": round(source_hash_seconds, 6),
        "source_decode_seconds": round(decode_seconds, 6),
        "source_cache_status": source_cache_status,
        "batch_compilation_seconds": round(compile_seconds, 6),
        "cache_status": cache_status,
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "parquet_bytes": len(data),
        "logical_sha256": sha256(_json_bytes(logical)).hexdigest(),
    }


def load_real_oracle_batches(cache_root: Path, *, start: str, end: str, source_sha256: str):
    """Load only sealed, software/version/policy-pinned batch data for market joins."""
    import polars as pl

    key = {
        "inputs": source_sha256,
        "software": sha256(Path(__file__).read_bytes()).hexdigest(),
        "period": sha256(f"{start}/{end}".encode()).hexdigest(),
        "policy": sha256(POLICY.encode()).hexdigest(),
    }
    store = ImmutableCache(
        cache_root,
        max_object_bytes=MAX_PARQUET_BYTES,
        min_free_bytes=1024 * 1024 * 1024,
    )
    data = store.load("oracle_batches", key, version=SCHEMA)
    if data is None:
        raise ManifestBlocked("MISSING_SEALED_REAL_ORACLE_TAPE")
    frame = pl.read_parquet(BytesIO(data))
    required = {
        "delay_minutes",
        "account_sha256",
        "instrument",
        "execute_ms",
        "source_fill_count",
        "first_event_ms",
        "last_event_ms",
    }
    if set(frame.columns) != required:
        raise ManifestBlocked("INVALID_SEALED_REAL_ORACLE_SCHEMA")
    return frame, sha256(data).hexdigest()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--engine", choices=("streaming", "in-memory"), default="streaming")
    args = parser.parse_args()
    print(
        json.dumps(
            compile_real_historical_oracle(
                args.source_root,
                args.cache_root,
                start=args.start,
                end=args.end,
                engine=args.engine,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
