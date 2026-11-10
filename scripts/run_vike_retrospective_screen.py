"""Research-only Vike retro-k OOS screen and durable private rank receipt.

A callable orchestration seam only: reuses the v3 offline Polars model and
versioned cache. No registry writes, live source changes or portfolio risk permits.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

from copytrade_pm.pm_offline_job import run_offline_job
from copytrade_pm.pm_v4_fast_screen import RETRO_REPORT, _v2_source_files
from scripts.research_vike_prewindow_k import checked_publish


def registry_exclusions(registry_db: Path) -> tuple[dict[str, list[str]], str]:
    """Use authoritative SQLite metadata strictly read-only; never clear exclusions."""
    path = Path(registry_db).resolve(strict=True)
    if path.is_symlink() or not path.is_file():
        raise ValueError("MISSING_OR_UNSAFE_REGISTRY_DATABASE")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("REGISTRY_PHYSICAL_INTEGRITY_FAILED")
        excluded: dict[str, set[str]] = {}
        for address, reason in conn.execute(
            "SELECT w.address, e.reason FROM exclusions e JOIN wallets w ON w.wallet_id=e.wallet_id"
        ):
            key = sha256(address.lower().encode()).hexdigest()
            excluded.setdefault(key, set()).add("owner:" + reason)
        for address, reason in conn.execute("SELECT address,reason FROM propfirm_exclusions"):
            key = sha256(address.lower().encode()).hexdigest()
            excluded.setdefault(key, set()).add("prop:" + reason)
    ordered = {key: sorted(value) for key, value in sorted(excluded.items())}
    fingerprint = sha256(
        json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ordered, fingerprint


def apply_research_screening(
    ranking: list[dict], exclusions: dict[str, list[str]]
) -> tuple[list[dict], list[dict]]:
    """Preserve every wallet's result; exclusions veto only proposed shortlist."""
    selected = []
    blocked_positive = []
    for row in ranking:
        reasons = exclusions.get(row["wallet_sha256"], [])
        row["current_registry_exclusions"] = reasons
        base = row["base"]
        if base["estimated_complete_episodes"] <= 0:
            verdict = "NOT_ECONOMICALLY_ESTIMABLE"
        elif base["estimated_net_pnl"] is None or base["estimated_net_pnl"] <= 0:
            verdict = "NO_POSITIVE_BASE_EVIDENCE"
        elif reasons:
            verdict = "EXCLUDED_BY_CURRENT_REGISTRY"
            blocked_positive.append(row)
        elif base["estimated_complete_episodes"] < 10 or row["evaluation_observation_days"] < 30:
            verdict = "BELOW_SHORTLIST_OBSERVATION_FLOOR"
        else:
            verdict = "RESEARCH_SHORTLIST_ONLY_NO_ADMISSION"
            selected.append(row)
        row["research_selection"] = verdict
    return selected, blocked_positive


