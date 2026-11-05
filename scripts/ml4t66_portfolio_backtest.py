"""Retrospective ML4T-66 *portfolio* cash/inventory/mark-to-market sensitivity.

This is a historical source-event oracle, NOT a faithful first-known follower
copy or an admissible contract-selector tape. Research-only and offline.
The explicitly counterfactual policy starts a NEW $10k follower flat, waits
for the first observed source fill whose startPosition is zero for each
wallet/coin, then copies net signed fill deltas. It NEVER invents source NAV,
opening book, missing native candles, funding or execution acknowledgements.

Native next-OPEN executions, 1m close MTM and same-bar low/high adverse stress.
An unpriceable order is NOT executed, and gaps while holding are UNKNOWN;
the resulting cash path is an omission counterfactual, not a true account.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import math
import os
from pathlib import Path

import numpy as np
import polars as pl

from copytrade_pm.pm_ml4t_batch_recovery import (
    MINUTE_MS,
    anchored_batches,
    local_sources,
    roster,
)
from copytrade_pm.pm_offline_manifest import ManifestBlocked
from copytrade_pm.pm_offline_market import _verified_day
from copytrade_pm.pm_offline_repository import native_instrument

START = datetime(2026, 8, 5, tzinfo=UTC)
END = datetime(2026, 11, 3, tzinfo=UTC)
DAYS = (END - START).days
MINUTES = DAYS * 1440
START_MS = int(START.timestamp() * 1000)
CONTRACTS = {
    "EXPLORER": {
        "members": ("M10", "M33", "M53"),
        "daily": 500.0,
        "trailing": 800.0,
        "eod_trailing": False,
        "targets": (1000.0, 500.0),
    },
    "SPRINT": {
        "members": ("M52", "M42", "M53"),
        "daily": 300.0,
        "trailing": 500.0,
        "eod_trailing": True,
        "targets": (800.0,),
    },
    "PRECOMPUTED_CONTROL": {
        "members": ("M52", "M56", "M10"),
        "daily": 300.0,
        "trailing": 500.0,
        "eod_trailing": True,
        "targets": (800.0,),
    },
}
SUPPLEMENT = Path(
    "/home/quant/.local/share/copytrade/reports/ml4t66-public-fills-g20261105-01/normalized"
)
ZERO = 1e-11


def source_zero_cut(rows: list[dict]) -> tuple[list[dict], dict]:
    """Only admit a coin after an observed zero pre-position on a source fill.

    Retrospective zero *per coin* still does not prove an atomic whole-wallet
    opening book. All earlier activity remains censored/unknown.
    """
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["alias"], row["coin"])].append(row)
    retained = []
    skipped = 0
    no_zero = []
    cut_times = {}
    for key, group in sorted(grouped.items()):
        zero_times = sorted(row["time"] for row in group if row["start_zero_observed"])
        if not zero_times:
            skipped += len(group)
            no_zero.append(key)
            continue
        cut = zero_times[0]
        cut_times["/".join(key)] = cut
        retained.extend(row for row in group if row["time"] >= cut)
        skipped += sum(row["time"] < cut for row in group)
    return retained, {
        "pre_zero_source_fills_skipped": skipped,
        "no_observed_flat_anchor_coins": ["/".join(x) for x in no_zero],
        "coin_first_zero_event_ms": cut_times,
        "start_policy": "FIRST_OBSERVED_SOURCE_PRE_POSITION_ZERO_PER_WALLET_COIN",
    }


def source_rows(stores: dict, identities: dict, members: set[str]) -> tuple[pl.DataFrame, dict]:
    rows = []
    attrs = {}
    for address, info in identities.items():
        alias = info["alias"]
        if alias not in members:
            continue
        record = stores[address]
        errors = set(record["errors"])
        if errors:
            raise ValueError(f"BLOCKED_SOURCE_ROW_CONFLICT:{alias}:{sorted(errors)}")
        equities = set(record["equity_values"])
        if len(equities) != 1 or Decimal(next(iter(equities))) <= 0:
            raise ValueError(f"BLOCKED_STATIC_SCALAR_EQUITY:{alias}")
        scalar_equity = Decimal(next(iter(equities)))
        attrs[alias] = {
            "static_equity_scalar": str(scalar_equity),
            "source_files_sha256": sorted(x["source_sha256"] for x in record["files"]),
        }
        for event in record["events"].values():
            ms = event["time"]
            if not START_MS <= ms < int(END.timestamp() * 1000):
                continue
            q = float(event["sz"])
            px = float(event["px"])
            if not (q > 0 and px > 0 and math.isfinite(q) and math.isfinite(px)):
                raise ValueError("INVALID_SOURCE_FILL")
            if event["side"] not in ("A", "B"):
                raise ValueError("INVALID_SOURCE_SIDE")
            pos = event.get("startPosition", event.get("start_position"))
            if pos is None:
                raise ValueError("MISSING_SOURCE_FILL_PRE_POSITION")
            p = Decimal(str(pos))
            rows.append(
                {
                    "alias": alias,
                    "coin": event["coin"],
                    "time": ms,
                    "size": q if event["side"] == "B" else -q,
                    "notional": q * px,
                    "start_zero_observed": p == 0,
                }
            )
    if not rows:
        raise ValueError("NO_SOURCE_EVENTS")
    selected, cut = source_zero_cut(rows)
    if not selected:
        raise ValueError("NO_SOURCE_FLAT_ANCHOR_EVENTS")
    return pl.DataFrame(selected).sort(["alias", "coin", "time"]), {
        **cut,
        "all_source_fill_rows": len(rows),
        "admitted_source_fill_rows": len(selected),
        "wallets": attrs,
    }


def load_native_panels(market_root: Path, coin_first_ms: dict[str, int]) -> tuple[dict, dict]:
    """Read SHA-verified complete native 1m days from first eligible order onward."""
    fields = ("open", "close", "low", "high")
    price = {}
    diagnostics = {}
    for coin, first_ms in sorted(coin_first_ms.items()):
        panels = {field: np.full(MINUTES, np.nan, np.float64) for field in fields}
        missing = Counter()
        valid_days = 0
        instrument = native_instrument(coin)
        first_day_index = max(0, (first_ms - START_MS) // 86_400_000)
        for day_index in range(first_day_index, DAYS):
            day = START + timedelta(days=day_index)
            try:
                frame, _, _ = _verified_day(market_root, instrument, day)
                if frame.height != 1440:
                    raise ManifestBlocked("NONCOMPLETE_NATIVE_DAY")
                ts = frame["timestamp"].dt.epoch("ms").to_numpy()
                expected = (
                    START_MS + np.arange(day_index * 1440, (day_index + 1) * 1440) * MINUTE_MS
                )
                if not np.array_equal(ts, expected):
                    raise ManifestBlocked("BAD_NATIVE_FULL_DAY_GRID")
                for field in fields:
                    panels[field][day_index * 1440 : (day_index + 1) * 1440] = (
                        frame[field].to_numpy().astype(np.float64)
                    )
                valid_days += 1
            except (ManifestBlocked, OSError, ValueError, TypeError) as exc:
                missing[str(getattr(exc, "code", type(exc).__name__))] += 1
        price[coin] = panels
        diagnostics[coin] = {
            "verified_complete_native_days": valid_days,
            "days_requested": DAYS - first_day_index,
            "missing_days_by_reason": dict(sorted(missing.items())),
            "native_instrument": instrument,
        }
    return price, diagnostics


def simulate_inventory(
    batches: pl.DataFrame,
    members: tuple[str, ...],
    attr: dict,
    prices: dict,
    *,
    cost_bps: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Cash + signed inventory marked at observed 1m closes.

    Each pod uses fixed static equity reference k. No intrapod/internetted
    venue offset; assumes each pod pays its own costs (conservative).
    """
    if cost_bps < 0:
        raise ValueError("NEGATIVE_COST")
    all_pnl = np.zeros(MINUTES, np.float64)
    all_adverse = np.zeros(MINUTES, np.float64)
    gross = np.zeros(MINUTES, np.float64)
    bad = np.zeros(MINUTES, np.bool_)
    member_report = {}
    error_count = Counter()
    skipped_by_coin = Counter()
    missed_order = np.zeros(MINUTES, np.bool_)
    first_skipped_order = None
    held_at_end = []
    for member in members:
        per_coin_events = batches.filter(pl.col("alias") == member).partition_by(
            ["coin"], as_dict=True
        )
        equity = Decimal(attr[member]["static_equity_scalar"])
        k = float(
            (Decimal(1) / Decimal(len(members))) * min(Decimal(".35"), Decimal(10000) / equity)
        )
        pod_cash = np.zeros(MINUTES, np.float64)
        pod_value = np.zeros(MINUTES, np.float64)
        pod_adverse = np.zeros(MINUTES, np.float64)
        pod_bad = np.zeros(MINUTES, np.bool_)
        costs = 0.0
        traded = 0.0
        fills = 0
        for key, order_group in per_coin_events.items():
            coin = key[0] if isinstance(key, tuple) else key
            panel = prices[coin]
            changes = np.zeros(MINUTES, np.float64)
            for order in order_group.iter_rows(named=True):
                index = (order["execute_ms"] - START_MS) // MINUTE_MS
                if not 0 <= index < MINUTES:
                    error_count["OUTSIDE_STUDY_WINDOW"] += 1
                    continue
                op = panel["open"][index]
                if not np.isfinite(op):
                    error_count["MISSING_NATIVE_EXECUTION_BAR"] += 1
                    skipped_by_coin[coin] += 1
                    missed_order[index] = True
                    first_skipped_order = (
                        min(first_skipped_order, index)
                        if first_skipped_order is not None
                        else index
                    )
                    continue
                delta = order["net_qty"] * k
                nominal = abs(delta * op)
                if nominal < 10.0:
                    error_count["BELOW_MIN_ORDER_NOTIONAL"] += 1
                    continue
                changes[index] += delta
                slip = 0.0001 * (cost_bps - 3.5)
                fee = nominal * 3.5 / 10000.0
                px = op * (1 + np.sign(delta) * slip)
                pod_cash[index] -= delta * px + fee
                costs += nominal * cost_bps / 10000.0
                traded += nominal
                fills += 1
            q = np.cumsum(changes)
            value_available = np.isfinite(panel["close"])
            unpriced = (np.abs(q) > ZERO) & ~value_available
            bad |= unpriced
            pod_bad |= unpriced
            close = np.where(value_available, panel["close"], 0.0)
            low = np.where(np.isfinite(panel["low"]), panel["low"], 0.0)
            high = np.where(np.isfinite(panel["high"]), panel["high"], 0.0)
            pod_value += q * close
            pod_adverse += q * np.where(q >= 0, low, high)
            gross += np.abs(q * close)
            if abs(q[-1]) > ZERO:
                held_at_end.append(
                    {"alias": member, "coin": coin, "quantity": round(float(q[-1]), 8)}
                )
        pnl = np.cumsum(pod_cash) + pod_value
        adverse = np.cumsum(pod_cash) + pod_adverse
        all_pnl += pnl
        all_adverse += adverse
        member_report[member] = {
            "static_k_eff": round(k, 8),
            "scenario_trades_executed": fills,
            "scenario_turnover_usd": round(traded, 2),
            "scenario_fixed_fee_plus_slippage_usd": round(costs, 2),
            "scenario_terminal_pnl_usd": round(float(pnl[-1]), 2) if not pod_bad[-1] else None,
            "pod_unpriced_active_minutes": int(pod_bad.sum()),
        }
    pnl_equity = 10000 + all_pnl
    adverse_equity = 10000 + all_adverse
    # A missing mark while a nonflat synthetic position exists makes the
    # actual equity/stop unknown, not zero or carried forward.
    pnl_equity[bad] = np.nan
    adverse_equity[bad] = np.nan
    gross[bad] = np.nan
    failure = bad | missed_order
    first_failure = int(np.flatnonzero(failure)[0]) if failure.any() else None
    diagnostics = {
        "pod_results": member_report,
        "missing_execution_first_at": _iso_minute(first_skipped_order)
        if first_skipped_order is not None
        else None,
        "first_follower_path_unknown_at": _iso_minute(first_failure)
        if first_failure is not None
        else None,
        "first_follower_path_unknown_reason": (
            "UNPRICED_ACTIVE_POSITION" if bad[first_failure] else "MISSING_EXECUTION_BAR"
        )
        if first_failure is not None
        else None,
        "order_failures": dict(error_count),
        "missing_executions_by_coin": dict(skipped_by_coin),
        "unpriced_active_minutes": int(bad.sum()),
        "unpriced_active_calendar_days": int(bad.reshape(DAYS, 1440).any(axis=1).sum()),
        "unknown_first_active_minute": datetime.fromtimestamp(
            (START_MS + int(np.argmax(bad)) * MINUTE_MS) / 1000, tz=UTC
        ).isoformat()
        if bad.any()
        else None,
        "terminal_open_inventory": held_at_end,
        "gross_notional_peak_on_priced_minutes_usd": (
            round(float(np.nanmax(gross)), 2) if np.isfinite(gross).any() else None
        ),
        "gross_leverage_peak_vs_initial_10k": (
            round(float(np.nanmax(gross)) / 10000, 3) if np.isfinite(gross).any() else None
        ),
        "costs_include_funding_impact_l2": False,
        "failure_index_or_none": first_failure,
        "source_equity_asof_verified": False,
        "source_first_known_receipts_verified": False,
    }
    return pnl_equity, adverse_equity, gross, bad, diagnostics


