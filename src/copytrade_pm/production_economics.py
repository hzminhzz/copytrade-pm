"""20-day research dossier using the existing joint-tape and contract engines.

Policy tapes must already encode each causally executed policy. This module never
fabricates policy fills, resizes hindsight PnL, or builds another execution simulator.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path

from .contract_actuary import Contract, simulate
from .pm_contract_selector import JointBlockBootstrap, load_tape
from .production_manifest import verify

POLICIES = ("FIXED", "VOLATILITY_THROTTLED", "BARRIER_AWARE")


def _probability(value: float, paths: int) -> dict:
    z = 1.959963984540054
    denominator = 1 + z * z / paths
    center = (value + z * z / (2 * paths)) / denominator
    half = z * math.sqrt(value * (1 - value) / paths + z * z / (4 * paths * paths)) / denominator
    return {
        "estimate": value,
        "lower_95": max(0, center - half),
        "upper_95": min(1, center + half),
        "uncertainty": "CONDITIONAL_MONTE_CARLO_BINOMIAL_NOT_MODEL_UNCERTAINTY",
    }


def evaluate(
    policy_tapes: dict[str, Path],
    *,
    predeclaration: dict | None,
    reviewer=None,
    follower_attestations: dict | None = None,
    paths: int = 10000,
    seed: int = 20261105,
    assumed_fee: float | None = None,
) -> dict:
    if type(paths) is not int or not 2 <= paths <= 250000:
        raise ValueError("MONTE_CARLO_PATHS")
    missing = sorted(set(POLICIES) - set(policy_tapes))
    blockers = []
    if missing or set(policy_tapes) - set(POLICIES):
        blockers.append("MATCHED_PREDECLARED_POLICY_TAPES_MISSING")
    if assumed_fee is not None and (not math.isfinite(assumed_fee) or assumed_fee <= 0):
        raise ValueError("CONTRACT_FEE")
    blockers.extend(
        [
            "ACCOUNT_RULEBOOK_UNAUTHENTICATED",
            "PAYOUT_TERMS_UNVERIFIED",
            "INDEPENDENT_ECONOMIC_REVIEW_REQUIRED",
        ]
    )
    if assumed_fee is None:
        blockers.append("CONTRACT_FEE_UNKNOWN")
    declaration = None
    if predeclaration and reviewer:
        try:
            declaration = verify(predeclaration, reviewer, "economics-reviewer")
            if declaration["schema"] != "economics_predeclaration_v1":
                raise ValueError("DECLARATION_SCHEMA")
            if (
                not declaration["known_at_ms"]
                <= declaration["train_end_ms"]
                < declaration["oos_start_ms"]
            ):
                raise ValueError("POST_HOC_SELECTION_OR_OVERLAP")
            if set(declaration["policy_code_shas"]) != set(POLICIES):
                raise ValueError("POLICY_CODE_NOT_PREDECLARED")
        except ValueError, KeyError, TypeError:
            blockers.append("PREDECLARATION_SIGNATURE_OR_CAUSAL_BOUNDARY")
            declaration = None
    else:
        blockers.append("PREDECLARATION_OR_REVIEW_AUTHORITY_MISSING")
    results = {}
    windows = set()
    sensitivity = {}
    for policy in POLICIES:
        if policy not in policy_tapes:
            continue
        try:
            tape = load_tape(policy_tapes[policy])
            window = (
                tape.portfolio_id,
                tape.definition_sha256,
                tape.members,
                tape.first_interval_utc,
                tape.end_exclusive_utc,
                tape.step_minutes,
            )
            windows.add(window)
            if tape.source_status != "PROSPECTIVE_FOLLOWER_UNATTESTED":
                blockers.append("SYNTHETIC_OR_UNATTESTED_FOLLOWER_TAPE")
            if declaration:
                start = int(datetime.fromisoformat(tape.first_interval_utc).timestamp() * 1000)
                end = int(datetime.fromisoformat(tape.end_exclusive_utc).timestamp() * 1000)
                if (
                    start < declaration["oos_start_ms"]
                    or end > declaration["oos_end_ms"]
                    or tape.definition_sha256 != declaration["portfolio_definition_sha256"]
                ):
                    raise ValueError("OOS_WINDOW_OR_PORTFOLIO_SCOPE")
            attested = False
            if follower_attestations and reviewer and policy in follower_attestations:
                proof = verify(
                    follower_attestations[policy], reviewer, "follower-economics-reviewer"
                )
                attested = (
                    proof["tape_sha256"] == tape.sha256
                    and proof["policy"] == policy
                    and proof["causal_receipts"] is True
                    and proof["full_account_scope"] is True
                    and proof["executable_fills_independently_matched"] is True
                    and proof["costs_marketability_margin_liquidity_verified"] is True
                    and proof["batch_seconds"] == 300
                )
            if not attested:
                blockers.append("INDEPENDENT_FULL_FOLLOWER_TAPE_ATTESTATION_MISSING")
            if tape.step_minutes > 60 and tape.source_status != "SYNTHETIC_FIXTURE":
                raise ValueError("INTRADAY_BARRIERS_UNOBSERVABLE")
            contract = Contract(
                "Provisional 10k / target 1k / daily 500 / trailing 1k",
                assumed_fee or 1,
                (1000,),
                1000,
                500,
                1000,
                500,
                False,
            )
            stats = None
            costs = []
            for extra_cost in (0.0, 5.0, 20.0):
                # Identical joint day blocks across policies and cost scenarios.
                innovations = JointBlockBootstrap(
                    tape, paths=paths, max_days=40, block_days=7, seed=seed
                )
                run = simulate(
                    contract,
                    paths=paths,
                    seed=seed,
                    evaluation_days=20,
                    funded_days=20,
                    steps_per_day=tape.increments.shape[1],
                    daily_sigma=math.sqrt(tape.increments.shape[1]),
                    daily_mu=0,
                    daily_cost=extra_cost,
                    innovations=innovations,
                )
                if extra_cost == 0:
                    stats = run
                costs.append(
                    {
                        "extra_daily_cost_usd": extra_cost,
                        "pass_within_20_days": run["evaluation_pass_probability"],
                        "net_ev": run["net_ev"] if assumed_fee is not None else None,
                    }
                )
            assert stats is not None
            standard_error = stats["payout_standard_error"]
            ev = stats["net_ev"] if assumed_fee is not None else None
            results[policy] = {
                "tape_sha256": tape.sha256,
                "source_status": tape.source_status,
                "pass_within_20_days": _probability(stats["evaluation_pass_probability"], paths),
                "breach_before_pass": _probability(
                    stats["evaluation_breach_before_pass_probability"], paths
                ),
                "timeout": _probability(stats["evaluation_timeout_probability"], paths),
                "conditional_pass_time_days": stats["conditional_pass_time_days"],
                "conditional_pass_time_standard_error": stats[
                    "conditional_pass_time_standard_error"
                ],
                "maximum_daily_adverse_excursion": stats["maximum_daily_adverse_excursion"],
                "made_95th_percentile": stats["made_95th_percentile"],
                "expected_contract_value": {
                    "estimate": ev,
                    "lower_95": ev - 1.96 * standard_error if ev is not None else None,
                    "upper_95": ev + 1.96 * standard_error if ev is not None else None,
                },
                "model_scope": "JOINT_BLOCK_RESAMPLING_OF_SUPPLIED_NET_TAPE",
                "history_days": tape.days,
                "independent_tape_attested": attested,
            }
            sensitivity[policy] = costs
        except ValueError, KeyError, TypeError, OSError:
            blockers.append("TAPE_" + policy + "_INVALID_OR_INCOMPLETE")
    if len(windows) > 1:
        blockers.append("POLICY_WINDOWS_OR_IDENTITIES_UNMATCHED")
    return {
        "schema": "production_20day_economics_v1",
        "verdict": "BLOCKED_ECONOMICS",
        "blockers": sorted(set(blockers)),
        "missing_policies": missing,
        "policies": results,
        "no_buy": {"net_ev": 0, "fee": 0, "breach_probability": 0},
        "selection": "NO_POST_HOC_WINNER",
        "seed": seed,
        "paths": paths,
        "evaluation_days": 20,
        "funded_days_scenario": 20,
        "assumed_fee": assumed_fee,
        "sensitivity": {
            "extra_daily_cost": sensitivity,
            "batch_2m_vs_5m": "UNKNOWN_MATCHED_TAPES_REQUIRED",
            "margin_liquidity_gap_stale": "UNKNOWN_EXECUTABLE_VARIANT_TAPES_REQUIRED",
        },
        "uncertainty_limitations": [
            "Sampling uncertainty does not bound regime/model error",
            "Monte Carlo paths are not independent prospective trading observations",
            "No winner is selected from the holdout",
            "Sub-interval jumps can breach between observations",
        ],
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for policy in POLICIES:
        parser.add_argument("--" + policy.lower().replace("_", "-"), type=Path)
    parser.add_argument("--paths", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--assumed-fee", type=float)
    args = parser.parse_args(argv)
    tapes = {p: getattr(args, p.lower()) for p in POLICIES if getattr(args, p.lower()) is not None}
    try:
        result = evaluate(
            tapes,
            predeclaration=None,
            paths=args.paths,
            seed=args.seed,
            assumed_fee=args.assumed_fee,
        )
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 2
    except ValueError, OSError, ImportError:
        print(
            '{"verdict":"BLOCKED_ECONOMICS","reason":"INPUT_OR_DEPENDENCY","trading_authorized":false}'
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
