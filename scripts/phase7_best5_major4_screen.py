"""Phase 7 exploratory five-pod selection from already captured BTC/ETH/SOL/HYPE fills.

Every candidate belongs to the current 158-wallet research registry. Source
data are SHA-pinned, original files read-only, and no APIs or fills are
retrieved. Selection uses only days 1-60 of the historical 90-day replay;
days 61-90 are a reused temporal diagnostic, *not* a pristine OOS holdout.

The follower policy and economics are a partial historical oracle: observed
leader source-event timestamp + hypothetical 5m wait, next 5m grid native
1m open, equal observed-book gross budget; no source-equity faithful
positions/first-known receipts/true fills. No trade authorization.
"""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from copytrade_pm.wallet_registry import DB
from scripts.phase7_major4_portfolio_screen import (
    MAJORS,
    eligible_wallets,
    registry_addresses,
)
from scripts.phase7_major4_10k_filtered_follow import (
    EXPERIMENTS,
    N,
    N_DAYS,
    _metrics,
    _remove_csv_exact_duplicates,
    load_fills,
    model_wallet,
    verified_bars,
)

TRAIN_DAYS = 60
COSTS = (10, 20, 30)
BUDGETS = (5_000.0, 6_000.0)
MIN_FOCUS = 0.75
MIN_COIN_FRACTION = 0.075
MAX_POOL = 24
BASELINE_M3 = tuple(EXPERIMENTS["M3-BALANCED"])
PREVIOUS_M5 = tuple(EXPERIMENTS["M5-SOL-BOOST"])
MAX_FINALISTS = 26
MAX_COMBINATIONS = 55_000


def _daily_net_unit(model: dict, bps: int) -> np.ndarray:
    assert N_DAYS == 90
    return (
        (model["pnl_delta_per_budget_usd"] - model["turnover_per_budget_usd"] * bps / 10_000)
        .reshape(N_DAYS, 1440)
        .sum(axis=1)
    )


def _close_max_drawdown(pnl: np.ndarray) -> float:
    equity = np.concatenate(([0.0], np.cumsum(pnl)))
    return float(np.max(np.maximum.accumulate(equity) - equity))


def _fit(members: tuple[str, ...], roster: dict) -> tuple[float, dict[str, float]]:
    per_market = {
        coin: sum(
            roster[alias]["gross_turnover_by_coin_fraction"].get(coin, 0.0) for alias in members
        )
        / len(members)
        for coin in MAJORS
    }
    return sum(per_market.values()), per_market


def _stage1_record(
    members: tuple[str, ...],
    roster: dict,
    net20: dict[str, np.ndarray],
    net30: dict[str, np.ndarray],
    pair_correlations: dict[tuple[str, str], float] | None = None,
) -> dict | None:
    focus, weights = _fit(members, roster)
    if focus < MIN_FOCUS or min(weights.values()) < MIN_COIN_FRACTION:
        return None
    per_pod = BUDGETS[0] / len(members)
    train20 = per_pod * sum((net20[a][:TRAIN_DAYS] for a in members))
    train30 = per_pod * sum((net30[a][:TRAIN_DAYS] for a in members))
    gross20 = float(train20.sum())
    gross30 = float(train30.sum())
    dd20 = _close_max_drawdown(train20)
    worst = float(train20.min())
    tail = float(np.sort(train20)[:5].mean())
    correlations = (
        [pair_correlations[tuple(sorted((a, b)))] for a, b in combinations(members, 2)]
        if pair_correlations is not None
        else []
    )
    coincident_loss_days = int(
        sum(sum(net20[a][day] < 0 for a in members) >= 3 for day in range(TRAIN_DAYS))
    )
    # Transparent, heuristic *in-sample* score; not evidence of a risk pass.
    score = gross30 - dd20 - 0.5 * max(0, -tail * 5 - 450)
    return {
        "members": list(members),
        "market_fraction": round(focus, 4),
        "market_mix": {c: round(v, 4) for c, v in weights.items()},
        "train60_pnl_20bps_usd": round(gross20, 2),
        "train60_pnl_30bps_usd": round(gross30, 2),
        "train60_daily_close_dd_20bps_usd": round(dd20, 2),
        "train60_worst_close_day_20bps_usd": round(worst, 2),
        "train60_worst_five_day_avg_20bps_usd": round(tail, 2),
        "train60_score": round(score, 2),
        "train60_mean_daily_net_pair_corr": round(float(np.mean(correlations)), 4)
        if correlations
        else None,
        "train60_max_daily_net_pair_corr": round(max(correlations), 4) if correlations else None,
        "train60_days_with_three_or_more_loss_wallets": coincident_loss_days,
        "risk_reference_scope": "FIRST_60_DAYS_DAILY_CLOSE_SCREEN_ONLY",
    }