def metrics(equity: np.ndarray, bad: np.ndarray) -> dict:
    """Descriptive observed-mark metrics, NOT qualified drawdown bounds."""
    seen = np.isfinite(equity)
    if not np.any(seen):
        return {"status": "NO_MARKED_EQUITY"}
    vals = equity[seen]
    hwm = np.maximum.accumulate(np.r_[10000.0, vals])
    dd = hwm[1:] - vals
    worst_index = int(np.argmax(dd))
    worst_peak = float(hwm[worst_index + 1])
    safe_days = ~bad.reshape(DAYS, 1440).any(axis=1)
    eod = equity.reshape(DAYS, 1440)[:, -1]
    all_day = np.r_[10000.0, eod]
    available = np.isfinite(all_day[:-1]) & np.isfinite(all_day[1:]) & safe_days
    daily = np.diff(all_day)[available]
    sharpe = (
        float(np.mean(daily) / np.std(daily, ddof=1) * np.sqrt(365))
        if len(daily) >= 10 and np.std(daily, ddof=1) > 0
        else None
    )
    p95 = np.percentile(daily, 5) if len(daily) >= 10 else None
    tail = daily[daily <= p95] if p95 is not None else np.empty(0)
    return {
        "status": "PARTIAL_PIT_HISTORICAL_ORACLE_SCENARIO"
        if bad.any()
        else "HISTORICAL_EVENT_ORACLE_ONLY",
        "net_pnl_terminal_usd": round(float(equity[-1] - 10000), 2)
        if np.isfinite(equity[-1])
        else None,
        "terminal_return_pct": round(float((equity[-1] - 10000) / 100), 2)
        if np.isfinite(equity[-1])
        else None,
        "peak_equity_usd_on_marked_minutes": round(float(np.max(vals)), 2),
        "observed_only_max_drawdown_usd_lower_bound": round(float(max(dd.max(), 0.0)), 2),
        # The legacy 10k-normalized amount is NOT conventional percent max DD.
        "observed_only_max_drawdown_pct_initial_10k": round(float(max(dd.max(), 0.0)) / 100, 2),
        "observed_only_max_drawdown_pct_prior_peak": round(
            float(max(dd.max(), 0.0)) / worst_peak * 100, 2
        ),
        "observed_min_equity_usd": round(float(vals.min()), 2),
        "whole_safe_calendar_days": int(safe_days.sum()),
        "completely_priced_daily_changes": int(len(daily)),
        "positive_complete_days": int((daily > 0).sum()),
        "worst_complete_day_usd": round(float(daily.min()), 2) if len(daily) else None,
        "best_complete_day_usd": round(float(daily.max()), 2) if len(daily) else None,
        "daily_sharpe_descriptive": round(sharpe, 3) if sharpe is not None else None,
        "daily_cvar_95_usd": round(float(tail.mean()), 2) if len(tail) else None,
        "unpriced_time_makes_dd_and_pass_unverifiable": bool(bad.any()),
    }


