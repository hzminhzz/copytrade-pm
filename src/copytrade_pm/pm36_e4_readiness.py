"""Audit real Portfolio C evidence prerequisites for E4 without revealing addresses.

This never manufactures a complete wallet book/equity from episode fragments,
or mistakes retrospective Hyperliquid account history for first-known data.
Existing immutable source cache/overlay generations are read-only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path

from .pm36_e4 import END, PODS, START
from .pm_portfolio_c_driver import (
    SOURCE_EPISODES_SHA,
    SOURCE_FILLS_SHA,
    _checked_report,
    _private_json,
)
from .pm_fill_replay import _coins, _market_instrument
from .pm_hyperx_overlay_audit import examine
from .pm_quarter_fill_audit import wallet_fills
from .pm_shadow import MarketDataBlocked
from .pm_sources import load_cohort

AUDIT_SCHEMA = "pm_c_e4_historical_fidelity_readiness_v1"
REPORT_FILL_SCHEMA = "pm36_independent_2026q3_vendor_fill_audit_v1"
REPORT_EP_SCHEMA = "pm36_2026q3_independent_completed_episode_replay_v1"


def historical_e4_preflight(
    root: Path,
    fill_report: Path,
    episode_report: Path,
    generations: tuple[Path, ...],
) -> dict:
    filled = _checked_report(fill_report, SOURCE_FILLS_SHA, REPORT_FILL_SCHEMA)
    episodes = _checked_report(episode_report, SOURCE_EPISODES_SHA, REPORT_EP_SCHEMA)
    if filled["source_manifests_sha256"] != episodes["source_manifests_sha256"]:
        raise ValueError("E4_FROZEN_SOURCE_REPORT_CONFLICT")
    if filled["overlay_generation_shas"] != episodes["overlay_source_generation_sha256"]:
        raise ValueError("E4_FROZEN_OVERLAY_CONFLICT")
    cohort, manifests = load_cohort(root)
    if manifests != filled["source_manifests_sha256"]:
        raise ValueError("E4_SOURCE_MANIFEST_DRIFT")
    index = {entry.alias: entry for entry in cohort}
    overlay, verified = examine(root, generations)
    if (
        not overlay["original_vendor_cache_intact"]
        or overlay["private_generations"] != filled["overlay_generation_shas"]
    ):
        raise ValueError("E4_UNVERIFIED_OVERLAY_DRIFT")
    results = []
    for pod in PODS:
        entry = index[pod]
        coins = _coins(root, pod)
        fills, issues = wallet_fills(
            root,
            entry,
            generations=generations,
            verified_additions=verified.get(pod, []),
        )
        first_seen = {}
        in_quarter = Counter()
        unknown_symbols = []
        for coin in coins:
            try:
                _market_instrument(coin)
            except MarketDataBlocked:
                unknown_symbols.append(coin)
        for fill in fills:
            first_seen.setdefault(fill.coin, fill.timestamp)
            if START <= fill.timestamp < END:
                in_quarter[fill.coin] += 1
        first_observed_after_start = sorted(
            [coin for coin in coins if first_seen.get(coin, END) >= START]
        )
        account = root / "hyperliquid_account_history" / (entry.address_sha256[:20] + ".json")
        point_count = 0
        point_dates = set()
        account_present = account.is_file()
        if account_present:
            doc = json.loads(account.read_bytes())
            if str(doc.get("address", "")).lower() != entry.address.lower() or not isinstance(
                doc.get("portfolio"), list
            ):
                raise ValueError("E4_ACCOUNT_HISTORY_WRONG_WALLET")
            for period in doc["portfolio"]:
                if not isinstance(period, list) or len(period) != 2:
                    raise ValueError("E4_INVALID_RETROSPECTIVE_EQUITY_HISTORY")
                data = period[1]
                for event in data.get("accountValueHistory", []):
                    if not isinstance(event, list) or len(event) != 2:
                        raise ValueError("E4_INVALID_RETROSPECTIVE_EQUITY_HISTORY")
                    when = datetime.fromtimestamp(event[0] / 1000, UTC)
                    if START <= when < END:
                        point_dates.add(when.isoformat())
            point_count = len(point_dates)
        blockers = [
            "NO_INDEPENDENT_FULL_EXCHANGE_ACCOUNT_BOOK_CENSUS",
            "NO_VERIFIED_POINT_IN_TIME_WALLET_EQUITY_AND_COLLATERAL",
            "NO_VERIFIED_COMPLETE_ACCOUNT_EVENT_FEED",
            "NO_HISTORICALLY_FIRST_KNOWN_FOLLOWER_RECEIPTS",
            "NO_HISTORICAL_PROPR_BROKER_INSTRUMENT_ALLOWLIST",
        ]
        if first_observed_after_start:
            blockers.append("NOT_EVERY_VENDOR_INSTRUMENT_ANCHORED_BEFORE_Q3")
        if issues:
            blockers.append("SOURCE_POSITION_CHAIN_OR_SOURCE_GAP")
        if unknown_symbols:
            blockers.append("UNMAPPABLE_ACCOUNT_INSTRUMENT")
        if not account_present:
            blockers.append("NO_RETROSPECTIVE_ACCOUNT_HISTORY_FILE")
        results.append(
            {
                "pod": pod,
                "frozen_wallet_identity_sha256": entry.address_sha256,
                "vendor_listed_instrument_count": len(coins),
                "q3_vendor_fill_count": sum(in_quarter.values()),
                "coins_anchored_only_after_q3_start_count": len(first_observed_after_start),
                "coins_with_q3_fills": len(in_quarter),
                "source_gap_issues": len(issues),
                "unmappable_native_instrument_count": len(unknown_symbols),
                "retrospective_account_history_file_present": account_present,
                "retrospective_q3_account_value_timestamps_count": point_count,
                "retrospective_value_is_first_known": False,
                "all_dex_source_book_census_verified": False,
                "funding_and_collateral_reconciled": False,
                "admissible_e4_snapshot_count": 0,
                "qualification": "BLOCKED_E4_SOURCE_EVIDENCE",
                "blockers": blockers,
            }
        )
    return {
        "schema": AUDIT_SCHEMA,
        "q3_start": START.isoformat(),
        "q3_end_exclusive": END.isoformat(),
        "cohort_manifest_sha256": manifests,
        "source_fill_report_sha256": SOURCE_FILLS_SHA,
        "source_episode_report_sha256": SOURCE_EPISODES_SHA,
        "wallets": results,
        "source_account_history_noncause": True,
        "e4_admissible_wallet_count": 0,
        "e4_historic_backtest_authorized": False,
        "source_books_or_wallet_equity_fabricated": False,
        "decision": "BLOCKED_EVIDENCE_NOT_A_PROFIT_RESULT",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--fill-report", type=Path, required=True)
    p.add_argument("--episode-report", type=Path, required=True)
    p.add_argument("--hyperx-generations", nargs="+", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = historical_e4_preflight(
        a.research_root,
        a.fill_report,
        a.episode_report,
        tuple(a.hyperx_generations),
    )
    path, digest = _private_json(a.out, "e4-readiness", result)
    print(
        json.dumps(
            {
                "path": str(path),
                "sha256": digest,
                "state": result["decision"],
                "wallets": [
                    {k: v for k, v in row.items() if k not in ("frozen_wallet_identity_sha256",)}
                    for row in result["wallets"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
