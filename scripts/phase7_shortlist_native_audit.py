"""Audited evidence completeness for already screened Phase 7 wallets.

Only full UTC one-minute bars entirely inside a consistent source-fill
position interval count as known exposure. No new portfolio optimization,
equity-normalization, executable PnL, or alpha qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import polars as pl

if __package__:
    from scripts.phase7_native_exposure import (
        BASE,
        END_MS,
        START_MS,
        consistent_intervals,
        native_marks_with_audit,
    )
else:
    from phase7_native_exposure import (
        BASE,
        END_MS,
        START_MS,
        consistent_intervals,
        native_marks_with_audit,
    )

MINUTE_MS = 60_000
MAX_WALLETS = 20
MAX_COIN_BUDGET = 40


def complete_minute_bins(interval: dict) -> int:
    """Count only full minute bars after opening and before closing source fill."""
    first = ((interval["start_ms"] + MINUTE_MS - 1) // MINUTE_MS) * MINUTE_MS
    last = ((interval["end_ms"] // MINUTE_MS) - 1) * MINUTE_MS
    return max(0, (last - first) // MINUTE_MS + 1)


def observed_interval_bars(intervals: list[dict], bars: pl.DataFrame) -> tuple[int, int]:
    """No partial-bar exposure; ms identifies beginning of each UTC minute."""
    full = [x for x in intervals if complete_minute_bins(x) > 0]
    if not full:
        return 0, 0
    frame = pl.DataFrame(full).sort("start_ms")
    matched = (
        bars.sort("ms")
        .join_asof(frame, left_on="ms", right_on="start_ms", strategy="backward")
        .filter(pl.col("ms") + MINUTE_MS <= pl.col("end_ms"))
    )
    return matched.height, matched["ms"].n_unique()


def raw_sources(root: Path, required_addresses: set[str]) -> dict[str, dict]:
    """Exact address matching to source JSON bytes, keeping paths private."""
    found = {}
    for folder in (
        "wallet_fills_90d",
        "broader_active_inventory_fills_90d",
        "nansen_smart_money_fills_90d",
    ):
        for path in (root / folder).glob("*.json"):
            blob = path.read_bytes()
            payload = json.loads(blob)
            address = str(payload.get("address", "")).lower()
            if address not in required_addresses:
                continue
            if address in found:
                raise ValueError("DUPLICATE_SOURCE_ADDRESS")
            found[address] = {
                "payload": payload,
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
    return found


def inspect_wallet(
    payload: dict,
    source_sha: str,
    *,
    max_coins: int = MAX_COIN_BUDGET,
) -> dict:
    intervals, detail = consistent_intervals(payload.get("fills", []))
    by_coin = defaultdict(list)
    for item in intervals:
        by_coin[item["coin"]].append(item)
    duration = {coin: sum(complete_minute_bins(x) for x in rows) for coin, rows in by_coin.items()}
    chosen = sorted(by_coin, key=lambda coin: (-duration[coin], coin))[:max_coins]
    possible = sum(duration.values())
    audited_possible = sum(duration[x] for x in chosen)
    supported = 0
    matched = 0
    missing_native = []
    coins = []
    for coin in chosen:
        records = by_coin[coin]
        first = max(START_MS, min(row["start_ms"] for row in records))
        end = min(END_MS, max(row["end_ms"] for row in records))
        if end <= first:
            continue
        bars, market_audit = native_marks_with_audit(coin, first, end)
        if bars is None or bars.is_empty():
            missing_native.append(coin)
            total, unique = 0, 0
        else:
            total, unique = observed_interval_bars(records, bars)
        supported += total
        matched += unique
        coins.append(
            {
                "coin": coin,
                "verified_full_minute_intervals": total,
                "unique_minutes": unique,
                "source_position_minutes": duration[coin],
                "unverified_position_minutes": duration[coin] - total,
                "native_market_day_audit": market_audit,
            }
        )
    return {
        "scope": "PARTIAL_FILL_CHAIN_CONSISTENCY_ON_VERIFIED_FULL_MINUTE_BARS",
        "source_sha256": source_sha,
        "source_eligibility": "SOURCE_FILL_STARTPOSITION_ONLY_NOT_ATOMIC_ACCOUNT_BOOK",
        **detail,
        "main_perp_source_coins": len(by_coin),
        "top_coins_audited": chosen,
        "unsupported_missing_native_coins": missing_native,
        "verified_full_minute_chain_bars": supported,
        "unique_verified_full_minute_chain_bars": matched,
        "full_minute_positions_all_source_coins": possible,
        "full_minute_positions_top_coins_before_native": audited_possible,
        "top_coin_coverage_fraction": round(audited_possible / possible, 4) if possible else None,
        "native_coverage_of_top_source_chain_minutes": round(supported / audited_possible, 4)
        if audited_possible
        else None,
        "verified_lower_bound_fraction_all_chain_minutes": round(supported / possible, 4)
        if possible
        else None,
        "unscanned_coins_due_to_limit": sorted(set(by_coin) - set(chosen)),
        "unscanned_chain_minutes_due_to_limit": possible - audited_possible,
        "unverified_chain_minutes_in_scanned_coins": audited_possible - supported,
        "coins_audited": len(chosen),
        "all_known_main_perp_coins_scanned": len(chosen) == len(by_coin),
        "by_coin": coins,
        "continuous_90d_book": False,
        "historical_source_nav": None,
        "risk_budget_follower_pnl": None,
    }


def run(
    candidate_json: Path,
    source_root: Path,
    *,
    max_coins: int = MAX_COIN_BUDGET,
    wallet_alias: str | None = None,
) -> dict:
    if not 1 <= max_coins <= MAX_COIN_BUDGET:
        raise ValueError("INVALID_NATIVE_COIN_BUDGET")
    cohort = json.loads(candidate_json.read_text())
    if cohort.get("schema") != "phase7_first_stage_candidate_screen_v2":
        raise ValueError("REQUIRES_CORRECTED_STAGE1_SCREEN")
    canonical_addresses = {
        address
        for name in ("top10_screen_three", "top10_screen_five")
        for row in cohort.get(name, [])
        for address in row["canonical_addresses"]
    }
    if not canonical_addresses or len(canonical_addresses) > MAX_WALLETS:
        raise ValueError("INVALID_BOUNDED_CANDIDATE_SCOPE")
    private = raw_sources(source_root, canonical_addresses)
    wallet_by_address = {
        address: name
        for name in ("top10_screen_three", "top10_screen_five")
        for row in cohort.get(name, [])
        for address, name in zip(row["canonical_addresses"], row["members"], strict=True)
    }
    if wallet_alias is not None and wallet_alias not in set(wallet_by_address.values()):
        raise ValueError("WALLET_ALIAS_NOT_IN_FROZEN_SCREEN")
    rows = {}
    for address, alias in sorted(wallet_by_address.items(), key=lambda kv: kv[1]):
        if wallet_alias is not None and alias != wallet_alias:
            continue
        source = private.get(address)
        if source is None:
            rows[alias] = {"scope": "MISSING_PRIVATE_SOURCE_JSON", "risk_budget_follower_pnl": None}
        else:
            rows[alias] = inspect_wallet(source["payload"], source["sha256"], max_coins=max_coins)
    combos = {}
    for key in ("top10_screen_three", "top10_screen_five"):
        if wallet_alias is not None:
            # The unobserved peers in a targeted audit cannot be called failed.
            combos[key] = []
            continue
        combos[key] = [
            {
                "members": item["members"],
                "all_members_some_verified_bar": all(
                    rows[x].get("verified_full_minute_chain_bars", 0) > 0 for x in item["members"]
                ),
                "min_member_native_coverage_of_top_chain": min(
                    (rows[x].get("native_coverage_of_top_source_chain_minutes") or 0)
                    for x in item["members"]
                ),
                "min_member_lower_bound_all_chain": min(
                    (rows[x].get("verified_lower_bound_fraction_all_chain_minutes") or 0)
                    for x in item["members"]
                ),
                "all_members_gte_80pct_known_chain_lower_bound": all(
                    (rows[x].get("verified_lower_bound_fraction_all_chain_minutes") or 0) >= 0.8
                    for x in item["members"]
                ),
                "risk_budget_follower_pnl": None,
                "new_portfolio_ranking": None,
            }
            for item in cohort[key]
        ]
    return {
        "schema": "phase7_stage1_native_chain_audit_v2",
        "audit_scope": "SINGLE_WALLET" if wallet_alias is not None else "FULL_SHORTLIST",
        "audit_wallet_alias": wallet_alias,
        "max_coins_per_wallet": max_coins,
        "source_stage1_sha256": hashlib.sha256(candidate_json.read_bytes()).hexdigest(),
        "study_window_start_ms": START_MS,
        "study_window_end_ms_exclusive": END_MS,
        "wallets": rows,
        "combinations": combos,
        "scientific_qualification": False,
        "trading_authorization": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("screen_json", type=Path)
    parser.add_argument("--source-root", type=Path, default=BASE / "data")
    parser.add_argument("--max-coins", type=int, default=MAX_COIN_BUDGET)
    parser.add_argument("--wallet-alias", type=str)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(
        args.screen_json,
        args.source_root,
        max_coins=args.max_coins,
        wallet_alias=args.wallet_alias,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("IMMUTABLE_PRIVATE_REPORT_EXISTS")
        args.output.write_text(encoded)
    print(
        json.dumps(
            {
                "report_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                "wallets": {
                    alias: {
                        key: val
                        for key, val in metrics.items()
                        if key
                        in (
                            "supported_nonflat_intervals",
                            "main_perp_source_coins",
                            "verified_full_minute_chain_bars",
                            "native_coverage_of_top_source_chain_minutes",
                            "verified_lower_bound_fraction_all_chain_minutes",
                            "unscanned_chain_minutes_due_to_limit",
                            "unverified_chain_minutes_in_scanned_coins",
                            "coins_audited",
                        )
                    }
                    for alias, metrics in result["wallets"].items()
                },
                "top10_combo_count": {key: len(v) for key, v in result["combinations"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
