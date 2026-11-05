"""Historical-oracle **protected** 3-pod $10k copytrade portfolio sensitivity.

This research-only bridge uses the *same* PM-04 pod stop semantics:
- pod net executed and marked PnL against own running profit peak
- max_drawdown=200 USD (2% of the account) => irreversible SUSPENDED latch
- freeze source signal immediately; request full pod book flatten next minute OPEN
- retained position until actual modeled exit; exiting costs and gaps charged
- independent pods continue unless central account challenge floor breached
This is not a PM-03/PM-04 execution adapter and has no live account/broker route.
It does NOT establish point-in-time source equity, receipts or official pass odds.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

import numpy as np
import polars as pl

if __package__:
    from . import ml4t66_portfolio_backtest as base
else:
    import ml4t66_portfolio_backtest as base

START_USD = 10_000.0
DEFAULT_POD_DD_USD = 200.0
EPSILON = 1e-9


@dataclass
class Pod:
    alias: str
    k: float
    cash: float = 0.0
    holdings: dict[str, float] = field(default_factory=dict)
    high_water_pnl: float = 0.0
    day_start_pnl: float = 0.0
    current_pnl: float = 0.0
    state: str = "ACTIVE"
    reason: str | None = None
    triggered_at: int | None = None
    exit_complete_at: int | None = None
    pnl_when_triggered: float | None = None
    pnl_when_flat: float | None = None
    exit_attempts: int = 0
    fills: int = 0
    fees_slip_usd: float = 0.0
    skipped_after_stop: int = 0


def pnl_at(pod: Pod, panels: dict, index: int, *, field: str = "close") -> float:
    value = pod.cash
    for coin, qty in pod.holdings.items():
        if abs(qty) <= EPSILON:
            continue
        px = panels[coin][field][index]
        if not np.isfinite(px) or px <= 0:
            raise ValueError(f"UNPRICED_ACTIVE_POSITION:{pod.alias}:{coin}")
        value += qty * float(px)
    return value


def mark_pnl(pod: Pod, panels: dict, index: int, mark_mode: str) -> float:
    if mark_mode == "close":
        return pnl_at(pod, panels, index, field="close")
    if mark_mode != "adverse":
        raise ValueError("INVALID_MARK_MODE")
    value = pod.cash
    for coin, qty in pod.holdings.items():
        if abs(qty) <= EPSILON:
            continue
        # Worst-low/high simultaneously is an intentionally conservative
        # 1-minute OHLC bound, not an observed synchronously tradable mark.
        field = "low" if qty > 0 else "high"
        px = panels[coin][field][index]
        if not np.isfinite(px) or px <= 0:
            raise ValueError(f"UNPRICED_ACTIVE_POSITION:{pod.alias}:{coin}")
        value += qty * float(px)
    return value


def execute(
    pod: Pod,
    coin: str,
    delta: float,
    open_px: float,
    *,
    cost_bps: float,
) -> None:
    if not np.isfinite(open_px) or open_px <= 0:
        raise ValueError("UNPRICED_EXECUTION_OPEN")
    if cost_bps < 3.5:
        raise ValueError("INVALID_COST")
    notional = abs(delta * open_px)
    slippage = (cost_bps - 3.5) / 10000
    fill_px = open_px * (1 + np.sign(delta) * slippage)
    fee = notional * 3.5 / 10000
    pod.cash -= delta * fill_px + fee
    pod.holdings[coin] = pod.holdings.get(coin, 0.0) + delta
    if abs(pod.holdings[coin]) < EPSILON:
        pod.holdings.pop(coin, None)
    pod.fills += 1
    pod.fees_slip_usd += notional * cost_bps / 10000


def portfolio_equity(pods: dict[str, Pod]) -> float:
    return START_USD + sum(p.current_pnl for p in pods.values())


def stop_if_needed(
    pod: Pod,
    index: int,
    *,
    budget_usd: float,
    daily_usd: float | None,
) -> bool:
    if pod.state != "ACTIVE":
        return False
    # Do not replenish a spent budget on recovery or day reset.
    pod.high_water_pnl = max(pod.high_water_pnl, pod.current_pnl)
    dd = pod.high_water_pnl - pod.current_pnl
    daily = pod.day_start_pnl - pod.current_pnl
    if dd + EPSILON >= budget_usd or (daily_usd is not None and daily + EPSILON >= daily_usd):
        pod.state = "SUSPENDED_PENDING_EXIT" if pod.holdings else "SUSPENDED_FLAT"
        pod.reason = "POD_TRAILING_DD" if dd + EPSILON >= budget_usd else "POD_DAILY_LOSS"
        pod.triggered_at = index
        pod.pnl_when_triggered = pod.current_pnl
        if not pod.holdings:
            pod.exit_complete_at = index
            pod.pnl_when_flat = pod.current_pnl
        return True
    return False


def order_index(batches: pl.DataFrame) -> dict[int, list[tuple[str, str, float]]]:
    result: dict[int, list[tuple[str, str, float]]] = {}
    for rec in batches.iter_rows(named=True):
        at = (rec["execute_ms"] - base.START_MS) // base.MINUTE_MS
        if 0 <= at < base.MINUTES:
            result.setdefault(at, []).append((rec["alias"], rec["coin"], float(rec["net_qty"])))
    return result


def protected(
    batches: pl.DataFrame,
    members: tuple[str, ...],
    attr: dict,
    panels: dict,
    *,
    cost_bps: float = 6.0,
    budget_usd: float = DEFAULT_POD_DD_USD,
    pod_daily_limit: float | None = None,
    pod_budgets_usd: dict[str, float] | None = None,
    pod_daily_limits_usd: dict[str, float] | None = None,
    mark_mode: str = "close",
    contract_rule: dict | None = None,
) -> dict:
    """Run chronological cash/position replay. Do NOT clamp a prior PnL path."""
    if budget_usd <= 0 or (pod_daily_limit is not None and pod_daily_limit <= 0):
        raise ValueError("INVALID_POD_STOP_BUDGET")
    if cost_bps < 3.5 or mark_mode not in ("close", "adverse"):
        raise ValueError("INVALID_COST_OR_MARKING")
    for policy in (pod_budgets_usd, pod_daily_limits_usd):
        if policy is not None and (
            set(policy) != set(members)
            or any(not np.isfinite(value) or value <= 0 for value in policy.values())
        ):
            raise ValueError("INVALID_PER_POD_BUDGETS")
    pods = {}
    for member in members:
        scalar = Decimal(attr[member]["static_equity_scalar"])
        k = float(
            Decimal(1) / Decimal(len(members)) * min(Decimal("0.35"), Decimal("10000") / scalar)
        )
        pods[member] = Pod(alias=member, k=k)
    by_minute = order_index(batches.filter(pl.col("alias").is_in(members)))
    instrument_orders = Counter()
    blocked_orders = Counter()
    stops = []
    timeline = []
    global_peak = START_USD
    eod_peak = START_USD
    previous_equity = START_USD
    day_base = START_USD
    day_peak = START_USD
    green_days = 0
    account_reason = None
    account_at = None
    unknown = None
    global_halt = False
    target_at = None
    portfolio_marked_peak = START_USD
    max_dd = 0.0
    max_dd_ratio = 0.0
    peak_gross = 0.0
    last_equity = START_USD
    last_valid = -1
    for i in range(base.MINUTES):
        if i % 1440 == 0:
            day_base = previous_equity
            day_peak = day_base
            for pod in pods.values():
                pod.day_start_pnl = pod.current_pnl

        # Open: exit orders requested at the previous minute close take
        # precedence over all source risk-increasing orders. Never reopen.
        for pod in pods.values():
            if pod.state != "SUSPENDED_PENDING_EXIT" and not (global_halt and pod.holdings):
                continue
            coins = sorted(pod.holdings)
            for coin in coins:
                qty = pod.holdings.get(coin, 0.0)
                if abs(qty) <= EPSILON:
                    pod.holdings.pop(coin, None)
                    continue
                px = panels[coin]["open"][i]
                if not np.isfinite(px) or px <= 0:
                    unknown = {
                        "at": base._iso_minute(i),
                        "reason": "UNPRICED_POD_FORCED_EXIT",
                        "pod": pod.alias,
                        "coin": coin,
                    }
                    break
                execute(pod, coin, -qty, float(px), cost_bps=cost_bps)
                pod.exit_attempts += 1
                instrument_orders["risk_exit"] += 1
            if unknown is not None:
                break
            if not pod.holdings and pod.state == "SUSPENDED_PENDING_EXIT":
                pod.state = "SUSPENDED_FLAT"
                pod.exit_complete_at = i
                pod.pnl_when_flat = pod.cash
        if unknown is not None:
            break

        # Existing target reductions remain hypothetically represented by
        # non-resetting signed source net deltas. No source new risk after stop.
        for alias, coin, raw_delta in by_minute.get(i, []):
            pod = pods[alias]
            if global_halt or pod.state != "ACTIVE":
                blocked_orders["AFTER_HALT_OR_POD_STOP"] += 1
                pod.skipped_after_stop += 1
                continue
            px = panels[coin]["open"][i]
            if not np.isfinite(px) or px <= 0:
                unknown = {
                    "at": base._iso_minute(i),
                    "reason": "UNPRICED_FOLLOWER_SOURCE_ORDER",
                    "pod": pod.alias,
                    "coin": coin,
                }
                break
            delta = raw_delta * pod.k
            if abs(delta * float(px)) < 10:
                blocked_orders["BELOW_10USD"] += 1
                continue
            execute(pod, coin, delta, float(px), cost_bps=cost_bps)
            instrument_orders["source_delta"] += 1
        if unknown is not None:
            break

        # Native CLOSE MTM drives historical-oracle account and PM04-equivalent
        # high-water. OHLC 'adverse' is only an auxiliary safety stress mode.
        for pod in pods.values():
            try:
                pod.current_pnl = pnl_at(pod, panels, i, field="close")
                trigger_mark = (
                    mark_pnl(pod, panels, i, "adverse")
                    if mark_mode == "adverse"
                    else pod.current_pnl
                )
            except ValueError as exc:
                unknown = {
                    "at": base._iso_minute(i),
                    "reason": str(exc),
                    "pod": pod.alias,
                }
                break
            if pod.state == "SUSPENDED_FLAT":
                pod.pnl_when_flat = pod.current_pnl
                continue
            if pod.state == "ACTIVE":
                # Preserve high water of actual close PnL; apply adverse OHLC
                # only to conservative stop trigger, not realized PnL.
                pod.high_water_pnl = max(pod.high_water_pnl, pod.current_pnl)
                compare_value = min(pod.current_pnl, trigger_mark)
                saved = pod.current_pnl
                pod.current_pnl = compare_value
                did_stop = stop_if_needed(
                    pod, i,
                    budget_usd=(pod_budgets_usd or {}).get(pod.alias, budget_usd),
                    daily_usd=(pod_daily_limits_usd or {}).get(pod.alias, pod_daily_limit),
                )
                pod.current_pnl = saved
                if did_stop:
                    stops.append(
                        {
                            "pod": pod.alias,
                            "at": base._iso_minute(i),
                            "reason": pod.reason,
                            "marked_pnl_at_trigger_usd": round(saved, 2),
                            "stress_marked_pnl_at_trigger_usd": round(compare_value, 2),
                            "high_water_pnl_usd": round(pod.high_water_pnl, 2),
                            "pending_forced_exit_count": len(pod.holdings),
                        }
                    )
            if pod.state != "ACTIVE" and not pod.holdings and pod.exit_complete_at is None:
                pod.state = "SUSPENDED_FLAT"
                pod.exit_complete_at = i
                pod.pnl_when_flat = pod.current_pnl
        if unknown is not None:
            break

        now_equity = portfolio_equity(pods)
        prior_day_peak = day_peak
        prior_global_peak = global_peak
        day_peak = max(day_peak, now_equity)
        previous_equity = now_equity
        portfolio_marked_peak = max(portfolio_marked_peak, now_equity)
        drawdown = portfolio_marked_peak - now_equity
        max_dd = max(max_dd, drawdown)
        max_dd_ratio = max(max_dd_ratio, drawdown / portfolio_marked_peak)
        gross = 0.0
        for pod in pods.values():
            for coin, qty in pod.holdings.items():
                gross += abs(qty) * float(panels[coin]["close"][i])
        peak_gross = max(peak_gross, gross)
        last_equity = now_equity
        last_valid = i
        global_peak = (
            max(global_peak, now_equity)
            if (not contract_rule or not contract_rule["eod_trailing"])
            else global_peak
        )
        if not global_halt and contract_rule:
            # At today's close, for EOD floors use previously fixed EOD HWM;
            # for continuous trailing, today's marked HWM is effective.
            trail_ref = eod_peak if contract_rule["eod_trailing"] else global_peak
            day_ref = max(day_base, day_peak) if contract_rule.get("daily_hwm", False) else day_base
            floor = max(
                day_ref - contract_rule["daily"],
                trail_ref - contract_rule["trailing"],
            )
            worst_equity = now_equity
            prior_day_ref = (max(day_base, prior_day_peak)
                             if contract_rule.get("daily_hwm", False) else day_base)
            prior_trail_ref = (eod_peak if contract_rule["eod_trailing"]
                               else prior_global_peak)
            prior_floor = max(
                prior_day_ref - contract_rule["daily"],
                prior_trail_ref - contract_rule["trailing"],
            )
            if contract_rule.get("account_adverse_ohlc", False):
                try:
                    stressed = START_USD + sum(
                        mark_pnl(pod, panels, i, "adverse") for pod in pods.values()
                    )
                except ValueError as exc:
                    unknown = {"at": base._iso_minute(i), "reason": str(exc)}
                    break
                worst_equity = min(now_equity, stressed)
            # OHLC order is unknown: compare adverse range against the
            # PRE-minute floor, not the floor raised by this bar's close.
            # The current close is checked against the updated floor.
            if now_equity <= floor + EPSILON or worst_equity <= prior_floor + EPSILON:
                global_halt = True
                account_reason = "CONTRACT_FLOOR_BREACH"
                account_at = base._iso_minute(i)
            elif now_equity >= START_USD + contract_rule["targets"][0]:
                if (len(contract_rule["targets"]) == 1
                    and green_days < contract_rule.get("minimum_green_days", 5)):
                    pass
                else:
                    global_halt = True
                    account_reason = (
                        "PHASE1_TARGET_REACHED_STAGE2_NOT_SIMULATED"
                        if len(contract_rule["targets"]) > 1
                        else (
                            "CHALLENGE_TARGET_REACHED" if contract_rule.get("minimum_green_days", 5) == 0
                            else "SPRINT_TARGET_WITH_5_GREEN_DAYS"
                        )
                    )
                    account_at = base._iso_minute(i)
                    target_at = account_at
        if i % 1440 == 1439:
            if now_equity > day_base:
                green_days += 1
            eod_peak = max(eod_peak, now_equity)
        if i % 1440 == 1439 or stops and stops[-1]["at"] == base._iso_minute(i):
            timeline.append(
                {
                    "at": base._iso_minute(i),
                    "account_equity_usd": round(now_equity, 2),
                    "gross_usd": round(gross, 2),
                    "pods": {
                        alias: {"state": p.state, "pnl_usd": round(p.current_pnl, 2)}
                        for alias, p in pods.items()
                    },
                }
            )
        if global_halt and not any(p.holdings for p in pods.values()):
            break
        if all(p.state != "ACTIVE" and not p.holdings for p in pods.values()):
            account_reason = account_reason or "ALL_PODS_SUSPENDED_AND_FLAT"
            account_at = account_at or base._iso_minute(i)
            break

    result_pods = {
        alias: {
            "state": p.state,
            "reason": p.reason,
            "static_k_eff": round(p.k, 8),
            "stopped_at": base._iso_minute(p.triggered_at) if p.triggered_at is not None else None,
            "exit_complete_at": base._iso_minute(p.exit_complete_at)
            if p.exit_complete_at is not None
            else None,
            "pnl_when_triggered_usd": round(p.pnl_when_triggered, 2)
            if p.pnl_when_triggered is not None
            else None,
            "pnl_after_flat_usd": round(p.pnl_when_flat, 2)
            if p.pnl_when_flat is not None
            else None,
            "final_marked_pnl_usd": round(p.current_pnl, 2),
            "source_fills_executed": p.fills,
            "fees_plus_slippage_usd": round(p.fees_slip_usd, 2),
            "exit_orders_executed": p.exit_attempts,
            "source_orders_ignored_after_stop": p.skipped_after_stop,
            "remaining_coin_qty": {
                coin: round(qty, 10) for coin, qty in p.holdings.items() if abs(qty) > EPSILON
            },
        }
        for alias, p in pods.items()
    }
    # Final cash+signed-position accounting identity always includes
    # *modeled* outstanding inventory. If unpriceable, do not fabricate mark.
    final_equity = round(last_equity, 2) if last_valid >= 0 else START_USD
    allowed = (
        unknown is None
        and (account_reason is not None or last_valid == base.MINUTES - 1)
        and all(p.state != "SUSPENDED_PENDING_EXIT" for p in pods.values())
    )
    status = (
        "BLOCKED_UNKNOWN_EXECUTION_OR_MARK"
        if unknown is not None
        else account_reason or "STUDY_WINDOW_END"
    )
    return {
        "status": status,
        "status_at": account_at,
        "valid_complete_path": allowed,
        "portfolio": list(members),
        "pod_trailing_budget_usd": budget_usd,
        "pod_daily_limit_usd": pod_daily_limit,
        "pod_budgets_usd": pod_budgets_usd,
        "pod_daily_limits_usd": pod_daily_limits_usd,
        "mark_mode": mark_mode,
        "cost_bps_per_executed_side": cost_bps,
        "terminal_equity_usd": final_equity if allowed else None,
        "terminal_equity_at_last_complete_mark_usd": final_equity,
        "net_pnl_usd": round(final_equity - START_USD, 2) if allowed else None,
        "max_drawdown_usd_observed": round(max_dd, 2),
        "max_drawdown_pct_from_prior_peak_observed": round(max_dd_ratio * 100, 2),
        "peak_gross_usd": round(peak_gross, 2),
        "account_halt": global_halt,
        "first_follower_unknown": unknown,
        "green_days": green_days,
        "target_at": target_at,
        "fills_executed_by_type": dict(instrument_orders),
        "blocked_orders": dict(blocked_orders),
        "pods": result_pods,
        "timeline_daily_and_stop": timeline,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--portfolio",
        choices=("EXPLORER", "SPRINT", "PRECOMPUTED_CONTROL"),
        nargs="+",
        default=["EXPLORER", "SPRINT", "PRECOMPUTED_CONTROL"],
    )
    parser.add_argument("--delay", nargs="+", type=int, choices=(1, 2, 5), default=[1, 2, 5])
    parser.add_argument("--cost", nargs="+", type=float, default=[6.0])
    parser.add_argument("--pod-dd-usd", type=float, default=200.0)
    parser.add_argument("--pod-daily-usd", type=float, default=None)
    parser.add_argument("--mark-mode", choices=("close", "adverse"), default="close")
    args = parser.parse_args()
    if any(c < 3.5 for c in args.cost):
        parser.error("cost must be >= 3.5bps")
    selected_names = tuple(dict.fromkeys(args.portfolio))
    ids, cohort_sha = base.roster(args.db)
    stores, counts = base.local_sources(args.source_root, ids, extra_source_dirs=(base.SUPPLEMENT,))
    wanted = set(sum((list(base.CONTRACTS[name]["members"]) for name in selected_names), []))
    events, source = base.source_rows(stores, ids, wanted)
    batches_by_delay = {d: base.anchored_batches(events, d) for d in args.delay}
    markets = {}
    for batch in batches_by_delay.values():
        for row in batch.iter_rows(named=True):
            markets[row["coin"]] = min(
                markets.get(row["coin"], row["execute_ms"]), row["execute_ms"]
            )
    panels, market_coverage = base.load_native_panels(args.market_root, markets)
    results = []
    for name in selected_names:
        rule = base.CONTRACTS[name]
        for d in args.delay:
            for cost in args.cost:
                run = protected(
                    batches_by_delay[d],
                    rule["members"],
                    source["wallets"],
                    panels,
                    cost_bps=cost,
                    budget_usd=args.pod_dd_usd,
                    pod_daily_limit=args.pod_daily_usd,
                    mark_mode=args.mark_mode,
                    contract_rule=rule,
                )
                results.append({"name": name, "delay": d, "cost": cost, **run})
    report = {
        "schema": "ml4t66_historical_protected_pod_2pct_flatten_replay_v1",
        "cohort_source_sha256": cohort_sha,
        "source": source,
        "source_inventory": counts,
        "market_coverage": market_coverage,
        "assumptions": {
            "source_first_known": "MISSING_RETROSPECTIVE_SOURCE_EVENTS_ONLY",
            "source_asof_equity": "MISSING_STATIC_VENDOR_EQUITY_SCALAR",
            "initial_source_book": "PER_COIN_FIRST_OBSERVED_ZERO_NOT_FULL_ATOMIC_BOOK",
            "pod_loss_budget": "200_USD_PER_POD_FROM_MARKED_PNL_HIGH_WATER",
            "pod_daily_budget": args.pod_daily_usd,
            "risk_latch": "SUSPENDED_NO_AUTOMATIC_REENTRY",
            "risk_flatten": "NEXT_NATIVE_MINUTE_OPEN_IF_AVAILABLE_NO_SYNTHETIC_FILLS",
            "risk_exit_cost": "SAME_TAKER_FEE_AND_ADVERSE_SLIPPAGE_AS_SOURCE_EXECUTIONS",
            "broker_execution": "HISTORICAL_ORACLE_MARK_NOT_LIVE_RECEIPT",
            "no_automatic_stage_2": True,
            "provider_mark_gaps": "FAIL_CLOSED",
            "intrabar_ohlc_stress_is_not_executable": True,
            "full_account_portfolio_with_netting": "CASH_PLUS_INDEPENDENT_POD_BOOKS_NO_BROKER_CROSS_ATTRIBUTION",
            "pretrade_gross_cap": "NOT_ENFORCED_NO_UNAMBIGUOUS_APPROVED_PROPORTION",
            "no_liquidation_latency_exceeding_one_minute": "ASSUMED",
        },
        "results": results,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }
    args.output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output_root.stat().st_mode & 0o077 or args.output_root.is_symlink():
        raise ValueError("PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    digest = sha256(raw).hexdigest()
    target = args.output_root / f"ml4t66_protected_pod_replay_{digest[:20]}.json"
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("REPORT_SHA_COLLISION")
    else:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
    print(
        json.dumps(
            {
                "private_report": str(target),
                "sha256": digest,
                "results": [
                    {
                        "portfolio": r["name"],
                        "delay_min": r["delay"],
                        "cost_bps": r["cost"],
                        "status": r["status"],
                        "pnl": r["net_pnl_usd"],
                        "max_dd_usd": r["max_drawdown_usd_observed"],
                        "peak_gross_usd": r["peak_gross_usd"],
                        "stops": {
                            name: {
                                "at": pod["stopped_at"],
                                "pnl_flat": pod["pnl_after_flat_usd"],
                                "remaining": pod["remaining_coin_qty"],
                            }
                            for name, pod in r["pods"].items()
                        },
                        "first_unknown": r["first_follower_unknown"],
                    }
                    for r in results
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
