"""Native-minute conditional stress on source-position legs.

Important: this is a SCREEN_ONLY, read-only diagnostic, NOT a PM03 financial
account simulator. K values are Gemini historical frozen conditional coefficients.
Unavailable source-position intervals are UNKNOWN rather than flat.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

if __package__:
    from scripts.phase7_native_exposure import BASE, END_MS, START_MS, consistent_intervals, native_marks, source_files
else:
    from phase7_native_exposure import BASE, END_MS, START_MS, consistent_intervals, native_marks, source_files

SCALES = {
    "E2": {"ACT04": 0.00428, "S053-HYPE": 0.04708, "S051-BTC": 0.04847},
    "E6": {"ACT04": 0.00257, "S053-HYPE": 0.02825, "S051-BTC": 0.02908,
           "CM-002": 0.00231, "Whale_0x5f94": 0.00029},
}
STUDY_MINUTES = (END_MS - START_MS) // 60_000


def event_intervals(data: list[dict]) -> tuple[dict[str, list[dict]], dict]:
    intervals, status = consistent_intervals(data)
    by_coin = defaultdict(list)
    for i, x in enumerate(intervals):
        by_coin[x["coin"]].append({**x, "interval_id": i})
    return by_coin, status


def build_legs(root: Path, *, top_coins_per_wallet: int = 15) -> tuple[dict[tuple[str, str], np.ndarray], dict]:
    files = source_files(root)
    requested = set().union(*(set(x) for x in SCALES.values()))
    groups = {}
    meta = {}
    for alias in sorted(requested):
        path = files.get(alias)
        if path is None:
            meta[alias] = {"status": "MISSING_SOURCE_CHAIN", "covered_main_coins": 0}
            continue
        payload = json.loads(path.read_text())
        by_coin, counts = event_intervals(payload.get("fills", []))
        # Bound expensive market reads by total source-position duration, but
        # always include BTC/ETH/HYPE when present. Skipped coins are UNKNOWN.
        ranks = sorted(by_coin, key=lambda coin: -sum(
            abs(e["qty"]) * (e["end_ms"] - e["start_ms"]) for e in by_coin[coin]
        ))
        selected = ranks[:top_coins_per_wallet]
        for coin in ("BTC", "ETH", "HYPE"):
            if coin in by_coin and coin not in selected:
                selected.append(coin)
        groups[alias] = {coin: by_coin[coin] for coin in selected}
        meta[alias] = {
            "status": "PARTIAL_SOURCE_POSITION_CHAIN",
            **counts,
            "covered_main_coins": len(selected),
            "total_main_coins_with_start_position": len(by_coin),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    coin_index = defaultdict(dict)
    for alias, by_coin in groups.items():
        for coin, intervals in by_coin.items():
            coin_index[coin][alias] = intervals
    legs: dict[tuple[str, str], np.ndarray] = {}
    no_mark = defaultdict(list)
    for coin, by_alias in sorted(coin_index.items()):
        first = min(e["start_ms"] for events in by_alias.values() for e in events)
        end = max(e["end_ms"] for events in by_alias.values() for e in events)
        bars = native_marks(coin, first, end)
        if bars is None or bars.is_empty():
            for alias in by_alias:
                no_mark[alias].append(coin)
            continue
        for alias, events in by_alias.items():
            frame = pl.DataFrame(events).sort("start_ms")
            matched = bars.join_asof(frame, left_on="ms", right_on="start_ms", strategy="backward").filter(
                pl.col("ms") < pl.col("end_ms")
            )
            if matched.is_empty():
                no_mark[alias].append(coin)
                continue
            # Source-open-to-next-fill interval, no assumptions after last fill.
            # Filter exact minute; the arrays' zero denotes 'unobserved or
            # truly zero', never independently sufficient evidence of flat.
            positions = np.zeros(STUDY_MINUTES, dtype=np.float32)
            ix = ((matched["ms"].to_numpy() - START_MS) // 60_000).astype(np.int64)
            valid = (ix >= 0) & (ix < STUDY_MINUTES)
            qty = matched["qty"].to_numpy() * matched["close"].to_numpy()
            positions[ix[valid]] = qty[valid].astype(np.float32)
            legs[(alias, coin)] = positions
            meta[alias]["priced_minute_legs"] = meta[alias].get("priced_minute_legs", 0) + int(valid.sum())
    for alias, coins in no_mark.items():
        meta[alias]["native_coins_without_priced_chain"] = sorted(coins)
    return legs, meta


def port_exposure(
    legs: dict[tuple[str, str], np.ndarray], scales: dict[str, float]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    per_coin = {}
    for (wallet, coin), vector in legs.items():
        if wallet not in scales:
            continue
        if coin not in per_coin:
            per_coin[coin] = np.zeros(STUDY_MINUTES, dtype=np.float32)
        per_coin[coin] += vector * scales[wallet]
    per_wallet = {}
    for wallet in scales:
        rows = [v for (who, _), v in legs.items() if who == wallet]
        if rows:
            per_wallet[wallet] = np.sum(np.abs(np.stack(rows)), axis=0) * scales[wallet]
    return per_coin, per_wallet


def max_loss(pnl: np.ndarray, any_known: np.ndarray) -> dict:
    vals = pnl[any_known]
    if vals.size == 0:
        return {"worst_model_loss_usd": None, "observed_loss_breach_minutes_450": None}
    # A modeled concurrent shock is not a realized 1-minute PnL.
    return {
        "worst_model_loss_usd": round(float(max(0, -float(vals.min()))), 2),
        "observation_minutes": int(vals.size),
        "shock_crosses_450_usd_minutes": int(np.count_nonzero(vals <= -450)),
        "shock_crosses_850_usd_minutes": int(np.count_nonzero(vals <= -850)),
    }


def evaluate(legs: dict[tuple[str, str], np.ndarray], meta: dict) -> dict:
    result = {"schema": "phase7_conditional_frozen_k_native_stress_v1",
              "scope": "NATIVE_MARK_KNOWN_LEG_SHOCK_ONLY_NOT_ACCOUNT_EQUITY",
              "funding_included": False, "actual_order_receipts": False,
              "source_equity_faithful": False, "whole_account_mtm": False,
              "model_k": SCALES, "portfolios": {}, "source_coverage": meta}
    for portfolio, scales in SCALES.items():
        by_coin, by_wallet = port_exposure(legs, scales)
        if not by_coin:
            result["portfolios"][portfolio] = {"status": "NO_OBSERVED_MARKED_LEGS"}
            continue
        all_coin = np.stack(list(by_coin.values()))
        gross_by_coin = {}
        for (wallet, coin), vector in legs.items():
            if wallet in scales:
                if coin not in gross_by_coin:
                    gross_by_coin[coin] = np.zeros(STUDY_MINUTES, dtype=np.float32)
                gross_by_coin[coin] += np.abs(vector) * scales[wallet]
        net = np.sum(all_coin, axis=0)
        adverse_coin = -0.1 * np.sum(np.abs(all_coin), axis=0)
        known = np.any(np.abs(all_coin) > 0, axis=0)
        wallet_gross = np.stack(list(by_wallet.values()))
        known_gross = np.sum(wallet_gross, axis=0)
        current_max = np.maximum(known_gross, 0)
        # Gross-before-net; same-coin opposite directions reduce net stress but
        # gross risk and funding/instrument margin remain uncancelled.
        by_coin_abs = np.abs(all_coin)
        denom = np.sum(by_coin_abs**2, axis=0)
        effective_coin_bets = np.divide(
            np.sum(by_coin_abs, axis=0)**2, denom,
            out=np.zeros(STUDY_MINUTES), where=denom > 0,
        )
        active = known & (known_gross > 0)
        scenarios = {
            "BTC_DOWN_10": {"BTC": -0.10},
            "ETH_DOWN_10": {"ETH": -0.10},
            "HYPE_DOWN_20": {"HYPE": -0.20},
            "BTC_ETH_DOWN10_HYPE_DOWN20": {"BTC": -0.10, "ETH": -0.10, "HYPE": -0.20},
        }
        shock_results = {}
        for name, shock in scenarios.items():
            pnl = np.zeros(STUDY_MINUTES, dtype=np.float64)
            for coin, rate in shock.items():
                if coin in by_coin:
                    pnl += by_coin[coin] * rate
            shock_results[name] = max_loss(pnl, known)
        shock_results["MARKET_ALL_DOWN10"] = max_loss(-0.10 * net, known)
        shock_results["MARKET_ALL_UP10"] = max_loss(+0.10 * net, known)
        shock_results["ADVERSARIAL_EACH_COIN_10"] = max_loss(adverse_coin, known)
        shock_results["ALL_PODS_SAME_SIGN_DOWN10"] = max_loss(-0.10 * known_gross, known)
        largest_pod = max(by_wallet, key=lambda name: by_wallet[name].max())
        shock_results["LARGEST_POD_DOUBLE_GROSS_10"] = max_loss(
            -0.1 * (known_gross + by_wallet[largest_pod]), known
        )
        top_two = np.sort(wallet_gross, axis=0)[-2:]
        shock_results["TWO_PODS_CORRELATED_ADVERSE_10"] = max_loss(
            -0.1 * np.sum(top_two, axis=0), known
        )
        if "Whale_0x5f94" in by_wallet:
            shock_results["WHALE_DOUBLE_GROSS_10"] = max_loss(
                -0.10 * (known_gross + by_wallet["Whale_0x5f94"]), known
            )
        # Leave-one-out is a hypothetical exposure stress, NOT identification
        # of best/worst realized manager, which requires real account PnL.
        wallet_net = np.sum(np.stack([
            positions * scales[wallet] for (wallet, _), positions in legs.items()
            if wallet == largest_pod
        ]), axis=0)
        shock_results["REMOVE_LARGEST_GROSS_POD_MARKET_DOWN10"] = max_loss(
            -0.1 * (net - wallet_net), known
        )
        sliced = {}
        for block in range(3):
            begin = block * 30 * 24 * 60
            end = min(STUDY_MINUTES, begin + 30 * 24 * 60)
            window_active = active[begin:end]
            window_pnl = net[begin:end]
            sliced[f"days_{block * 30}_to_{(block + 1) * 30}"] = {
                "observed_any_leg_minutes": int(window_active.sum()),
                "peak_known_gross_usd": round(float(current_max[begin:end].max()), 2),
                "market_down10_max_conditional_loss_usd": round(float(max(
                    0, -float((-0.10 * window_pnl).min()))), 2),
            }
        # Holding-only mark changes on continuously observed minutes and
        # immutable source qty are not computed in this shock module.
        # Missing stop policy, funding, actual broker fill or wallet NAV all
        # explicitly remain UNKNOWN rather than accidental 0.
        result["portfolios"][portfolio] = {
            "status": "PARTIAL_KNOWN_LEG_ONLY",
            "missing_wallets": [w for w in scales if w not in by_wallet],
            "observed_priced_coins": sorted(by_coin),
            "observed_minutes_at_least_one_source_leg": int(np.count_nonzero(known)),
            "max_model_gross_usd": round(float(current_max.max()), 2),
            "p95_model_gross_usd": round(float(np.percentile(current_max[active], 95)), 2),
            "max_model_coin_gross_before_net_usd": round(float(
                np.max(np.stack(list(gross_by_coin.values())))), 2),
            "median_effective_coin_bets_observed": round(float(np.median(effective_coin_bets[active])), 2),
            "fraction_observed_minutes_above_hypothetical_20k_gross_cap": round(float(
                np.mean(current_max[active] > 20_000)), 4),
            "max_gross_usd_by_wallet": {wallet: round(float(x.max()), 2) for wallet, x in by_wallet.items()},
            "largest_pod_by_peak_gross": largest_pod,
            "scenario_shocks": shock_results,
            "thirty_day_sensitivity": sliced,
            "execution_2x_3x": "SEE_SEPARATE_PHASE7_DELAY_COST_SCREEN_NOT_FULL_FILL_TCA",
            "partial_fill_and_residual_risk": "UNKNOWN_NO_EXECUTABLE_RECEIPTS",
            "data_stale_outage_or_halt_survival": "UNKNOWN_NO_PM03_REAL_BOOK",
            "best_worst_wallet_removal_pnl": "UNKNOWN_NO_SOURCE_NAV",
            "conditional_cost_one_way_10bps_for_current_max_gross_usd": round(float(current_max.max() * 0.001), 2),
            "account_equity_drawdown": None,
            "period_follower_pnl": None,
            "source_asof_nav": None,
            "first_known_receipt": None,
            "breach_certified": None,
        }
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source-root", type=Path, default=BASE / "data")
    p.add_argument("--cap-coins", type=int, default=15)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    legs, meta = build_legs(args.source_root, top_coins_per_wallet=args.cap_coins)
    result = evaluate(legs, meta)
    blob = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("immutable output already exists")
        args.output.write_text(blob)
    print(json.dumps({"sha256": hashlib.sha256(blob.encode()).hexdigest(),
        "ports": {key: {k: v for k, v in data.items() if k in (
            "observed_minutes_at_least_one_source_leg", "missing_wallets",
            "max_model_gross_usd", "p95_model_gross_usd", "median_effective_coin_bets_observed",
            "fraction_observed_minutes_above_hypothetical_20k_gross_cap", "max_gross_usd_by_wallet",
            "scenario_shocks")} for key, data in result["portfolios"].items()}}, indent=2))


if __name__ == "__main__":
    main()
