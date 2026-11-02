"""Consolidate verified SHA-addressed Q3 equity-weight studies without promoting PnL.

Requires 1 base A/B/C report, exactly 7 disjoint mixed-portfolio batches,
and 3 selected custom-trio sensitivity reports. Every source evidence digest
must agree. This is a reporting utility for historical exploratory research,
not a candidate authorization or a live trading tool.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .pm_research import _write_private_evidence
from .pm_sparse_equity_portfolio import SCHEMA

REPORT_SCHEMA = "pm_q3_sparse_equity_84_replay_summary_v1"
MIXED_COUNT = 81
FROZEN_COUNT = 3
EXPECTED_SENSITIVITIES = frozenset({"BASE_8D_1X", "NAV_16D_1X", "COST_8D_2X", "CAPACITY_8D_1X"})


def _load_file(path: Path):
    content = path.read_bytes()
    digest = sha256(content).hexdigest()
    if not path.name.startswith("pm01-36-wallets-" + digest[:20] + ".json"):
        raise ValueError("REPLAY_REPORT_CONTENT_SHA_INVALID")
    parsed = json.loads(content)
    if parsed.get("schema") != SCHEMA:
        raise ValueError("REPLAY_REPORT_SCHEMA_INVALID")
    return parsed, digest


def _fingerprint(doc: dict):
    return (
        doc["source_fill_manifests"],
        doc["source_account_raw_sha256"],
        doc["propr_browser_scope_sha256"],
        doc["risk_caps_usd"],
        doc["execution"],
        doc["portfolio_membership"],
    )


def _compact(row: dict):
    track = row.get("action_weighted_exposure_tracking") or {}
    return {
        "combo": row["name"],
        "wallets": row["wallets"],
        "scenario": row["scenario"],
        "status": row["status"],
        "stop_reason": row.get("stop_reason"),
        "observed_through": row.get("observed_through"),
        "modeled_pnl_at_stop_usd": row.get("pnl_usd"),
        "max_observed_drawdown_usd": row.get("max_observed_drawdown_usd"),
        "hypothetical_fills": row.get("counters", {}).get("hypothetical_net_orders", 0),
        "capacity_over_5pct_minute_volume": row.get("counters", {}).get(
            "orders_above_5pct_minute_volume_or_zero_volume", 0
        ),
        "capacity_blocked_rebalances": row.get("counters", {}).get("capacity_blocked_orders", 0),
        "capacity_volume_reference": row.get("capacity_volume_reference"),
        "risk_veto_batches": row.get("counters", {}).get("risk_budget_rejected_batches", 0),
        "source_exposure_tracking_errors": {
            wallet: stats["action_weighted_tracking_error_fraction"]
            for wallet, stats in sorted(track.items())
        },
        "source_equity_skipped_decisions": {
            wallet: sum(
                v
                for k, v in detail["counters"].items()
                if k.startswith("skipped_sizing_decisions_")
            )
            for wallet, detail in sorted(row.get("equity_sizing", {}).items())
        },
    }


def aggregate(
    base: Path,
    mixed_batches: tuple[Path, ...],
    custom_runs: tuple[Path, ...],
) -> dict:
    origin, origin_sha = _load_file(base)
    if origin.get("mixed_batch", {}).get("only_mixed"):
        raise ValueError("BASE_REPORT_MUST_CONTAIN_A_B_C")
    expected = _fingerprint(origin)
    base_rows = [r for r in origin["results"] if r["scenario"] == "BASE_8D_1X"]
    if sorted(r["name"] for r in base_rows) != ["A", "B", "C"]:
        raise ValueError("BASE_NOT_EXACTLY_A_B_C")
    if {r["scenario"] for r in origin["results"]} != EXPECTED_SENSITIVITIES:
        raise ValueError("BASE_SENSITIVITIES_INCOMPLETE")
    if len(mixed_batches) != 7 or len(custom_runs) != 3:
        raise ValueError("EXPECTED_7_BATCHES_AND_3_CUSTOM_STUDIES")

    evidence = {"abc_base": origin_sha, "mixed_batches": {}, "custom_sensitivity": {}}
    all_rows = list(base_rows)
    seen_batch_offsets = set()
    for file in mixed_batches:
        doc, digest = _load_file(file)
        if _fingerprint(doc) != expected:
            raise ValueError("MIXED_SOURCE_EVIDENCE_MISMATCH")
        batch = doc.get("mixed_batch", {})
        offset = batch.get("offset")
        if (
            not batch.get("only_mixed")
            or offset in seen_batch_offsets
            or not isinstance(offset, int)
            or batch.get("total_mixed_available") != MIXED_COUNT
        ):
            raise ValueError("INVALID_MIXED_BATCH_INDEX")
        seen_batch_offsets.add(offset)
        if batch.get("executed_mixed_count") != len(doc["results"]):
            raise ValueError("MIXED_BATCH_COUNT_MISMATCH")
        if any(
            row["scenario"] != "BASE_8D_1X" or not row["name"].startswith("MIX_")
            for row in doc["results"]
        ):
            raise ValueError("NONBASE_MIXED_ROW")
        evidence["mixed_batches"][str(offset)] = digest
        all_rows.extend(doc["results"])
    if sorted(seen_batch_offsets) != [0, 12, 24, 36, 48, 60, 72]:
        raise ValueError("MIXED_BATCH_COVERAGE_GAP")
    names = [r["name"] for r in all_rows]
    if len(names) != MIXED_COUNT + FROZEN_COUNT or len(set(names)) != len(names):
        raise ValueError("MISSING_OR_DUPLICATE_THREE_WALLET_COMBO")

    sensitive = {}
    for file in custom_runs:
        doc, digest = _load_file(file)
        if _fingerprint(doc) != expected:
            raise ValueError("CUSTOM_SOURCE_EVIDENCE_MISMATCH")
        trio = doc.get("custom_trio")
        if not isinstance(trio, list) or len(set(trio)) != 3:
            raise ValueError("CUSTOM_TRIO_INVALID")
        key = "+".join(trio)
        if key in sensitive or len(doc["results"]) != 4:
            raise ValueError("CUSTOM_DUPLICATE_OR_INCOMPLETE")
        if {r["scenario"] for r in doc["results"]} != EXPECTED_SENSITIVITIES:
            raise ValueError("CUSTOM_SENSITIVITIES_INCOMPLETE")
        if any(r["name"] != "CUSTOM_" + "_".join(trio) for r in doc["results"]):
            raise ValueError("CUSTOM_MEMBERSHIP_CHANGED")
        evidence["custom_sensitivity"][key] = digest
        sensitive[key] = {
            label: _compact(next(r for r in doc["results"] if r["scenario"] == label))
            for label in sorted(EXPECTED_SENSITIVITIES)
        }

    counts = dict(Counter(r.get("stop_reason") for r in all_rows))
    return {
        "schema": REPORT_SCHEMA,
        "status": "EXECUTED_84_CONDITIONAL_HINDSIGHT_ACCOUNT_SCENARIOS",
        "evidence_sha256": evidence,
        "studied_utc_days": origin["study_days"],
        "studied_start_utc": origin["source_window_inclusive_start"],
        "studied_end_exclusive_utc": origin["source_window_exclusive_end"],
        "wallets": origin["portfolio_membership"],
        "initial_follower_cash_usd": origin["account_initial_usd"],
        "capital_per_pod_usd": origin["pod_capital_usd"],
        "source_account_nav_points": {
            wallet: {
                "count": info["q3_points"],
                "max_gap_hours": info["q3_max_gap_hours_between_samples"],
            }
            for wallet, info in sorted(origin["source_account_nav_audit"].items())
        },
        "source_episode_eligibility": origin["source_episode_eligibility"],
        "market_policy": origin["execution"],
        "simulated_risk_caps_usd": origin["risk_caps_usd"],
        "total_unique_3wallet_combinations": len(all_rows),
        "historical_base_outcome_counts": counts,
        "frozen_A_B_C_baseline": {row["name"]: _compact(row) for row in base_rows},
        "frozen_A_B_C_sensitivity": {
            wallet: {
                row["scenario"]: _compact(row) for row in origin["results"] if row["name"] == wallet
            }
            for wallet in ("A", "B", "C")
        },
        "all_84_baseline_outcomes": [
            _compact(row) for row in sorted(all_rows, key=lambda r: r["name"])
        ],
        "post_selected_custom_sensitivity": sensitive,
        "status_assessment": {
            "historical_whole_wallet_source_equity_at_every_decision": "UNAVAILABLE",
            "complete_wallet_book": "UNAVAILABLE",
            "propr_executable_orders": "UNVERIFIED",
            "source_event_first_known_at_decision": "UNVERIFIED_HINDSIGHT",
            "sampling_and_selection": "POST_HOC_84_COMBOS_SAME_QUARTER_NO_UNUSED_HOLDOUT",
            "modeled_profit_target_is_live_pass": False,
            "verified_pass_probability": None,
            "valid_best_wallet_combo": None,
            "qualification": False,
            "trading_authorized": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--mixed-batches", required=True, nargs=7, type=Path)
    parser.add_argument("--custom-runs", required=True, nargs=3, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = aggregate(
        args.base,
        tuple(args.mixed_batches),
        tuple(args.custom_runs),
    )
    path, signature = _write_private_evidence(args.out, output)
    print(
        json.dumps(
            {
                "path": str(path),
                "sha256": signature,
                "study_days": output["studied_utc_days"],
                "unique_combinations": output["total_unique_3wallet_combinations"],
                "reasons": output["historical_base_outcome_counts"],
                "A_B_C": output["frozen_A_B_C_baseline"],
                "selected": {
                    trio: {
                        label: {
                            "stop_reason": row["stop_reason"],
                            "modeled_pnl_at_stop_usd": row["modeled_pnl_at_stop_usd"],
                            "capacity_blocked_rebalances": row["capacity_blocked_rebalances"],
                        }
                        for label, row in runs.items()
                    }
                    for trio, runs in output["post_selected_custom_sensitivity"].items()
                },
                "qualified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
