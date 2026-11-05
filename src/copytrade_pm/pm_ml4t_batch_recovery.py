"""Offline-first ML4T cohort reconciliation and API-saving market-day plan.

Research-only: immutable local evidence, no network/broker requests, no SQLite writes.
Source event clocks do NOT provide first-known follower receipts, source NAV or PnL.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from .pm_offline_repository import _market_day, native_instrument
from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource

ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")
SOURCE_DIRS = (
    "ml4t_100k_500k_fills_90d",
    "ml4t_top6_fills_90d",
    "ml4t_jul1_to_now_fills",
    "wallet_fills_90d",
    "broader_active_inventory_fills_90d",
    "nansen_smart_money_fills_90d",
)
SELECTED = ("M52", "M56", "M10", "M33", "M42", "M53")
DELAYS = (1, 2, 5)
MINUTE_MS = 60_000
COST_BPS = Decimal("6.0")


def roster(db: Path) -> tuple[dict[str, dict], str]:
    """SQLite is the sole cohort/alias/exclusion authority."""
    uri = f"file:{db.resolve(strict=True)}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        members = con.execute("""
            SELECT w.address, w.wallet_id, COALESCE(
              (SELECT a.alias FROM wallet_aliases a
               WHERE a.wallet_id=w.wallet_id AND a.namespace='ml4t_strict'
               ORDER BY a.known_at DESC LIMIT 1),
              (SELECT a.alias FROM wallet_aliases a
               WHERE a.wallet_id=w.wallet_id ORDER BY a.known_at DESC LIMIT 1),
              'UNALIASED')
            FROM cohort_memberships c JOIN wallets w USING(wallet_id)
            WHERE c.cohort_id='ml4t-strict-66'
              AND NOT EXISTS (SELECT 1 FROM propfirm_exclusions x
                              WHERE x.address = w.address OR x.wallet_id=w.wallet_id)
            ORDER BY w.address
        """).fetchall()
        cohort = con.execute("""
            SELECT source_sha256 FROM cohorts
            WHERE cohort_id='ml4t-strict-66' ORDER BY version DESC LIMIT 1
        """).fetchone()
    if not cohort or len(members) != 66 or len({r[0] for r in members}) != 66:
        raise ValueError("INVALID_SQLITE_COHORT_CARDINALITY")
    identities = {addr.lower(): {"alias": alias, "wallet_id": wid} for addr, wid, alias in members}
    if not all(ADDRESS.fullmatch(a) for a in identities):
        raise ValueError("INVALID_SQLITE_HEX_ADDRESS")
    return identities, cohort[0]


def _number(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except ValueError, TypeError, InvalidOperation:
        return None


def batch_minute(source_ms: int, delay: int) -> int:
    """Native historical oracle contract: after source + delay, NEXT bar open."""
    if type(source_ms) is not int or source_ms <= 0 or delay not in DELAYS:
        raise ValueError("INVALID_SOURCE_CLOCK_OR_DELAY")
    return ((source_ms + delay * MINUTE_MS) // MINUTE_MS + 1) * MINUTE_MS


def effective_k(weight: Decimal, leader_equity: Decimal) -> Decimal:
    if not Decimal(0) < weight <= Decimal(1) or leader_equity <= 0:
        raise ValueError("INVALID_WEIGHT_OR_LEADER_EQUITY")
    return weight * min(Decimal("0.35"), Decimal(10000) / leader_equity)


def fill_identity(event: dict) -> tuple:
    # Do not compare non-economic vendor SDK deserialization fields.
    return (
        event.get("coin"),
        event.get("time"),
        event.get("side"),
        str(event.get("px")),
        str(event.get("sz")),
        str(event.get("startPosition", event.get("start_position"))),
    )


def _verify_public_generation(folder: Path, path: Path, payload: dict, address: str) -> None:
    """Independently verify normalized rows against original immutable raw pages."""
    if (
        folder.name != "normalized"
        or payload.get("source") != "OFFICIAL_HL_INFO_HISTORICAL_NOT_PIT"
        or payload.get("historical_first_known_proven") is not False
        or path.stem != sha256(address.encode()).hexdigest()[:18]
    ):
        raise ValueError("INVALID_PUBLIC_GENERATION_PROVENANCE")
    shas = payload.get("source_page_shas")
    if not isinstance(shas, list) or not shas or len(shas) > 4:
        raise ValueError("INVALID_PUBLIC_GENERATION_PAGE_LIST")
    raw_dir = folder.parent / "raw" / path.stem
    pages = sorted(p for p in raw_dir.glob("page-*.json") if not p.name.endswith(".meta.json"))
    if len(pages) != len(shas):
        raise ValueError("PUBLIC_GENERATION_MISSING_RAW_PAGES")
    unique: dict[tuple[str, str], dict] = {}
    for n, (page, expected_sha) in enumerate(zip(pages, shas, strict=True)):
        if (
            page.name != f"page-{n:03d}.json"
            or page.is_symlink()
            or not isinstance(expected_sha, str)
            or len(expected_sha) != 64
        ):
            raise ValueError("INVALID_PUBLIC_GENERATION_RAW_PAGE")
        raw = page.read_bytes()
        meta_file = page.with_suffix(".meta.json")
        if meta_file.is_symlink() or not meta_file.is_file():
            raise ValueError("MISSING_PUBLIC_GENERATION_PAGE_METADATA")
        meta = json.loads(meta_file.read_bytes())
        if sha256(raw).hexdigest() != expected_sha or meta.get("page_sha256") != expected_sha:
            raise ValueError("PUBLIC_GENERATION_PAGE_SHA_MISMATCH")
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError("INVALID_PUBLIC_GENERATION_PAGE_ROWS")
        for event in rows:
            if not isinstance(event, dict) or (event.get("user", address).lower() != address):
                raise ValueError("PUBLIC_GENERATION_WRONG_WALLET")
            key = (str(event.get("coin")), str(event.get("tid")))
            if key in unique and unique[key] != event:
                raise ValueError("PUBLIC_GENERATION_DUPLICATE_CONFLICT")
            unique[key] = event
    exact_rows = sorted(unique.values(), key=lambda x: (x["time"], x["coin"], x["tid"]))
    if payload["fills"] != exact_rows:
        raise ValueError("PUBLIC_GENERATION_NORMALIZED_RAW_MISMATCH")


def local_sources(
    root: Path,
    identities: dict[str, dict],
    *,
    extra_source_dirs: tuple[Path, ...] = (),
) -> tuple[dict[str, dict], dict]:
    """Merge nonconflicting local generations by exact address + coin + tid."""
    stored = {
        addr: {"events": {}, "files": [], "equity_values": [], "errors": []} for addr in identities
    }
    total_files = 0
    alias_drift_files = 0
    collisions = 0
    duplicate_tids = 0
    directories = [(root / group, group) for group in SOURCE_DIRS]
    for extra in extra_source_dirs:
        folder = Path(extra)
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("UNSAFE_OR_MISSING_SUPPLEMENTAL_SOURCE")
        directories.append((folder, "OFFICIAL_PUBLIC_HISTORICAL_GENERATION"))
    for folder, group in directories:
        if not folder.is_dir() or folder.is_symlink():
            continue
        for path in sorted(folder.glob("*.json")):
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
                continue
            data = path.read_bytes()
            try:
                payload = json.loads(data)
            except ValueError, UnicodeDecodeError:
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("fills"), list):
                continue
            addr = str(payload.get("address", "")).lower()
            if addr not in stored:
                continue
            if group == "OFFICIAL_PUBLIC_HISTORICAL_GENERATION":
                _verify_public_generation(folder, path, payload, addr)
            total_files += 1
            record = stored[addr]
            record["files"].append({"source_sha256": sha256(data).hexdigest(), "file_group": group})
            if payload.get("alias") not in {None, identities[addr]["alias"]}:
                alias_drift_files += 1
            eq = _number(payload.get("equity"))
            if eq is not None and eq > 0:
                record["equity_values"].append(str(eq))
            for event in payload["fills"]:
                if not isinstance(event, dict):
                    record["errors"].append("INVALID_SOURCE_ROW")
                    continue
                tid, coin, ts = event.get("tid"), event.get("coin"), event.get("time")
                if (
                    not isinstance(tid, (str, int))
                    or isinstance(tid, bool)
                    or not isinstance(coin, str)
                    or type(ts) is not int
                ):
                    record["errors"].append("INVALID_TID_COIN_OR_TIME")
                    continue
                if event.get("user", addr).lower() != addr:
                    record["errors"].append("FILL_USER_ADDRESS_MISMATCH")
                    continue
                key = (coin, str(tid))
                previous = record["events"].get(key)
                if previous is not None:
                    duplicate_tids += 1
                    if fill_identity(previous) != fill_identity(event):
                        collisions += 1
                        record["errors"].append("CONFLICTING_SOURCE_TID")
                    continue
                record["events"][key] = event
    summary = {
        "source_json_files_matched": total_files,
        "source_json_alias_drift_files": alias_drift_files,
        "duplicate_source_tids_consistent_or_conflicting": duplicate_tids,
        "conflicting_source_tids": collisions,
        "wallets_with_fills": sum(bool(s["events"]) for s in stored.values()),
        "wallets_without_fills": sum(not s["events"] for s in stored.values()),
    }
    return stored, summary


def _raw_events(
    stored: dict[str, dict], identities: dict[str, dict], selected: set[str]
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    members = []
    for addr, record in sorted(stored.items()):
        alias = identities[addr]["alias"]
        fills = list(record["events"].values())
        if alias not in selected:
            continue
        errors = sorted(set(record["errors"]))
        equities = sorted(set(record["equity_values"]))
        # Current vendor equity is a scalar: usable only for a scenario floor, not PIT sizing.
        source_equity = _number(equities[0]) if len(equities) == 1 else None
        unknown_open = set()
        seen_coin = set()
        for f in sorted(fills, key=lambda x: x["time"]):
            coin = f["coin"]
            if coin not in seen_coin:
                seen_coin.add(coin)
                pos = _number(f.get("startPosition", f.get("start_position")))
                if pos is None or pos != 0:
                    unknown_open.add(coin)
            px = _number(f.get("px"))
            qty = _number(f.get("sz"))
            if f.get("side") not in {"A", "B"} or px is None or px <= 0 or qty is None or qty <= 0:
                errors.append("INVALID_SOURCE_FILL_PRICE_SIZE_OR_SIDE")
                continue
            rows.append(
                {
                    "alias": alias,
                    "address": addr,
                    "coin": coin,
                    "time": f["time"],
                    "size": float(qty) * (1 if f["side"] == "B" else -1),
                    "notional": float(px * qty),
                }
            )
        members.append(
            {
                "alias": alias,
                "address": addr,
                "source_sha256": sorted(f["source_sha256"] for f in record["files"]),
                "source_fill_count": len(fills),
                "source_coins": sorted(seen_coin),
                "initial_filled_instrument_positions_nonzero_or_unknown": sorted(unknown_open),
                "all_instrument_opening_book_verified": False,
                "source_equity_asof_verified": False,
                "equity_scalar_values": equities,
                "reference_k_eff_equal_weight": str(
                    effective_k(Decimal(1) / Decimal(3), source_equity)
                )
                if source_equity is not None
                else None,
                "source_errors": sorted(set(errors)),
            }
        )
    return rows, {"selected": members}


def _market_instrument(coin: str) -> str:
    return native_instrument(coin)


def anchored_batches(events, delay: int):
    """Causal event-anchored batching; no events later than first-fill + delay.

    An order is decided at the delay boundary, filled strictly later at the
    next minute open. A longer delay actually collapses source fills.
    """
    import polars as pl

    orders = []
    for group in events.sort(["alias", "coin", "time"]).partition_by(
        ["alias", "coin"], maintain_order=True
    ):
        records = group.iter_rows(named=True)
        first = next(records, None)
        while first is not None:
            anchor = first["time"]
            cutoff = anchor + delay * MINUTE_MS
            net = first["size"]
            count = 1
            following = next(records, None)
            while following is not None and following["time"] <= cutoff:
                net += following["size"]
                count += 1
                following = next(records, None)
            if abs(net) > 1e-12:
                orders.append(
                    {
                        "alias": first["alias"],
                        "coin": first["coin"],
                        "execute_ms": (cutoff // MINUTE_MS + 1) * MINUTE_MS,
                        "net_qty": net,
                        "fill_count": count,
                    }
                )
            first = following
    if not orders:
        return pl.DataFrame(
            schema={
                "alias": pl.String,
                "coin": pl.String,
                "execute_ms": pl.Int64,
                "net_qty": pl.Float64,
                "fill_count": pl.Int64,
            }
        )
    return pl.DataFrame(orders).sort(["alias", "coin", "execute_ms"])


def run(
    db: Path,
    source_root: Path,
    market_root: Path,
    selected: tuple[str, ...] = SELECTED,
    extra_source_dirs: tuple[Path, ...] = (),
) -> dict:
    import polars as pl

    identities, cohort_sha = roster(db)
    sources, counts = local_sources(source_root, identities, extra_source_dirs=extra_source_dirs)
    known = {item["alias"] for item in identities.values()}
    if len(set(selected)) != len(selected) or not set(selected) <= known:
        raise ValueError("UNKNOWN_SELECTED_ALIAS")
    rows, detail = _raw_events(sources, identities, set(selected))
    if not rows:
        raise ValueError("NO_SELECTED_SOURCE_FILLS")
    events = pl.DataFrame(rows)
    per_wallet = {m["alias"]: m for m in detail["selected"]}
    audited_days: dict[tuple[str, int], tuple[str, int]] = {}
    # Reuse the native owner path and SHA/day contract; never infer XYZ/IO/PARA as coin dirs.
    loader = VerifiedHyperliquidMinuteSource(market_root)
    summaries = []
    missing_days: dict[tuple[str, int], set[int]] = defaultdict(set)
    for delay in DELAYS:
        trades = anchored_batches(events, delay)
        outcomes = Counter()
        after_k_below_min = 0
        gross_follower_dollars = Decimal(0)
        cost_after_k = Decimal(0)
        for rec in trades.iter_rows(named=True):
            coin = rec["coin"]
            ms = rec["execute_ms"]
            day_number = ms // 86_400_000
            key = (coin, day_number)
            if key not in audited_days:
                instrument = _market_instrument(coin)
                date = datetime.fromtimestamp(day_number * 86400, tz=UTC)
                audited_days[key] = _market_day(market_root, instrument, date, verify_sha=True)
            status, _bars = audited_days[key]
            if status != "VERIFIED_NATIVE_DAY":
                missing_days[key].add(delay)
                outcomes[status] += 1
                continue
            minute = datetime.fromtimestamp(ms / 1000, tz=UTC)
            try:
                bar = loader.get(_market_instrument(coin), minute)
            except MarketDataBlocked as exc:
                outcomes[str(exc)] += 1
                missing_days[key].add(delay)
                continue
            per_wallet_entry = per_wallet[rec["alias"]]
            ref_k = per_wallet_entry["reference_k_eff_equal_weight"]
            if ref_k is None:
                outcomes["BLOCKED_MISSING_SOURCE_EQUITY_SCALAR"] += 1
                continue
            k = Decimal(ref_k)
            follower_notional = abs(Decimal(str(rec["net_qty"]))) * bar.open * k
            if follower_notional < Decimal(10):
                after_k_below_min += 1
                outcomes["BELOW_MINIMUM_NOTIONAL_POST_SCALE"] += 1
                continue
            outcomes["VERIFIED_NATIVE_OPEN_SCENARIO_ONLY"] += 1
            gross_follower_dollars += follower_notional
            cost_after_k += follower_notional * COST_BPS / Decimal(10000)
        summaries.append(
            {
                "delay_minutes": delay,
                "nonzero_net_delta_orders": trades.height,
                "outcome_counts": dict(sorted(outcomes.items())),
                "reference_follower_traded_notional_usd": str(round(gross_follower_dollars, 2)),
                "reference_one_way_fee_and_slippage_usd": str(round(cost_after_k, 2)),
                "below_hl_minimum_orders_post_scale": after_k_below_min,
                "financial_status": "BLOCKED_OPENING_BOOK_PIT_NAV_FIRST_KNOWN_AND_ECONOMICS",
            }
        )
    missing = [
        {
            "coin": coin,
            "utc_day": datetime.fromtimestamp(day_num * 86400, tz=UTC).date().isoformat(),
            "status": audited_days[(coin, day_num)][0],
            "requested_delays": sorted(delays),
            "native_instrument": _market_instrument(coin),
        }
        for (coin, day_num), delays in sorted(missing_days.items())
    ]
    requested_days = len({(c, d) for (c, d) in audited_days})
    return {
        "schema": "ml4t66_research_batch_recovery_v1",
        "cohort_id": "ml4t-strict-66",
        "cohort_source_sha256": cohort_sha,
        "db_cohort_wallets": len(identities),
        "hard_excluded_in_selected_cohort": 0,
        "local_sources": counts,
        "wallets_missing_local_fills": [
            {"address": addr, "alias": identities[addr]["alias"]}
            for addr, record in sorted(sources.items())
            if not record["events"]
        ],
        "wallets_with_source_conflicts": [
            {
                "address": addr,
                "alias": identities[addr]["alias"],
                "errors": sorted(set(record["errors"])),
            }
            for addr, record in sorted(sources.items())
            if "CONFLICTING_SOURCE_TID" in record["errors"]
        ],
        "selected_wallets": detail["selected"],
        "selected_source_event_rows": events.height,
        "reference_weight_per_pod": "1/3",
        "batch_policy": "FIRST_EVENT_ANCHORED_DELAY_THEN_STRICTLY_NEXT_MINUTE_OPEN",
        "native_market_day_pairs_requested": requested_days,
        "native_market_day_pairs_missing_or_invalid": len(missing),
        "missing_market_day_plan": missing,
        "delay_replay_diagnostics": summaries,
        "batch_plan_unique_market_days": len(missing),
        "network_api_calls_consumed": 0,
        "supplemental_public_source_generations": len(extra_source_dirs),
        "source_books_complete": False,
        "source_equity_point_in_time_complete": False,
        "prospective_first_known_receipts": False,
        "portfolio_contract_ev": "BLOCKED",
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def save_private(output: Path, report: dict) -> Path:
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.is_symlink() or output.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_REPORT_DIRECTORY_REQUIRED")
    raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    digest = sha256(raw).hexdigest()
    target = output / f"ml4t66_batch_audit_{digest[:20]}.json"
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("REPORT_SHA_CONFLICT")
        return target
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--wallets", nargs="+", default=list(SELECTED))
    parser.add_argument("--extra-source-dir", action="append", type=Path, default=[])
    args = parser.parse_args()
    report = run(
        args.db,
        args.source_root,
        args.market_root,
        tuple(args.wallets),
        extra_source_dirs=tuple(args.extra_source_dir),
    )
    path = save_private(args.output_root, report)
    print(
        json.dumps(
            {
                "status": "OFFLINE_FIRST_RECOVERY_PLANNED_NOT_FINANCIALLY_QUALIFIED",
                "cohort_wallets": report["db_cohort_wallets"],
                **report["local_sources"],
                "selected_source_events": report["selected_source_event_rows"],
                "unique_market_days_examined": report["native_market_day_pairs_requested"],
                "missing_market_day_pairs": report["native_market_day_pairs_missing_or_invalid"],
                "delays": report["delay_replay_diagnostics"],
                "network_api_calls": report["network_api_calls_consumed"],
                "private_report": str(path),
                "report_sha256": sha256(path.read_bytes()).hexdigest(),
                "contract_ev": report["portfolio_contract_ev"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