def screen(
    pool: list[dict],
    models: dict[str, dict],
) -> tuple[dict, list[dict], list[dict]]:
    aliases = sorted(x["alias"] for x in pool)
    roster = {x["alias"]: x for x in pool}
    if len(aliases) != MAX_POOL or len(models) != MAX_POOL:
        raise ValueError("FROZEN_POOL_SIZE_OR_MODEL_MISMATCH")
    net20 = {a: _daily_net_unit(models[a], 20) for a in aliases}
    net30 = {a: _daily_net_unit(models[a], 30) for a in aliases}
    pair_correlations = {}
    for a, b in combinations(aliases, 2):
        x = net20[a][:TRAIN_DAYS]
        y = net20[b][:TRAIN_DAYS]
        x = x - x.mean()
        y = y - y.mean()
        denom = float(np.linalg.norm(x) * np.linalg.norm(y))
        if denom < 1e-15:
            raise ValueError("UNIDENTIFIABLE_FIRST60_WALLET_RETURN_CORRELATION")
        pair_correlations[(a, b)] = float(np.clip(np.dot(x, y) / denom, -1.0, 1.0))
    all5 = []
    m3extended = []
    diagnostics = Counter()
    for members in combinations(aliases, 5):
        diagnostics["all_five_considered"] += 1
        if diagnostics["all_five_considered"] > MAX_COMBINATIONS:
            raise ValueError("UNBOUNDED_FIVE_WALLET_SEARCH")
        trial = _stage1_record(members, roster, net20, net30, pair_correlations)
        if trial is None:
            continue
        diagnostics["admitted_market_focus"] += 1
        all5.append(trial)
        if set(BASELINE_M3).issubset(members):
            m3extended.append(trial)
    diagnostics["m3_extension_in_admitted_pool"] = len(m3extended)
    diagnostics["positive_30bps_train60"] = sum(x["train60_pnl_30bps_usd"] > 0 for x in all5)
    diagnostics["dailyclose_train60_dd_under_850"] = sum(
        x["train60_daily_close_dd_20bps_usd"] <= 850 for x in all5
    )
    if not all5 or not m3extended:
        raise ValueError("NO_RELEVANT_FIVE_WALLET_CANDIDATES")

    best_extension = max(m3extended, key=lambda x: (x["train60_score"], x["members"]))
    best_all = max(all5, key=lambda x: (x["train60_score"], x["members"]))
    defensive = min(
        (x for x in all5 if x["train60_pnl_30bps_usd"] > 0),
        key=lambda x: (x["train60_daily_close_dd_20bps_usd"], -x["train60_score"], x["members"]),
    )
    profitable = max(all5, key=lambda x: (x["train60_pnl_20bps_usd"], x["members"]))
    # A genuine *lower-correlation* economic control is not the same as
    # the highest-return five. Retain positive first-60d 30bps margin,
    # then minimize modeled daily wallet return correlation without reading
    # the last 30d diagnostic.
    low_correlation = min(
        (x for x in all5 if x["train60_pnl_30bps_usd"] > 300),
        key=lambda x: (
            x["train60_mean_daily_net_pair_corr"],
            x["train60_max_daily_net_pair_corr"],
            -x["train60_score"],
            x["members"],
        ),
    )
    balanced = max(
        all5,
        key=lambda x: (
            x["train60_score"]
            - 500 * sum((v / x["market_fraction"]) ** 2 for v in x["market_mix"].values()),
            x["members"],
        ),
    )
    # Include multiple near-top preselected alternatives; do not choose
    # based on the reused final 30-day diagnostic.
    top_extension = sorted(m3extended, key=lambda x: (-x["train60_score"], x["members"]))[:5]
    top_all = sorted(all5, key=lambda x: (-x["train60_score"], x["members"]))[:10]
    labels = {
        "M5-M3-EXTENSION": best_extension,
        "M5-BROAD-SEARCH-BEST": best_all,
        "M5-LOW-CORRELATION": low_correlation,
        "M5-DEFENSIVE": defensive,
        "M5-RETURN-SEEKING": profitable,
        "M5-BALANCED-MAJORS": balanced,
    }
    selected: dict[tuple[str, ...], dict] = {}
    for name, item in labels.items():
        key = tuple(item["members"])
        selected.setdefault(key, {"members": item["members"], "roles": [], "selection": item})[
            "roles"
        ].append(name)
    for label, group in (("EXTENSION_TOP5", top_extension), ("BROAD_TOP10", top_all)):
        for rank, item in enumerate(group, 1):
            key = tuple(item["members"])
            selected.setdefault(key, {"members": item["members"], "roles": [], "selection": item})[
                "roles"
            ].append(f"{label}_R{rank}")
    for name, items in (("M3-BASELINE", BASELINE_M3), ("M5-PREVIOUS", PREVIOUS_M5)):
        key = tuple(items)
        selected.setdefault(key, {"members": list(items), "roles": [], "selection": None})[
            "roles"
        ].append(name)
    if len(selected) > MAX_FINALISTS:
        raise ValueError("UNBOUNDED_EXACT_MINUTE_FINALIST_COUNT")
    return dict(sorted(diagnostics.items())), list(selected.values()), top_all