def run(
    *,
    jobfile: Path,
    input_root: Path,
    source_root: Path,
    market_root: Path,
    cache_root: Path,
    output_root: Path,
    registry_db: Path,
) -> dict:
    result = run_offline_job(
        jobfile,
        input_root=input_root,
        source_root=source_root,
        market_root=market_root,
        cache_root=cache_root,
    )
    if result["schema"] != RETRO_REPORT or result["order_route"] != "NONE":
        raise ValueError("RETROSPECTIVE_RESEARCH_ROUTE_REQUIRED")
    policy = json.loads(
        (input_root / json.loads(jobfile.read_bytes())["k_policy_path"]).read_bytes()
    )
    aliases = {}
    for path in _v2_source_files(source_root):
        address = json.loads(path.read_bytes())["address"].lower()
        wallet = sha256(address.encode()).hexdigest()
        aliases[wallet] = path.stem.split("_0x")[0]
    ranking = []
    for wallet in result["wallet_ranking"]:
        account = wallet["account_sha256"]
        row = {
            "wallet_sha256": account,
            "alias": aliases.get(account, "UNMAPPED"),
            "k": policy["wallets"].get(account, {}).get("k"),
            "training_observation_days": policy["wallets"].get(account, {}).get("observation_days"),
            "evaluation_observation_days": wallet["observation_days"],
            "supported_source_episodes": wallet["supported_episodes"],
            "episode_candidates": wallet["episodes"],
            "base": wallet["scenarios"]["BASE"],
            "delayed": wallet["scenarios"]["DELAYED"],
            "adverse": wallet["scenarios"]["ADVERSE"],
            "sensitivity": wallet["sensitivity"],
            "research_diagnostic": "RANKED_RETROSPECTIVE_ONLY"
            if wallet["scenarios"]["BASE"]["estimated_complete_episodes"] > 0
            else "NOT_ECONOMICALLY_ESTIMABLE",
        }
        ranking.append(row)
    excluded, exclusion_fingerprint = registry_exclusions(registry_db)
    shortlist, excluded_positive = apply_research_screening(ranking, excluded)
    eligible = [r for r in ranking if r["base"]["estimated_complete_episodes"] > 0]
    positive = [r for r in eligible if r["base"]["estimated_net_pnl"] > 0]
    ranked = {
        "schema": "vike_prewindow_k_oos_rank_receipt_v1",
        "classification": "RETROSPECTIVE_FOLLOWER_EXECUTION_PROXY_RESEARCH_ONLY",
        "scientifically_qualified": False,
        "trading_authorized": False,
        "historical_signed_k_release": False,
        "order_route": "NONE",
        "screen_report_sha256": result["report_sha256"],
        "k_policy_sha256": result["k_policy_sha256"],
        "source_collection_sha256": result["source_collection_sha256"],
        "market_fingerprint_sha256": result["market_fingerprint_sha256"],
        "sqlite_exclusion_fingerprint_sha256": exclusion_fingerprint,
        "sqlite_integrity": "VERIFIED_READ_ONLY",
        "cost_policy": result["execution_cost_policy"],
        "execution_scenarios": result["scenario_definitions"],
        "metrics": {
            "source_accounts": result["source_accounts"],
            "vike_k_wallets": len(policy["wallets"]),
            "wallets_with_eligible_base": len(eligible),
            "positive_base_wallets": len(positive),
            "heuristic_shortlist_wallets": len(shortlist),
            "positive_wallets_vetoed_by_registry": len(excluded_positive),
            "scenario_estimated_complete_results": result["estimated_episode_results"],
            "economic_outcomes": result["economic_outcomes"],
            "source_episode_count": result["episode_candidates"],
            "source_supported_episodes": result["supported_episodes"],
            "market_matched_actions": result["market_matched_action_count"],
            "market_candidate_actions": result["market_candidate_action_count"],
        },
        "ranking": ranking,
        "research_shortlist_aliases": [r["alias"] for r in shortlist],
        "research_shortlist_wallet_sha256s": [r["wallet_sha256"] for r in shortlist],
        "vetoed_positive_wallets": [
            {
                "alias": r["alias"],
                "wallet_sha256": r["wallet_sha256"],
                "reasons": r["current_registry_exclusions"],
            }
            for r in excluded_positive
        ],
        "limitations": [
            "Vike hourly position aggregates are retrospective and not original signed source receipts",
            "k created after OOS window from observed prewindow max gross exposure only",
            "k risk method is a 20pct exposure shock proxy, not a leader max-drawdown bound",
            "market amount-step and minimum-notional are declared research proxies, not historical exchange specs",
            "market volume is 1m capacity proxy, not executable broker depth",
            "complete source fills are not authentic first-known position observations",
            "PM03/PM04 overlapping portfolio drawdown, cash/funding and contractual risk not simulated",
        ],
    }
    filename, evidence_sha = checked_publish(output_root, "retro-vike-oos-ranking", ranked)
    return {
        "path": str(filename),
        "sha256": evidence_sha,
        "report_sha256": result["report_sha256"],
        "report_cache_status": result["report_cache_status"],
        **ranked["metrics"],
        "top_10": [
            {
                "alias": r["alias"],
                "base_pnl_usd": r["base"]["estimated_net_pnl"],
                "delayed_pnl_usd": r["delayed"]["estimated_net_pnl"],
                "adverse_pnl_usd": r["adverse"]["estimated_net_pnl"],
                "base_episodes": r["base"]["estimated_complete_episodes"],
                "source_days": r["evaluation_observation_days"],
            }
            for r in eligible[:10]
        ],
        "shortlist": ranked["research_shortlist_aliases"],
        "excluded_positive": ranked["vetoed_positive_wallets"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "jobfile",
        "input_root",
        "source_root",
        "market_root",
        "cache_root",
        "output_root",
    ):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--registry-db", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(**vars(args)), sort_keys=True))


if __name__ == "__main__":
    main()
