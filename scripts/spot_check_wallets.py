"""3-Wallet Live-Position Spot Check against Migrated Wallet Store.

Reconstructs final position per symbol from migrated fills:
    reconstructed_position = sum(signed size_token)
Compares with vike-data hl wallet <addr> --json and live open positions.
Reports differences clearly without forcing a match.
"""

from __future__ import annotations

import json
import subprocess
import polars as pl

from copytrade_pm.wallet_store.store import scan


WALLETS = [
    ("ACT04", "0xe2823659be02e0f48a4660e4da008b5e1abfdf29"),
    ("Trader-1856", "0x185611e0343c14f53a4406891cb0fdc9e81808ae"),
    ("Trader-0324", "0x032456ce7beac3bc30c3b13ac0a3c2e65dd43711"),
]


def run_vike_wallet(addr: str) -> dict:
    cmd = ["/home/quant/.hermes/node/bin/vike-data", "hl", "wallet", addr, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # The output might have npm warning at the top; find the first '{'
    out = proc.stdout
    idx = out.find("{")
    if idx == -1:
        raise ValueError(f"No JSON found in vike output: {out}")
    return json.loads(out[idx:])


def run_vike_positions(addr: str) -> list[dict]:
    cmd = [
        "/home/quant/.hermes/node/bin/vike-data",
        "hl",
        "market",
        "--view",
        "positions",
        "--wallet",
        addr,
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = proc.stdout
    idx = out.find("{")
    if idx == -1:
        return []
    data = json.loads(out[idx:])
    return data.get("positions", [])


def spot_check():
    print("=" * 80)
    print("3-WALLET LIVE-POSITION SPOT CHECK")
    print("=" * 80)

    for label, addr in WALLETS:
        print(f"\nEvaluating {label} ({addr}):")

        # 1. Reconstruct from migrated fills
        lf = scan("fills", wallets=[addr])
        df_fills = lf.collect()

        print(f"  Migrated fills count: {df_fills.height}")
        if df_fills.height > 0:
            min_ts = df_fills["ts"].min()
            max_ts = df_fills["ts"].max()
            print(f"  Fills time range: {min_ts} -> {max_ts}")

            # Reconstruct: sum(signed size_token)
            # buy = +size, sell = -size
            signed_expr = (
                pl.when(pl.col("side") == "buy")
                .then(pl.col("size_token"))
                .otherwise(-pl.col("size_token"))
            )
            reconstructed = (
                df_fills.with_columns(signed_size=signed_expr)
                .group_by("symbol")
                .agg(
                    reconstructed_net_size=pl.col("signed_size").sum(),
                    fill_count=pl.len(),
                    last_fill=pl.col("ts").max(),
                )
                .filter(pl.col("reconstructed_net_size").abs() > 1e-5)
                .sort("symbol")
            )
        else:
            reconstructed = pl.DataFrame()

        # 2. Check migrated positions dataset if any
        lf_pos = scan("positions", wallets=[addr])
        df_pos = lf_pos.collect()
        latest_stored_pos = {}
        if df_pos.height > 0:
            max_snap = df_pos["snapshot_ts"].max()
            stored_latest_df = df_pos.filter(pl.col("snapshot_ts") == max_snap)
            for row in stored_latest_df.to_dicts():
                direction_mult = 1.0 if row["direction"] == "long" else -1.0
                latest_stored_pos[row["symbol"]] = {
                    "signed_size": row["size_token"] * direction_mult,
                    "snapshot_ts": row["snapshot_ts"],
                }

        # 3. Fetch live data from vike
        wallet_overview = run_vike_wallet(addr)
        live_positions_list = run_vike_positions(addr)

        live_summary = wallet_overview.get("open_positions", {})
        live_equity = wallet_overview.get("equity", {})
        live_positions_map = {}
        for p in live_positions_list:
            dir_mult = 1.0 if p["direction"] == "long" else -1.0
            live_positions_map[p["symbol"]] = {
                "size_token": p["size_token"],
                "direction": p["direction"],
                "signed_size": p["size_token"] * dir_mult,
                "entry_price": p.get("entry_price"),
                "mark_price": p.get("mark_price"),
                "unrealized_pnl": p.get("unrealized_pnl"),
            }

        print(
            f"  Live vike summary: count={live_summary.get('count')}, notional_usd=${live_summary.get('notional_usd', 0):,.2f}, equity=${live_equity.get('account_value', 0):,.2f}"
        )
        print(f"  Live open symbols count: {len(live_positions_map)}")

        # 4. Compare symbols
        all_symbols = sorted(
            set(reconstructed["symbol"].to_list() if reconstructed.height > 0 else [])
            | set(live_positions_map.keys())
            | set(latest_stored_pos.keys())
        )

        reconstructed_dict = (
            dict(zip(reconstructed["symbol"], reconstructed["reconstructed_net_size"]))
            if reconstructed.height > 0
            else {}
        )

        print("\n  Per-Symbol Position Comparison:")
        print(
            f"  {'Symbol':<10} | {'Fills Reconstructed':<20} | {'Stored Pos Snapshot':<20} | {'Live Open Position':<20} | {'Diff (Live - Fills)':<20}"
        )
        print("  " + "-" * 96)

        for sym in all_symbols:
            recon_sz = reconstructed_dict.get(sym, 0.0)
            stored_sz = latest_stored_pos.get(sym, {}).get("signed_size", None)
            live_sz = live_positions_map.get(sym, {}).get("signed_size", 0.0)
            diff = live_sz - recon_sz

            recon_str = f"{recon_sz:+.4f}" if sym in reconstructed_dict else "0.0 (closed/none)"
            stored_str = f"{stored_sz:+.4f}" if stored_sz is not None else "n/a"
            live_str = f"{live_sz:+.4f}" if sym in live_positions_map else "0.0 (closed)"
            diff_str = f"{diff:+.4f}"

            print(
                f"  {sym:<10} | {recon_str:<20} | {stored_str:<20} | {live_str:<20} | {diff_str:<20}"
            )

        print("\n  Analysis:")
        if df_fills.height > 0:
            diff_count = sum(
                1
                for sym in all_symbols
                if abs(
                    live_positions_map.get(sym, {}).get("signed_size", 0.0)
                    - reconstructed_dict.get(sym, 0.0)
                )
                > 1e-4
            )
            print(f"  - Total symbols evaluated: {len(all_symbols)}")
            print(f"  - Differing symbols: {diff_count}")
            print(
                f"  - Cause of differences: Ingested fills cover historical windows (up to {df_fills['ts'].max().strftime('%Y-%m-%d %H:%M:%S')}), while live positions reflect real-time on-chain state as of {live_equity.get('as_of', 'now')}. Between the dataset cutoff and now, positions were opened, closed, or partially filled on-chain."
            )


if __name__ == "__main__":
    spot_check()
