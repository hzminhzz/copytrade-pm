"""Phase 7: bounded, historical-oracle known-position-chain portfolio sensitivity.

Reuses Phase 7 native SHA-verified market days and fill-to-fill startPosition
intervals. DOES NOT reconstruct full account books, source equity, first-known
receipts, or executable follower PnL. Never downloads additional fills.
Normalizes each *observed* wallet book to a stated gross budget and uses
a conservative 5m/next-complete-minute observation delay, rather than
inventing source-equity leverage. Result is a CONDITIONAL MARKET MARK proxy.

Use all 328 previously defined V5 Stage 1 exploratory combinations. Preserve
all trial counts and the frozen E2/E6/P1 portfolio control identities.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np

from copytrade_pm.wallet_registry import DB, readonly_sqlite

if __package__:
    from scripts.phase7_candidate_screen import score_combo, select_pool
    from scripts.phase7_native_exposure import (
        ALIASES,
        END_MS,
        START_MS,
        consistent_intervals,
        native_marks_with_audit,
    )
    from scripts.phase7_shortlist_native_audit import raw_sources
else:
    from phase7_candidate_screen import score_combo, select_pool
    from phase7_native_exposure import (
        ALIASES,
        END_MS,
        START_MS,
        consistent_intervals,
        native_marks_with_audit,
    )
    from phase7_shortlist_native_audit import raw_sources

MINUTE_MS = 60_000
MINUTES = (END_MS - START_MS) // MINUTE_MS
DAYS = MINUTES // 1440
REBALANCE_MINUTES = 5
DEFAULT_DELAY_MINUTES = 5
INITIAL_CASH = 10_000.0
TOTAL_GROSS_BUDGET = 6_000.0  # not a $600 loss budget
FRICTIONS_BPS = (10, 20, 30)
MIN_NATIVE_COVERAGE = 0.95
MIN_COMPLETE_DAYS = 75
MAX_COINS = 120
MAX_POOL = 10
MAX_COMBINATIONS = 400


@dataclass
class WalletModel:
    alias: str
    unit_mark: np.ndarray
    unit_turnover: np.ndarray
    invalid: np.ndarray
    active: np.ndarray
    selected_coin_weights: dict[str, np.ndarray]
    source_coin_weights: dict[str, np.ndarray]
    source_sha256: str
    interval_count: int
    full_interval_leg_minutes: int
    priced_interval_leg_minutes: int
    eligible_fill_events: int
    missing_price_source_leg_minutes: int
    estimated_active_source_minutes: int

    @property
    def native_coverage(self) -> float:
        return (
            self.priced_interval_leg_minutes / self.full_interval_leg_minutes
            if self.full_interval_leg_minutes
            else 0.0
        )


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verified_pool(stage1: dict, universe: dict) -> list[dict]:
    if stage1.get("schema") != "phase7_first_stage_candidate_screen_v2":
        raise ValueError("UNVERIFIED_V5_STAGE1_SCHEMA")
    if stage1.get("n_combinations_evaluated") != {"3": 118, "5": 210}:
        raise ValueError("UNRECONCILED_FROZEN_STAGE1_TRIALS")
    candidates = [
        {
            **item,
            "alias": next(
                (
                    alias
                    for alias, address in ALIASES.items()
                    if address.lower() == item["address"].lower()
                ),
                item["alias"],
            ),
        }
        for item in universe["wallets"]
    ]
    pool = select_pool(candidates)
    if len(pool) != MAX_POOL or [x["alias"] for x in pool] != stage1["pool_aliases"]:
        raise ValueError("STAGE1_CANDIDATE_IDENTITY_CHANGED")
    if len({x["alias"] for x in pool}) != len(pool) or len(
        {x["address"].lower() for x in pool}
    ) != len(pool):
        raise ValueError("AMBIGUOUS_STAGE1_ALIAS_OR_ADDRESS")
    for row in pool:
        if row["alias"] in ALIASES and row["address"].lower() != ALIASES[row["alias"]].lower():
            raise ValueError("CONFLICTING_PRIVATE_FROZEN_ALIAS")
    return pool


def registry_source_identity(pool: list[dict]) -> dict:
    """Confirm V5 pool belongs to current research identity, not display-only labels."""
    with closing(readonly_sqlite(DB)) as database:
        generations = dict(database.execute("SELECT key,value FROM snapshot_meta"))
        present = {
            row[0]
            for row in database.execute(
                "SELECT DISTINCT lower(w.address) FROM cohort_memberships m "
                "JOIN wallets w ON m.wallet_id=w.wallet_id "
                "WHERE m.cohort_id IN ('research-108','nansen-20','hyperx-30')"
            )
        }
        excluded = {
            row[0]
            for row in database.execute(
                "SELECT DISTINCT lower(w.address) FROM exclusions e "
                "JOIN wallets w ON e.wallet_id=w.wallet_id"
            )
        }
    if len(present) != 158 or not all(x["address"].lower() in present for x in pool):
        raise ValueError("SCREEN_POOL_NOT_IN_CURRENT_RESEARCH_REGISTRY")
    if any(x["address"].lower() in excluded for x in pool):
        raise ValueError("EXCLUDED_OWNER_WALLET_IN_SCREEN")
    if not generations.get("manifest_sha256"):
        raise ValueError("NO_PINNED_REGISTRY_GENERATION")
    return {
        "registry_manifest_sha256": generations["manifest_sha256"],
        "registry_observed_at": generations.get("observed_at"),
        "registry_research_unique_count": len(present),
        "shortlist_pool_registry_membership": "ALL_EXACT_ADDRESS_MATCH",
    }


def candidates(pool: list[dict]) -> list[dict]:
    rows = []
    for size in (3, 5):
        for pick in combinations(pool, size):
            if Counter(x["top_coin"] for x in pick).most_common(1)[0][1] >= 3:
                continue
            model = score_combo(list(pick))
            rows.append(
                {
                    "members": model["members"],
                    "size": size,
                    "turnover_overlap": model["mean_pair_gross_fill_turnover_overlap"],
                    "top_turnover_coin_concentration": model[
                        "largest_aggregate_gross_fill_turnover_coin_fraction"
                    ],
                    "turnover_diversity_score": model["score_screen_only"],
                    "member_source_top_coins": {x["alias"]: x["top_coin"] for x in pick},
                    "member_observation_days": {x["alias"]: x["observation_days"] for x in pick},
                }
            )
    if len(rows) != 328:
        raise ValueError("V5_COMBINATION_COUNT_DRIFT")
    return rows


def _full_minute_slice(interval: dict) -> tuple[int, int]:
    """Only [whole minute, whole minute + 60s] entirely within source chain."""
    start = (int(interval["start_ms"]) + MINUTE_MS - 1) // MINUTE_MS
    end = int(interval["end_ms"]) // MINUTE_MS
    return max(0, start - START_MS // MINUTE_MS), min(MINUTES, end - START_MS // MINUTE_MS)


def _prepare_source(
    source: dict[str, dict], aliases: list[str], identities: dict[str, str]
) -> tuple[dict[str, dict], dict[str, dict[str, list[dict]]]]:
    meta = {}
    all_coins: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for alias in aliases:
        address = identities[alias].lower()
        blob = source.get(address)
        if blob is None:
            raise ValueError("MISSING_PRIVATE_FILL_SOURCE")
        intervals, counters = consistent_intervals(blob["payload"].get("fills", []))
        if not intervals:
            raise ValueError("NO_SOURCE_POSITION_CHAIN")
        meta[alias] = {"source_sha256": blob["sha256"], **counters}
        for interval in intervals:
            all_coins[interval["coin"]][alias].append(interval)
    if len(all_coins) > MAX_COINS:
        raise ValueError("UNBOUNDED_COIN_MARKET_SCOPE")
    return meta, all_coins


def _fetch_native_arrays(by_coin: dict[str, dict[str, list[dict]]]) -> dict[str, np.ndarray]:
    native = {}
    for coin, wallets in sorted(by_coin.items()):
        intervals = [x for group in wallets.values() for x in group]
        earliest = min(x["start_ms"] for x in intervals)
        latest = max(x["end_ms"] for x in intervals)
        lower = max(START_MS, (earliest // MINUTE_MS) * MINUTE_MS - 12 * MINUTE_MS)
        upper = min(END_MS, ((latest + MINUTE_MS - 1) // MINUTE_MS) * MINUTE_MS + 12 * MINUTE_MS)
        close = np.full(MINUTES, np.nan, dtype=np.float32)
        if lower < upper:
            bars, _ = native_marks_with_audit(coin, lower, upper)
            if bars is not None and not bars.is_empty():
                idx = ((bars["ms"].to_numpy() - START_MS) // MINUTE_MS).astype(np.int64)
                valid = (idx >= 0) & (idx < MINUTES)
                close[idx[valid]] = bars["close"].to_numpy()[valid].astype(np.float32)
        if np.any(np.isfinite(close) & (close <= 0)):
            raise ValueError("INVALID_VERIFIED_NATIVE_CLOSE")
        native[coin] = close
    return native


def _source_weights(
    alias: str, meta: dict, by_coin: dict[str, dict[str, list[dict]]], native: dict[str, np.ndarray]
) -> tuple[dict[str, np.ndarray], dict]:
    signed: dict[str, np.ndarray] = {}
    source_missing = np.zeros(MINUTES, dtype=np.bool_)
    gross = np.zeros(MINUTES, dtype=np.float64)
    expected, priced = 0, 0
    for coin, wallets in by_coin.items():
        segments = wallets.get(alias, [])
        if not segments:
            continue
        q = np.zeros(MINUTES, dtype=np.float32)
        for interval in segments:
            first, end = _full_minute_slice(interval)
            if first < end:
                if np.any(q[first:end] != 0):
                    raise ValueError("OVERLAPPING_SOURCE_POSITION_INTERVALS")
                q[first:end] = float(interval["qty"])
                expected += end - first
        close = native[coin]
        missing = (q != 0) & ~np.isfinite(close)
        source_missing |= missing
        priced += int(np.count_nonzero((q != 0) & np.isfinite(close)))
        value = np.where(np.isfinite(close), q * close, 0.0).astype(np.float32)
        if np.any(value != 0):
            signed[coin] = value
            gross += np.abs(value)
    if expected == 0:
        raise ValueError("NO_COMPLETE_MINUTE_SOURCE_POSITION_EVIDENCE")
    weights = {
        coin: np.divide(
            notion,
            gross,
            out=np.zeros(MINUTES, dtype=np.float32),
            where=gross > 0,
        )
        for coin, notion in signed.items()
    }
    return weights, {
        **meta,
        "all_reconstructed_source_chain_leg_minutes": expected,
        "sha_verified_native_chain_leg_minutes": priced,
        "source_market_missing_minute_leg_count": expected - priced,
        "observed_source_active_minute_count": int(np.count_nonzero(gross > 0)),
        "source_missing_any_coin": source_missing,
    }


def model_wallet(
    alias: str,
    weights: dict[str, np.ndarray],
    native: dict[str, np.ndarray],
    evidence: dict,
    *,
    delay: int = DEFAULT_DELAY_MINUTES,
) -> WalletModel:
    if not 0 <= delay <= 10:
        raise ValueError("INVALID_ORACLE_DELAY")
    # A source position at the end of minute s cannot be acted on until its
    # bar completes; the hypothetical follower then waits 5m and rebalances
    # at the next 5m boundary. This is NOT a measured first-known receipt.
    execution_index = np.arange(MINUTES)
    source_index = (execution_index // REBALANCE_MINUTES) * REBALANCE_MINUTES - delay - 1
    applicable = source_index >= 0
    indices = np.clip(source_index, 0, MINUTES - 1)
    invalid = applicable & evidence["source_missing_any_coin"][indices].copy()
    unit_mark = np.zeros(MINUTES, dtype=np.float64)
    unit_turn = np.zeros(MINUTES, dtype=np.float64)
    active = np.zeros(MINUTES, dtype=np.bool_)
    selected_coins = {}
    source_returns = {}
    for coin, w in sorted(weights.items()):
        shifted = np.where(applicable, w[indices], 0.0).astype(np.float32)
        active |= shifted != 0
        diff = np.empty(MINUTES, dtype=np.float32)
        diff[0] = shifted[0]
        diff[1:] = shifted[1:] - shifted[:-1]
        unit_turn += np.abs(diff)
        close = native[coin]
        market_return = np.full(MINUTES, np.nan, dtype=np.float64)
        okay = np.isfinite(close[:-1]) & np.isfinite(close[1:]) & (close[:-1] > 0) & (close[1:] > 0)
        market_return[:-1][okay] = (
            close[1:][okay].astype(np.float64) / close[:-1][okay].astype(np.float64) - 1
        )
        # Missing next-bar marks while a known leg is held are UNKNOWN;
        # do not silently count the return as zero.
        invalid |= (shifted != 0) & ~np.isfinite(market_return)
        unit_mark += np.where(
            np.isfinite(market_return), shifted * np.nan_to_num(market_return), 0.0
        )
        if coin in ("BTC", "ETH", "HYPE"):
            selected_coins[coin] = shifted
        source_returns[coin] = w
    return WalletModel(
        alias=alias,
        unit_mark=unit_mark,
        unit_turnover=unit_turn,
        invalid=invalid,
        active=active,
        selected_coin_weights=selected_coins,
        source_coin_weights=source_returns,
        source_sha256=evidence["source_sha256"],
        interval_count=evidence["supported_nonflat_intervals"],
        full_interval_leg_minutes=evidence["all_reconstructed_source_chain_leg_minutes"],
        priced_interval_leg_minutes=evidence["sha_verified_native_chain_leg_minutes"],
        eligible_fill_events=evidence["eligible_fills"],
        missing_price_source_leg_minutes=evidence["source_market_missing_minute_leg_count"],
        estimated_active_source_minutes=evidence["observed_source_active_minute_count"],
    )


def _max_drawdown(pnl_days: np.ndarray) -> float:
    equity = INITIAL_CASH + np.concatenate(([0], np.cumsum(pnl_days)))
    return float(np.max(np.maximum.accumulate(equity) - equity))


def _pairwise_same_coin_overlap(wallets: list[WalletModel]) -> tuple[float | None, float | None]:
    """Contemporaneous known-chain signed, common-coin gross fractions."""
    common, co_signed = 0.0, 0.0
    for a, b in combinations(wallets, 2):
        for coin in a.source_coin_weights.keys() & b.source_coin_weights.keys():
            x = a.source_coin_weights[coin]
            y = b.source_coin_weights[coin]
            scale = np.minimum(np.abs(x), np.abs(y))
            common += float(np.sum(scale))
            co_signed += float(np.sum(scale * (np.sign(x) == np.sign(y))))
    return (
        round(co_signed / common, 4) if common else None,
        round(common / max(1.0, MINUTES * math.comb(len(wallets), 2)), 4),
    )


def simulate(combo: dict, wallets: dict[str, WalletModel]) -> dict:
    members = combo["members"]
    selected = [wallets[alias] for alias in members]
    size = len(members)
    cash_per_wallet = TOTAL_GROSS_BUDGET / size
    valid = ~np.logical_or.reduce([w.invalid for w in selected])
    # If the final in-window minute carries a known position, the next
    # minute's mark is unavailable. Preserve its invalid flag and exclude
    # the affected final calendar day; never substitute a zero return.
    min_coverage = min(x.native_coverage for x in selected)
    modeled_gross_ret = cash_per_wallet * sum((w.unit_mark for w in selected))
    modeled_turnover = cash_per_wallet * sum((w.unit_turnover for w in selected))
    day_valid = valid.reshape(DAYS, 1440).all(axis=1)
    available_days = int(day_valid.sum())
    gross_by_day = modeled_gross_ret.reshape(DAYS, 1440).sum(axis=1)
    turnover_by_day = modeled_turnover.reshape(DAYS, 1440).sum(axis=1)
    gross_minutes_by_priced_day = modeled_gross_ret.reshape(DAYS, 1440)[day_valid]
    turnover_minutes_by_priced_day = modeled_turnover.reshape(DAYS, 1440)[day_valid]
    complete_gross = gross_by_day[day_valid]
    complete_turnover = turnover_by_day[day_valid]
    net = {basis: complete_gross - complete_turnover * basis / 10_000 for basis in FRICTIONS_BPS}
    shock = np.zeros(MINUTES, dtype=np.float64)
    for w in selected:
        shock -= cash_per_wallet * (
            0.1 * w.selected_coin_weights.get("BTC", 0.0)
            + 0.1 * w.selected_coin_weights.get("ETH", 0.0)
            + 0.2 * w.selected_coin_weights.get("HYPE", 0.0)
        )
    # Only matched, entirely observed book samples; stress is instantaneous
    # and not a historical event path or actual daily loss.
    max_stress = float(max(0.0, -np.min(shock[valid]))) if np.any(valid) else math.nan
    metrics = {}
    for bp, daily in net.items():
        pnl = float(daily.sum())
        dd = _max_drawdown(daily) if len(daily) else None
        worstday = float(daily.min()) if len(daily) else None
        minute_path = gross_minutes_by_priced_day - turnover_minutes_by_priced_day * bp / 10_000
        intraday_dd = _max_drawdown(minute_path.ravel()) if minute_path.size else None
        worst_intraday_from_day_start = (
            float(
                np.min(
                    np.minimum(
                        np.cumsum(minute_path, axis=1),
                        0.0,
                    )
                )
            )
            if minute_path.size
            else None
        )
        blocks = []
        calendar_daily = np.full(DAYS, np.nan, dtype=np.float64)
        calendar_daily[day_valid] = daily
        for block in range(3):
            chunk = calendar_daily[block * 30 : (block + 1) * 30]
            blocks.append(
                {
                    "block_index_in_sample": block + 1,
                    "priced_days": int(np.isfinite(chunk).sum()),
                    "net_on_priced_days_usd": round(float(np.nansum(chunk)), 2),
                }
            )
        metrics[str(bp)] = {
            "thirty_day_in_sample_blocks": blocks,
            "positive_in_sample_blocks": sum(x["net_on_priced_days_usd"] > 0 for x in blocks),
            "conditional_net_mark_pnl_usd": round(pnl, 2),
            "conditional_net_mark_pct_of_10k": round(pnl / INITIAL_CASH * 100, 2),
            "sample_only_max_equity_drawdown_usd": round(dd, 2) if dd is not None else None,
            "worst_completed_day_usd": round(worstday, 2) if worstday is not None else None,
            "sample_only_day_loss_exceeds_450": int(np.sum(daily < -450)),
            "sample_only_drawdown_exceeds_850": bool(dd > 850) if dd is not None else None,
            "minute_sample_only_max_drawdown_usd": round(intraday_dd, 2)
            if intraday_dd is not None
            else None,
            "worst_intraday_loss_from_day_start_usd": round(worst_intraday_from_day_start, 2)
            if worst_intraday_from_day_start is not None
            else None,
            "intraday_model_daily_loss_reference_exceeded": bool(
                worst_intraday_from_day_start < -450
            )
            if worst_intraday_from_day_start is not None
            else None,
            "intraday_model_trailing_reference_exceeded": bool(intraday_dd > 850)
            if intraday_dd is not None
            else None,
        }
    same_direction, common_overlap = _pairwise_same_coin_overlap(selected)
    # Explicit model-selection penalty in USD, not a statistical significance test.
    r = metrics["30"]
    dd = metrics["20"]["sample_only_max_equity_drawdown_usd"]
    daily = metrics["20"]["worst_completed_day_usd"]
    if dd is None or daily is None:
        score = None
    else:
        score = (
            r["conditional_net_mark_pnl_usd"]
            - dd
            - 2 * max(0.0, -daily - 450)
            - 3 * max(0, 90 - available_days) * 10
            - 0.25 * max_stress
        )
    risk20 = bool(
        metrics["20"]["sample_only_max_equity_drawdown_usd"] is not None
        and metrics["20"]["sample_only_max_equity_drawdown_usd"] <= 850
        and metrics["20"]["worst_completed_day_usd"] >= -450
    )
    risk30 = bool(
        metrics["30"]["sample_only_max_equity_drawdown_usd"] is not None
        and metrics["30"]["sample_only_max_equity_drawdown_usd"] <= 850
        and metrics["30"]["worst_completed_day_usd"] >= -450
    )
    return {
        **combo,
        "simulation_status": "PARTIAL_KNOWN_CHAIN_NORMALIZED_ORACLE_SENSITIVITY",
        "sample_only_loss_reference_pass_20bps": risk20,
        "sample_only_loss_reference_pass_30bps": risk30,
        "intraday_model_loss_reference_pass_20bps": bool(
            metrics["20"]["minute_sample_only_max_drawdown_usd"] is not None
            and metrics["20"]["minute_sample_only_max_drawdown_usd"] <= 850
            and metrics["20"]["worst_intraday_loss_from_day_start_usd"] >= -450
        ),
        "intraday_model_loss_reference_pass_30bps": bool(
            metrics["30"]["minute_sample_only_max_drawdown_usd"] is not None
            and metrics["30"]["minute_sample_only_max_drawdown_usd"] <= 850
            and metrics["30"]["worst_intraday_loss_from_day_start_usd"] >= -450
        ),
        "pod_normalized_gross_usd": round(cash_per_wallet, 2),
        "native_source_chain_coverage_min_fraction": round(min_coverage, 4),
        "complete_priced_days": available_days,
        "incomplete_priced_minutes": int(np.count_nonzero(~valid)),
        "modeled_5m_turnover_notional_usd_priced_days": round(float(complete_turnover.sum()), 2),
        "same_coin_observed_overlap_co_directional_fraction": same_direction,
        "same_coin_observed_overlap_weighted_proxy": common_overlap,
        "worst_instant_btc_eth_down10_hype_down20_usd": round(max_stress, 2),
        "scenario": metrics,
        "transparent_exploratory_score": round(score, 2) if score is not None else None,
        "financial_follower_pnl": None,
        "source_equity_series": None,
        "prospective_first_known": False,
        "scientific_qualification": False,
    }


def evaluate(stage1_path: Path, universe_path: Path, root: Path) -> dict:
    stage1 = json.loads(stage1_path.read_bytes())
    universe = json.loads(universe_path.read_bytes())
    pool = verified_pool(stage1, universe)
    registry = registry_source_identity(pool)
    combos = candidates(pool)
    requested = [x["alias"] for x in pool]
    identities = {x["alias"]: x["address"].lower() for x in pool}
    sources = raw_sources(root, set(identities.values()))
    meta, groups = _prepare_source(sources, requested, identities)
    native = _fetch_native_arrays(groups)
    probes = {}
    for alias in requested:
        weights, evidence = _source_weights(alias, meta[alias], groups, native)
        probes[alias] = model_wallet(alias, weights, native, evidence)
    evaluated = [simulate(combo, probes) for combo in combos]
    safe = [
        p
        for p in evaluated
        if p["native_source_chain_coverage_min_fraction"] >= MIN_NATIVE_COVERAGE
        and p["complete_priced_days"] >= MIN_COMPLETE_DAYS
        and p["transparent_exploratory_score"] is not None
    ]
    eligible_sorted = sorted(
        safe,
        key=lambda p: (
            -p["transparent_exploratory_score"],
            -p["scenario"]["30"]["conditional_net_mark_pnl_usd"],
            p["members"],
        ),
    )
    loss20_pass = [x for x in eligible_sorted if x["sample_only_loss_reference_pass_20bps"]]
    loss30_pass = [x for x in eligible_sorted if x["sample_only_loss_reference_pass_30bps"]]
    shortlist = []
    for size in (3, 5):
        shortlist.extend([x for x in loss20_pass if x["size"] == size][:5])
    if len(shortlist) < 10:
        raise ValueError("LESS_THAN_TEN_20BPS_DIAGNOSTIC_PASS_COMBOS")
    names = {tuple(p["members"]) for p in shortlist}
    return {
        "schema": "phase7_328_combo_known_chain_oracle_sensitivity_v3",
        "experiment_design": {
            "source_stage1_sha256": _hash(stage1_path),
            "source_universe_sha256": _hash(universe_path),
            "source_registry_identity": registry,
            "daily_close_only_loss_tests_not_prop_intraday_authorization": True,
            "source_window": "2026-08-05_UTC_to_2026-11-03_UTC_end_exclusive",
            "candidate_selection_retrospective": True,
            "total_prior_stage1_trials": 1875,
            "this_stage1_reused_combo_count": len(combos),
            "this_later_score_and_diagnostic_selection_is_in_sample": True,
            "research_only_loss_reference_daily_usd": 450,
            "research_only_loss_reference_trailing_usd": 850,
            "multiple_testing_not_independent_oos": True,
            "wallet_pool_count": len(pool),
            "wallet_pool_aliases": requested,
            "normalization": "EQUAL_KNOWN_SOURCE_GROSS_PER_WALLET_NO_SOURCE_EQUITY",
            "account_comparison_capital_usd": INITIAL_CASH,
            "total_known_gross_budget_usd": TOTAL_GROSS_BUDGET,
            "pod_known_gross_usd_3": TOTAL_GROSS_BUDGET / 3,
            "pod_known_gross_usd_5": TOTAL_GROSS_BUDGET / 5,
            "delay": "5m retrospective source position + next full minute and 5m rebalance grid",
            "native_marks": "EXACT_SHA_VERIFIED_HYPERLIQUID_1M_CLOSE",
            "cost_model": "WEIGHT_CHANGE_NOTIONAL_BPS_SCREEN_ONLY_NO_SPREAD_DEPTH_OR_IMPACT",
            "cost_scenarios_bps": list(FRICTIONS_BPS),
            "daily_drop_if_any_active_known_leg_unpriced": True,
            "strict_source_equity_fidelity": False,
            "follower_first_known_receipts": False,
            "complete_wallet_book": False,
            "unobserved_source_inventory_excluded_not_proven_flat": True,
            "missing_pricing_days_excluded_risk_understatement_possible": True,
            "actual_broker_executable_fills": False,
            "scientifically_qualified": False,
            "portfolio_freezes_changed": False,
        },
        "wallet_diagnostics": {
            alias: {
                "source_sha256": w.source_sha256,
                "eligible_fill_events": w.eligible_fill_events,
                "supported_nonflat_intervals": w.interval_count,
                "source_chain_leg_minutes": w.full_interval_leg_minutes,
                "native_matched_source_chain_leg_minutes": w.priced_interval_leg_minutes,
                "native_coverage_fraction": round(w.native_coverage, 4),
                "minutes_at_least_one_source_leg": w.estimated_active_source_minutes,
                "model_active_minutes": int(np.count_nonzero(w.active)),
                "model_unpriceable_minutes": int(np.count_nonzero(w.invalid)),
            }
            for alias, w in sorted(probes.items())
        },
        "combos_evaluated": len(evaluated),
        "combos_meeting_exploratory_minimum_native_and_day_coverage": len(safe),
        "model_loss_20bps_diagnostic_pass_count": len(loss20_pass),
        "model_loss_30bps_diagnostic_pass_count": len(loss30_pass),
        "intraday_model_loss_reference_pass_20bps_count": sum(
            x["intraday_model_loss_reference_pass_20bps"] for x in safe
        ),
        "intraday_model_loss_reference_pass_30bps_count": sum(
            x["intraday_model_loss_reference_pass_30bps"] for x in safe
        ),
        "model_loss_30bps_and_positive_net_count": sum(
            x["scenario"]["30"]["conditional_net_mark_pnl_usd"] > 0 for x in loss30_pass
        ),
        "shortlist_10": [
            {
                **p,
                "shortlist_marker": "TOP_5_PER_SIZE_AMONG_20BPS_LOSS_REFERENCE_PASS_NOT_AUTHORIZED",
            }
            for p in shortlist
        ],
        "full_combo_results": [
            {**p, "selected_shortlist_10": tuple(p["members"]) in names} for p in evaluated
        ],
        "previous_benchmarks": {
            "E2": "GEMINI_PHASE6A_P2_FLATTEN_HISTORICAL_MODEL_NOT_COMPARABLE",
            "E6": "GEMINI_PHASE6A_P2_FLATTEN_HISTORICAL_MODEL_NOT_COMPARABLE",
            "P1": "GEMINI_PHASE6A_P2_FLATTEN_HISTORICAL_MODEL_NOT_COMPARABLE",
        },
        "scientific_qualification": False,
        "trading_authorization": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage1_json", type=Path)
    p.add_argument("universe_json", type=Path)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError("IMMUTABLE_REPORT_ALREADY_EXISTS")
    result = evaluate(args.stage1_json, args.universe_json, args.source_root)
    data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(data)
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "combos_evaluated": result["combos_evaluated"],
                "eligible": result["combos_meeting_exploratory_minimum_native_and_day_coverage"],
                "risk20": result["model_loss_20bps_diagnostic_pass_count"],
                "risk30": result["model_loss_30bps_diagnostic_pass_count"],
                "risk30_and_positive": result["model_loss_30bps_and_positive_net_count"],
                "intraday20": result["intraday_model_loss_reference_pass_20bps_count"],
                "intraday30": result["intraday_model_loss_reference_pass_30bps_count"],
                "shortlist": [
                    {
                        "members": p["members"],
                        "size": p["size"],
                        "score": p["transparent_exploratory_score"],
                        "net30": p["scenario"]["30"]["conditional_net_mark_pnl_usd"],
                        "dd20": p["scenario"]["20"]["sample_only_max_equity_drawdown_usd"],
                        "priced_days": p["complete_priced_days"],
                    }
                    for p in result["shortlist_10"]
                ],
                "sha256": sha256(data.encode()).hexdigest(),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
