"""Full migration script for the canonical wallet data store.

Normalizes all 11 existing source datasets into mode 700 Hive-partitioned zstd Parquet
store at data/private/wallet_store/ with mode 600 files, deterministic provenance sidecars,
SQLite catalog, full cross-source deduplication, chain check, and exact row reconciliation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import glob
import gzip
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import polars as pl

from copytrade_pm.wallet_store.adapters import (
    adapt_fill_row,
    from_vike,
    parse_dex,
    to_decimal,
    to_utc_datetime,
)
from copytrade_pm.wallet_store.catalog import (
    DEFAULT_REGISTRY_DB,
    DEFAULT_STORE_DIR,
    get_catalog_path,
    init_catalog,
    query_uncovered_registry_wallets,
)
from copytrade_pm.wallet_store.schema import (
    FILLS_POLARS_SCHEMA,
    POSITIONS_POLARS_SCHEMA,
    Fill,
    Position,
)
from copytrade_pm.wallet_store.store import (
    ensure_mode_600,
    ensure_mode_700,
    ingest,
    verify,
)

SOURCE_RANKS = {
    "vike": 4,
    "archive": 3,
    "hyperx": 2,
    "dextra": 1,
}


def fill_to_dict(f: Fill) -> dict[str, Any]:
    return {
        "ts": f.ts,
        "wallet": f.wallet,
        "symbol": f.symbol,
        "dex": f.dex,
        "side": f.side,
        "size_token": float(f.size_token),
        "price": float(f.price),
        "size_usd": float(f.size_usd),
        "fee": float(f.fee),
        "fee_token": f.fee_token,
        "is_maker": f.is_maker,
        "order_id": f.order_id,
        "trade_id": f.trade_id,
        "crossed": f.crossed,
        "closed_pnl": float(f.closed_pnl),
        "start_position": float(f.start_position) if f.start_position is not None else None,
        "source": f.source,
        "source_ts": f.source_ts,
    }


def position_to_dict(p: Position) -> dict[str, Any]:
    return {
        "snapshot_ts": p.snapshot_ts,
        "wallet": p.wallet,
        "symbol": p.symbol,
        "dex": p.dex,
        "direction": p.direction,
        "size_token": float(p.size_token),
        "size_usd": float(p.size_usd),
        "entry_price": float(p.entry_price),
        "mark_price": float(p.mark_price),
        "liquidation_price": float(p.liquidation_price)
        if p.liquidation_price is not None
        else None,
        "unrealized_pnl": float(p.unrealized_pnl),
        "leverage": float(p.leverage),
        "leverage_type": p.leverage_type,
        "margin_used": float(p.margin_used),
        "opened_at": p.opened_at,
        "pnl_cohort": p.pnl_cohort,
        "size_cohort": p.size_cohort,
        "liq_progress": float(p.liq_progress) if p.liq_progress is not None else None,
        "source": p.source,
    }


def run_migration(store_dir: Path = DEFAULT_STORE_DIR) -> dict[str, Any]:
    start_time = time.time()
    print("=" * 80)
    print("STARTING CANONICAL WALLET STORE MIGRATION")
    print(f"Target store: {store_dir}")
    print("=" * 80)

    ensure_mode_700(store_dir)
    catalog_path = get_catalog_path(store_dir)
    con = init_catalog(catalog_path)

    # Global tracking counters
    rows_read: dict[str, int] = defaultdict(int)
    rows_loaded: dict[str, int] = defaultdict(int)
    duplicates_removed: dict[str, int] = defaultdict(int)
    rows_rejected: dict[str, int] = defaultdict(int)
    rejection_reasons: dict[str, int] = defaultdict(int)

    duplicates_by_wallet: dict[str, int] = defaultdict(int)
    dedup_drops: list[dict[str, Any]] = []
    blocked_drops: list[dict[str, Any]] = []
    equity_scalars: dict[str, dict[str, Any]] = {}
    gaps_by_wallet_symbol: dict[tuple[str, str], int] = defaultdict(int)

    # 1. Map files by wallet
    print("\n[Phase 1] Indexing sources by wallet...")
    wallet_sources: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: {
            "json_fills": [],
            "dextra_fills": [],
            "hx_pages": [],
            "act04_fills": False,
            "act04_positions": False,
        }
    )

    # JSON files
    json_globs = [
        ("wallet_fills_90d", "data/wallet_fills_90d/*.json"),
        ("ml4t_top6", "data/ml4t_top6_fills_90d/*.json"),
        ("ml4t_100k_500k", "data/ml4t_100k_500k_fills_90d/*.json"),
        ("broader_active", "data/broader_active_inventory_fills_90d/*.json"),
        ("nansen_smart_money", "data/nansen_smart_money_fills_90d/*.json"),
        ("ml4t_jul1_empty", "data/ml4t_jul1_to_now_fills/*.json"),
    ]

    json_file_count = 0
    empty_json_wallets = []

    for category, pattern in json_globs:
        for fpath in sorted(glob.glob(pattern)):
            json_file_count += 1
            with open(fpath, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            addr = (d.get("address") or d.get("user") or "").lower().strip()
            if not addr:
                continue

            fills = d.get("fills", [])
            if not fills:
                empty_json_wallets.append((addr, fpath))
                continue

            wallet_sources[addr]["json_fills"].append((fpath, category))

            # Record static equity scalar if present
            if "equity" in d and d["equity"] is not None:
                equity_scalars[addr] = {
                    "wallet": addr,
                    "equity_scalar": float(d["equity"]),
                    "as_of": None,
                    "source": category,
                }

    print(f"  Indexed {json_file_count} JSON files across {len(wallet_sources)} wallets.")
    print(f"  Found {len(empty_json_wallets)} empty JSON files (e.g. ml4t_jul1_to_now_fills).")

    # Dextra files
    dextra_files = sorted(glob.glob("data/private/dextra_wallet_fills_20261107/fills_*.jsonl"))
    for fpath in dextra_files:
        base = os.path.basename(fpath)
        parts = base.split("_")
        addr = ""
        for p in parts:
            clean_p = p.split(".")[0].lower()
            if clean_p.startswith("0x") and len(clean_p) == 42:
                addr = clean_p
                break
        if addr:
            wallet_sources[addr]["dextra_fills"].append(fpath)

    print(f"  Indexed {len(dextra_files)} Dextra jsonl files.")

    # HyperX cache v1 pages
    hx_dir = Path(
        os.path.expanduser(
            "~/.local/share/copytrade/reports/five-pod-20261029-research/slow_pod_data_v1/hyperx_fills_cache_v1/pages"
        )
    )
    hx_pages = sorted(hx_dir.glob("*/*/*.json.gz")) if hx_dir.exists() else []
    hx_wallet_pages: dict[str, list[Path]] = defaultdict(list)
    for p in hx_pages:
        try:
            with gzip.open(p, "rt") as fp:
                d = json.load(fp)
                addr = (d.get("address") or "").lower().strip()
                if addr:
                    hx_wallet_pages[addr].append(p)
                    wallet_sources[addr]["hx_pages"].append(p)
        except Exception as exc:
            blocked_drops.append(
                {
                    "source": "hyperx_cache",
                    "path": str(p),
                    "error": str(exc),
                }
            )
            rows_rejected["hyperx_cache"] += 1
            rejection_reasons["UNREADABLE_HX_CACHE_PAGE"] += 1

    print(f"  Indexed {len(hx_pages)} HyperX cache pages across {len(hx_wallet_pages)} wallets.")

    # ACT04 verified
    act04_fill_path = Path("data/private/triadA_verified/act04_fills_verified_20261111.json")
    act04_addr = "0xe2823659be02e0f48a4660e4da008b5e1abfdf29"
    if act04_fill_path.exists():
        wallet_sources[act04_addr]["act04_fills"] = True
    print(f"  ACT04 verified fills located for {act04_addr}.")

    # Archive fills slice
    archive_fills_path = Path(
        "data/private/registry_archive_slice/registry_archive_fills_20260929_1001.parquet"
    )
    print("  Loading Archive fills slice into memory partitions...")
    df_arch_fills = pl.read_parquet(archive_fills_path)
    arch_fill_parts_raw = df_arch_fills.partition_by("wallet", as_dict=True)
    arch_fill_parts: dict[str, pl.DataFrame] = {
        k[0].lower().strip(): v for k, v in arch_fill_parts_raw.items()
    }
    for w_addr in arch_fill_parts:
        wallet_sources[w_addr]  # ensure in set

    print(
        f"  Archive fills slice partitioned: {len(df_arch_fills)} rows across {len(arch_fill_parts)} wallets."
    )

    all_wallets = sorted(list(wallet_sources.keys()))
    print(f"\nTotal unique wallets with fills across all sources: {len(all_wallets)}")

    # 2. Process fills wallet by wallet
    print("\n[Phase 2] Normalizing, deduplicating, and ingesting FILLS partition by partition...")
    total_fills_loaded = 0

    for idx, wallet in enumerate(all_wallets, start=1):
        if idx % 50 == 0 or idx == len(all_wallets):
            print(f"  Processing fills wallet {idx}/{len(all_wallets)}: {wallet}...")

        w_sources = wallet_sources[wallet]
        wallet_candidates: list[tuple[int, int, Fill]] = []

        # Load from Archive slice
        if wallet in arch_fill_parts:
            sub_df = arch_fill_parts[wallet]
            for row in sub_df.to_dicts():
                rows_read["archive"] += 1
                try:
                    fill_obj = from_vike(row, wallet=wallet, source="archive")
                    wallet_candidates.append(
                        (SOURCE_RANKS["archive"], len(wallet_candidates), fill_obj)
                    )
                except Exception as exc:
                    rows_rejected["archive"] += 1
                    rejection_reasons[f"ARCHIVE_VALIDATION_{type(exc).__name__}"] += 1
                    blocked_drops.append(
                        {"source": "archive", "wallet": wallet, "error": str(exc), "row": row}
                    )

        # Load from ACT04 verified
        if w_sources["act04_fills"] and wallet == act04_addr:
            with open(act04_fill_path, "r", encoding="utf-8") as fp:
                act04_data = json.load(fp)
            for row in act04_data.get("fills", []):
                rows_read["vike"] += 1
                try:
                    fill_obj = from_vike(row, wallet=wallet, source="vike")
                    wallet_candidates.append(
                        (SOURCE_RANKS["vike"], len(wallet_candidates), fill_obj)
                    )
                except Exception as exc:
                    rows_rejected["vike"] += 1
                    rejection_reasons[f"VIKE_VALIDATION_{type(exc).__name__}"] += 1
                    blocked_drops.append(
                        {"source": "vike", "wallet": wallet, "error": str(exc), "row": row}
                    )

        # Load from HyperX cache pages
        for p in w_sources["hx_pages"]:
            try:
                with gzip.open(p, "rt") as fp:
                    p_data = json.load(fp)
                for row in p_data.get("fills", []):
                    rows_read["hyperx"] += 1
                    try:
                        fill_obj = adapt_fill_row(row, wallet=wallet, default_source="hyperx")
                        wallet_candidates.append(
                            (SOURCE_RANKS["hyperx"], len(wallet_candidates), fill_obj)
                        )
                    except Exception as exc:
                        rows_rejected["hyperx"] += 1
                        rejection_reasons[f"HYPERX_CACHE_VALIDATION_{type(exc).__name__}"] += 1
                        blocked_drops.append(
                            {"source": "hyperx", "wallet": wallet, "error": str(exc), "row": row}
                        )
            except Exception:
                pass

        # Load from JSON files
        for fpath, cat in w_sources["json_fills"]:
            with open(fpath, "r", encoding="utf-8") as fp:
                j_data = json.load(fp)
            for row in j_data.get("fills", []):
                rows_read["hyperx"] += 1
                try:
                    fill_obj = adapt_fill_row(row, wallet=wallet, default_source="hyperx")
                    wallet_candidates.append(
                        (SOURCE_RANKS["hyperx"], len(wallet_candidates), fill_obj)
                    )
                except Exception as exc:
                    rows_rejected["hyperx"] += 1
                    rejection_reasons[f"JSON_VALIDATION_{type(exc).__name__}"] += 1
                    blocked_drops.append(
                        {"source": "hyperx", "wallet": wallet, "error": str(exc), "row": row}
                    )

        # Load from Dextra
        for fpath in w_sources["dextra_fills"]:
            with open(fpath, "r", encoding="utf-8") as fp:
                for line in fp:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    rows_read["dextra"] += 1
                    try:
                        row = json.loads(line_str)
                        fill_obj = from_vike(row, wallet=wallet, source="dextra")
                        wallet_candidates.append(
                            (SOURCE_RANKS["dextra"], len(wallet_candidates), fill_obj)
                        )
                    except Exception as exc:
                        rows_rejected["dextra"] += 1
                        rejection_reasons[f"DEXTRA_VALIDATION_{type(exc).__name__}"] += 1
                        blocked_drops.append(
                            {"source": "dextra", "wallet": wallet, "error": str(exc)}
                        )

        # Deduplicate fills for this wallet
        # Deduplication key: (symbol, trade_id, ts)
        dedup_map: dict[tuple[str, str, datetime], tuple[int, int, Fill]] = {}
        for rank, orig_idx, fill in wallet_candidates:
            key = (fill.symbol, fill.trade_id, fill.ts)
            if key not in dedup_map:
                dedup_map[key] = (rank, orig_idx, fill)
            else:
                existing_rank, existing_idx, existing_fill = dedup_map[key]
                if rank > existing_rank:
                    dedup_drops.append(
                        {
                            "key": {
                                "wallet": wallet,
                                "symbol": fill.symbol,
                                "trade_id": fill.trade_id,
                                "ts": fill.ts.isoformat(),
                            },
                            "winning_source": fill.source,
                            "dropped_source": existing_fill.source,
                        }
                    )
                    duplicates_removed[existing_fill.source] += 1
                    duplicates_by_wallet[wallet] += 1
                    dedup_map[key] = (rank, orig_idx, fill)
                elif rank < existing_rank:
                    dedup_drops.append(
                        {
                            "key": {
                                "wallet": wallet,
                                "symbol": fill.symbol,
                                "trade_id": fill.trade_id,
                                "ts": fill.ts.isoformat(),
                            },
                            "winning_source": existing_fill.source,
                            "dropped_source": fill.source,
                        }
                    )
                    duplicates_removed[fill.source] += 1
                    duplicates_by_wallet[wallet] += 1
                else:
                    new_richness = 1 if fill.start_position is not None else 0
                    old_richness = 1 if existing_fill.start_position is not None else 0
                    if new_richness > old_richness:
                        dedup_drops.append(
                            {
                                "key": {
                                    "wallet": wallet,
                                    "symbol": fill.symbol,
                                    "trade_id": fill.trade_id,
                                    "ts": fill.ts.isoformat(),
                                },
                                "winning_source": fill.source,
                                "dropped_source": existing_fill.source,
                            }
                        )
                        duplicates_removed[existing_fill.source] += 1
                        duplicates_by_wallet[wallet] += 1
                        dedup_map[key] = (rank, orig_idx, fill)
                    else:
                        dedup_drops.append(
                            {
                                "key": {
                                    "wallet": wallet,
                                    "symbol": fill.symbol,
                                    "trade_id": fill.trade_id,
                                    "ts": fill.ts.isoformat(),
                                },
                                "winning_source": existing_fill.source,
                                "dropped_source": fill.source,
                            }
                        )
                        duplicates_removed[fill.source] += 1
                        duplicates_by_wallet[wallet] += 1

        surviving_fills = [f for _, _, f in dedup_map.values()]

        # Chain check for start_position
        by_symbol_startpos: dict[str, list[Fill]] = defaultdict(list)
        for f in surviving_fills:
            if f.start_position is not None:
                by_symbol_startpos[f.symbol].append(f)

        for sym, sym_fills in by_symbol_startpos.items():
            sym_fills.sort(
                key=lambda x: (x.ts, int(x.trade_id) if x.trade_id.isdigit() else x.trade_id)
            )
            for i in range(len(sym_fills) - 1):
                curr_f = sym_fills[i]
                next_f = sym_fills[i + 1]
                signed_sz = curr_f.size_token if curr_f.side == "buy" else -curr_f.size_token
                expected_next = curr_f.start_position + signed_sz
                if abs(next_f.start_position - expected_next) > Decimal("1e-4"):
                    gaps_by_wallet_symbol[(wallet, sym)] += 1

        # Group surviving fills by UTC day
        by_day: dict[str, list[Fill]] = defaultdict(list)
        for f in surviving_fills:
            day_str = f.ts.strftime("%Y-%m-%d")
            by_day[day_str].append(f)

        for day_str, day_fills in by_day.items():
            day_fills.sort(
                key=lambda x: (x.ts, int(x.trade_id) if x.trade_id.isdigit() else x.trade_id)
            )
            records = [fill_to_dict(f) for f in day_fills]
            df_partition = pl.DataFrame(records, schema=FILLS_POLARS_SCHEMA)
            sources_present = sorted(list({f.source for f in day_fills}))
            src_label = ",".join(sources_present)

            ingest(
                kind="fills",
                wallet=wallet,
                day=day_str,
                df=df_partition,
                source=src_label,
                source_cmd="migrate_wallet_store.py",
                store_dir=store_dir,
                con=con,
            )

            for f in day_fills:
                rows_loaded[f.source] += 1
                total_fills_loaded += 1

    print(f"\n[Phase 2 Complete] Ingested {total_fills_loaded} deduplicated canonical fills.")

    # 3. Process Positions
    print("\n[Phase 3] Normalizing, deduplicating, and ingesting POSITIONS...")
    positions_read: dict[str, int] = defaultdict(int)
    positions_loaded: dict[str, int] = defaultdict(int)
    positions_dupes: dict[str, int] = defaultdict(int)
    positions_rejected: dict[str, int] = defaultdict(int)

    # Load ACT04 positions
    act04_pos_path = Path(
        "data/private/triadA_verified/act04_positions_5m_20260801_20261001.parquet"
    )
    act04_positions_list: list[Position] = []
    if act04_pos_path.exists():
        df_act04_pos = pl.read_parquet(act04_pos_path)
        print(f"  Reading {len(df_act04_pos)} rows from ACT04 5-min positions...")
        for row in df_act04_pos.to_dicts():
            positions_read["vike"] += 1
            snap_ts = to_utc_datetime(row["snapshot_ts"])
            opened_at_val = (
                to_utc_datetime(row["opened_at"]) if row.get("opened_at") is not None else None
            )
            sym = str(row["symbol"])
            dex = parse_dex(sym, row.get("dex_name"))
            try:
                pos = Position(
                    snapshot_ts=snap_ts,
                    wallet=act04_addr,
                    symbol=sym,
                    dex=dex,
                    direction="long" if str(row["direction"]).lower() == "long" else "short",
                    size_token=to_decimal(row["size_token"]),
                    size_usd=to_decimal(row["size_usd"]),
                    entry_price=to_decimal(row["entry_price"]),
                    mark_price=to_decimal(row["mark_price"]),
                    liquidation_price=None,
                    unrealized_pnl=to_decimal(row["unrealized_pnl"]),
                    leverage=to_decimal(row["leverage"]),
                    leverage_type=None,
                    margin_used=to_decimal(row["margin_used"]),
                    opened_at=opened_at_val,
                    pnl_cohort=str(row.get("pnl_cohort"))
                    if row.get("pnl_cohort") is not None
                    else None,
                    size_cohort=str(row.get("size_cohort"))
                    if row.get("size_cohort") is not None
                    else None,
                    liq_progress=to_decimal(row["liq_progress"])
                    if row.get("liq_progress") is not None
                    else None,
                    source="vike",
                )
                act04_positions_list.append(pos)
            except Exception as exc:
                positions_rejected["vike"] += 1
                blocked_drops.append(
                    {"source": "vike_positions", "wallet": act04_addr, "error": str(exc)}
                )

    # Load Archive positions slice
    archive_pos_path = Path(
        "data/private/registry_archive_slice/registry_archive_positions_20260929.parquet"
    )
    print(f"  Loading Archive positions slice from {archive_pos_path}...")
    df_arch_pos = pl.read_parquet(archive_pos_path)
    arch_pos_parts_raw = df_arch_pos.partition_by("wallet", as_dict=True)
    arch_pos_parts: dict[str, pl.DataFrame] = {
        k[0].lower().strip(): v for k, v in arch_pos_parts_raw.items()
    }
    print(f"  Archive positions partitioned across {len(arch_pos_parts)} wallets.")

    all_pos_wallets = sorted(list(set([act04_addr] + list(arch_pos_parts.keys()))))
    print(f"  Total unique wallets with positions: {len(all_pos_wallets)}")

    total_positions_loaded = 0

    for idx, wallet in enumerate(all_pos_wallets, start=1):
        if idx % 100 == 0 or idx == len(all_pos_wallets):
            print(f"  Processing positions wallet {idx}/{len(all_pos_wallets)}: {wallet}...")

        w_pos_candidates: list[tuple[int, int, Position]] = []

        # ACT04 positions
        if wallet == act04_addr:
            for p in act04_positions_list:
                w_pos_candidates.append((SOURCE_RANKS["vike"], len(w_pos_candidates), p))

        # Archive positions
        if wallet in arch_pos_parts:
            sub_pos_df = arch_pos_parts[wallet]
            for row in sub_pos_df.to_dicts():
                positions_read["archive"] += 1
                snap_ts = to_utc_datetime(row["snapshot_ts"])
                sym = str(row["asset"])
                dex = parse_dex(sym, row.get("dex_name"))
                dir_val = "long" if row["direction"] == 1 else "short"
                liq_px = (
                    to_decimal(row["liquidation_price"])
                    if row.get("liquidation_price") is not None
                    else None
                )
                opened_val = (
                    to_utc_datetime(row["state_ts"]) if row.get("state_ts") is not None else None
                )
                try:
                    pos = Position(
                        snapshot_ts=snap_ts,
                        wallet=wallet,
                        symbol=sym,
                        dex=dex,
                        direction=dir_val,
                        size_token=to_decimal(abs(float(row["size_token"]))),
                        size_usd=to_decimal(row["size_usd"]),
                        entry_price=to_decimal(row["entry_price"]),
                        mark_price=to_decimal(row["mark_price"]),
                        liquidation_price=liq_px,
                        unrealized_pnl=to_decimal(row["unrealized_pnl"]),
                        leverage=to_decimal(row["leverage"]),
                        leverage_type=str(row["leverage_type"])
                        if row.get("leverage_type") is not None
                        else None,
                        margin_used=to_decimal(row["margin_used"]),
                        opened_at=opened_val,
                        pnl_cohort=str(row["pnl_cohort"])
                        if row.get("pnl_cohort") is not None
                        else None,
                        size_cohort=str(row["size_cohort"])
                        if row.get("size_cohort") is not None
                        else None,
                        liq_progress=to_decimal(row["liq_progress"])
                        if row.get("liq_progress") is not None
                        else None,
                        source="archive",
                    )
                    w_pos_candidates.append((SOURCE_RANKS["archive"], len(w_pos_candidates), pos))
                except Exception as exc:
                    positions_rejected["archive"] += 1
                    blocked_drops.append(
                        {"source": "archive_positions", "wallet": wallet, "error": str(exc)}
                    )

        # Deduplicate positions for this wallet
        # Deduplication key: (snapshot_ts, symbol)
        pos_dedup_map: dict[tuple[datetime, str], tuple[int, int, Position]] = {}
        for rank, orig_idx, pos in w_pos_candidates:
            key = (pos.snapshot_ts, pos.symbol)
            if key not in pos_dedup_map:
                pos_dedup_map[key] = (rank, orig_idx, pos)
            else:
                existing_rank, existing_idx, existing_pos = pos_dedup_map[key]
                if rank > existing_rank:
                    dedup_drops.append(
                        {
                            "key": {
                                "wallet": wallet,
                                "symbol": pos.symbol,
                                "snapshot_ts": pos.snapshot_ts.isoformat(),
                            },
                            "winning_source": pos.source,
                            "dropped_source": existing_pos.source,
                        }
                    )
                    positions_dupes[existing_pos.source] += 1
                    pos_dedup_map[key] = (rank, orig_idx, pos)
                else:
                    dedup_drops.append(
                        {
                            "key": {
                                "wallet": wallet,
                                "symbol": pos.symbol,
                                "snapshot_ts": pos.snapshot_ts.isoformat(),
                            },
                            "winning_source": existing_pos.source,
                            "dropped_source": pos.source,
                        }
                    )
                    positions_dupes[pos.source] += 1

        surviving_positions = [p for _, _, p in pos_dedup_map.values()]

        # Group positions by UTC day
        pos_by_day: dict[str, list[Position]] = defaultdict(list)
        for p in surviving_positions:
            day_str = p.snapshot_ts.strftime("%Y-%m-%d")
            pos_by_day[day_str].append(p)

        for day_str, day_positions in pos_by_day.items():
            day_positions.sort(key=lambda x: (x.snapshot_ts, x.symbol))
            records = [position_to_dict(p) for p in day_positions]
            df_pos_partition = pl.DataFrame(records, schema=POSITIONS_POLARS_SCHEMA)
            sources_present = sorted(list({p.source for p in day_positions}))
            src_label = ",".join(sources_present)

            ingest(
                kind="positions",
                wallet=wallet,
                day=day_str,
                df=df_pos_partition,
                source=src_label,
                source_cmd="migrate_wallet_store.py",
                store_dir=store_dir,
                con=con,
            )

            for p in day_positions:
                positions_loaded[p.source] += 1
                total_positions_loaded += 1

    print(
        f"\n[Phase 3 Complete] Ingested {total_positions_loaded} deduplicated canonical positions."
    )

    con.close()

    # 4. Save metadata: equity scalars, dedup report, blocked report
    print("\n[Phase 4] Saving provenance metadata reports...")
    equity_scalar_dir = store_dir / ".metadata" / "equity_scalars"
    ensure_mode_700(equity_scalar_dir)
    for addr, eq_info in equity_scalars.items():
        eq_path = equity_scalar_dir / f"{addr}.json"
        with open(eq_path, "w", encoding="utf-8") as fp:
            json.dump(eq_info, fp, indent=2)
        ensure_mode_600(eq_path)

    dedup_path = store_dir / "dedup_report.json"
    with open(dedup_path, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "total_duplicates_dropped": len(dedup_drops),
                "fills_duplicates_by_source": dict(duplicates_removed),
                "positions_duplicates_by_source": dict(positions_dupes),
                "duplicates_by_wallet": dict(duplicates_by_wallet),
                "sample_drops": dedup_drops[:500],
            },
            fp,
            indent=2,
        )
    ensure_mode_600(dedup_path)

    blocked_path = store_dir / "blocked.json"
    with open(blocked_path, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "total_rows_rejected": len(blocked_drops),
                "fills_rejected_by_source": dict(rows_rejected),
                "positions_rejected_by_source": dict(positions_rejected),
                "rejection_reasons": dict(rejection_reasons),
                "blocked_entries": blocked_drops,
            },
            fp,
            indent=2,
        )
    ensure_mode_600(blocked_path)

    # 5. Row-count reconciliation
    print("\n[Phase 5] Reconciling row counts...")
    print("  FILLS RECONCILIATION:")
    fills_reconciled = True
    for src in ["vike", "archive", "hyperx", "dextra"]:
        r_read = rows_read[src]
        r_loaded = rows_loaded[src]
        r_dupes = duplicates_removed[src]
        r_rej = rows_rejected[src]
        summed = r_loaded + r_dupes + r_rej
        ok = r_read == summed
        print(
            f"    Source '{src}': read={r_read} == loaded({r_loaded}) + dupes({r_dupes}) + rejected({r_rej}) -> {summed} [MATCH: {ok}]"
        )
        if not ok:
            fills_reconciled = False

    print("  POSITIONS RECONCILIATION:")
    positions_reconciled = True
    for src in ["vike", "archive"]:
        p_read = positions_read[src]
        p_loaded = positions_loaded[src]
        p_dupes = positions_dupes[src]
        p_rej = positions_rejected[src]
        summed = p_loaded + p_dupes + p_rej
        ok = p_read == summed
        print(
            f"    Source '{src}': read={p_read} == loaded({p_loaded}) + dupes({p_dupes}) + rejected({p_rej}) -> {summed} [MATCH: {ok}]"
        )
        if not ok:
            positions_reconciled = False

    # 6. Chain check summary
    total_gaps = sum(gaps_by_wallet_symbol.values())
    print("\n[Phase 6] Chain check on start_position:")
    print(f"  Total gaps found across all wallet-symbols: {total_gaps}")
    print(f"  Wallet-symbols with gaps: {len(gaps_by_wallet_symbol)}")

    # 7. Physical Store Verification
    print("\n[Phase 7] Running store verification (verify())...")
    problems = verify(store_dir=store_dir)

    # 8. Registry Coverage Check
    print("\n[Phase 8] Checking registry coverage...")
    con = init_catalog(catalog_path)
    try:
        uncovered = query_uncovered_registry_wallets(con, DEFAULT_REGISTRY_DB)
        print(f"  Registry wallets with 0 cached data in store: {len(uncovered)}")
    finally:
        con.close()

    elapsed = time.time() - start_time
    print("=" * 80)
    print(f"MIGRATION COMPLETED IN {elapsed:.1f}s")
    print(f"Problems found during verify(): {problems}")
    print("=" * 80)

    return {
        "status": "SUCCESS"
        if (fills_reconciled and positions_reconciled and problems == 0)
        else "FAILED",
        "elapsed_sec": round(elapsed, 2),
        "total_fills_loaded": total_fills_loaded,
        "total_positions_loaded": total_positions_loaded,
        "total_duplicates_removed": len(dedup_drops),
        "total_rows_rejected": len(blocked_drops),
        "total_gaps_found": total_gaps,
        "verify_problems": problems,
        "uncovered_registry_wallets_count": len(uncovered),
    }


if __name__ == "__main__":
    res = run_migration()
    print("Result summary:", json.dumps(res, indent=2))
    sys.exit(0 if res["status"] == "SUCCESS" else 1)
