"""Read-only, retrospective barbell stress research on SQLite ML4T-66 wallets.

Uses native SHA-verified 1m OHLC and existing flat-start, next-open, per-pod
follower simulator. This is NOT PIT faithful: selection and risk calibration
are retrospective, source equity scalars are not timestamped, source first-known
receipts/NAV/funding/quotes are unknown, and pod stops/flatten fills are NOT
implemented. Never promote output to trading authorization.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from hashlib import sha256
import itertools
import json
import math
import os
from pathlib import Path

import numpy as np
import polars as pl

from copytrade_pm.pm_ml4t_batch_recovery import roster, local_sources, anchored_batches
if __package__:
    from . import ml4t66_portfolio_backtest as base
else:
    import ml4t66_portfolio_backtest as base

ANCHORS = ("M22", "H34", "M55", "M51")
RUNNERS = ("H36", "M40", "M50", "M58")
MEMBERS = tuple(dict.fromkeys(ANCHORS + RUNNERS))
STARTING_EQUITY = 10_000.0
TRAIN_DAYS = 45
STRESS = 1.5
COST_BUFFER = 20.0
DAILY_LIMIT = 500.0
TRAILING_LIMIT = 1_000.0
PASS_TARGET = 11_000.0


def risk_stats(close_equity: np.ndarray, adverse_equity: np.ndarray) -> tuple[float, float]:
    """Worst observed intraday close-HWM to 1m adverse mark, and lifetime HWM."""
    if not len(close_equity) or not np.isfinite(close_equity).all() or not np.isfinite(adverse_equity).all():
        raise ValueError("INCOMPLETE_RISK_CALIBRATION")
    lifetime_peak = np.maximum.accumulate(np.r_[STARTING_EQUITY, close_equity])[1:]
    lifetime = max(0.0, float(np.max(lifetime_peak - adverse_equity)))
    day_max = 0.0
    for first in range(0, len(close_equity), 1440):
        seq = close_equity[first:first + 1440]
        adv = adverse_equity[first:first + 1440]
        day_start = float(close_equity[first - 1]) if first else STARTING_EQUITY
        hwm = np.maximum.accumulate(np.r_[day_start, seq])[1:]
        day_max = max(day_max, float(np.max(hwm - adv)))
    return day_max, lifetime


def scale_batch(batch: pl.DataFrame, members: tuple[str, ...], ks: dict[str, float],
                static_equities: dict[str, str]) -> pl.DataFrame:
    """Rescale net source quantities so unchanged native simulator applies true k.

    Existing engine computes k=(1/n)*min(.35,10000/E). By transforming only
    input deltas, fill minimums and modeled costs apply to the requested k.
    """
    selection = batch.filter(pl.col("alias").is_in(members))
    ratio = pl.lit(1.0)
    for alias in members:
        equity = float(static_equities[alias])
        default = min(.35, 10_000.0 / equity) / len(members)
        ratio = pl.when(pl.col("alias") == alias).then(pl.lit(ks[alias] / default)).otherwise(ratio)
    return selection.with_columns((pl.col("net_qty") * ratio).alias("net_qty"))


def passage(close: np.ndarray, adverse: np.ndarray, first_unknown: int | None) -> dict:
    """Conservative 5% intraday daily-HWM / 10% continuous trailing / +10%."""
    day_start = STARTING_EQUITY
    day_peak = STARTING_EQUITY
    total_peak = STARTING_EQUITY
    previous = STARTING_EQUITY
    end = min(len(close), first_unknown) if first_unknown is not None else len(close)
    for t in range(end):
        mark, adverse_mark = float(close[t]), float(adverse[t])
        if not math.isfinite(mark) or not math.isfinite(adverse_mark):
            return {"status": "BLOCKED_MARK", "minute": t}
        if t % 1440 == 0:
            day_start = previous
            day_peak = day_start
        # Check downside BEFORE a same-minute apparent profit-target touch.
        day_peak = max(day_peak, mark)
        total_peak = max(total_peak, mark)
        daily_floor = max(day_start, day_peak) - DAILY_LIMIT
        trailing_floor = total_peak - TRAILING_LIMIT
        floor = max(daily_floor, trailing_floor)
        if adverse_mark <= floor:
            return {
                "status": "MODELED_BREACH_BEFORE_GAP", "minute": t,
                "floor_usd": round(floor, 2), "adverse_equity_usd": round(adverse_mark, 2),
            }
        if mark >= PASS_TARGET:
            return {"status": "MODELED_TARGET_BEFORE_GAP", "minute": t,
                    "equity_usd": round(mark, 2)}
        previous = mark
    return {"status": "BLOCKED_GAP" if first_unknown is not None else "UNRESOLVED_AT_END",
            "minute": end, "last_close_equity": round(float(close[end-1]), 2) if end else None}


def first_unmanaged_pod_stop(close: np.ndarray, adverse: np.ndarray, role: str) -> dict | None:
    """Diagnostic: first stop the *unmanaged* position path would hit.

    Not a simulation of flatten orders or post-stop portfolio returns.
    """
    peak = STARTING_EQUITY
    previous = STARTING_EQUITY
    day_start = STARTING_EQUITY
    daily_hard = 120.0 if role == "anchor" else 100.0
    lifetime_hard = 200.0 if role == "anchor" else 150.0
    for t, mark in enumerate(close):
        if t % 1440 == 0:
            day_start = previous
        peak = max(peak, float(mark))
        low = float(adverse[t])
        if low <= day_start - daily_hard:
            return {"minute": t, "reason": "DAILY_HARD"}
        if low <= peak - lifetime_hard:
            return {"minute": t, "reason": "LIFETIME_DRAWDOWN_HARD"}
        previous = float(mark)
    return None


def evaluate(db: Path, source_root: Path, market_root: Path) -> dict:
    roster_by_address, cohort_sha = roster(db)
    stores, provenance = local_sources(source_root, roster_by_address,
                                       extra_source_dirs=(base.SUPPLEMENT,))
    df, source = base.source_rows(stores, roster_by_address, set(MEMBERS))
    batches = {m: anchored_batches(df, m) for m in (2, 5)}
    coin_first: dict[str, int] = {}
    for batch in batches.values():
        for row in batch.iter_rows(named=True):
            coin_first[row["coin"]] = min(coin_first.get(row["coin"], row["execute_ms"]),
                                          row["execute_ms"])
    panels, coverage = base.load_native_panels(market_root, coin_first)
    equity_by_wallet = {s: source["wallets"][s]["static_equity_scalar"] for s in MEMBERS}
    risk = {}
    train_count = TRAIN_DAYS * 1440
    for alias in MEMBERS:
        q = batches[5].filter(pl.col("alias") == alias)
        c, a, _, _, d = base.simulate_inventory(q, (alias,), source["wallets"],
                                                panels, cost_bps=6.0)
        first_unknown = d["failure_index_or_none"]
        if first_unknown is not None and first_unknown < base.MINUTES:
            raise ValueError(f"CANDIDATE_HAS_INCOMPLETE_NATIVE_MARKS:{alias}")
        training_daily, training_dd = risk_stats(c[:train_count], a[:train_count])
        full_daily, full_dd = risk_stats(c, a)
        if min(training_daily, training_dd) < 1:
            raise ValueError(f"INSUFFICIENT_RISK_TAIL_FOR_SIZING:{alias}")
        base_k = min(.35, 10000.0 / float(equity_by_wallet[alias]))
        source_times = df.filter(pl.col("alias") == alias).select(
            pl.col("time").min().alias("first"), pl.col("time").max().alias("last")).row(0)
        risk[alias] = {
            "source_fill_events": int(len(df.filter(pl.col("alias") == alias))),
            "source_first_event_ms": source_times[0],
            "source_last_event_ms": source_times[1],
            "base_single_pod_k": base_k,
            "risk_train_45d_at_base_k": {
                "worst_daily_adverse_usd": round(training_daily, 2),
                "lifetime_adverse_dd_usd": round(training_dd, 2),
            },
            "risk_full_90d_at_base_k": {
                "worst_daily_adverse_usd": round(full_daily, 2),
                "lifetime_adverse_dd_usd": round(full_dd, 2),
            },
            "source_static_equity_usd": equity_by_wallet[alias],
            "source_files_sha256": source["wallets"][alias]["source_files_sha256"],
        }

    def make_k(alias: str, role: str) -> float:
        daily_budget, life_budget = (120.0, 200.0) if role == "anchor" else (100.0, 150.0)
        d = risk[alias]["risk_train_45d_at_base_k"]
        k_base = risk[alias]["base_single_pod_k"]
        return min(
            k_base,
            k_base * (daily_budget - COST_BUFFER) / (STRESS * d["worst_daily_adverse_usd"]),
            k_base * (life_budget - COST_BUFFER) / (STRESS * d["lifetime_adverse_dd_usd"]),
        )

    policies = [
        ("ANCHORS_3", ("M22", "H34", "M55"), ("anchor", "anchor", "anchor")),
        ("ANCHORS_3_ALT", ("M22", "H34", "M51"), ("anchor", "anchor", "anchor")),
        ("ANCHORS_3_FULL_MARKS", ("H34", "M55", "M51"), ("anchor", "anchor", "anchor")),
    ]
    for pair, runner in itertools.product(itertools.combinations(ANCHORS, 2), RUNNERS):
        policies.append(("BARBELL_" + "_".join((*pair, runner)),
                         (*pair, runner), ("anchor", "anchor", "runner")))

    policies.extend([
        ("BARBELL_H34_M51_H36_COCRASH_CLAMP",
         ("H34", "M51", "H36"), ("anchor", "anchor", "runner")),
        ("BARBELL_H34_M51_H36_FULL90_RISK",
         ("H34", "M51", "H36"), ("anchor", "anchor", "runner")),
    ])
    results = []
    pod_stop_cache = {}
    for label, members, roles in policies:
        ks = {alias: make_k(alias, role) for alias, role in zip(members, roles)}
        if label.endswith("_FULL90_RISK"):
            for alias, role in zip(members, roles):
                daily_budget, life_budget = ((120.0, 200.0) if role == "anchor"
                                             else (100.0, 150.0))
                d = risk[alias]["risk_full_90d_at_base_k"]
                kbase = risk[alias]["base_single_pod_k"]
                ks[alias] = min(
                    kbase,
                    kbase * (daily_budget-COST_BUFFER) / (STRESS*d["worst_daily_adverse_usd"]),
                    kbase * (life_budget-COST_BUFFER) / (STRESS*d["lifetime_adverse_dd_usd"]),
                )
        if label.endswith("_COCRASH_CLAMP"):
            others = sum(
                risk[alias]["risk_full_90d_at_base_k"]["worst_daily_adverse_usd"]
                *ks[alias]/risk[alias]["base_single_pod_k"]
                for alias in ("H34", "H36")
            )
            remaining = max(0., 400.0/STRESS - others)
            ks["M51"] = min(
                ks["M51"], remaining*risk["M51"]["base_single_pod_k"]
                /risk["M51"]["risk_full_90d_at_base_k"]["worst_daily_adverse_usd"])
        co_worst = STRESS*sum(
            risk[alias]["risk_full_90d_at_base_k"]["worst_daily_adverse_usd"]
            *ks[alias]/risk[alias]["base_single_pod_k"] for alias in members
        )
        for delay in (2, 5):
            for cost in (6.0, 12.0, 18.0):
                scaled = scale_batch(batches[delay], members, ks, equity_by_wallet)
                equity, adverse, gross, bad, diagnostics = base.simulate_inventory(
                    scaled, members, source["wallets"], panels, cost_bps=cost)
                first_unknown = diagnostics["failure_index_or_none"]
                event = passage(equity, adverse, first_unknown)
                stop_warnings = {}
                for alias, role in zip(members, roles):
                    key = (alias, role, delay, cost)
                    if key not in pod_stop_cache:
                        solo = scale_batch(batches[delay], (alias,), {alias:ks[alias]}, equity_by_wallet)
                        pc, pa, _, _, pd = base.simulate_inventory(
                            solo, (alias,), source["wallets"], panels, cost_bps=cost)
                        if pd["failure_index_or_none"] is not None:
                            stop_warnings[alias] = {"status": "BLOCKED_POD_MARKS"}
                            pod_stop_cache[key] = stop_warnings[alias]
                        else:
                            pod_stop_cache[key] = first_unmanaged_pod_stop(pc, pa, role)
                    stop = pod_stop_cache[key]
                    if stop is not None:
                        stop_warnings[alias] = stop
                first_pod_hard = min(
                    (x["minute"] for x in stop_warnings.values() if "minute" in x),
                    default=None)
                before_target = bool(event["status"] == "MODELED_TARGET_BEFORE_GAP"
                      and first_pod_hard is not None and first_pod_hard <= event["minute"])
                end = first_unknown if first_unknown is not None else len(equity)
                prefix = equity[:end]
                prefix_adverse = adverse[:end]
                daily, drawdown = risk_stats(prefix, prefix_adverse) if len(prefix) else (None, None)
                results.append({
                    "portfolio": label, "members": members, "roles": roles,
                    "k_factors": {x: round(ks[x], 9) for x in members},
                    "pod_equivalent_capital_usd": {
                        x: round(ks[x] * float(equity_by_wallet[x]), 2) for x in members
                    },
                    "delay_minutes": delay, "one_side_total_cost_bps": cost,
                    "coincident_full_sample_worst_day_stress_1_5x_usd": round(co_worst, 2),
                    "passes_internal_400_usd_coincident_stress": co_worst <= 400.0,
                    "intact_days_before_first_unknown": round(end / 1440, 3),
                    "first_unknown": diagnostics["first_follower_path_unknown_at"],
                    "modeled_orders": sum(x["scenario_trades_executed"]
                                          for x in diagnostics["pod_results"].values()),
                    "fixed_cost_usd": round(sum(x["scenario_fixed_fee_plus_slippage_usd"]
                                                for x in diagnostics["pod_results"].values()), 2),
                    "terminal_pnl_usd": round(float(equity[-1] - STARTING_EQUITY), 2)
                       if first_unknown is None and np.isfinite(equity[-1]) else None,
                    "prefix_pnl_usd": round(float(prefix[-1] - STARTING_EQUITY), 2)
                       if len(prefix) else None,
                    "worst_daily_adverse_usd": round(daily, 2) if daily is not None else None,
                    "max_adverse_dd_usd": round(drawdown, 2) if drawdown is not None else None,
                    "peak_gross_leverage": round(float(np.nanmax(gross)) / STARTING_EQUITY, 3)
                        if np.isfinite(gross).any() else None,
                    "unmanaged_pod_stops": stop_warnings,
                    "first_pod_hard_stop_minute": first_pod_hard,
                    "target_requires_ignored_prior_pod_hard_stop": before_target,
                    "first_passage": {**event,
                        "utc": (base.START + timedelta(minutes=event["minute"])).isoformat()},
                    "missing_executions_by_coin": diagnostics["missing_executions_by_coin"],
                })
    # Dependence uses synchronous 4h increments of simulated, sized follower
    # equity, not overlapping source realized fill P&L or unsynchronized dates.
    four_hour = {}
    for alias in MEMBERS:
        role = "anchor" if alias in ANCHORS else "runner"
        k = make_k(alias, role)
        solo = scale_batch(batches[5], (alias,), {alias: k}, equity_by_wallet)
        e, _, _, bad, check = base.simulate_inventory(
            solo, (alias,), source["wallets"], panels, cost_bps=6.0)
        if bad.any() or check["failure_index_or_none"] is not None:
            risk[alias]["4h_dependence_status"] = "BLOCKED_BY_SIZED_FOLLOWER_MARK_GAP"
            continue
        increments = np.diff(np.r_[STARTING_EQUITY, e[239::240]])
        four_hour[alias] = increments
        standard = float(np.std(increments))
        normal = (increments-float(np.mean(increments)))/standard if standard > 0 else None
        mix = (df.filter(pl.col("alias") == alias)
               .group_by("coin").agg(pl.col("notional").sum().alias("usd"))
               .sort("usd", descending=True))
        total_mix = mix["usd"].sum()
        risk[alias]["turnover_top_coins"] = [
            {"coin": coin, "fraction": round(float(usd/total_mix), 4)}
            for coin, usd in mix.select("coin", "usd").head(4).iter_rows()
        ]
        risk[alias]["descriptive_4h_skew_at_sized_k"] = (
            round(float(np.mean(normal**3)), 3) if normal is not None else None
        )
        risk[alias]["descriptive_4h_excess_kurtosis_at_sized_k"] = (
            round(float(np.mean(normal**4)-3), 3) if normal is not None else None
        )
        risk[alias]["4h_sample_count"] = len(increments)
    dependence = {}
    for a, b in itertools.combinations(sorted(four_hour), 2):
        x, y = four_hour[a], four_hour[b]
        threshold_x, threshold_y = np.quantile(x, .05), np.quantile(y, .05)
        bottom_x, bottom_y = x <= threshold_x, y <= threshold_y
        count_y = int(bottom_y.sum())
        pearson = float(np.corrcoef(x, y)[0, 1])
        rank_x = np.asarray(pl.Series(x).rank("average").to_list(), float)
        rank_y = np.asarray(pl.Series(y).rank("average").to_list(), float)
        spearman = float(np.corrcoef(rank_x, rank_y)[0, 1])
        dependence[a + "__" + b] = {
            "pearson_4h": round(pearson, 4) if math.isfinite(pearson) else None,
            "spearman_4h": round(spearman, 4) if math.isfinite(spearman) else None,
            "conditional_joint_bottom_5pct": round(
                float((bottom_x & bottom_y).sum()/count_y), 3
            ) if count_y else None,
            "bottom_5pct_joint_count": int((bottom_x & bottom_y).sum()),
            "4h_intervals": len(x),
        }
    return {
        "schema": "ml4t66_barbell_retrospective_sizing_stress_v3",
        "study_window": [base.START.isoformat(), base.END.isoformat()],
        "research_input": {"sqlite_cohort": "ml4t-strict-66", "source_sha256": cohort_sha,
                           "wallets_evaluated": list(MEMBERS), "source_fill_count": len(df),
                           "market_coin_count": len(panels),
                           "native_market_coverage_sha256": sha256(
                               json.dumps(coverage, sort_keys=True, allow_nan=False).encode()
                           ).hexdigest()},
        "rule": {"account_usd": 10000, "daily_hwm_loss_usd": DAILY_LIMIT,
                 "continuous_trailing_dd_usd": TRAILING_LIMIT, "target_usd": PASS_TARGET,
                 "daily_reset_utc": "00:00", "provider_version": "USER_SCENARIO_UNVERIFIED"},
        "risk": {"training_days_for_static_k": TRAIN_DAYS, "stress_multiplier": STRESS,
                 "4h_dependence_is_retrospective_sized_follower_scenario_not_validated_independent_observation": True,
                 "coincident_stress_internal_ceiling_usd": 400.0,
                 "coincident_stress_is_adversarial_alignment_of_nonsimultaneous_historical_worsts": True,
                 "full90_risk_and_cocrash_clamp_variants_are_full_sample_hindsight_sensitivity": True,
                 "additional_dollar_buffer_per_pod": COST_BUFFER,
                 "anchors_daily_lifetime_usd": [120, 200],
                 "runner_daily_lifetime_usd": [100, 150],
                 "reserve_usd": 50,
                 "risk_calibration_has_selection_and_hindsight_bias": True,
                 "source_equity_asof_available": False,
                 "pod_stop_rebalance_or_flatten_fills": "NOT_SIMULATED"},
        "wallets": risk, "dependence_4h": dependence, "portfolios": results,
        "native_market_coverage": coverage,
        "scientifically_qualified": False, "trading_authorized": False,
        "unknown": ["source NAV and full subaccount books", "independent first-local follower clocks",
                    "funding and margin liquidations", "reliable executable spread/depth/impact",
                    "risk stop enforcement and forced liquidation", "independent OOS validation"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.db, args.source_root, args.market_root)
    out = args.output_root
    out.mkdir(parents=True, mode=0o700, exist_ok=True)
    if out.is_symlink() or out.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_OUTPUT_ROOT_REQUIRED")
    data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    digest = sha256(data).hexdigest()
    path = out / f"barbell_research_{digest[:20]}.json"
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("NONIDENTICAL_IMMUTABLE_REPORT_HASH")
    else:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as writer:
            writer.write(data)
            writer.flush()
            os.fsync(writer.fileno())
    count = {}
    for row in result["portfolios"]:
        if row["delay_minutes"] == 5 and row["one_side_total_cost_bps"] == 6:
            s = row["first_passage"]["status"]
            count[s] = count.get(s, 0) + 1
            print(json.dumps({"portfolio": row["portfolio"], "k": row["k_factors"],
                              "pnl": row["terminal_pnl_usd"], "maxdd":row["max_adverse_dd_usd"],
                              "outcome":row["first_passage"], "orders":row["modeled_orders"]}))
    print(json.dumps({"sha256": digest, "path": str(path), "counts_5m_6bps": count}))


if __name__ == "__main__":
    main()
