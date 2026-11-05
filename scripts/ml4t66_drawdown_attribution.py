"""Read-only attribution of the unprotected 5m ML4T-66 Explorer historical DD.

Reconstructs the same executed event deltas as the recorded oracle simulation,
then decomposes the peak-to-trough cash and inventory PnL by pod/instrument.
Not a protected trading backtest or actual follower loss.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path

import numpy as np
import polars as pl

import ml4t66_portfolio_backtest as bt


def audit(db: Path, source_root: Path, market_root: Path) -> dict:
    ids, _ = bt.roster(db)
    stores, _ = bt.local_sources(source_root, ids, extra_source_dirs=(bt.SUPPLEMENT,))
    members = bt.CONTRACTS["EXPLORER"]["members"]
    source, source_meta = bt.source_rows(stores, ids, set(members))
    batch = bt.anchored_batches(source, 5)
    first = {}
    for order in batch.iter_rows(named=True):
        first[order["coin"]] = min(
            first.get(order["coin"], order["execute_ms"]), order["execute_ms"]
        )
    price, _ = bt.load_native_panels(market_root, first)
    equity, _worst, gross, bad, execution = bt.simulate_inventory(
        batch, members, source_meta["wallets"], price, cost_bps=6
    )
    first_unknown = execution["failure_index_or_none"]
    prefix = equity[:first_unknown] if first_unknown is not None else equity
    running_peak = np.maximum.accumulate(np.r_[10000.0, prefix])[1:]
    depth = running_peak - prefix
    trough = int(np.argmax(depth))
    candidate_peak = int(np.argmax(np.r_[10000.0, prefix[: trough + 1]])) - 1
    start_equity = float(prefix[candidate_peak]) if candidate_peak >= 0 else 10000.0
    end_equity = float(prefix[trough])
    contribution = []
    for member in members:
        scalar = Decimal(source_meta["wallets"][member]["static_equity_scalar"])
        k = float(Decimal(1) / Decimal(3) * min(Decimal(".35"), Decimal(10000) / scalar))
        for grp in (
            batch.filter(pl.col("alias") == member).partition_by(["coin"], as_dict=True).values()
        ):
            coin = grp["coin"][0]
            native = price[coin]
            changes = np.zeros(bt.MINUTES, dtype=np.float64)
            delta_cash = np.zeros(bt.MINUTES, dtype=np.float64)
            fees = np.zeros(bt.MINUTES, dtype=np.float64)
            for event in grp.iter_rows(named=True):
                index = (event["execute_ms"] - bt.START_MS) // bt.MINUTE_MS
                if not 0 <= index < bt.MINUTES or not np.isfinite(native["open"][index]):
                    continue
                dq = float(event["net_qty"]) * k
                op = native["open"][index]
                if abs(dq * op) < 10:
                    continue
                changes[index] += dq
                px = op * (1.0 + np.sign(dq) * 0.00025)
                delta_cash[index] -= dq * px
                fees[index] += abs(dq * op) * 0.00035
            q = np.cumsum(changes)
            cash = np.cumsum(delta_cash - fees)
            # Endpoint instrument PnL is cash plus inventory mark.
            t0 = (
                cash[candidate_peak] + q[candidate_peak] * native["close"][candidate_peak]
                if candidate_peak >= 0
                else 0.0
            )
            t1 = cash[trough] + q[trough] * native["close"][trough]
            price0 = float(native["close"][candidate_peak]) if candidate_peak >= 0 else None
            price1 = float(native["close"][trough])
            contribution.append(
                {
                    "wallet": member,
                    "market": coin,
                    "pnl_change_usd": round(float(t1 - t0), 2),
                    "qty_peak": round(float(q[candidate_peak]), 8) if candidate_peak >= 0 else 0,
                    "qty_trough": round(float(q[trough]), 8),
                    "mark_peak": round(price0, 8)
                    if price0 is not None and np.isfinite(price0)
                    else None,
                    "mark_trough": round(price1, 8),
                    "gross_peak_usd": round(
                        abs(float(q[candidate_peak] * native["close"][candidate_peak])), 2
                    )
                    if candidate_peak >= 0
                    else 0.0,
                    "gross_trough_usd": round(abs(float(q[trough] * native["close"][trough])), 2),
                    "new_exec_between": int(
                        np.count_nonzero(changes[candidate_peak + 1 : trough + 1])
                    ),
                    "fees_between_usd": round(
                        float(fees[candidate_peak + 1 : trough + 1].sum()), 2
                    ),
                }
            )
    wallet_delta = {
        member: round(sum(x["pnl_change_usd"] for x in contribution if x["wallet"] == member), 2)
        for member in members
    }
    peak_time = (
        (bt.START + timedelta(minutes=candidate_peak)).isoformat()
        if candidate_peak >= 0
        else "START"
    )
    trough_time = (bt.START + timedelta(minutes=trough)).isoformat()
    out = {
        "reported_max_dd_usd": round(float(depth.max()), 2),
        "reconstructed_peak_to_trough_loss": round(start_equity - end_equity, 2),
        "peak_equity_usd": round(start_equity, 2),
        "trough_equity_usd": round(end_equity, 2),
        "peak_time_utc": peak_time,
        "trough_time_utc": trough_time,
        "gross_at_peak": round(float(gross[candidate_peak]), 2) if candidate_peak >= 0 else 0,
        "gross_at_trough": round(float(gross[trough]), 2),
        "first_unpriceable_time": execution["first_follower_path_unknown_at"],
        "wallet_contributions": wallet_delta,
        "top_contributions": sorted(contribution, key=lambda x: x["pnl_change_usd"])[:12],
        "gross_at_peak_by_member": {
            member: round(
                sum(x["gross_peak_usd"] for x in contribution if x["wallet"] == member), 2
            )
            for member in members
        },
        "pnl_sum_matches_equity": abs(
            sum(x["pnl_change_usd"] for x in contribution) + (start_equity - end_equity)
        )
        < 0.1,
        "scientifically_qualified": False,
    }
    if not out["pnl_sum_matches_equity"]:
        raise ValueError("INSTRUMENT_ATTRIBUTION_DOES_NOT_RECONCILE")
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.db, args.source_root, args.market_root), indent=2))
