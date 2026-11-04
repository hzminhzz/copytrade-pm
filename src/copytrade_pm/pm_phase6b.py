"""Phase 6B: immutable, offline native-market coverage preflight for frozen Gemini pods.

This is a research evidence gate, not an execution engine. A blocked source
cannot produce account PnL, shock survival, or a challenge pass verdict.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import gzip
from hashlib import sha256
import json
from pathlib import Path

START = datetime(2026, 8, 5, 4, 30, tzinfo=UTC)
END = datetime(2026, 11, 3, 4, 30, tzinfo=UTC)
WALLETS = {
    "A_base": {"H21": 25, "N01": 25, "N07": 20, "N02": 15, "H17": 15},
    "A_active": {"H21": 35, "N01": 35, "N07": 30, "N02": 25, "H17": 25},
    "B_base": {"N01": 25, "N07": 25, "N02": 20, "N05": 15, "ACT08": 15},
    "B_active": {"N01": 35, "N07": 35, "N02": 30, "N05": 25, "ACT08": 35},
    "C_equal": {"H21": 100 / 3, "N01": 100 / 3, "N07": 100 / 3},
    "D_equal": {"N01": 100 / 3, "N07": 100 / 3, "ACT08": 100 / 3},
}
DD_CLAIMS = {"N07": 0.03, "A_base": 1.02, "A_active": 1.60, "B_base": 0.46}
REQUIRED_FROZEN_IDS = {
    "A_base": "Ensemble_A_Pure_New50_1x",
    "A_active": "Ensemble_A_Pure_New50_Active_1.5x",
    "B_base": "Ensemble_B_CrossCohort_Hybrid_1x",
    "B_active": "Ensemble_B_CrossCohort_Hybrid_Active_1.6x",
}
ONE_MINUTE = timedelta(minutes=1)


def source_market_scope(coin: str) -> str:
    """Classify official Hyperliquid fill coin names before perp-only pricing.

    Official spot tokens use @<spot-pair-index> (e.g., @107 is HYPE/USDC)
    or PURR/USDC. Binary/special # IDs are not perpetual positions.
    Never silently promote either class into the perp market book.
    """
    if not isinstance(coin, str) or not coin:
        raise ValueError("SOURCE_INSTRUMENT_IDENTITY_MISSING")
    if coin.startswith("@"):
        if not coin[1:].isdigit():
            raise ValueError("INVALID_SOURCE_SPOT_INSTRUMENT")
        return "SPOT"
    if coin == "PURR/USDC":
        return "SPOT"
    if coin.startswith("#"):
        if not coin[1:].isdigit():
            raise ValueError("INVALID_SOURCE_SPECIAL_INSTRUMENT")
        return "BINARY_OR_SPECIAL"
    if ":" in coin:
        dex, symbol = coin.split(":", 1)
        if dex not in {"xyz", "io", "para"} or not symbol.isalnum():
            raise ValueError("UNRECOGNIZED_SOURCE_PERP_NAMESPACE")
    elif not coin.isalnum():
        raise ValueError("UNRECOGNIZED_SOURCE_MARKET_SCOPE")
    return "PERP"


def fingerprint(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def require_same_frozen(portfolios: list[dict]) -> None:
    indexed = {x["portfolio_id"]: x for x in portfolios}
    for key, original in REQUIRED_FROZEN_IDS.items():
        members = indexed[original]["members"]
        actual = {x["member_alias"]: D(str(x["original_weight_percent"])) for x in members}
        expected = {name: D(str(weight)) for name, weight in WALLETS[key].items()}
        if actual != expected:
            raise ValueError("PHASE5_FROZEN_WEIGHTS_CHANGED:" + key)


def inspect_fill_chain(fills: list[dict], address: str) -> dict:
    """Account for initial unknown books, linked same-ms fills and gaps.

    A source zero-after observation can establish that *instrument* is flat
    subsequently, but no partial list proves all-DEX full-wallet continuity.
    """
    by_coin = defaultdict(list)
    blockers = Counter()
    excluded_scopes = Counter()
    total_fills_in_window = 0
    seen = set()
    for row in fills:
        if row.get("user", "").lower() != address.lower():
            raise ValueError("FILL_WALLET_IDENTITY_MISMATCH")
        coin, tid = row.get("coin"), row.get("tid")
        if not isinstance(coin, str) or not coin or tid is None:
            raise ValueError("UNRESOLVED_FILL_IDENTITY")
        if (coin, str(tid)) in seen:
            blockers["DUPLICATE_COIN_TID"] += 1
        seen.add((coin, str(tid)))
        try:
            t = datetime.fromtimestamp(int(row["time"]) / 1000, UTC)
            qty, prior, price = (D(str(row[k])) for k in ("sz", "start_position", "px"))
        except (KeyError, ValueError, ArithmeticError, TypeError, OverflowError) as exc:
            raise ValueError("INVALID_FILL_FIELDS") from exc
        side = row.get("side")
        if side not in ("A", "B") or qty <= 0 or price <= 0:
            raise ValueError("INVALID_FILL_SIDE_SIZE_OR_PRICE")
        if not all(x.is_finite() for x in (qty, prior, price)):
            raise ValueError("NONFINITE_FILL")
        after = prior + (qty if side == "B" else -qty)
        if START <= t < END:
            total_fills_in_window += 1
            scope = source_market_scope(coin)
            if scope != "PERP":
                excluded_scopes[scope] += 1
                continue
            by_coin[coin].append((t, str(tid), prior, after))
    instruments = []
    for coin, records in sorted(by_coin.items()):
        records.sort(key=lambda x: x[0])
        prev = None
        first_before = None
        breaks = 0
        anchor = None
        for instant in sorted({r[0] for r in records}):
            remaining = [r for r in records if r[0] == instant]
            while remaining:
                linked = [r for r in remaining if prev is not None and _same(prev, r[2])]
                if linked:
                    pick = min(linked, key=lambda r: r[1])
                else:
                    starts = [
                        r
                        for r in remaining
                        if not any(_same(y[3], r[2]) for y in remaining if y is not r)
                    ]
                    pick = min(starts or remaining, key=lambda r: r[1])
                remaining.remove(pick)
                if first_before is None:
                    first_before = pick[2]
                if prev is not None and not _same(prev, pick[2]):
                    breaks += 1
                if pick[3] == 0 and anchor is None:
                    anchor = pick[0].isoformat()
                prev = pick[3]
        if breaks:
            blockers["POSITION_CHAIN_BREAK"] += breaks
        if first_before != 0:
            blockers["UNKNOWN_PRE_ANCHOR_POSITION"] += 1
        if anchor is None:
            blockers["NO_OBSERVED_FLAT_ANCHOR"] += 1
        instruments.append(
            {
                "instrument": coin,
                "fills_in_window": len(records),
                "initial_source_position": str(first_before),
                "first_observed_event_at": records[0][0].isoformat(),
                "last_source_position": str(prev),
                "first_observed_flat_after_at": anchor,
                "chain_breaks": breaks,
                "full_wallet_continuity_verified": False,
            }
        )
    return {
        "instruments": instruments,
        "counts": dict(blockers),
        "fill_events_in_window": sum(x["fills_in_window"] for x in instruments),
        "raw_fills_in_window": total_fills_in_window,
        "excluded_nonperp_fills_by_scope": dict(excluded_scopes),
        "excluded_nonperp_collateral_reconciled": False,
    }


def _same(a: D, b: D) -> bool:
    return abs(a - b) <= D("0.0000001") * max(D(1), abs(a))


def _market_directory(market_root: Path, coin: str) -> tuple[Path | None, str]:
    try:
        scope = source_market_scope(coin)
    except ValueError:
        return None, "UNSUPPORTED_SYMBOL"
    if scope != "PERP":
        return None, "OUT_OF_SCOPE_NONPERP_INSTRUMENT"
    if ":" in coin:
        dex, symbol = coin.split(":", 1)
        if dex not in {"xyz", "io", "para"} or not symbol.isalnum():
            return None, "UNSUPPORTED_DEX_OR_SYMBOL"
        return (
            market_root
            / ("crypto_futures_ohlcv_1m_HYPERLIQUID_" + dex.upper() + "_PERP")
            / ("symbol=" + symbol)
        ), coin
    if not coin.isalnum():
        return None, "UNSUPPORTED_SYMBOL"
    return market_root / ("crypto_futures_ohlcv_1m_HYPERLIQUID_" + coin + "_PERP"), coin


def market_days(
    market_root: Path, coin: str, *, start: datetime = START, end: datetime = END
) -> dict:
    family, symbol = _market_directory(market_root, coin)
    if family is None:
        return {
            "status": symbol,
            "expected_days": 0,
            "native_days": 0,
            "coverage_pct": None,
            "missing_days": [],
            "source_types": [],
        }
    cursor = start.date()
    days = 0
    available = 0
    absent = []
    rejected = []
    types = Counter()
    while cursor <= (end - timedelta(microseconds=1)).date():
        days += 1
        day = (
            family
            / f"year={cursor.year:04d}"
            / f"month={cursor.month:02d}"
            / f"day={cursor.day:02d}"
        )
        meta, parquet = day / "source.json", day / "data.parquet"
        if not meta.is_file() or not parquet.is_file():
            absent.append(cursor.isoformat())
        else:
            try:
                doc = json.loads(meta.read_text())
                checksum = doc.get("sha256")
                valid = (
                    doc.get("exchange") in {"hyperliquid_futures", "hyperliquid", "HYPERLIQUID"}
                    and doc.get("source_symbol") == symbol
                    and doc.get("source_type") in {"trades", "candles"}
                    and isinstance(checksum, str)
                    and len(checksum) == 64
                )
                if valid:
                    available += 1
                    types[doc["source_type"]] += 1
                else:
                    rejected.append(cursor.isoformat())
            except OSError, ValueError, TypeError:
                rejected.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return {
        "status": "DAY_MANIFEST_INVENTORY_NOT_MINUTE_SHA_VALIDATED",
        "expected_days": days,
        "native_days": available,
        "coverage_pct": round(100 * available / days, 3),
        "missing_days": absent,
        "invalid_manifest_days": rejected,
        "source_types": dict(types),
        "all_parquet_hashes_verified": False,
        "all_minute_gaps_verified": False,
    }


def safe_write_json(path: Path, value: dict | list) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError("IMMUTABLE_RESEARCH_GENERATION_CONFLICT")
    else:
        path.write_bytes(raw)
        path.chmod(0o600)
    return sha256(raw).hexdigest()


def locate_phase4_wallet(root: Path, address: str) -> Path:
    """Resolve one existing raw Phase4 wallet by signed address, not filename.

    There is no API request and no rewrite. Require exactly one raw match; the
    aggregated Gemini CSV loses position-before values and is NOT a substitute.
    """
    paths = sorted(root.glob("*.json"))
    if not paths or len(paths) > 100:
        raise ValueError("PHASE4_UNBOUNDED_OR_EMPTY_SOURCE_ROOT")
    matches = []
    for path in paths:
        obj = json.loads(path.read_text())
        if isinstance(obj, dict) and str(obj.get("address", "")).lower() == address.lower():
            matches.append(path)
    if len(matches) != 1:
        raise ValueError("PHASE4_UNIQUE_RAW_WALLET_NOT_FOUND")
    return matches[0]


def normalize_phase4_wallet(source: dict, address: str) -> list[dict]:
    """Unify actual native HL startPosition and HyperX start_position keys."""
    if str(source.get("address", "")).lower() != address.lower():
        raise ValueError("PHASE4_SOURCE_ACCOUNT_MISMATCH")
    fills = source.get("fills")
    if not isinstance(fills, list) or len(fills) != source.get("total_fills_90d"):
        raise ValueError("PHASE4_SOURCE_FILL_COUNT_MISMATCH")
    if (int(source.get("hl_fills_count", -1)) + int(source.get("hx_fills_count", -1))) != len(
        fills
    ):
        raise ValueError("PHASE4_HL_HYPERX_COUNT_MISMATCH")
    normalized = []
    for f in fills:
        if not isinstance(f, dict):
            raise ValueError("PHASE4_FILL_NOT_OBJECT")
        position = f.get("start_position", f.get("startPosition"))
        if position is None or "startPosition" in f and "start_position" in f:
            raise ValueError("PHASE4_MISSING_OR_AMBIGUOUS_START_POSITION")
        if "user" in f and str(f["user"]).lower() != address.lower():
            raise ValueError("PHASE4_FILL_DIFFERENT_OWNER")
        normalized.append({**f, "user": address, "start_position": position})
    return normalized


def preflight(
    *, phase5: Path, new50: Path, market_root: Path, out: Path, phase4_source: Path | None = None
) -> dict:
    source = json.loads(phase5.read_text())
    require_same_frozen(source["portfolios"])
    mappings = {m["member_alias"]: m for p in source["portfolios"] for m in p["members"]}
    roster_path = new50 / "NEW50_FULL_VENDOR_FILL_ROSTER_20261103.csv"
    roster = {r["address"].lower(): r for r in csv.DictReader(roster_path.open())}
    unique = set().union(*(set(p) for p in WALLETS.values()))
    wallets = {}
    used_coins = set()
    provenance = {"phase5_manifest": fingerprint(phase5), "new50_roster": fingerprint(roster_path)}
    for alias in sorted(unique):
        address = mappings[alias]["address"].lower()
        if alias == "ACT08":
            if phase4_source is None:
                raise ValueError("PHASE4_POSITION_AWARE_RAW_SOURCE_REQUIRED")
            path = locate_phase4_wallet(Path(phase4_source), address)
            checksum = fingerprint(path)
            raw = json.loads(path.read_bytes())
            normalized = normalize_phase4_wallet(raw, address)
            if checksum != fingerprint(path):
                raise ValueError("PHASE4_RAW_CHANGED_DURING_READ")
            chain = inspect_fill_chain(normalized, address)
            used_coins.update(x["instrument"] for x in chain["instruments"])
            wallets[alias] = {
                "alias": alias,
                "source_status": "VERIFIED_FILE_INCOMPLETE_ACCOUNT_BOOK",
                "source_file_sha256": checksum,
                "source_fills_total": len(normalized),
                "source_position": chain,
                "full_account_equity": "UNKNOWN",
                "account_mode": mappings[alias]["account_mode"],
                "first_known_receipts": "UNKNOWN",
                "full_account_book_qualified": False,
                "reason": "HL public and HyperX historical raw fills normalized without rewriting original bytes.",
            }
            provenance["fill_" + alias] = checksum
            continue
        record = roster.get(address)
        if record is None:
            raise ValueError("FROZEN_WALLET_MISSING_FROM_ROSTER:" + alias)
        path = new50 / "wallet_fills_90d" / (address + ".json.gz")
        digest = fingerprint(path)
        if digest != record["file_sha256"]:
            raise ValueError("SOURCE_FILL_SHA_MISMATCH:" + alias)
        raw = json.loads(gzip.decompress(path.read_bytes()))
        if raw.get("address", "").lower() != address:
            raise ValueError("SOURCE_FILL_ADDRESS_MISMATCH:" + alias)
        if len(raw["fills"]) != int(record["total_fills"]):
            raise ValueError("SOURCE_FILL_COUNT_MISMATCH:" + alias)
        chain = inspect_fill_chain(raw["fills"], address)
        used_coins.update(x["instrument"] for x in chain["instruments"])
        wallets[alias] = {
            "alias": alias,
            "source_status": "VERIFIED_FILE_INCOMPLETE_ACCOUNT_BOOK",
            "source_file_sha256": digest,
            "source_fills_total": len(raw["fills"]),
            "source_position": chain,
            "full_account_equity": "UNKNOWN",
            "account_mode": mappings[alias]["account_mode"],
            "first_known_receipts": "UNKNOWN",
            "full_account_book_qualified": False,
        }
        provenance["fill_" + alias] = digest
    market = {coin: market_days(market_root, coin) for coin in sorted(used_coins)}
    for row in wallets.values():
        for inst in row.get("source_position", {}).get("instruments", []):
            inst["market_day"] = market[inst["instrument"]]
            inst["historical_follower_full_book_status"] = "BLOCKED"
    portfolio_states = []
    for name, weights in WALLETS.items():
        portfolio_states.append(
            {
                "portfolio": name,
                "members": list(weights),
                "nominal_capital_weights_percent": weights,
                "faithful_equity_account_pnl": None,
                "max_daily_dd_pct": None,
                "max_trailing_dd_pct": None,
                "first_passage_result": "UNKNOWN",
                "status": "BLOCKED_SOURCE_EQUITY_AND_FULL_BOOK",
                "blocked_sources": [
                    x
                    for x in weights
                    if wallets[x]["source_status"] != "VERIFIED_FILE_INCOMPLETE_ACCOUNT_BOOK"
                ],
            }
        )
    assumptions = {
        "schema": "phase6b_frozen_assumptions_v1",
        "study_start_utc": START.isoformat(),
        "study_end_exclusive_utc": END.isoformat(),
        "hypothetical_initial_equity_usd": 10000,
        "daily_drawdown": [0.05, 0.045],
        "trailing_drawdown": 0.10,
        "target": 0.10,
        "internal_supervisor_daily_soft": 0.035,
        "internal_daily_hard": 0.045,
        "internal_trailing": 0.085,
        "pod_nominal_daily_aggregate": 0.03,
        "policies": ["P0", "P1", "P2"],
        "stress": ["S1", "S2", "S3_10", "S3_20", "S3_30", "S4", "S5", "S6", "S7", "S8"],
        "execution_wait_minutes": 5,
        "source_event_is_not_follower_first_known": True,
        "source_notional_over_compatible_equity_required": True,
        "portfolios": WALLETS,
        "source_phase5_three_pod_controls_gemini_optimized": False,
        "active_is_nominal_capital_scaling_not_measured_risk": True,
        "research_not_live": True,
    }
    coverage = {
        "schema": "phase6b_source_coverage_v1",
        "wallets": wallets,
        "market_day_inventory": market,
        "portfolios": portfolio_states,
        "market_day_inventory_is_not_minute_integrity": True,
        "historical_source_equity_is_not_current_equity": True,
    }
    out.mkdir(parents=True, mode=0o700, exist_ok=True)
    out.chmod(0o700)
    artifact_shas = {
        "assumptions.json": safe_write_json(out / "assumptions.json", assumptions),
        "source_coverage.json": safe_write_json(out / "source_coverage.json", coverage),
    }
    report = [
        "# Phase 6B: frozen Phase 5 independent preflight",
        "",
        "Result: **BLOCKED** for full-book, source-equity-faithful historical account PnL.",
        "Historical fill events are not follower first-known observations. No orders were sent.",
        "",
        "## Data gates",
        "",
        "| Wallet | File | In-window fills | Instruments | Instrument chain breaks | Unknown opening positions | Market-day manifest gaps |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for alias, row in sorted(wallets.items()):
        pos = row.get("source_position", {})
        days = sum(len(x["market_day"].get("missing_days", [])) for x in pos.get("instruments", []))
        counts = pos.get("counts", {})
        report.append(
            f"| {alias} | {row['source_status']} | {pos.get('fill_events_in_window', '—')} | "
            f"{len(pos.get('instruments', []))} | {counts.get('POSITION_CHAIN_BREAK', '—')} | "
            f"{counts.get('UNKNOWN_PRE_ANCHOR_POSITION', '—')} | {days if pos else '—'} |"
        )
    report.extend(
        [
            "",
            "Native market-day manifests are inventoried, **not** validated for continuous minute coverage or all SHA bytes.",
            "The market source can provide close-price proxies after exact-minute, sidecar and SHA verification.",
            "No continuous source-equity history, collateral/funding reconciliation or complete verified source books",
            "were available as inputs to this preflight. ACT08's original Phase4 raw source has start-position fields, but still lacks full account history.",
            "",
            "## Gemini DD verification",
            "",
            "| Claim | Gemini reported max trailing DD | Independent DD |",
            "|---|---:|---|",
        ]
    )
    for claim, value in DD_CLAIMS.items():
        report.append(
            f"| {claim} | {value:.2f}% | UNKNOWN — faithful portfolio reconstruction blocked |"
        )
    report.extend(
        [
            "",
            "## P0/P1/P2 and S1–S8",
            "",
            "All $10,000 follower equity, DD, stop-order and target/breach statistics are NULL.",
            "Do not read a null result as zero risk or as the portfolio surviving a shock.",
            "Full-book synced minute paths, compatible historical equity and all-DEX evidence",
            "must pass their individual gates before retrospective execution is defensible.",
            "",
            "## Three versus five pods",
            "",
            "C (H21/N01/N07) and D (N01/N07/ACT08) are equal-capital diagnostic controls only.",
            "They are not Gemini-optimized. Normalized **loss risk** cannot be inferred from",
            "equal nominal allocations. Structure ranking remains UNKNOWN.",
            "",
            "Status: NOT SCIENTIFICALLY QUALIFIED. No forward matched follower evidence.",
        ]
    )
    text = "\n".join(report) + "\n"
    report_path = out / "phase6b_report.md"
    if report_path.exists() and report_path.read_text() != text:
        raise FileExistsError("IMMUTABLE_REPORT_CONFLICT")
    report_path.write_text(text)
    report_path.chmod(0o600)
    artifact_shas["phase6b_report.md"] = fingerprint(report_path)
    manifest = {
        "schema": "phase6b_coverage_generation_v1",
        "status": "BLOCKED",
        "inputs_sha256": provenance,
        "artifacts_sha256": artifact_shas,
        "science_qualified": False,
        "orders_sent": False,
        "equity_curve_produced": False,
        "reason": "NO_COMPLETE_HISTORICAL_ACCOUNT_EQUITY_OR_BOOK",
    }
    safe_write_json(out / "manifest.json", manifest)
    return {
        "status": "BLOCKED_SOURCE_EQUITY_AND_BOOK",
        "generation": str(out),
        "wallet_count": len(wallets),
        "instrument_count": len(market),
        "portfolios": len(portfolio_states),
        "source_sha_verified_wallets": sum(bool(x["source_file_sha256"]) for x in wallets.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase5", type=Path, required=True)
    parser.add_argument("--new50", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase4-source", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            preflight(
                phase5=args.phase5,
                new50=args.new50,
                market_root=args.market_root,
                out=args.output,
                phase4_source=args.phase4_source,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