def _iso_minute(index: int) -> str:
    return (START + timedelta(minutes=index)).isoformat()


def challenge_first_passage(
    equity: np.ndarray, bad: np.ndarray, rule: dict, *, conservative_extremes: bool = False
) -> dict:
    """First-passage against owner-supplied challenge barrier assumptions.

    Incomplete active markets terminate evidence at first gap; report the
    observed prefix outcome. Actual evaluation stage reset requires flat
    positions and a new account -- continuing the path is hypothetical.
    """
    target = rule["targets"]
    phase = 0
    orig = 0.0
    peak = 10000.0
    eod_peak = 10000.0
    day_base = 10000.0
    previous = 10000.0
    green = 0
    start_target_at = None
    for i, val in enumerate(equity):
        if bad[i] or not np.isfinite(val):
            return {
                "status": "BLOCKED_BY_FIRST_UNKNOWN_EXECUTION_OR_MARK",
                "first_unpriced_at": _iso_minute(i),
                "stage_at_block": phase + 1,
                "completed_green_days_prefix": green,
                "phase1_target_seen_at": start_target_at,
                "challenge_pass": None,
            }
        stage_value = 10000.0 + val - 10000.0 - orig
        if i % 1440 == 0:
            day_base = previous
        if not rule["eod_trailing"]:
            peak = max(peak, stage_value)
        floor = max(
            day_base - rule["daily"],
            (eod_peak if rule["eod_trailing"] else peak) - rule["trailing"],
        )
        if stage_value <= floor:
            return {
                "status": "MODELED_BREACH_BEFORE_ANY_MARK_GAP",
                "at": _iso_minute(i),
                "stage": phase + 1,
                "breach_floor_usd": round(floor, 2),
                "stage_equity_usd": round(stage_value, 2),
                "challenge_pass": False,
                "model_intrabar_adverse_joint_extremes": conservative_extremes,
            }
        if stage_value >= 10000.0 + target[phase]:
            if phase == len(target) - 1:
                return {
                    "status": "MODELED_TARGET_BEFORE_ANY_MARK_GAP",
                    "at": _iso_minute(i),
                    "stage": phase + 1,
                    "green_days_before_target": green,
                    "challenge_pass": True,
                    "model_intrabar_adverse_joint_extremes": conservative_extremes,
                    "conditional_on_stage_reset_without_liquidating_positions": len(target) > 1,
                }
            if phase == 0:
                start_target_at = _iso_minute(i)
            phase += 1
            orig = val - 10000.0
            peak = eod_peak = day_base = previous = 10000.0
        if i % 1440 == 1439:
            if stage_value > day_base:
                green += 1
            if rule["eod_trailing"]:
                eod_peak = max(eod_peak, stage_value)
        previous = stage_value
    return {
        "status": "OPEN_AT_STUDY_END_NO_BREACH",
        "stage": phase + 1,
        "challenge_pass": False,
        "green_days": green,
    }


