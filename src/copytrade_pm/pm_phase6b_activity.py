"""Phase 6B: market-data repair queue ranked by actual observed source exposure.

Provider fill timestamps are retrospective; this inventory is NOT an executable
portfolio or a prospective first-known signal. An observed coin's first fill
anchors only that coin, not the entire unknown wallet book. Missing source
coins, incomplete DEX coverage, and discontinuities are never treated as flat.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import gzip
import json
from pathlib import Path

from .pm_phase6b import (
    END,
    START,
    WALLETS,
    _same,
    fingerprint,
    locate_phase4_wallet,
    normalize_phase4_wallet,
    safe_write_json,
)

ONE_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class SourceStep:
    t: datetime
    tid: str
    coin: str
    before: D
    after: D
    price: D


def load_events(
    phase5: Path, new50: Path, phase4_root: Path, source_coverage: Path
) -> dict[str, list[SourceStep]]:
    frozen = json.loads(phase5.read_text())
    existing = json.loads(source_coverage.read_text())
    if existing.get("schema") != "phase6b_source_coverage_v1":
        raise ValueError("PHASE6B_SOURCE_COVERAGE_SCHEMA_MISMATCH")
    members = {}
    for portfolio in frozen["portfolios"]:
        for member in portfolio["members"]:
            if (
                member["member_alias"] in members
                and members[member["member_alias"]] != member["address"]
            ):
                raise ValueError("CONFLICTING_FROZEN_IDENTITY")
            members[member["member_alias"]] = member["address"]
    result = {}
    for alias in sorted(set().union(*(set(p) for p in WALLETS.values()))):
        address = members[alias].lower()
        if alias == "ACT08":
            path = locate_phase4_wallet(phase4_root, address)
            before = fingerprint(path)
            rows = normalize_phase4_wallet(json.loads(path.read_bytes()), address)
        else:
            path = new50 / "wallet_fills_90d" / (address + ".json.gz")
            before = fingerprint(path)
            raw = json.loads(gzip.decompress(path.read_bytes()))
            if raw.get("address", "").lower() != address:
                raise ValueError("SOURCE_ADDRESS_MISMATCH")
            rows = raw["fills"]
        if before != existing["wallets"][alias]["source_file_sha256"]:
            raise ValueError("SOURCE_FILE_NOT_FROZEN:" + alias)
        if fingerprint(path) != before:
            raise ValueError("SOURCE_FILE_CHANGED_DURING_LOAD")
        seen = set()
        grouped: dict[str, list[SourceStep]] = defaultdict(list)
        for row in rows:
            if str(row.get("user", "")).lower() != address:
                raise ValueError("FILL_OWNER_MISMATCH")
            tid = str(row["tid"])
            coin = str(row["coin"])
            if not coin or (coin, tid) in seen:
                raise ValueError("SOURCE_DUPLICATE_COIN_TID")
            seen.add((coin, tid))
            t = datetime.fromtimestamp(int(row["time"]) / 1000, UTC)
            before_qty = D(str(row["start_position"]))
            size = D(str(row["sz"]))
            price = D(str(row["px"]))
            side = row["side"]
            if (
                side not in ("A", "B")
                or size <= 0
                or price <= 0
                or not all(x.is_finite() for x in (before_qty, size, price))
            ):
                raise ValueError("INVALID_SOURCE_FINANCIAL_ROW")
            after_qty = before_qty + (size if side == "B" else -size)
            if START <= t < END:
                grouped[coin].append(SourceStep(t, tid, coin, before_qty, after_qty, price))
        events = []
        for coin, seq in sorted(grouped.items()):
            seq.sort(key=lambda x: (x.t, int(x.tid)))
            prev: D | None = None
            for t in sorted({row.t for row in seq}):
                remaining = [s for s in seq if s.t == t]
                while remaining:
                    linked = [s for s in remaining if prev is not None and _same(s.before, prev)]
                    if linked:
                        pick = min(linked, key=lambda s: int(s.tid))
                    else:
                        starts = [
                            s
                            for s in remaining
                            if not any(
                                _same(other.after, s.before)
                                for other in remaining
                                if other is not s
                            )
                        ]
                        pick = min(starts or remaining, key=lambda s: int(s.tid))
                    events.append(pick)
                    remaining.remove(pick)
                    prev = pick.after
        # Stable time merge preserves the linked same-millisecond order per coin.
        events.sort(key=lambda x: x.t)
        result[alias] = events
    return result


def active_intervals(
    steps: list[SourceStep],
) -> tuple[list[tuple[str, datetime, datetime, D]], dict]:
    by_coin = defaultdict(list)
    for item in steps:
        by_coin[item.coin].append(item)
    intervals = []
    breaks = defaultdict(int)
    for coin, rows in by_coin.items():
        # Do not reorder a same-millisecond position-linked chain by TID.
        rows.sort(key=lambda x: x.t)
        prev: SourceStep | None = None
        for step in rows:
            if prev is not None and not _same(prev.after, step.before):
                breaks[coin] += 1
            # A gap in the vendor chain cannot be trusted as a continuous
            # position, even when the previous *observed* after is nonzero.
            elif prev is not None and prev.after:
                left = min(END, max(START, prev.t))
                right = min(END, max(START, step.t))
                if right > left:
                    intervals.append((coin, left, right, prev.after))
            prev = step
        if prev is not None and prev.after:
            intervals.append((coin, max(START, prev.t), END, prev.after))
    return intervals, dict(breaks)


def count_exposure_minutes(
    intervals: list[tuple[str, datetime, datetime, D]], minutely: dict
) -> dict:
    counts = defaultdict(lambda: defaultdict(int))
    for coin, left, right, qty in intervals:
        if qty == 0:
            continue
        if coin not in minutely:
            raise ValueError("MISSING_COIN_IN_NATIVE_MARKET_AUDIT")
        by_day = {row["day"]: row for row in minutely[coin]["days"]}
        cursor = left.date()
        while cursor <= (right - timedelta(microseconds=1)).date():
            day_start = datetime(cursor.year, cursor.month, cursor.day, tzinfo=UTC)
            a = max(day_start, left)
            b = min(day_start + timedelta(days=1), right)
            minutes = max(0, int((b - a).total_seconds() // 60))
            counts[coin]["exposure_minutes"] += minutes
            status = by_day[cursor.isoformat()]["status"]
            bucket = (
                "full_day_sha_verified_minutes"
                if status == "EXACT_MINUTE_SHA_VERIFIED"
                else "unverified_exposure_minutes"
            )
            counts[coin][bucket] += minutes
            counts[coin]["exposure_instrument_days"] += 1
            if status != "EXACT_MINUTE_SHA_VERIFIED":
                counts[coin]["unverified_exposure_instrument_days"] += 1
            cursor += timedelta(days=1)
    return {k: dict(v) for k, v in counts.items()}


def build(
    phase5: Path,
    new50: Path,
    phase4_root: Path,
    source_coverage: Path,
    native_minute: Path,
    out: Path,
) -> dict:
    market = json.loads(native_minute.read_text())
    if market.get("original_coverage_sha256") != fingerprint(source_coverage):
        raise ValueError("SOURCE_AND_MINUTE_AUDIT_DIFFERENT_GENERATIONS")
    events = load_events(phase5, new50, phase4_root, source_coverage)
    by_wallet = {}
    total = defaultdict(lambda: defaultdict(int))
    for wallet, rows in sorted(events.items()):
        intervals, breaks = active_intervals(rows)
        availability = count_exposure_minutes(intervals, market["instruments"])
        for coin, meta in availability.items():
            for key, value in meta.items():
                total[coin][key] += value
        by_wallet[wallet] = {
            "source_events": len(rows),
            "observed_source_instruments": len({r.coin for r in rows}),
            "position_chain_breaks": breaks,
            "intervals_nonzero": len(intervals),
            "intervals": [
                {
                    "coin": coin,
                    "start_at": a.isoformat(),
                    "end_at": b.isoformat(),
                    "quantity": str(q),
                }
                for coin, a, b, q in intervals
            ],
            "coverage": availability,
            "source_book_complete": False,
        }
    highest = [
        {
            "instrument": coin,
            **vals,
            "market_day_disqualified": len(market["instruments"][coin]["disqualified_days"]),
        }
        for coin, vals in total.items()
    ]
    highest.sort(key=lambda x: (-x.get("unverified_exposure_minutes", 0), x["instrument"]))
    summary = {
        "schema": "phase6b_observed_exposure_coverage_v1",
        "asof_status": "RETROSPECTIVE_VENDOR_EVENTS_NOT_PROSPECTIVE",
        "scope": "PER_INSTRUMENT_OBSERVED_ONLY_NOT_COMPLETE_ACCOUNT",
        "phase5_sha256": fingerprint(phase5),
        "source_coverage_sha256": fingerprint(source_coverage),
        "native_minute_sha256": fingerprint(native_minute),
        "wallets": by_wallet,
        "priority_native_market_gaps": highest,
        "total_observed_exposure_minutes": sum(
            x.get("exposure_minutes", 0) for x in total.values()
        ),
        "total_unverified_exposure_minutes": sum(
            x.get("unverified_exposure_minutes", 0) for x in total.values()
        ),
        "not_account_pnl": True,
        "not_qualified": True,
        "no_broker_orders": True,
    }
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.chmod(0o700)
    digest = safe_write_json(out / "source_exposure_coverage.json", summary)
    return {
        "schema": summary["schema"],
        "report_sha256": digest,
        "wallets": len(by_wallet),
        "instruments": len(highest),
        "total_unverified_exposure_minutes": summary["total_unverified_exposure_minutes"],
        "top_unverified_symbols": [x["instrument"] for x in highest[:10]],
        "output": str(out / "source_exposure_coverage.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase5", type=Path, required=True)
    parser.add_argument("--new50", type=Path, required=True)
    parser.add_argument("--phase4-source", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--native-minute", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.phase5,
                args.new50,
                args.phase4_source,
                args.coverage,
                args.native_minute,
                args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
