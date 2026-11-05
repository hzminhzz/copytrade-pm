"""Extended 3-5 pod ML4T-66 barbell research with chronological risk exits.

Retrospective source events, not first-known receipts. Sizing calibration uses
days 1-45; follower OOS starts FLAT at day 46 only after new observed source
zero-position events. Portfolio selection itself remains retrospectively chosen.
No independent NAV, funding, liquidity or verified contract rules. NO_TRADE.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
from hashlib import sha256
import itertools
import json
import os
from pathlib import Path

import polars as pl

if __package__:
    from . import ml4t66_portfolio_backtest as source_replay
    from . import ml4t66_barbell_research as barbell
    from . import ml4t66_protected_portfolio_replay as protected_replay
else:
    import ml4t66_portfolio_backtest as source_replay
    import ml4t66_barbell_research as barbell
    import ml4t66_protected_portfolio_replay as protected_replay
from copytrade_pm.pm_ml4t_batch_recovery import anchored_batches, local_sources, roster

ANCHORS = ("H34", "M55", "M51", "M22")
RUNNERS = ("H36", "M40", "M50", "M58", "M32", "M29")
MEMBERS = tuple(dict.fromkeys(ANCHORS + RUNNERS))
TRAIN_DAYS = 45
TRAIN_MINUTES = TRAIN_DAYS * 1440
STRESS_FACTOR = 1.5
EXTRA_BUFFER_PER_POD = 10.0
STRESS_CEILING_USD = 400.0
STARTING_EQUITY = 10000.0
RULE = {
    "daily": 500.0,
    "trailing": 1000.0,
    "eod_trailing": False,
    "targets": (1000.0,),
    "minimum_green_days": 0,
    "daily_hwm": True,
    "account_adverse_ohlc": True,
}
# (daily anchor, lifetime anchor, daily runner, lifetime runner)
BUDGET = {
    3: (120.0, 200.0, 100.0, 150.0),
    4: (90.0, 130.0, 100.0, 180.0),
    5: (75.0, 120.0, 70.0, 100.0),
}


def portfolio_universe() -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    policies = []
    for anchors in itertools.combinations(ANCHORS, 2):
        for runner in RUNNERS:
            members = (*anchors, runner)
            policies.append(("3P_" + "_".join(members), members, ("anchor", "anchor", "runner")))
    for anchors in itertools.combinations(ANCHORS, 3):
        for runner in RUNNERS:
            members = (*anchors, runner)
            policies.append(("4P_" + "_".join(members), members, ("anchor", "anchor", "anchor", "runner")))
    # 5 pod: three anchors + two correlated/crash-specialist runner challengers.
    for anchors in (("H34", "M55", "M51"), ("H34", "M55", "M22")):
        for runners in (("H36", "M40"), ("H36", "M58"), ("M40", "M50")):
            members = (*anchors, *runners)
            policies.append(("5P_" + "_".join(members), members,
                             ("anchor", "anchor", "anchor", "runner", "runner")))
    return policies


def calculate_k(
    members: tuple[str, ...],
    roles: tuple[str, ...],
    calibration: dict,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], float, float]:
    config = BUDGET[len(members)]
    daily_limits: dict[str, float] = {}
    life_limits: dict[str, float] = {}
    ks: dict[str, float] = {}
    for alias, role in zip(members, roles, strict=True):
        idx = 0 if role == "anchor" else 2
        daily, lifetime = config[idx], config[idx + 1]
        daily_limits[alias] = daily
        life_limits[alias] = lifetime
        stat = calibration[alias]
        base_k = stat["base_k"]
        ks[alias] = min(
            base_k,
            base_k * (daily - EXTRA_BUFFER_PER_POD)
            / (STRESS_FACTOR * stat["training_daily_adverse_usd"]),
            base_k * (lifetime - EXTRA_BUFFER_PER_POD)
            / (STRESS_FACTOR * stat["training_lifetime_adverse_usd"]),
        )
    train_joint = STRESS_FACTOR * sum(
        ks[alias] / calibration[alias]["base_k"] *
        calibration[alias]["training_daily_adverse_usd"] for alias in members
    )
    if train_joint > STRESS_CEILING_USD:
        ratio = STRESS_CEILING_USD / train_joint
        ks = {alias: k * ratio for alias, k in ks.items()}
        train_joint = STRESS_CEILING_USD
    hindsight_joint = STRESS_FACTOR * sum(
        ks[alias] / calibration[alias]["base_k"] *
        calibration[alias]["full_daily_adverse_usd"] for alias in members
    )
    return ks, daily_limits, life_limits, train_joint, hindsight_joint


def run_replay(
    batch: pl.DataFrame,
    members: tuple[str, ...],
    roles: tuple[str, ...],
    stat: dict,
    scalars: dict,
    panels: dict,
    *,
    cost: float,
    delay: int,
    label: str,
) -> dict:
    ks, daily_limits, life_limits, train_joint, full_joint = calculate_k(members, roles, stat)
    adapted = barbell.scale_batch(batch, members, ks, scalars)
    result = protected_replay.protected(
        adapted,
        members,
        {alias: {"static_equity_scalar": scalars[alias]} for alias in members},
        panels,
        cost_bps=cost,
        budget_usd=150.0,
        pod_daily_limit=100.0,
        pod_budgets_usd=life_limits,
        pod_daily_limits_usd=daily_limits,
        mark_mode="adverse",
        contract_rule=RULE,
    )
    return {
        "name": label,
        "size": len(members),
        "members": list(members),
        "roles": list(roles),
        "delay_min": delay,
        "total_bps_per_side": cost,
        "k": {x: round(y, 9) for x, y in ks.items()},
        "daily_budget_usd": daily_limits,
        "lifetime_budget_usd": life_limits,
        "training_coincident_stress_usd": round(train_joint, 2),
        "full_period_coincident_stress_usd_hindsight": round(full_joint, 2),
        "status": result["status"],
        "at": result["status_at"],
        "target_at": result["target_at"],
        "complete_path": result["valid_complete_path"],
        "net_usd": result["net_pnl_usd"],
        "last_complete_mark_usd": result["terminal_equity_at_last_complete_mark_usd"],
        "max_dd_usd": result["max_drawdown_usd_observed"],
        "gross_peak_usd": result["peak_gross_usd"],
        "unknown": result["first_follower_unknown"],
        "pod_stops": {
            alias: {
                "state": x["state"],
                "reason": x["reason"],
                "at": x["stopped_at"],
                "flat_at": x["exit_complete_at"],
                "net_pnl_usd": x["final_marked_pnl_usd"],
            } for alias, x in result["pods"].items()
        },
        "source_orders": result["fills_executed_by_type"].get("source_delta", 0),
        "risk_flatten_orders": result["fills_executed_by_type"].get("risk_exit", 0),
        "block_orders": result["blocked_orders"],
    }


def evaluate(db: Path, source_root: Path, market_root: Path) -> dict:
    cohort, sha = roster(db)
    stores, acquisition = local_sources(
        source_root, cohort, extra_source_dirs=(source_replay.SUPPLEMENT,),
    )
    events, provenance = source_replay.source_rows(stores, cohort, set(MEMBERS))
    train_end_ms = source_replay.START_MS + TRAIN_MINUTES * source_replay.MINUTE_MS
    after_train = events.filter(pl.col("time") >= train_end_ms)
    new_starts, cut = source_replay.source_zero_cut(after_train.to_dicts())
    if not new_starts:
        raise ValueError("NO_OOS_ZERO_SOURCE_POSITION_EVENTS")
    oos = pl.DataFrame(new_starts).sort(["alias", "coin", "time"])
    batches = {d: anchored_batches(events, d) for d in (2, 5)}
    oos_batches = {d: anchored_batches(oos, d) for d in (2, 5)}
    requested_markets: dict[str, int] = {}
    for batch in batches.values():
        for row in batch.iter_rows(named=True):
            requested_markets[row["coin"]] = min(
                requested_markets.get(row["coin"], row["execute_ms"]), row["execute_ms"]
            )
    panels, coverage = source_replay.load_native_panels(market_root, requested_markets)
    scalars = {name: provenance["wallets"][name]["static_equity_scalar"] for name in MEMBERS}
    calibration = {}
    for name in MEMBERS:
        c, a, _, bad, diag = source_replay.simulate_inventory(
            batches[5].filter(pl.col("alias") == name),
            (name,), provenance["wallets"], panels, cost_bps=6.,
        )
        first_unknown = diag["failure_index_or_none"]
        if first_unknown is not None and first_unknown < TRAIN_MINUTES:
            raise ValueError(f"MISSING_TRAINING_RISK_MARKS:{name}")
        d, life = barbell.risk_stats(c[:TRAIN_MINUTES], a[:TRAIN_MINUTES])
        if d <= 0 or life <= 0:
            raise ValueError(f"INSUFFICIENT_TRAINING_ADVERSE_RANGE:{name}")
        full_end = first_unknown or len(c)
        full_d, full_life = barbell.risk_stats(c[:full_end], a[:full_end])
        calibration[name] = {
            "training_daily_adverse_usd": round(d, 4),
            "training_lifetime_adverse_usd": round(life, 4),
            "full_daily_adverse_usd": round(full_d, 4),
            "full_lifetime_adverse_usd": round(full_life, 4),
            "base_k": min(.35, STARTING_EQUITY / float(scalars[name])),
            "first_unknown_base_at": (
                (source_replay.START + timedelta(minutes=first_unknown)).isoformat()
                if first_unknown is not None else None
            ),
            "source_fill_events_90d": int(events.filter(pl.col("alias") == name).height),
            "new_source_zero_event_fills_after_split": int(
                oos.filter(pl.col("alias") == name).height
            ),
            "source_file_sha": provenance["wallets"][name]["source_files_sha256"],
        }

    policies = portfolio_universe()
    screen: list[dict] = []
    for label, members, roles in policies:
        screen.append(run_replay(
            oos_batches[5], members, roles, calibration, scalars, panels,
            cost=6.0, delay=5, label=label
        ))
    # Rerun top non-breaching modeled outcomes across delay/cost combinations,
    # not only the historically fastest (where a fast breach is unacceptable).
    eligible = [r for r in screen
                if r["unknown"] is None
                and r["status"] != "CONTRACT_FLOOR_BREACH"]
    eligible.sort(key=lambda r: (
        0 if r["status"] == "CHALLENGE_TARGET_REACHED" else 1,
        0 if r["full_period_coincident_stress_usd_hindsight"] <= 400 else 1,
        -(r["net_usd"] or -100000),
        r["max_dd_usd"],
        r["name"],
    ))
    chosen = {r["name"] for r in eligible[:10]}
    validation: list[dict] = []
    for label, members, roles in policies:
        if label not in chosen:
            continue
        for delay, cost in ((2, 6.0), (2, 12.0), (5, 12.0), (5, 18.0)):
            validation.append(run_replay(
                oos_batches[delay], members, roles, calibration, scalars, panels,
                cost=cost, delay=delay, label=label,
            ))
    return {
        "schema": "ml4t66_barbell_protected_oos_20261106_v1",
        "evidence": "HISTORICAL_EVENT_ORACLE_UNQUALIFIED",
        "cohort": "ml4t-strict-66",
        "cohort_sha": sha,
        "source_fills_with_flat_coin_start": events.height,
        "oos_first_zero_source_fills": oos.height,
        "oos_first_zero_skipped_count": cut["pre_zero_source_fills_skipped"],
        "market_coin_count": len(panels),
        "market_coverage_sha256": sha256(
            json.dumps(coverage, sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
        "train": [source_replay.START.isoformat(),
                  (source_replay.START + timedelta(days=TRAIN_DAYS)).isoformat()],
        "oos": [(source_replay.START + timedelta(days=TRAIN_DAYS)).isoformat(),
                source_replay.END.isoformat()],
        "assumptions": {
            "sizing_only_uses_pre_split_adverse_marks": True,
            "wallet_universe_selection_was_retrospective": True,
            "source_nav_and_first_known_follower_receipt": "UNVERIFIED",
            "market_funding_broker_liquidity_and_margin": "MISSING",
            "oos_starts_flat_per_coin_only_after_observed_zero": True,
            "next_open_risk_flatten_with_costs": True,
            "pod_lifetime_hard_latch_after_intrabar_adverse": True,
            "pod_daily_hard_latch_after_intrabar_adverse": True,
            "account_floor_checks_simultaneous_adverse_ohlc_bound": True,
            "account_daily_floor_uses_close_intraday_hwm": True,
            "reference_contract": "USER_ASSUMED_5pct_DAILY_HWM_10pct_TRAILING_10pct_TARGET",
            "minimum_green_days": 0,
            "protected_portfolio_not_verified_source_account_replica": True,
            "independent_pod_books_no_broker_netting": True,
            "gross_and_concentration_pretrade_guards_not_enforced": True,
        },
        "candidate_wallets": calibration,
        "screen": screen,
        "validation": validation,
        "screen_status": dict(Counter(r["status"] for r in screen)),
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output = evaluate(args.db, args.source_root, args.market_root)
    target = args.output_root
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.is_symlink() or target.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_REPORT_DIRECTORY_REQUIRED")
    raw = (json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    digest = sha256(raw).hexdigest()
    path = target / f"ml4t66_barbell_protected_oos_{digest[:20]}.json"
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
    elif path.read_bytes() != raw:
        raise ValueError("IMMUTABLE_REPORT_HASH_CONFLICT")
    ranked = sorted(output["screen"], key=lambda x: (
        0 if x["status"] == "CHALLENGE_TARGET_REACHED" else 1,
        0 if x["unknown"] is None else 1,
        -float(x["net_usd"] or -999999),
        x["name"],
    ))
    print(json.dumps({
        "report_path": str(path),
        "sha256": digest,
        "screen_n": len(output["screen"]),
        "validation_n": len(output["validation"]),
        "statuses": output["screen_status"],
        "top_screen": [{
            "name": row["name"],
            "status": row["status"],
            "net_usd": row["net_usd"],
            "drawdown_usd": row["max_dd_usd"],
            "coin_stress_usd": row["full_period_coincident_stress_usd_hindsight"],
            "stops": sum(x["at"] is not None for x in row["pod_stops"].values())
        } for row in ranked[:15]],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
