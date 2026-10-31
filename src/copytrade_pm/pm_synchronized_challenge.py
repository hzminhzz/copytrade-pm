"""Research-only synchronized PM-01 historical wallet equity and challenge-floor diagnostic.

This is NOT a live copy-trading backtest or a probability estimator.
Historical vendor timestamps are hindsight-only, and 1m OPEN marks do not
prove that a firm's intraminute equity floor was never touched.
No portfolio selection or risk allocation is authorized by these outputs.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import combinations
import json
import os
from pathlib import Path
from typing import Any

from .pm02_audit import source_file_read
from .pm_fill_replay import (
    CUT,
    _coins,
    _source_fills,
    replay_wallet,
)
from .pm_shadow import MarketDataBlocked, Scenario, VerifiedHyperliquidMinuteSource
from .pm_sources import load_cohort


D = Decimal
ZERO = D("0")
CAPITAL = D("100000")
MIN_EVALUATION_DAYS = 30
SUCCESS = "HISTORICAL_HINDSIGHT_SIMULATION_ONLY"
LATENCIES = (5, 15, 60)
# Explicit research-only assumptions; not a contract or official firm attestation.
RESEARCH_LIMITS = {
    "label": "ILLUSTRATIVE_CLASSIC_ONE_STEP_NOT_CONTRACT_VERIFIED",
    "profit_target_fraction": "0.10",
    "daily_loss_fraction_of_initial": "0.03",
    "static_loss_fraction_of_initial": "0.06",
    "daily_reset_timezone": "UTC",
}
TRADING_AUTHORIZED = False


def utc(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_EVIDENCE_TIMESTAMP")
    return value.astimezone(UTC)


def _pnl(
    snapshot: dict, at: datetime, market: VerifiedHyperliquidMinuteSource, model: Scenario
) -> D:
    stamp = utc(snapshot["at"])
    if stamp > at:
        raise ValueError("FUTURE_BOOK_SNAPSHOT")
    positions = {k: D(v) for k, v in snapshot["positions"].items()}
    flows = {k: D(v) for k, v in snapshot["flows"].items()}
    if any(not q.is_finite() for q in (*positions.values(), *flows.values())):
        raise ValueError("NONFINITE_RECONSTRUCTED_EQUITY")
    marks = {name: market.get(name, at).open for name in positions}
    gross = sum((abs(qty * marks[name]) for name, qty in positions.items()), ZERO)
    elapsed = D(str((at - stamp).total_seconds()))
    projected_funding = gross * model.funding_abs_bps_per_8h / D("10000") * elapsed / D("28800")
    return (
        sum(flows.values(), ZERO)
        + sum((qty * marks[name] for name, qty in positions.items()), ZERO)
        - projected_funding
    )


def validate_source(replay: dict, lag: int) -> tuple[dict[str, dict], dict[str, int]]:
    if lag not in LATENCIES:
        raise ValueError("UNSUPPORTED_HISTORICAL_LAG")
    if (
        replay.get("schema") != "pm01_fill_only_replay_v2"
        or replay.get("wallet_count") != 36
        or replay.get("never_claim_prospective_alpha") is not True
        or replay.get("prospective_qualified_wallet_count") != 0
    ):
        raise ValueError("UNTRUSTED_OR_NONHISTORICAL_COHORT")
    rows = replay.get("rows")
    if not isinstance(rows, list) or len(rows) != 108:
        raise ValueError("INCOMPLETE_36_WALLET_SCENARIOS")
    by_key = {}
    for row in rows:
        key = (row["wallet"], row["latency_minutes"])
        if key in by_key or row.get("oracle_hindsight") is not True:
            raise ValueError("DUPLICATE_OR_UNTRUSTED_WALLET")
        if row.get("known_at") != "UNKNOWN_VENDOR_HISTORICAL_ORACLE":
            raise ValueError("INVENTED_FIRST_KNOWN_CLOCK")
        if row["latency_minutes"] not in LATENCIES:
            raise ValueError("UNEXPECTED_LATENCY")
        by_key[key] = row
    aliases = {wallet for wallet, _ in by_key}
    if len(aliases) != 36 or any(
        set(delay for wallet, delay in by_key if wallet == alias) != set(LATENCIES)
        for alias in aliases
    ):
        raise ValueError("COHORT_OR_LATENCY_INCOMPLETE")
    chosen = {a: by_key[(a, lag)] for a in sorted(aliases)}
    return chosen, dict(Counter(row["status"] for row in chosen.values()))


def opportunity_gate(
    replay: dict, lag: int = 5, *, minimum_days: int = MIN_EVALUATION_DAYS
) -> dict[str, Any]:
    """The feasibility test precedes any portfolio search; missing != zero."""
    if not 1 <= minimum_days <= 365:
        raise ValueError("INVALID_REQUIRED_HISTORY_DAYS")
    rows, counts = validate_source(replay, lag)
    end = utc(replay["study_cutoff"])
    if end != CUT:
        raise ValueError("RESEARCH_CUTOFF_CHANGED")
    success = {
        alias: row
        for alias, row in rows.items()
        if row["status"] == SUCCESS and row.get("pnl") is not None
    }
    starts = {
        alias: VerifiedHyperliquidMinuteSource._minute(
            utc(r["source_anchored_at"]) + timedelta(minutes=lag)
        )
        for alias, r in success.items()
    }
    candidates = sorted(success)
    target_duration = timedelta(days=minimum_days)
    # Search feasibility by all subsets, without substituting for missing wallets.
    feasibility = []
    for k in (1, 2, 3, 4, 5, 6, 8, 10):
        valid = 0
        example = None
        # At most 36 choose 10; early reject on the individual-duration gate.
        old_enough = [a for a in candidates if end - starts[a] >= target_duration]
        if k <= len(old_enough):
            # Stop after first witness: no exhaustive combinatorial search needed
            # for a common end and common minimum duration.
            example = old_enough[:k]
            valid = 1  # feasibility witness, NOT number of combinations
        feasibility.append(
            {
                "wallet_count": k,
                "feasible_at_least_one_combination": bool(valid),
                "example_only_not_optimized": example,
            }
        )
    common_hours = round((end - max(starts.values())).total_seconds() / 3600, 3) if starts else None
    return {
        "lag_minutes": lag,
        "minimum_required_days": minimum_days,
        "scenario_status_counts": counts,
        "historical_hindsight_completed": candidates,
        "candidate_windows": {
            a: {
                "anchor": success[a]["source_anchored_at"],
                "usable_hours": round((end - starts[a]).total_seconds() / 3600, 3),
                "prospective_first_known": False,
            }
            for a in candidates
        },
        "full_cohort_wallets": len(rows),
        "largest_completed_candidate_common_window_hours": common_hours,
        "feasibility_by_wallet_count": feasibility,
        "historical_cannot_establish_prospective_signals": True,
        "duration_only_preflight_not_1m_continuous_coverage": True,
    }


def _snapshots(row: dict) -> list[tuple[datetime, dict]]:
    points = row.get("historical_book_snapshots")
    if not points or row["status"] != SUCCESS:
        raise ValueError("NO_COMPLETED_WALLET_BOOK_PATH")
    parsed = [(utc(s["at"]), s) for s in points]
    if any(b[0] <= a[0] for a, b in zip(parsed, parsed[1:])):
        raise ValueError("NONMONOTONIC_WALLET_BOOK_PATH")
    return parsed


def synchronized_path(
    traces: dict[str, dict],
    market: VerifiedHyperliquidMinuteSource,
    *,
    lag: int,
    max_minutes: int = 1500,
    capital: D = CAPITAL,
) -> list[dict[str, Any]]:
    """Exact common 1m-open MTM; full-book marks required for every wallet/minute.

    A bounded *tail* window is allowed for exploration only, and is explicitly
    reported as such; it may not be used to infer full-horizon success.
    """
    if not traces or not 2 <= max_minutes <= 43200:
        raise ValueError("INVALID_SYNCHRONIZATION_REQUEST")
    parsed = {alias: _snapshots(row) for alias, row in traces.items()}
    start = max(items[0][0] for items in parsed.values())
    end = min(items[-1][0] for items in parsed.values())
    if (end - start).total_seconds() < 60:
        raise ValueError("NO_COMMON_FULL_MINUTE_INTERVAL")
    total = int((end - start).total_seconds() // 60) + 1
    if total > max_minutes:
        # A tail window is deliberately censored, not smuggled into a 30d estimate.
        start = end - timedelta(minutes=max_minutes - 1)
    # We require full minute-aligned input; never round a future observation back.
    if any(dt.second or dt.microsecond for dt in (start, end)):
        raise ValueError("UNALIGNED_HISTORICAL_SAMPLE")
    model = Scenario("HISTORICAL_ORACLE_ONLY", lag, capital, D("0.001"))
    cursors = {alias: 0 for alias in parsed}
    for alias, points in parsed.items():
        while cursors[alias] + 1 < len(points) and points[cursors[alias] + 1][0] <= start:
            cursors[alias] += 1
    result = []
    baseline = None
    count = int((end - start).total_seconds() // 60) + 1
    for minute in range(count):
        at = start + timedelta(minutes=minute)
        current = {}
        for alias, snapshots in parsed.items():
            while cursors[alias] + 1 < len(snapshots) and snapshots[cursors[alias] + 1][0] <= at:
                cursors[alias] += 1
            current[alias] = _pnl(snapshots[cursors[alias]][1], at, market, model)
        if baseline is None:
            baseline = current
        result.append(
            {
                "at": at.isoformat(),
                "delta_pnl_by_wallet": {a: str(current[a] - baseline[a]) for a in sorted(current)},
            }
        )
    return result


def simulate_equity(
    synchronized: list[dict],
    subset: tuple[str, ...],
    *,
    capital: D = CAPITAL,
    per_wallet_scale: D = D("1"),
    target_fraction: D = D(RESEARCH_LIMITS["profit_target_fraction"]),
    daily_loss_fraction: D = D(RESEARCH_LIMITS["daily_loss_fraction_of_initial"]),
    static_loss_fraction: D = D(RESEARCH_LIMITS["static_loss_fraction_of_initial"]),
) -> dict[str, Any]:
    """One historical path, NOT a probability. Exactly synchronized minute observations."""
    if not synchronized or not subset or len(set(subset)) != len(subset):
        raise ValueError("INVALID_PORTFOLIO_SELECTION")
    if capital <= 0 or not ZERO < per_wallet_scale <= 1:
        raise ValueError("INVALID_ALLOCATION_SCALE")
    if not (ZERO < daily_loss_fraction < static_loss_fraction < target_fraction < 1):
        raise ValueError("INVALID_RESEARCH_LIMITS")
    expected = set(synchronized[0]["delta_pnl_by_wallet"])
    if not set(subset).issubset(expected):
        raise ValueError("SELECTED_WALLET_DATA_UNAVAILABLE")
    first = utc(synchronized[0]["at"])
    previous = None
    day = first.date()
    daily_base = capital
    equity = capital
    peak = capital
    trough_dd = ZERO
    floor_static = capital * (1 - static_loss_fraction)
    floor_daily = daily_base - capital * daily_loss_fraction
    terminal = "OBSERVED_PATH_NOT_PASSED"
    decisive_at = None
    max_daily_loss = ZERO
    for row in synchronized:
        at = utc(row["at"])
        if previous is not None and at - previous != timedelta(minutes=1):
            raise ValueError("MISSING_OR_DUPLICATE_MARK_MINUTE")
        previous = at
        if set(row["delta_pnl_by_wallet"]) != expected:
            raise ValueError("MISSING_WALLET_AT_MINUTE")
        pnl_values = [D(row["delta_pnl_by_wallet"][a]) for a in subset]
        if any(not x.is_finite() for x in pnl_values):
            raise ValueError("NONFINITE_WALLET_EQUITY")
        next_equity = capital + per_wallet_scale * sum(pnl_values, ZERO)
        if at.date() != day:
            # We only have exact minute-open data, not the true prior midnight
            # close or broker balance. Reset on prior sample for diagnostic only.
            daily_base = equity
            day = at.date()
            floor_daily = daily_base - capital * daily_loss_fraction
        equity = next_equity
        peak = max(peak, equity)
        trough_dd = max(trough_dd, peak - equity)
        daily_loss = daily_base - equity
        max_daily_loss = max(max_daily_loss, daily_loss)
        if equity <= max(floor_static, floor_daily):
            terminal = "SAMPLED_FLOOR_BREACH"
            decisive_at = at.isoformat()
            break
        if equity >= capital * (1 + target_fraction):
            terminal = "SAMPLED_PROFIT_TARGET_TOUCH"
            decisive_at = at.isoformat()
            break
    return {
        "wallets": list(subset),
        "scaled_source_notional_multiplier": str(per_wallet_scale),
        "status": terminal,
        "decision_at": decisive_at,
        "first_mark_at": first.isoformat(),
        "last_evaluated_at": previous.isoformat() if previous else None,
        "sample_minutes": len(synchronized),
        "end_equity": str(equity),
        "sampled_max_drawdown_dollars": str(trough_dd),
        "sampled_max_daily_loss_dollars": str(max_daily_loss),
        "sampled_max_drawdown_fraction": str(trough_dd / capital),
        "time_window_excludes_intraminute_equity_extrema": True,
        "not_a_pass_probability": True,
    }


def _reconstruct_traces(
    replay: dict,
    root: Path,
    market: VerifiedHyperliquidMinuteSource,
    lag: int,
    risk_budget: D,
    generations: tuple[Path, ...],
    eligible: list[str],
) -> dict[str, dict]:
    if risk_budget != D("0.001"):
        raise ValueError("FROZEN_DEMONSTRATION_ONLY_AT_0_1PCT_GROSS")
    entries, contracts = load_cohort(root)
    if replay["source_contract_shas"] != contracts:
        raise ValueError("PM01_SOURCE_COHORT_MISMATCH")
    additions: dict[str, list] = {}
    if generations:
        from .pm_hyperx_overlay_audit import examine

        summary, additions = examine(root, generations)
        if (
            summary["wallet_count"] != 36
            or not summary["original_vendor_cache_intact"]
            or summary["new_verified_pre_cutoff_fills"]
            != replay["hyperx_verified_additional_fills"]
        ):
            raise ValueError("PM01_VERIFIED_OVERLAY_DRIFT")
    elif replay["hyperx_verified_additional_fills"] != 0:
        raise ValueError("MISSING_VERIFIED_SOURCE_GENERATIONS")
    source_rows, _ = validate_source(replay, lag)
    traces = {}
    for entry in entries:
        if entry.alias not in eligible:
            continue
        coins = _coins(root, entry.alias)
        fills, errors = _source_fills(
            root,
            entry.alias,
            entry.address,
            coins,
            additional_events=additions.get(entry.alias),
        )
        outcome = replay_wallet(
            root,
            entry,
            market,
            lag,
            risk_budget=risk_budget,
            prepared=(fills, errors, coins),
            record_path=True,
        )
        historic = source_rows[entry.alias]
        if (
            outcome["status"] != SUCCESS
            or outcome["pnl"] != historic["pnl"]
            or outcome["source_anchored_at"] != historic["source_anchored_at"]
            or outcome["hypothetical_fill_count"] != historic["hypothetical_fill_count"]
        ):
            raise ValueError("SEALED_PM01_RESULT_DOES_NOT_REPLAY")
        traces[entry.alias] = outcome
    if set(traces) != set(eligible):
        raise ValueError("MISSING_CANDIDATE_RECONSTRUCTION")
    return traces


def research(
    sealed_pm01: Path,
    research_root: Path | None,
    market_root: Path | None,
    *,
    generations: tuple[Path, ...] = (),
    lag: int = 5,
    max_minutes: int = 1500,
) -> dict:
    replay, source_sha = source_file_read(sealed_pm01)
    gate = opportunity_gate(replay, lag)
    output = {
        "schema": "pm36_synchronized_challenge_research_v1",
        "authority": "RESEARCH_ONLY_NO_TRADING_NO_PROBABILISTIC_CLAIM",
        "pm01_source_sha256": source_sha,
        "source_normalized_fills_sha256": replay["source_normalized_fills_sha256"],
        "study_cutoff": replay["study_cutoff"],
        "data_gate": gate,
        "risk_rule_assumptions": RESEARCH_LIMITS,
        "economic_execution": "PM01_SHA_VERIFIED_HYPERLIQUID_1M_ORACLE",
        "first_known_receipt_verified": False,
        "price_sampling": "1M_OPEN_ONLY_NOT_INTRAMINUTE_FLOOR_CERTIFIED",
        "joint_execution_liquidity_and_cross_wallet_netting_verified": False,
        "backtest_kind": "RETROSPECTIVE_HINDSIGHT_DIAGNOSTIC",
        "qualified_pass_probability": None,
        "qualified_wallet_combination": None,
        "live_risk_authorized": False,
        "exploratory_common_window": None,
        "portfolio_scenarios": [],
        "scientific_decision": "NO_QUALIFIED_PORTFOLIO",
    }
    if not gate["historical_hindsight_completed"] or research_root is None or market_root is None:
        return output
    market = VerifiedHyperliquidMinuteSource(market_root)
    traces = _reconstruct_traces(
        replay,
        research_root,
        market,
        lag,
        D(replay["risk_budget_fraction_of_initial_capital"]),
        generations,
        gate["historical_hindsight_completed"],
    )
    try:
        path = synchronized_path(traces, market, lag=lag, max_minutes=max_minutes)
    except (ValueError, MarketDataBlocked) as exc:
        output["exploratory_common_window"] = {
            "status": "BLOCKED_SYNCHRONIZED_PRICE_OR_BOOK",
            "reason": str(exc),
        }
        return output
    hours = (utc(path[-1]["at"]) - utc(path[0]["at"])).total_seconds() / 3600
    raw_first = max(_snapshots(trace)[0][0] for trace in traces.values())
    raw_last = min(_snapshots(trace)[-1][0] for trace in traces.values())
    raw_window_minutes = int((raw_last - raw_first).total_seconds() // 60) + 1
    output["exploratory_common_window"] = {
        "status": "HISTORICAL_MINUTE_OPEN_ONLY",
        "start": path[0]["at"],
        "end": path[-1]["at"],
        "hours": round(hours, 3),
        "marked_minutes": len(path),
        "wallets": sorted(traces),
        "tail_window_censored": raw_window_minutes > max_minutes,
        "market_source_day_count": len(market.source_days),
        "market_source_day_sha256": dict(sorted(market.source_days.items())),
    }
    evaluations = []
    for k in range(1, min(len(traces), 5) + 1):
        for chosen in combinations(sorted(traces), k):
            for name, scale in (
                ("FIXED_TESTED_NOTIONAL_PER_WALLET", D("1")),
                ("FIXED_TOTAL_TESTED_NOTIONAL", D("1") / D(k)),
            ):
                row = simulate_equity(path, chosen, per_wallet_scale=scale)
                row["allocation_policy"] = name
                evaluations.append(row)
    output["portfolio_scenarios"] = evaluations
    output["exploratory_scenario_count"] = len(evaluations)
    output["exploratory_target_touches"] = sum(
        x["status"] == "SAMPLED_PROFIT_TARGET_TOUCH" for x in evaluations
    )
    output["exploratory_floor_breaches"] = sum(
        x["status"] == "SAMPLED_FLOOR_BREACH" for x in evaluations
    )
    return output


def _save_private(out: Path, payload: dict) -> tuple[Path, str]:
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if out.stat().st_mode & 0o077:
        raise ValueError("INSECURE_RESEARCH_OUTPUT_DIRECTORY")
    raw = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    h = sha256(raw).hexdigest()
    path = out / f"pm36-sync-{h[:20]}.json"
    if path.exists():
        if path.read_bytes() != raw or path.stat().st_mode & 0o077:
            raise ValueError("CONFLICTING_OR_INSECURE_RESEARCH_ARTIFACT")
        return path, h
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return path, h


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pm01", required=True, type=Path)
    p.add_argument("--research-root", type=Path)
    p.add_argument("--market-root", type=Path)
    p.add_argument("--hyperx-generations", nargs="*", type=Path, default=[])
    p.add_argument("--lag", type=int, choices=LATENCIES, default=5)
    p.add_argument("--max-minutes", type=int, default=1500)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    result = research(
        args.pm01,
        args.research_root,
        args.market_root,
        generations=tuple(args.hyperx_generations),
        lag=args.lag,
        max_minutes=args.max_minutes,
    )
    target, h = _save_private(args.out, result)
    common = result["exploratory_common_window"]
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "wallets": result["data_gate"]["full_cohort_wallets"],
                "historical_completed": result["data_gate"]["historical_hindsight_completed"],
                "min_30d_multi_feasible": any(
                    row["wallet_count"] >= 2 and row["feasible_at_least_one_combination"]
                    for row in result["data_gate"]["feasibility_by_wallet_count"]
                ),
                "common_window": (
                    {k: v for k, v in common.items() if k != "market_source_day_sha256"}
                    if common
                    else None
                ),
                "scenarios": len(result["portfolio_scenarios"]),
                "scientific_decision": result["scientific_decision"],
                "sha256": h,
                "artifact": str(target),
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
