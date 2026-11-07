"""Consolidate pinned HL94 PM03 candidate replays without reoptimizing or rereading bars.

The rank is DESCRIPTIVE: early-stop PnL and open-inventory MTM are censored.
No source equity / historical qualification / live orders.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path

from .pm_hl94_research import REPLAY_SCHEMA, SCHEMA, write_evidence

SUMMARY_SCHEMA = "hl94_three_pod_descriptive_portfolio_comparison_v1"


def _verified_file(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest[:20] not in path.stem:
        raise ValueError("RESEARCH_REPORT_FILENAME_SHA_MISMATCH")
    return json.loads(raw), digest


def consolidate(screen_path: Path, replay_paths: tuple[Path, ...]) -> dict:
    screen, screen_sha = _verified_file(screen_path)
    if screen["schema"] != SCHEMA or not replay_paths:
        raise ValueError("INVALID_HL94_SUMMARY_INPUTS")
    source = screen["source_file_sha256"]
    selection = {
        tuple(sorted(x["wallets"]))
        for x in screen["top_10_candidate_triples"] + screen["frozen_validation_triples"]
    }
    complete = {}
    manifest = []
    common = None
    for path in replay_paths:
        report, digest = _verified_file(path)
        if report.get("schema") != REPLAY_SCHEMA:
            raise ValueError("HL94_REPLAY_SCHEMA_INVALID")
        if report.get("screening_source_sha256") != screen_sha:
            raise ValueError("HL94_REPLAY_SCREENING_HASH_DRIFT")
        params = {
            "risk_scale": report.get("risk_scale"),
            "pod_hard_stop_usd": report.get("pod_hard_stop_usd"),
            "delay_minutes": report.get("delay_minutes"),
            "cost_multiplier": report.get("cost_multiplier"),
            "capacity_enforced": report.get("capacity_enforced"),
        }
        if common is None:
            common = params
        elif common != params:
            raise ValueError("MIXED_RISK_OR_EXECUTION_SCENARIOS")
        manifest.append({"path": str(path), "sha256": digest,
                         "verified_market_days": len(report.get("source_market_day_sha256", {}))})
        grouped = defaultdict(dict)
        for row in report["results"]:
            trio = tuple(sorted(row["wallets"]))
            if trio not in selection or row["phase"] not in ("DISCOVERY", "VALIDATION"):
                raise ValueError("UNFROZEN_WALLET_COMBO")
            if row["phase"] in grouped[trio]:
                raise ValueError("DUPLICATE_REPLAY_PHASE")
            grouped[trio][row["phase"]] = row
        for trio, phases in grouped.items():
            if set(phases) != {"DISCOVERY", "VALIDATION"}:
                raise ValueError("INCOMPLETE_TWO_WINDOW_REPLAY")
            if trio in complete:
                raise ValueError("REPLAY_COMBINATION_DUPLICATED")
            complete[trio] = phases
    entries = []
    for trio, parts in sorted(complete.items()):
        discovery = parts["DISCOVERY"]
        validation = parts["VALIDATION"]
        counters = validation.get("counters", {})
        tracking = validation.get("action_weighted_exposure_tracking", {})
        outcome = validation.get("stop_reason")
        date_end = validation.get("observed_through")
        if outcome == "SIMULATED_STAGE_TARGET_REACHED":
            verdict = "TARGET_FIRST_PASSAGE_PROXY"
        elif outcome == "CONTRACTUAL_DRAWDOWN_BREACH":
            verdict = "LOSS_FLOOR_BREACH"
        elif outcome and outcome.startswith("MISSING_"):
            verdict = "MISSING_PRICE_CENSORED"
        else:
            verdict = "OPEN_INVENTORY_CENSORED_OR_OTHER"
        entries.append({
            "wallets": list(trio),
            "discovery_pnl_usd_at_stop_or_end": discovery.get("pnl_usd"),
            "discovery_stop_reason": discovery.get("stop_reason"),
            "validation_pnl_usd_at_stop_or_end": validation.get("pnl_usd"),
            "validation_observed_through": date_end,
            "validation_verdict": verdict,
            "max_observed_drawdown_usd": validation.get("max_observed_drawdown_usd"),
            "worst_observed_day_usd": validation.get("worst_observed_day_pnl_usd"),
            "validation_net_orders": counters.get("hypothetical_net_orders", 0),
            "fees_usd": counters.get("fees_usd", "0"),
            "funding_debit_usd": counters.get("funding_debit_usd", "0"),
            "turnover_usd": counters.get("hypothetical_order_notional_usd", "0"),
            "capacity_diagnostic_not_causal": counters.get("orders_above_5pct_minute_volume_or_zero_volume", 0),
            "internal_crosses": counters.get("internal_crosses", 0),
            "suspended_pods": validation.get("suspended_pods", []),
            "tracking_fraction_by_pod": {
                wallet: point.get("action_weighted_tracking_error_fraction")
                for wallet, point in tracking.items()
            },
            "per_wallet_pnl_usd": validation.get("per_wallet_pnl_usd", {}),
            "not_comparable_to_full_period_pnl": True,
        })
    entries.sort(key=lambda x: (
        0 if x["validation_verdict"] == "TARGET_FIRST_PASSAGE_PROXY" else
        1 if x["validation_verdict"] == "OPEN_INVENTORY_CENSORED_OR_OTHER" else
        2 if x["validation_verdict"] == "LOSS_FLOOR_BREACH" else 3,
        -D(x["validation_pnl_usd_at_stop_or_end"])
        if x["validation_pnl_usd_at_stop_or_end"] is not None else D("Infinity"),
    ))
    return {
        "schema": SUMMARY_SCHEMA,
        "status": "DESCRIPTIVE_RANKING_OF_CENSORED_FIXED_K_REPLAYS",
        "screening_source_sha256": screen_sha,
        "all_94_wallet_source_file_hash_count": len(source),
        "wallets_audited": screen["raw_wallet_count"],
        "discovery_shortlist": screen["shortlist"],
        "discovery_combos_screened": screen["all_discovery_triples_screened"],
        "scenarios": common,
        "raw_data_manifests": manifest,
        "replayed_portfolios": len(entries),
        "ranking": entries,
        "limitations": [
            "Historical source-equity replication waived; k based on discovery observed gross and realized worst day",
            "Only anchored observed partial source books; omitted source hedge/collateral may change outcomes",
            "Outcome stop dates and open positions censor returns, so ranked PnL is not common-horizon return",
            "Gemini PDF previously examined the October interval, so validation is not untouched",
            "Source discovery filters/ex-post Propr display snapshot introduce selection bias",
            "Simulated account uses PM03 and gross-cap/pod-loss overlay; independent PM04 supervisor not invoked",
            "No first-known follower receipts, actual Propr execution capacity, or real-account rule attestation",
        ],
        "scientifically_qualified": False,
        "live_trading_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--replays", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = consolidate(args.screen, tuple(args.replays))
    path, digest = write_evidence(args.out, summary)
    print(json.dumps({
        "report": str(path), "sha256": digest, "portfolios": summary["replayed_portfolios"],
        "ranking": [{
            "wallets": r["wallets"], "discovery_pnl": r["discovery_pnl_usd_at_stop_or_end"],
            "validation_pnl": r["validation_pnl_usd_at_stop_or_end"],
            "validation_verdict": r["validation_verdict"],
        } for r in summary["ranking"]]}, sort_keys=True))


if __name__ == "__main__":
    main()
