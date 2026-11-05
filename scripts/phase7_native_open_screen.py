"""Exact native next-minute-open context for Phase 7 retrospective source batches.

Reuses the merged, SHA-verified PM-offline native market-day adapter.
This is a HYPOTHETICAL event-timed open-price screen, not follower execution.
No actual first-known, bid/ask, book depth, equity, broker fills or account PnL.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import polars as pl

from copytrade_pm.pm_offline_manifest import ManifestInvalid
from copytrade_pm.pm_offline_oracle_market import _day_record, _join_day
from copytrade_pm.pm_offline_repository import native_instrument

if __package__:
    from scripts.phase7_conditional_stress import SCALES
    from scripts.phase7_delay_cost_screen import DELAYS, batch_orders
    from scripts.phase7_native_exposure import BASE, END_MS, MARKET, START_MS, source_files
else:
    from phase7_conditional_stress import SCALES
    from phase7_delay_cost_screen import DELAYS, batch_orders
    from phase7_native_exposure import BASE, END_MS, MARKET, START_MS, source_files

DAY_MS = 86_400_000
MINUTE_MS = 60_000
MAX_MARKET_DAYS = 5500
MAX_CANDIDATES = 50_000


def strict_next_open_ms(eligible_ms: int) -> int:
    """Strictly later full UTC minute: never use a partly known current bar."""
    return (eligible_ms // MINUTE_MS + 1) * MINUTE_MS


def source_groups(raw: list[dict]) -> tuple[dict[str, list[tuple[int, float, float]]], dict]:
    """Validate main-perp source fills without treating them as first-known."""
    by_coin = defaultdict(list)
    counts: Counter[str] = Counter()
    unique = set()
    for f in raw:
        if not isinstance(f, dict):
            counts["INVALID_EVENT"] += 1
            continue
        try:
            ms = f["time"]
            if type(ms) is not int or not START_MS <= ms < END_MS:
                counts["OUTSIDE_90D_OR_INVALID_TIME"] += 1
                continue
            coin = f["coin"]
            if not isinstance(coin, str) or ":" in coin or coin.startswith("@"):
                counts["UNSUPPORTED_MAIN_PERP_SCOPE"] += 1
                continue
            market = native_instrument(coin)
            if market != f"hyperliquid:mainnet:perp:default:{coin}":
                counts["UNSUPPORTED_MAIN_PERP_SCOPE"] += 1
                continue
            side = f["side"]
            price = float(f["px"])
            size = float(f["sz"])
            if side not in ("B", "A") or not all(math.isfinite(n) and n > 0 for n in (price, size)):
                counts["BAD_SOURCE_FILL"] += 1
                continue
            tid = f.get("tid")
            if not isinstance(tid, int | str) or isinstance(tid, bool):
                counts["MISSING_VALID_TID"] += 1
                continue
            identity = (coin, str(tid))
            if identity in unique:
                counts["DUPLICATE_TID"] += 1
                continue
            unique.add(identity)
            qty = size if side == "B" else -size
            by_coin[coin].append((ms, qty, price))
            counts["VALID_SOURCE_EVENTS"] += 1
        except KeyError, ValueError, TypeError, ManifestInvalid:
            counts["BAD_SOURCE_FILL"] += 1
    return by_coin, dict(sorted(counts.items()))


def compile_coin_candidates(
    alias: str, coin: str, events: list[tuple[int, float, float]]
) -> list[dict]:
    """Reuse one event-time policy for direct raw fills and weaker CSV rows."""
    ordered = sorted(events)
    times = [row[0] for row in ordered]
    instrument = native_instrument(coin)
    result: list[dict] = []
    for delay in DELAYS:
        for eligible_ms, signed_qty, ref_price, collapsed in batch_orders(ordered, delay * 60):
            execute_ms = strict_next_open_ms(eligible_ms)
            if not START_MS <= execute_ms < END_MS:
                continue
            start_ms = eligible_ms - delay * MINUTE_MS
            last_ms = times[bisect_left(times, eligible_ms) - 1] if delay else eligible_ms
            if last_ms < start_ms:
                raise ValueError("INCONSISTENT_BATCH_EVENT_CLOCK")
            result.append(
                {
                    "alias": alias,
                    "coin": coin,
                    "instrument": instrument,
                    "delay_minutes": delay,
                    "account_sha256": hashlib.sha256(alias.encode()).hexdigest(),
                    "execute_ms": execute_ms,
                    "day_number": execute_ms // DAY_MS,
                    "source_fill_count": collapsed,
                    "first_event_ms": start_ms,
                    "last_event_ms": last_ms,
                    "signed_qty": signed_qty,
                    "reference_last_leader_px": ref_price,
                }
            )
    return result


def compile_candidates(root: Path) -> tuple[pl.DataFrame, dict]:
    files = source_files(root)
    needed = sorted(set().union(*(set(x) for x in SCALES.values())))
    candidates: list[dict] = []
    sources: dict = {}
    for alias in needed:
        if alias not in files:
            sources[alias] = {"status": "MISSING_SOURCE_FILE"}
            continue
        payload_bytes = files[alias].read_bytes()
        payload = json.loads(payload_bytes)
        groups, counts = source_groups(payload.get("fills", []))
        sources[alias] = {
            "status": "READ_ONLY_RETROSPECTIVE_SOURCE_EVENTS",
            "source_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "counts": counts,
            "coin_count_main_perp": len(groups),
        }
        for coin, events in groups.items():
            candidates.extend(compile_coin_candidates(alias, coin, events))
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError("EXCEEDS_BOUNDED_RETROSPECTIVE_CANDIDATES")
    if not candidates:
        raise ValueError("NO_SUPPORTED_SOURCE_BATCHES")
    return pl.DataFrame(candidates).sort(
        ["instrument", "execute_ms", "delay_minutes", "alias"]
    ), sources


def join_native_context(
    candidates: pl.DataFrame,
    market_root: Path,
    *,
    max_market_days: int = MAX_MARKET_DAYS,
) -> tuple[pl.DataFrame, dict]:
    """Reuse sha-pinned existing day matcher; isolate missing days by status."""
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
        raise ValueError("EXCEEDS_BOUNDED_NATIVE_MARKET_DAY_FINGERPRINT")
    pinned = {key: _day_record(market_root, *key) for key in needed}
    result = []
    for (market, day), group in candidates.partition_by(
        ["instrument", "day_number"], as_dict=True
    ).items():
        part = _join_day(market_root, market, day, group, pinned)
        if part.height != group.height:
            raise ValueError("NATIVE_JOIN_CHANGED_BATCH_COUNT")
        result.append(part)
    joined = pl.concat(result, how="vertical").sort(
        ["instrument", "execute_ms", "delay_minutes", "alias"]
    )
    counts = dict(Counter(row["status"] for row in pinned.values()))
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                f"{market}@{day}": {
                    "status": d["status"],
                    "data_sha256": d["data_sha256"],
                    "metadata_sha256": d["metadata_sha256"],
                }
                for (market, day), d in sorted(pinned.items())
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return joined, {
        "required_market_days": len(required),
        "verified_and_predecessor_market_days": len(needed),
        "native_day_statuses": counts,
        "market_fingerprint_sha256": fingerprint,
    }


def report(joined: pl.DataFrame, sources: dict, market_info: dict) -> dict:
    output: dict = {
        "schema": "phase7_exact_native_open_context_screen_v1",
        "clock_basis": "HISTORICAL_SOURCE_EVENT_PLUS_DELAY_NOT_PIT_FIRST_KNOWN",
        "execution_time": "STRICT_NEXT_MINUTE_AFTER_ELIGIBILITY",
        "market_px": "VERIFIED_NATIVE_NEXT_MINUTE_OHLCV_OPEN_NOT_BID_ASK",
        "volume_px": "VERIFIED_COMPLETED_PREVIOUS_MINUTE_BASE_VOLUME",
        "financial_follower_pnl": None,
        "scientifically_qualified": False,
        "native_market": market_info,
        "source_wallets": sources,
        "portfolios": {},
    }
    for portfolio, scales in SCALES.items():
        member_rows = joined.filter(pl.col("alias").is_in(list(scales)))
        portfolio_result = {}
        for delay in DELAYS:
            frame = member_rows.filter(pl.col("delay_minutes") == delay)
            status = Counter(frame["match_status"].to_list())
            eligible = (
                frame.filter(pl.col("match_status") == "MATCHED_SCREEN_ONLY")
                .with_columns(
                    pl.col("alias").replace_strict(scales).cast(pl.Float64).alias("k"),
                )
                .with_columns(
                    (
                        pl.col("signed_qty").abs()
                        * pl.col("next_open_float_screen_only")
                        * pl.col("k")
                    ).alias("follower_notional_usd"),
                    (
                        (pl.col("next_open_float_screen_only") - pl.col("reference_last_leader_px"))
                        * pl.col("signed_qty")
                        * pl.col("k")
                    ).alias("adverse_price_move_usd"),
                    (
                        pl.col("signed_qty").abs()
                        * pl.col("k")
                        / pl.col("prior_base_volume_screen_only")
                    ).alias("prior_minute_participation"),
                )
            )
            matched = eligible.height
            notional = float(eligible["follower_notional_usd"].sum()) if matched else 0.0
            movement = float(eligible["adverse_price_move_usd"].sum()) if matched else 0.0
            if matched:
                capped = eligible.filter(pl.col("prior_base_volume_screen_only") > 0).filter(
                    pl.col("prior_minute_participation") <= 0.05
                )
                if capped.height:
                    capped_notional = float(capped["follower_notional_usd"].sum())
                else:
                    capped_notional = 0.0
                nonpos = eligible.filter(pl.col("prior_base_volume_screen_only") <= 0).height
                above = eligible.filter(
                    (pl.col("prior_minute_participation") > 0.05)
                    & (pl.col("prior_base_volume_screen_only") > 0)
                ).height
            else:
                capped_notional, nonpos, above = 0.0, 0, 0
            portfolio_result[str(delay)] = {
                "candidate_batches": frame.height,
                "matched_native_batches": matched,
                "match_rate": round(matched / frame.height, 4) if frame.height else None,
                "statuses": dict(sorted(status.items())),
                "matched_notional_usd": round(notional, 2) if matched else None,
                "signed_leader_to_next_open_price_move_usd": round(movement, 2)
                if matched
                else None,
                "illustrative_10bps_on_matched_notional_usd": round(notional * 0.001, 2)
                if matched
                else None,
                "illustrative_30bps_on_matched_notional_usd": round(notional * 0.003, 2)
                if matched
                else None,
                "participation_above_5pct_prior_complete_minute": above,
                "zero_prior_complete_minute_volume": nonpos,
                "notional_passes_5pct_prior_minute_cap": round(capped_notional, 2)
                if matched
                else None,
                "full_population_follower_returns": None,
            }
        output["portfolios"][portfolio] = {
            "missing_source_wallets": [
                alias
                for alias in scales
                if sources.get(alias, {}).get("status", "MISSING_SOURCE_FILE")
                == "MISSING_SOURCE_FILE"
            ],
            "delay_context": portfolio_result,
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=BASE / "data")
    parser.add_argument("--market-root", type=Path, default=MARKET)
    parser.add_argument("--max-days", type=int, default=MAX_MARKET_DAYS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    frame, sources = compile_candidates(args.source_root)
    joined, market_info = join_native_context(
        frame, args.market_root, max_market_days=args.max_days
    )
    payload = json.dumps(report(joined, sources, market_info), sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("IMMUTABLE_REPORT_EXISTS")
        args.output.write_text(payload)
    print(
        json.dumps(
            {
                "report_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "summary": json.loads(payload)["portfolios"],
                "market": market_info,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
