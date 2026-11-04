"""Phase 6B final evidence convergence: source SHA gates, honest scope and verdict.

This program only verifies saved immutable research generations. It must never
promote conditional known-leg stress to validated account economics.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .pm_phase6b import WALLETS, fingerprint, safe_write_json


def verify_evidence(
    *,
    phase5: Path,
    source: Path,
    minute: Path,
    activity: Path,
    historical_equity: Path,
    stress: Path,
    blocked: Path,
) -> dict:
    """Fail-closed cross-generation audit, no network, no accounts altered."""
    files = {
        "phase5_frozen_portfolios": phase5,
        "phase6b_source": source,
        "phase6b_native_minute": minute,
        "phase6b_observed_activity": activity,
        "phase6b_official_sparse_equity": historical_equity,
        "phase6b_conditional_stress": stress,
        "phase6b_blocked_account_scenarios": blocked,
    }
    sha = {name: fingerprint(path) for name, path in files.items()}
    data = {name: json.loads(path.read_text()) for name, path in files.items()}
    frozen = data["phase5_frozen_portfolios"]
    first = data["phase6b_source"]
    native = data["phase6b_native_minute"]
    observed = data["phase6b_observed_activity"]
    history = data["phase6b_official_sparse_equity"]
    modeled = data["phase6b_conditional_stress"]
    blocked_matrix = data["phase6b_blocked_account_scenarios"]
    phase5_shas = sha["phase5_frozen_portfolios"]
    source_sha = sha["phase6b_source"]
    minute_sha = sha["phase6b_native_minute"]
    conditions = {
        "phase5_frozen_portfolio_count": len(frozen["portfolios"]) == 5,
        "source_wallet_count": len(first["wallets"]) == 7,
        "source_only_wallets_covered": set(first["wallets"])
        == set().union(*(set(members) for members in WALLETS.values())),
        "unique_markets_reconciled": set(first["market_day_inventory"])
        == set(native["instruments"]),
        "native_audit_source_sha": native.get("original_coverage_sha256") == source_sha,
        "activity_source_sha": observed.get("source_coverage_sha256") == source_sha,
        "activity_minute_sha": observed.get("native_minute_sha256") == minute_sha,
        "activity_phase5_sha": observed.get("phase5_sha256") == phase5_shas,
        "nonperp_fill_scope_accounting_consistent": all(
            x["source_position"].get("excluded_nonperp_fills_by_scope", {})
            == observed.get("wallets", {}).get(alias, {}).get("excluded_nonperp_fills_by_scope", {})
            and x["source_position"].get("excluded_nonperp_collateral_reconciled") is False
            and observed.get("wallets", {})
            .get(alias, {})
            .get("excluded_nonperp_collateral_reconciled")
            is False
            for alias, x in first["wallets"].items()
        ),
        "ACT08_spot_fills_explicitly_excluded": first["wallets"]["ACT08"]["source_position"]
        .get("excluded_nonperp_fills_by_scope", {})
        .get("SPOT")
        == 4,
        "official_history_phase5_sha": history.get("frozen_phase5_sha256") == phase5_shas,
        "stress_source_sha": modeled.get("source_file_audit_sha256") == source_sha,
        "stress_minute_sha": modeled.get("native_market_audit_sha256") == minute_sha,
        "blocked_source_sha": blocked_matrix.get("source_coverage_sha256") == source_sha,
        "blocked_minute_sha": blocked_matrix.get("minute_coverage_sha256") == minute_sha,
        "blocked_scenario_count": blocked_matrix.get("scenario_rows") == 180,
        "blocked_attempted_stresses_zero": blocked_matrix.get("attempted_stresses") == 0,
        "historical_equity_not_reconciled": history.get("portfolio_total_equity_reconciled")
        is False,
        "first_known_not_demonstrated": history.get("historical_first_known_verified") is False,
        "modeled_account_pnl_not_claimed": modeled.get("account_challenge_curve") is None,
        "all_540_model_states_nonactionable": (
            len(modeled["daily_snapshots"]) == 540
            and all(
                r["actionable"] is False
                and r["actual_follower_pnl_usd"] is None
                and r["actual_challenge_first_passage"] is None
                and not r["PM03_actual_supervisor_unknown_source_gate"]["approved_new_risk"]
                for r in modeled["daily_snapshots"]
            )
        ),
        "source_positions_not_completely_reconstructed": all(
            x["full_account_book_qualified"] is False for x in first["wallets"].values()
        ),
    }
    if not all(conditions.values()):
        raise ValueError(
            "PHASE6B_EVIDENCE_INCOMPLETE_OR_CONFLICT:"
            + ",".join(k for k, v in conditions.items() if not v)
        )
    model_rows = modeled["daily_snapshots"]
    pm03 = Counter(
        x["PM03_actual_supervisor_unknown_source_gate"]["PM03_state"] for x in model_rows
    )
    market = native["instruments"]
    summary = {
        "schema": "phase6b_final_research_disposition_v1",
        "historical_provider_acquisition_completed_at_utc": history.get("completed_at"),
        "evidence_shas": sha,
        "cross_generation_integrity": conditions,
        "research_engineering": "COMPLETE",
        "whole_wallet_economic_replay": "BLOCKED",
        "scientific_qualification": "NOT_ESTABLISHED",
        "trading_authorization": False,
        "broker_or_service_actions": False,
        "follower_account_90d_pnl": None,
        "gemini_tiny_drawdowns_independently_verified": False,
        "account_challenge_first_passage": None,
        "wallets": len(first["wallets"]),
        "wallet_source_files_hash_verified": sum(
            bool(x["source_file_sha256"]) for x in first["wallets"].values()
        ),
        "study_days": 90,
        "native_markets": len(market),
        "spot_fills_outside_perp_replay": {
            alias: x["source_position"]["excluded_nonperp_fills_by_scope"]
            for alias, x in first["wallets"].items()
        },
        "spot_collateral_and_equity_reconciled": False,
        "native_instrument_minutes_verified": sum(x["verified_minutes"] for x in market.values()),
        "native_instrument_minutes_unweighted_expected": sum(
            x["expected_minutes"] for x in market.values()
        ),
        "native_markets_whole_window_covered": sum(
            x["missing_or_invalid_minutes"] == 0 for x in market.values()
        ),
        "observed_position_instrument_minutes": observed["total_observed_exposure_minutes"],
        "unverified_observed_position_instrument_minutes": observed[
            "total_unverified_exposure_minutes"
        ],
        "historical_portfolio_history_wallets": len(history["wallets"]),
        "historical_equity_intervals_max_gap_hours": {
            k: x["history"]["allTime"]["maximum_gap_hours"] for k, x in history["wallets"].items()
        },
        "conditional_stress_daily_snapshots": len(model_rows),
        "conditional_one_hour_static_leg_observations": sum(
            x["S1_frozen_one_hour_held_leg_diagnostic"]["verified_prior_held_legs"]
            for x in model_rows
        ),
        "PM03_fail_closed_states": dict(pm03),
        "S6_missing_or_unknown_risk_refusals": sum(
            x["S6_missing_feed_response_model"]["would_block_new_risk"] for x in model_rows
        ),
        "S8_fixed_30day_splits": {
            k: v for k, v in modeled["S8_30_day_temporal_sensitivity"].items()
        },
        "frozen_portfolio_model_summary": modeled["portfolio_summary"],
        "blocked_account_scenarios": blocked_matrix["scenario_rows"],
        "stress_model_frozen_scalars_are_not_equity_faithful": True,
        "remaining_scientific_blockers": [
            "CANNOT_RETROACTIVELY_ESTABLISH_FIRST_LOCAL_RECEIPT_CLOCKS_FROM_HISTORICAL_VENDOR_FILLS",
            "HISTORICAL_ALL_DEX_ACCOUNT_AND_SUBACCOUNT_EQUITY_FUNDING_UNRECONCILED",
            "POSITION_BASIS_AND_ACCOUNT_SCOPE_INCOMPLETE",
            "NATIVE_MINUTE_MARKETS_INCOMPLETE_AND_QUOTE_CAPACITY_UNVERIFIED",
            "REAL_FOLLOWER_ORDER_EXECUTION_AND_FIRST_PASSAGE_OUTCOMES_UNAVAILABLE",
        ],
        "decision": "PRESERVE_PHASE5_RESEARCH_ONLY_RUN_FUTURE_PROSPECTIVE_PAPER_EVIDENCE",
    }
    return summary


def finish(*, output: Path, **sources: Path) -> dict:
    report = verify_evidence(**sources)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    checksum = safe_write_json(output / "final_disposition.json", report)
    return {
        "status": report["research_engineering"],
        "science": report["scientific_qualification"],
        "science_blockers": report["remaining_scientific_blockers"],
        "sha256": checksum,
        "output": str(output / "final_disposition.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "phase5",
        "source",
        "minute",
        "activity",
        "historical_equity",
        "stress",
        "blocked",
    ):
        parser.add_argument("--" + arg.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = {
        k: getattr(args, k)
        for k in (
            "phase5",
            "source",
            "minute",
            "activity",
            "historical_equity",
            "stress",
            "blocked",
        )
    }
    print(json.dumps(finish(output=args.output, **inputs), indent=2))


if __name__ == "__main__":
    main()