def evaluate(
    db: Path,
    source_root: Path,
    market_root: Path,
    *,
    scenarios: tuple[str, ...],
    delays: tuple[int, ...],
    costs: tuple[float, ...],
) -> dict:
    identities, cohort_sha = roster(db)
    stores, provenance = local_sources(source_root, identities, extra_source_dirs=(SUPPLEMENT,))
    members = set().union(*(CONTRACTS[x]["members"] for x in scenarios))
    df, source = source_rows(stores, identities, members)
    batches = {d: anchored_batches(df, d) for d in delays}
    coin_first = {}
    for x in batches.values():
        for rec in x.iter_rows(named=True):
            coin_first[rec["coin"]] = min(
                coin_first.get(rec["coin"], rec["execute_ms"]), rec["execute_ms"]
            )
    panels, coverage = load_native_panels(market_root, coin_first)
    runs = []
    for name in scenarios:
        rule = CONTRACTS[name]
        for delay in delays:
            selected = batches[delay].filter(pl.col("alias").is_in(rule["members"]))
            for cost in costs:
                equity, adverse, gross, bad, detail = simulate_inventory(
                    selected, rule["members"], source["wallets"], panels, cost_bps=cost
                )
                performance = metrics(equity, bad)
                failure = detail["failure_index_or_none"]
                path_bad = bad.copy()
                if failure is not None:
                    path_bad[failure] = True
                    prefix = equity[:failure]
                else:
                    prefix = equity
                performance["unbroken_complete_path_minutes"] = len(prefix)
                performance["unbroken_prefix_end_exclusive"] = _iso_minute(len(prefix))
                performance["unbroken_prefix_net_pnl_usd"] = (
                    round(float(prefix[-1] - 10000), 2)
                    if len(prefix) and np.isfinite(prefix[-1])
                    else None
                )
                if len(prefix):
                    prefix_peak = np.maximum.accumulate(np.r_[10000.0, prefix])
                    performance["unbroken_prefix_max_dd_usd"] = round(
                        float(np.max(prefix_peak[1:] - prefix)), 2
                    )
                else:
                    performance["unbroken_prefix_max_dd_usd"] = None
                performance["challenge_first_passage_close"] = challenge_first_passage(
                    equity, path_bad, rule
                )
                performance["conservative_worst_bar_extremes_observed_prefix"] = (
                    challenge_first_passage(adverse, path_bad, rule, conservative_extremes=True)
                )
                # Retain later path as a diagnostic *conditional on skipping*
                # missing execution, never an actual challenge verdict.
                performance["conditional_skipped_orders_first_passage"] = (
                    challenge_first_passage(equity, bad, rule)
                    if detail["missing_execution_first_at"]
                    else None
                )
                performance["leg_count_with_position_at_end"] = len(
                    detail["terminal_open_inventory"]
                )
                detail.pop("failure_index_or_none")
                runs.append(
                    {
                        "portfolio": name,
                        "members": list(rule["members"]),
                        "delay_minutes": delay,
                        "total_combined_cost_bps_per_executed_side": cost,
                        "performance": performance,
                        "execution_and_coverage": detail,
                    }
                )
    return {
        "schema": "ml4t66_portfolio_flat_start_historical_oracle_v1",
        "study_start_utc": START.isoformat(),
        "study_end_exclusive_utc": END.isoformat(),
        "starting_account_usd": 10000,
        "cohort": "ml4t-strict-66",
        "cohort_source_sha256": cohort_sha,
        "source": source,
        "provenance": provenance,
        "market": coverage,
        "assumptions": {
            "source_clock": "RETROSPECTIVE_EVENT_TIME_NOT_FIRST_LOCAL_RECEIPT",
            "source_positions": "START_FLAT_PER_FOLLOWER_COIN_AFTER_OBSERVED_FIRST_ZERO_PRE_POSITION",
            "source_equity": "UNTIMESTAMPED_VENDOR_SCALAR_FOR_STATIC_K_NOT_POINT_IN_TIME",
            "k_formula": "(1/n) * min(0.35, 10000/leader_equity_scalar)",
            "batch_policy": "FIRST_EVENT_PLUS_1_2_5_MINUTE_NONRESETTING_WINDOW_NEXT_FULL_MINUTE_OPEN",
            "accounting": "SYNTHETIC_POD_CASH_AND_SIGNED_INVENTORY_FROM_EXECUTED_DELTA",
            "costs": "3.5bps_taker_PLUS_(totalbps-3.5)bps_adverse_price_slippage_each_executed_side",
            "missing_execution": "SKIP_WITH_EXPLICIT_OMISSION_COUNT_AS_COUNTERFACTUAL",
            "missing_active_market": "UNKNOWN_NOT_MARKED_AND_STOPS_CERTIFICATION",
            "intrabar": "JOINT_ASSET_HIGH_LOW_ADVERSE_BOUND_NOT_ACTUAL_SYNCHRONIZED_PATH",
            "source_funding": "UNKNOWN_EXCLUDED_SCENARIO_ZERO",
            "intraday_spread_depth_partial_fill": "UNKNOWN",
            "forced_terminal_liquidation": False,
            "source_last_fill_flat_assertion": False,
            "per_pod_loss_budget_enforced": False,
            "pretrade_gross_leverage_cap_enforced": False,
            "contract_kill_switch_enforced_on_positions": False,
            "continues_trading_after_modeled_contract_breach_for_diagnostics": True,
            "contract_payout_EV": None,
            "portfolio_selected_using_same_retrospective_window": True,
        },
        "results": runs,
        "scientifically_qualified": False,
        "actual_executable_follower_pnl": False,
        "trading_authorized": False,
    }