def _combine(
    members: list[str], models: dict[str, dict], budget: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    per_pod = budget / len(members)
    pnl = np.zeros(N, dtype=np.float64)
    worst = np.zeros(N, dtype=np.float64)
    turnover = np.zeros(N, dtype=np.float64)
    for alias in members:
        model = models[alias]
        pnl += per_pod * model["pnl_delta_per_budget_usd"]
        worst += per_pod * model["worst_bar_delta_per_budget_usd"]
        turnover += per_pod * model["turnover_per_budget_usd"]
    return pnl, worst, turnover


def _daily_pnl(pnl: np.ndarray, turnover: np.ndarray, cost_bps: int) -> np.ndarray:
    return (pnl - turnover * cost_bps / 10_000).reshape(N_DAYS, 1440).sum(axis=1)


def _strict_halt_evidence(metrics: dict) -> dict:
    """Model does not execute a stop. Record when the reference first trips."""
    time = metrics["earliest_model_reference_breach_at_utc"]
    return {
        "loss_reference_breached": metrics["illustrative_prop_loss_reference_breached"],
        "first_breach_utc": time,
        "no_post_breach_profit_can_be_credited_as_prop_account_return": bool(time),
        "real_stop_execution_price": None,
    }


def evaluate(universe_path: Path, root: Path, market_root: Path, db: Path) -> dict:
    raw = universe_path.read_bytes()
    universe = json.loads(raw)
    present, denied, generation = registry_addresses(db)
    pool = eligible_wallets(universe, present, denied)
    if len(pool) != MAX_POOL:
        raise ValueError("NOT_VERIFIED_24_SOURCE_WALLET_POOL")
    source, source_audit = load_fills(root, universe, {x["alias"]: x for x in pool})
    bars, market_audit = verified_bars(market_root)
    unit = {
        alias: model_wallet(
            fills, bars, delay_minutes=5, source_mode="anchored_or_episode", batch_minutes=5
        )
        for alias, fills in sorted(source.items())
    }
    diagnostics, finalists, near_top = screen(pool, unit)
    # Risk simulations for preselected finalists, not cherry-picking on
    # the later block. Original alternatives remain as controls.
    primary_roles = {
        "M5-M3-EXTENSION",
        "M5-BROAD-SEARCH-BEST",
        "M5-LOW-CORRELATION",
        "M5-DEFENSIVE",
        "M3-BASELINE",
        "M5-PREVIOUS",
    }
    primary = [item for item in finalists if set(item["roles"]) & primary_roles]
    primary_aliases = sorted({a for item in primary for a in item["members"]})
    alternative_modes = {
        "signed_delta_5m_batch": {
            a: model_wallet(
                source[a], bars, delay_minutes=5, source_mode="signed_delta", batch_minutes=5
            )
            for a in primary_aliases
        },
        "csv_exact_duplicate_collapsed_5m_batch": {
            a: model_wallet(
                _remove_csv_exact_duplicates(source[a]),
                bars,
                delay_minutes=5,
                source_mode="anchored_or_episode",
                batch_minutes=5,
            )
            for a in primary_aliases
        },
        "ten_minute_delayed_five_minute_batch": {
            a: model_wallet(
                source[a],
                bars,
                delay_minutes=10,
                source_mode="anchored_or_episode",
                batch_minutes=5,
            )
            for a in primary_aliases
        },
    }
    analyses = []
    for finalist in finalists:
        by_budget = {}
        for budget in BUDGETS:
            p, w, t = _combine(finalist["members"], unit, budget)
            result = {str(bp): _metrics(p, w, t, cost_bps=bp) for bp in COSTS}
            by_budget[str(int(budget))] = result
        base_p, _, base_t = _combine(finalist["members"], unit, BUDGETS[0])
        day20 = _daily_pnl(base_p, base_t, 20)
        day30 = _daily_pnl(base_p, base_t, 30)
        alternative_checks = {}
        if set(finalist["roles"]) & primary_roles:
            for variant, models in alternative_modes.items():
                alternative_checks[variant] = {}
                for budget in BUDGETS:
                    alt_p, alt_w, alt_t = _combine(finalist["members"], models, budget)
                    alternative_checks[variant][str(int(budget))] = {
                        str(bps): _metrics(alt_p, alt_w, alt_t, cost_bps=bps) for bps in (20, 30)
                    }
        ordered = {
            **finalist,
            "position_and_delay_assumption_sensitivities": alternative_checks,
            "size": len(finalist["members"]),
            "total_wallets_in_source": len(pool),
            "cost20_5000": by_budget["5000"]["20"],
            "cost30_5000": by_budget["5000"]["30"],
            "budget6000_cost20": by_budget["6000"]["20"],
            "budget6000_cost30": by_budget["6000"]["30"],
            "train60_20bps_net_usd": round(float(day20[:60].sum()), 2),
            "reused_last30_20bps_net_usd": round(float(day20[60:].sum()), 2),
            "reused_last30_30bps_net_usd": round(float(day30[60:].sum()), 2),
            "source_risk_evidence": "MODELED_KNOWN_FOUR_MARKET_POSITION_CHANGES",
            "stop_reference_5000_20bps": _strict_halt_evidence(by_budget["5000"]["20"]),
            "strict_follower_equity_profit_verified": False,
            "qualified": False,
        }
        analyses.append(ordered)
    per_wallet = {}
    for alias, model in unit.items():
        pnl = model["pnl_delta_per_budget_usd"].reshape(N_DAYS, 1440).sum(axis=1)
        turnover = model["turnover_per_budget_usd"].reshape(N_DAYS, 1440).sum(axis=1)
        per_wallet[alias] = {
            "observed_source_four_coin_fills": len(source[alias]),
            "unit_train60_net20": round(float((pnl[:60] - turnover[:60] * 0.002).sum()), 6),
            "unit_train60_net30": round(float((pnl[:60] - turnover[:60] * 0.003).sum()), 6),
            "unit_last30_net20": round(float((pnl[60:] - turnover[60:] * 0.002).sum()), 6),
            "model_source_events_processed": model["audit"]["source_events_processed"],
            "max_unit_gross_price_drift_multiplier": model["audit"][
                "max_unit_gross_from_price_drift"
            ],
            "source_events_skipped_after_study_end": model["audit"][
                "unexecuted_tail_source_events"
            ],
            "opening_source_book_complete": False,
            "source_equity_known": False,
            "position_anchor_observation_type": (
                "RAW_STARTPOSITION_PARTIAL"
                if next(x for x in pool if x["alias"] == alias)["source"]
                in (
                    "wallet_fills_90d",
                    "broader_active_inventory_fills_90d",
                    "nansen_smart_money_fills_90d",
                )
                else "CSV_INFERRED_ZERO_START"
            ),
        }
    return {
        "schema": "phase7_major4_best5_exploratory_replay_v1",
        "experiment": "5-wallet M3-extension vs wider 158-registry and defensive variations",
        "source_universe_sha256": sha256(raw).hexdigest(),
        "source_generation": generation,
        "selected_universe_wallets": len(pool),
        "fixed_study_window": "2026-08-05_UTC_to_2026-11-03_UTC",
        "source_audit": source_audit,
        "market_audit": market_audit,
        "candidate_search": diagnostics,
        "screen_params": {
            "research_only": True,
            "first60_ranking_uses_sample_exploratory": True,
            "last30_is_reused_seen_diagnostic_not_true_holdout": True,
            "screen_loss_reference_only_daily_close": True,
            "last30_not_used_for_selection": True,
            "source_equity_faithful": False,
            "real_first_known_receipts": False,
            "costs_bps": list(COSTS),
            "budgets_usd": list(BUDGETS),
            "per_wallet_equal_gross_budget": True,
            "gross_at_rebalance_only_not_hard_continuous_cap": True,
            "per_wallet_candle_price_drift_can_raise_interim_gross": True,
            "five_minute_event_time_delay_and_five_minute_grid": True,
            "trailing_reference_usd": 850,
            "daily_reference_usd": 450,
            "event_time_vs_receipt_time_unverified": True,
            "no_actual_risk_stop_or_broker_execution": True,
            "full_wallet_positions_complete": False,
            "observed_markets_only": list(MAJORS),
        },
        "stage1_in_sample_top10": near_top,
        "per_wallet_diagnostics": per_wallet,
        "finalists": analyses,
        "selection_changed": False,
        "paper_worker_started": False,
        "trading_authorized": False,
        "scientifically_qualified": False,
    }


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("universe", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path("/home/quant/dev/copytrade-pm"))
    parser.add_argument(
        "--market-root", type=Path, default=Path("/home/quant/dev/quant/ml4t-data/.data/store")
    )
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("IMMUTABLE_EVIDENCE_EXISTS")
    result = evaluate(args.universe, args.source_root, args.market_root, args.db)
    data = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "sha256": sha256(data).hexdigest(),
                "source_wallets": result["selected_universe_wallets"],
                "search": result["candidate_search"],
                "finalists": len(result["finalists"]),
                "summary": [
                    {
                        "roles": x["roles"],
                        "members": x["members"],
                        "net20": x["cost20_5000"]["net_pnl_usd"],
                        "net30": x["cost30_5000"]["net_pnl_usd"],
                        "dd20": x["cost20_5000"]["max_drawdown_worst_bar_bound_usd"],
                        "breach": x["stop_reference_5000_20bps"]["loss_reference_breached"],
                        "diagnostic_last30": x["reused_last30_20bps_net_usd"],
                    }
                    for x in result["finalists"]
                ],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    cli()
