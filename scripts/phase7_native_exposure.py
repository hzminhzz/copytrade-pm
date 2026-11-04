"""Read-only Phase 7 observed exposure study (not a follower-account simulator).

Reconstructs only source position intervals whose two endpoint fills agree.
Uses historical native minute close marks; never interprets event time as receipt.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

BASE = Path("/home/quant/dev/copytrade-pm")
MARKET = Path("/home/quant/dev/quant/ml4t-data/.data/store")
START_MS = 1785888000000  # 2026-08-05 UTC
END_MS = 1793664000000  # 2026-11-03 UTC (exclusive)
PORTFOLIOS = {
    "E2": ["ACT04", "S051-BTC", "S053-HYPE"],
    "E6": ["ACT04", "CM-002", "S051-BTC", "S053-HYPE", "Whale_0x5f94"],
    "P1": ["S035-ENA", "S051-BTC", "S053-HYPE"],
    "E3": ["ACT04", "CM-002", "S053-HYPE"],
    "P14": ["S035-ENA", "S051-BTC", "S053-HYPE", "S064-xyz:BRENTOIL", "Whale_0x5f94"],
}
def _load_private_aliases() -> dict[str, str]:
    """Resolve approved names from owner-private roster, never from Git."""
    roster = BASE / "docs/HL108_QUALIFIED_ROSTER_SUMMARY_20261103.csv"
    if not roster.is_file():
        return {}
    synonym = {
        "S035-ENA": "W016", "S051-BTC": "W080", "S053-HYPE": "W083",
        "S064-xyz:BRENTOIL": "W100",
    }
    requested = set(x for members in PORTFOLIOS.values() for x in members)
    resolved: dict[str, str] = {}
    with roster.open(newline="") as handle:
        for row in csv.DictReader(handle):
            address = row.get("address", "").lower()
            if not address.startswith("0x") or len(address) != 42:
                continue
            for alias in requested:
                expected = synonym.get(alias, alias)
                same_alias = row.get("alias") == expected
                whale = alias == "Whale_0x5f94" and row.get("alias") == "HL Perps Whale" \
                    and address.startswith(alias.split("_")[-1])
                if same_alias or whale:
                    if alias in resolved and resolved[alias] != address:
                        raise ValueError(f"conflicting private alias {alias}")
                    resolved[alias] = address
    return resolved


ALIASES = _load_private_aliases()


def source_files(root: Path) -> dict[str, Path]:
    found = {}
    for directory in ("wallet_fills_90d", "broader_active_inventory_fills_90d", "nansen_smart_money_fills_90d"):
        for path in (root / directory).glob("*.json"):
            # Require exact byte-backed source address, not a filename, prefix
            # substring, or ambiguous vendor display name.
            payload = json.loads(path.read_text())
            canonical_address = str(payload.get("address", "")).lower()
            for alias, address in ALIASES.items():
                if canonical_address == address:
                    if alias in found and found[alias] != path:
                        raise ValueError(f"duplicate source {alias}")
                    found[alias] = path
    return found


def consistent_intervals(raw: list[dict]) -> tuple[list[dict], dict]:
    """Build strictly supported fill-to-next-fill position intervals.

    Any unverified startPosition, discontinuity, same-ms event ambiguity,
    or end-censored segment contributes no exposure estimate.
    """
    groups = defaultdict(list)
    eligible = 0
    for i, f in enumerate(raw):
        ms = f.get("time")
        if not isinstance(ms, (int, float)) or not START_MS <= ms < END_MS:
            continue
        coin = f.get("coin")
        if not isinstance(coin, str) or ":" in coin or coin.startswith("@"):
            continue  # HIP-3/multi-DEX requires independent exact namespace
        try:
            starting = float(f["startPosition"])
            size = float(f["sz"])
            if not all(map(math.isfinite, (starting, size))) or size <= 0 or f["side"] not in ("B", "A"):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        groups[coin].append((int(ms), i, starting, size if f["side"] == "B" else -size))
        eligible += 1
    intervals = []
    n_gap = 0
    n_ambiguous = 0
    for coin, events in groups.items():
        events.sort()
        # Retain original intra-millisecond order; require sequence continuity.
        for j in range(len(events) - 1):
            ms, _, opening, delta = events[j]
            next_ms, _, next_open, _ = events[j + 1]
            after = opening + delta
            tolerance = max(1e-7, abs(after) * 1e-6)
            if abs(after - next_open) > tolerance:
                n_gap += 1
                continue
            if next_ms <= ms:
                n_ambiguous += 1
                continue
            if abs(after) <= 1e-10:
                continue
            intervals.append({"coin": coin, "start_ms": ms, "end_ms": next_ms, "qty": after})
    return intervals, {
        "eligible_fills": eligible,
        "supported_nonflat_intervals": len(intervals),
        "broken_adjacent_chains": n_gap,
        "same_timestamp_skips": n_ambiguous,
        "distinct_coins_with_start_position": len(groups),
    }


def native_marks(coin: str, start_ms: int, end_ms: int) -> pl.DataFrame | None:
    directory = MARKET / f"crypto_futures_ohlcv_1m_HYPERLIQUID_{coin}_PERP"
    if not directory.is_dir():
        return None
    # Exact day paths and source sidecar are required; no unverified cached reshaping.
    first = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date()
    last = datetime.fromtimestamp((end_ms - 1) / 1000, tz=timezone.utc).date()
    from datetime import timedelta
    day, paths = first, []
    while day <= last:
        folder = directory / f"year={day.year}" / f"month={day.month:02d}" / f"day={day.day:02d}"
        parquet = folder / "data.parquet"
        sidecar = folder / "source.json"
        if parquet.exists() and sidecar.exists():
            try:
                manifest = json.loads(sidecar.read_text())
                claimed = manifest.get("sha256")
                actual = hashlib.sha256(parquet.read_bytes()).hexdigest()
                if claimed == actual and manifest.get("bars") == 1440:
                    paths.append(str(parquet))
            except (OSError, ValueError, TypeError):
                pass  # missing or unverifiable day is not native evidence
        day += timedelta(days=1)
    if not paths:
        return None
    try:
        bars = pl.scan_parquet(paths, hive_partitioning=False).select(
            pl.col("timestamp").dt.replace_time_zone("UTC").dt.cast_time_unit("ms").alias("ts"),
            pl.col("close").cast(pl.Float64).alias("close"),
        ).filter(
            (pl.col("ts").dt.epoch("ms") >= start_ms)
            & (pl.col("ts").dt.epoch("ms") < end_ms)
        ).collect().sort("ts").unique(subset=["ts"], keep="first")
        return bars.with_columns(pl.col("ts").dt.epoch("ms").alias("ms")).select("ms", "close")
    except Exception:
        return None


def evaluate(root: Path, cap_coins: int = 30) -> dict:
    paths = source_files(root)
    observations = {}
    source_shas = {}
    all_intervals = {}
    counts = {}
    for alias in ALIASES:
        if alias not in paths:
            counts[alias] = {"source_status": "NO_RAW_START_POSITION_SOURCE", "supported_nonflat_intervals": 0}
            continue
        path = paths[alias]
        source_shas[alias] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = json.loads(path.read_text())
        intervals, detail = consistent_intervals(payload.get("fills", []))
        counts[alias] = {"source_status": "SOURCE_PARTIAL_POSITION_CHAIN", **detail}
        all_intervals[alias] = intervals

    wanted = set()
    for events in all_intervals.values():
        totals = defaultdict(int)
        for ev in events:
            totals[ev["coin"]] += ev["end_ms"] - ev["start_ms"]
        wanted.update(coin for coin, _ in sorted(totals.items(), key=lambda x: -x[1])[:cap_coins])
    # Finite-minute observations are always conditional on both matched source states and marks.
    for coin in sorted(wanted):
        by_wallet = {}
        for alias, intervals in all_intervals.items():
            evs = [x for x in intervals if x["coin"] == coin]
            if evs:
                by_wallet[alias] = evs
        if not by_wallet:
            continue
        start_ms = max(START_MS, min(x["start_ms"] for es in by_wallet.values() for x in es))
        end_ms = min(END_MS, max(x["end_ms"] for es in by_wallet.values() for x in es))
        bars = native_marks(coin, start_ms, end_ms)
        if bars is None or bars.is_empty():
            continue
        for alias, evs in by_wallet.items():
            frame = pl.DataFrame(evs).sort("start_ms")
            # Nonoverlapping intervals; mark bars only when source position is proven through the NEXT fill.
            marked = bars.join_asof(frame, left_on="ms", right_on="start_ms", strategy="backward").filter(
                pl.col("ms") < pl.col("end_ms")
            ).select("ms", "close", "qty").with_columns(
                (pl.col("qty") * pl.col("close")).alias("signed_notional")
            )
            if marked.is_empty():
                continue
            marked = marked.with_columns(
                pl.col("ms").shift(1).alias("prev_ms"),
                pl.col("close").shift(1).alias("prev_close"),
                pl.col("qty").shift(1).alias("prev_qty"),
            ).with_columns(
                pl.when(
                    (pl.col("ms") - pl.col("prev_ms") == 60_000)
                    & ((pl.col("qty") - pl.col("prev_qty")).abs() <= 1e-10)
                ).then(pl.col("qty") * (pl.col("close") - pl.col("prev_close")))
                .otherwise(None).alias("hold_only_one_minute_change_usd")
            ).drop("prev_ms", "prev_close", "prev_qty")
            observations.setdefault(alias, []).append(marked.with_columns(pl.lit(coin).alias("coin")))

    summary = {}
    combined_marks = {}
    for alias in ALIASES:
        frames = observations.get(alias, [])
        if not frames:
            summary[alias] = {"coverage": "NO_VERIFIED_MARKED_INTERVAL", **counts[alias]}
            continue
        full = pl.concat(frames, how="vertical")
        combined_marks[alias] = full
        grouped = full.group_by("ms").agg(
            pl.col("signed_notional").abs().sum().alias("gross"),
            pl.col("signed_notional").sum().alias("net"),
            pl.col("hold_only_one_minute_change_usd").sum().alias("hold_only_change"),
            pl.col("hold_only_one_minute_change_usd").count().alias("hold_only_valid_coins"),
            pl.len().alias("open_coin_count"),
        )
        summary[alias] = {
            **counts[alias],
            "coverage": "CONDITIONAL_KNOWN_CHAINS_NATIVE_CLOSE",
            "verified_market_minutes": grouped.height,
            "mean_gross_usd": round(grouped["gross"].mean(), 2),
            "peak_gross_usd": round(grouped["gross"].max(), 2),
            "max_concurrent_coins": grouped["open_coin_count"].max(),
            "hold_only_marked_minutes": grouped.filter(pl.col("hold_only_valid_coins") > 0).height,
            "worst_one_minute_hold_only_change_usd": round(grouped.filter(pl.col("hold_only_valid_coins") > 0)["hold_only_change"].min(), 2),
            "source_sha256": source_shas[alias],
        }
    pair_stats = {}
    for a, b in itertools.combinations(combined_marks, 2):
        joined = combined_marks[a].join(
            combined_marks[b], on=["ms", "coin"], how="inner", suffix="_other"
        ).filter((pl.col("signed_notional") != 0) & (pl.col("signed_notional_other") != 0))
        if joined.is_empty():
            continue
        agreement = (pl.col("signed_notional") * pl.col("signed_notional_other") > 0)
        pair_stats[f"{a}|{b}"] = {
            "same_coin_overlap_minutes": joined.height,
            "same_direction_overlap_minutes": joined.filter(agreement).height,
            "opposite_direction_overlap_minutes": joined.filter(~agreement).height,
            "jointly_observed_unique_minutes": joined["ms"].n_unique(),
        }
    portfolio_stats = {}
    for name, members in PORTFOLIOS.items():
        pair_names = [f"{a}|{b}" if f"{a}|{b}" in pair_stats else f"{b}|{a}"
            for a, b in itertools.combinations(members, 2)]
        available = [pair_stats[p] for p in pair_names if p in pair_stats]
        matching = sum(x["same_direction_overlap_minutes"] for x in available)
        opposing = sum(x["opposite_direction_overlap_minutes"] for x in available)
        coverage = {m: summary.get(m, {}).get("coverage", "UNKNOWN") for m in members}
        portfolio_stats[name] = {
            "members": members,
            "member_coverage": coverage,
            "pair_comparisons_observed": len(available),
            "pair_comparisons_expected": len(pair_names),
            "same_direction_share_of_observed_same_coin_pair_minutes": round(matching / (matching + opposing), 4) if matching + opposing else None,
            "same_direction_pair_minutes": matching,
            "opposite_direction_pair_minutes": opposing,
            "full_account_follower_pnl": None,
            "max_trailing_dd": None,
        }
    return {"scope": "CONDITIONAL_SOURCE_POSITION_CHAIN_NOT_ACCOUNT_EQUITY", "window_utc": ["2026-08-05", "2026-11-03"], "wallets": summary, "portfolios": portfolio_stats, "pair_overlap": pair_stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=BASE / "data")
    parser.add_argument("--cap-coins", type=int, default=30)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = json.dumps(evaluate(args.source_root, args.cap_coins), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        # Explicitly requested private research artifact, never tracked raw data.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("immutable report already exists")
        args.output.write_text(output)
        print(f"phase7_sha256={hashlib.sha256(output.encode()).hexdigest()}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