def save_private(root: Path, report: dict) -> tuple[Path, str]:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    digest = sha256(raw).hexdigest()
    target = root / f"ml4t66_portfolio_backtest_{digest[:20]}.json"
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("NONIDENTICAL_IMMUTABLE_REPORT_HASH")
    else:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    return target, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--scenarios", nargs="+", choices=tuple(CONTRACTS), default=list(CONTRACTS))
    parser.add_argument("--delays", nargs="+", type=int, choices=(1, 2, 5), default=[1, 2, 5])
    parser.add_argument("--costs", nargs="+", type=float, default=[6.0, 12.0, 18.0])
    args = parser.parse_args()
    if min(args.costs) < 3.5:
        parser.error("combined costs must include >=3.5bps commission")
    report = evaluate(
        args.db,
        args.source_root,
        args.market_root,
        scenarios=tuple(args.scenarios),
        delays=tuple(args.delays),
        costs=tuple(args.costs),
    )
    path, digest = save_private(args.output_root, report)
    print(
        json.dumps(
            {
                "status": "RESEARCH_ONLY_HINDSIGHT_PARTIAL_FOLLOWER_MTM",
                "report": str(path),
                "sha256": digest,
                "results": [
                    {
                        "portfolio": row["portfolio"],
                        "delay": row["delay_minutes"],
                        "cost": row["total_combined_cost_bps_per_executed_side"],
                        "net_pnl": row["performance"]["net_pnl_terminal_usd"],
                        "max_observed_dd_lower_bound": row["performance"][
                            "observed_only_max_drawdown_usd_lower_bound"
                        ],
                        "bad_days": row["execution_and_coverage"]["unpriced_active_calendar_days"],
                        "first_pass": row["performance"]["challenge_first_passage_close"]["status"],
                        "orders": sum(
                            x["scenario_trades_executed"]
                            for x in row["execution_and_coverage"]["pod_results"].values()
                        ),
                    }
                    for row in report["results"]
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
