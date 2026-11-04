"""Optional CM-002 lower-confidence CSV supplement to Phase 7 native-open screen.

This is deliberately separate from the SHA-verified raw-TID/source-position
lineage. The saved HL108 CSV has only second-precision event timestamps and
no native fill TIDs/startPosition. Treat rows as observations, not dedupable
exchange trade IDs; no whole-book exposure or account PnL is inferred.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from copytrade_pm.pm_offline_manifest import ManifestInvalid
from copytrade_pm.pm_offline_repository import native_instrument

if __package__:
    from scripts.phase7_native_exposure import ALIASES, BASE, END_MS, MARKET, START_MS
    from scripts.phase7_native_open_screen import (
        MAX_CANDIDATES,
        compile_candidates,
        compile_coin_candidates,
        join_native_context,
        report,
    )
else:
    from phase7_native_exposure import ALIASES, BASE, END_MS, MARKET, START_MS
    from phase7_native_open_screen import (
        MAX_CANDIDATES,
        compile_candidates,
        compile_coin_candidates,
        join_native_context,
        report,
    )


def secondary_rows(
    path: Path, *, expected_address: str
) -> tuple[dict[str, list[tuple[int, float, float]]], dict]:
    """Exact private address, source CSV row identity, *not* verified fill TID."""
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("MISSING_PRIVATE_PHASE4_CSV")
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    groups: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    counts = Counter()
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("alias") != "CM-002":
                continue
            if str(row.get("address", "")).lower() != expected_address.lower():
                raise ValueError("CM002_SECONDARY_CSV_IDENTITY_COLLISION")
            counts["source_rows"] += 1
            if counts["source_rows"] > 30_000:
                raise ValueError("CM002_SECONDARY_SOURCE_EXCEEDS_BOUND")
            try:
                time = datetime.fromisoformat(row["datetime_utc"])
                if time.tzinfo is None:
                    time = time.replace(tzinfo=UTC)
                else:
                    time = time.astimezone(UTC)
                ms = int(time.timestamp() * 1000)
                if not START_MS <= ms < END_MS:
                    counts["outside_window"] += 1
                    continue
                coin = row["coin"]
                if not isinstance(coin, str) or ":" in coin or coin.startswith("@"):
                    counts["unsupported_dex"] += 1
                    continue
                native_instrument(coin)
                qty = float(row["size"])
                price = float(row["price"])
                side = row["side"]
                if side not in ("B", "A") or not (
                    math.isfinite(qty) and qty > 0 and math.isfinite(price) and price > 0
                ):
                    counts["invalid_fill"] += 1
                    continue
                signed_qty = qty if side == "B" else -qty
                groups[coin].append((ms, signed_qty, price))
                counts["main_perp_second_precision_rows"] += 1
            except KeyError, ValueError, TypeError, ManifestInvalid:
                counts["invalid_fill"] += 1
    if not counts["main_perp_second_precision_rows"]:
        raise ValueError("CM002_SECONDARY_SOURCE_NO_SUPPORTED_EVENTS")
    return groups, {
        "status": "SECONDARY_CSV_SECOND_PRECISION_NO_TID_NO_STARTPOSITION",
        "source_sha256": source_sha,
        "event_identity_unique": False,
        "historical_first_known": False,
        "equity_faithful": False,
        "supported_coins": len(groups),
        "counts": dict(sorted(counts.items())),
    }


def run(
    source_root: Path,
    market_root: Path,
    csv_path: Path,
    *,
    max_days: int = 5500,
) -> dict:
    address = ALIASES.get("CM-002")
    if not address:
        raise ValueError("CM002_PRIVATE_ALIAS_UNRESOLVED")
    primary, sources = compile_candidates(source_root)
    if sources.get("CM-002", {}).get("status") != "MISSING_SOURCE_FILE":
        raise ValueError("CM002_PRIMARY_ALREADY_AVAILABLE_NO_SECONDARY_MIX")
    group, provenance = secondary_rows(csv_path, expected_address=address)
    supplement = [
        row
        for coin, events in group.items()
        for row in compile_coin_candidates("CM-002", coin, events)
    ]
    if not supplement or len(supplement) + primary.height > MAX_CANDIDATES:
        raise ValueError("CM002_SECONDARY_CANDIDATE_COUNT_BLOCKED")
    combined = pl.concat([primary, pl.DataFrame(supplement)], how="vertical")
    sources["CM-002"] = provenance
    joined, market_info = join_native_context(combined, market_root, max_market_days=max_days)
    output = report(joined, sources, market_info)
    output["schema"] = "phase7_secondary_cm002_native_open_context_v1"
    output["data_tiers"] = {
        "primary": "EXCHANGE_TID_RAW_MAIN_PERP_FILLS",
        "supplementary": "UNDEDUPLICATED_SECOND_PRECISION_CSV_ROWS",
    }
    output["portfolio_source_books_reconstructed"] = False
    output["CM002_historical_source_positions_available"] = False
    output["CM002_actual_trading_orders_certified"] = False
    output["source_equity_sizing_authorized"] = False
    for name, portfolio in output["portfolios"].items():
        if "CM-002" in portfolio.get("missing_source_wallets", []):
            raise ValueError("CM002_SECONDARY_WRONGLY_MARKED_MISSING")
        portfolio["secondary_source_wallets"] = ["CM-002"] if name == "E6" else []
        portfolio["whole_book_follower_pnl"] = None
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=BASE / "data")
    parser.add_argument("--market-root", type=Path, default=MARKET)
    parser.add_argument(
        "--secondary-csv",
        type=Path,
        default=BASE / "docs/HL108_ALL_90D_FILLS_CONSOLIDATED_20261103.csv.gz",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.source_root, args.market_root, args.secondary_csv)
    blob = json.dumps(output, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("IMMUTABLE_REPORT_EXISTS")
        args.output.write_text(blob)
    print(
        json.dumps(
            {
                "report_sha256": hashlib.sha256(blob.encode()).hexdigest(),
                "CM002_quality": output["source_wallets"]["CM-002"]["status"],
                "CM002_counts": output["source_wallets"]["CM-002"]["counts"],
                "E2_5m": output["portfolios"]["E2"]["delay_context"]["5"],
                "E6_5m": output["portfolios"]["E6"]["delay_context"]["5"],
                "native_days": output["native_market"]["required_market_days"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
