"""Backfill missing fills for research wallets using Vike API and canonical store."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import polars as pl

from copytrade_pm.wallet_store.adapters import from_vike
from copytrade_pm.wallet_store.catalog import refresh_wallet_summary
from copytrade_pm.wallet_store.schema import FILLS_POLARS_SCHEMA
from copytrade_pm.wallet_store.store import ingest, verify

DEFAULT_REGISTRY_DB = Path.home() / ".local/share/copytrade/registry/wallet_registry.sqlite"
DEFAULT_WALLET_IDS = (50, 61, 74, 117, 199)


def _resolve_target_wallets(
    wallet_ids: tuple[int, ...] = DEFAULT_WALLET_IDS,
    registry_db: Path = DEFAULT_REGISTRY_DB,
) -> list[str]:
    db_path = Path(os.environ.get("COPYTRADE_WALLET_REGISTRY_DB", str(registry_db)))
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite wallet registry not found at {db_path}; pass --wallets or set COPYTRADE_WALLET_REGISTRY_DB."
        )
    placeholders = ",".join("?" for _ in wallet_ids)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT lower(address) FROM wallets WHERE wallet_id IN ({placeholders}) ORDER BY wallet_id",
            wallet_ids,
        ).fetchall()
        return [str(r[0]) for r in rows]
    finally:
        conn.close()


def fetch_vike_fills(wallet: str, max_pages: int = 5) -> list[dict]:
    all_fills = []
    cursor = None
    
    for page in range(max_pages):
        cmd = [
            "/home/quant/.hermes/node/bin/vike-data",
            "hl",
            "wallet-activity",
            wallet,
            "--view",
            "fills",
            "--limit",
            "5000",
            "--json",
        ]
        if cursor:
            cmd.extend(["--cursor", cursor])
            
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"  Error fetching page {page} for {wallet}: {proc.stderr[:200]}")
            break
            
        out = proc.stdout
        idx = out.find("{")
        if idx == -1:
            print(f"  No JSON output for {wallet}")
            break
            
        data = json.loads(out[idx:])
        items = data.get("items", [])
        if not items:
            break
            
        all_fills.extend(items)
        cursor = data.get("nextCursor")
        if not cursor:
            break
        time.sleep(0.2)
        
    return all_fills


def backfill(wallets: list[str] | None = None):
    print("=" * 80)
    print("BACKFILLING MISSING FILLS VIA VIKE FOR ZERO-FILL WALLETS")
    print("=" * 80)

    target_wallets = wallets if wallets is not None else _resolve_target_wallets()
    total_loaded = 0

    for wallet in target_wallets:
        print(f"\nProcessing {wallet}...")
        raw_fills = fetch_vike_fills(wallet)
        print(f"  Fetched {len(raw_fills)} fills from Vike")
        if not raw_fills:
            continue
            
        # Parse through canonical strict model
        parsed_fills = []
        for r in raw_fills:
            try:
                fill_obj = from_vike(r, wallet=wallet, source="vike")
                parsed_fills.append(fill_obj)
            except Exception as e:
                print(f"  Parse error on fill: {e}")
                
        print(f"  Successfully parsed {len(parsed_fills)} canonical fills")
        
        # Group by UTC day
        day_groups: dict[str, list[dict]] = {}
        for f in parsed_fills:
            d_str = f.ts.strftime("%Y-%m-%d")
            day_groups.setdefault(d_str, []).append({
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
            })
            
        # Ingest daily partitions
        days_ingested = 0
        for d_str, rows in day_groups.items():
            df = pl.DataFrame(rows, schema=FILLS_POLARS_SCHEMA)
            ingest("fills", wallet, d_str, df, source="vike")
            days_ingested += 1
            
        print(f"  Ingested {len(parsed_fills)} fills across {days_ingested} daily partitions")
        total_loaded += len(parsed_fills)
        
    print("\nRefreshing catalog wallet summary...")
    refresh_wallet_summary()
    
    print("Verifying store integrity...")
    errs = verify()
    print(f"Verification complete: {errs} errors found")
    print(f"Total new fills loaded into canonical store: {total_loaded}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallets", nargs="+", default=None, help="Optional wallet addresses (defaults to SQLite registry IDs)")
    args = parser.parse_args()
    backfill(wallets=[w.lower() for w in args.wallets] if args.wallets else None)
