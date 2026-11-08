"""Ingest an immutable local Hyperliquid observer generation into Combo2.

Only pre-captured official read-only first-local receipts may enter a prospective
paper ledger. The private scope manifest lives outside the Git worktree.
No WebSocket, Propr SDK, HTTP or order client is imported by this command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pm_combo2 import Combo2PaperTracker, MANAGERS
from .pm_combo2_capture import CapturedSourceScope, _private_file, ingest_e4_generation


def run(manifest_path: Path, generation: Path, paper_root: Path) -> dict:
    owner = json.loads(_private_file(manifest_path))
    if owner.get("schema") != "combo2_prospective_source_config_v1":
        raise ValueError("INVALID_PRIVATE_SOURCE_MANIFEST_SCHEMA")
    accounts = owner.get("scopes")
    if not isinstance(accounts, dict) or set(accounts) != set(MANAGERS):
        raise ValueError("THREE_MANAGER_SOURCE_SCOPE_REQUIRED")
    scopes = {}
    for manager, row in accounts.items():
        if not isinstance(row, dict):
            raise ValueError("INVALID_PRIVATE_SOURCE_SCOPE")
        scopes[manager] = CapturedSourceScope(
            manager=manager,
            address=row["address"],
            expected_dexs=frozenset(row["expected_dexs"]),
            account_mode=row["account_mode"],
            subaccount_scope_complete=row["subaccount_scope_complete"],
            verified_no_subaccounts=row["verified_no_subaccounts"],
            spot_collateral_verified_absent=row["spot_collateral_verified_absent"],
            evidence_sha256=row["evidence_sha256"],
        )
    tracker = Combo2PaperTracker(
        paper_root,
        run_id=owner["run_id"],
        started_at=owner["started_at"],
        source_subject_hashes={m: scope.subject_sha for m, scope in scopes.items()},
        prospective=True,
        source_evidence_hashes={m: scope.evidence_sha256 for m, scope in scopes.items()},
        market_contract_sha=owner.get("market_contract_sha"),
    )
    result = ingest_e4_generation(tracker, generation_dir=generation, scopes=scopes)
    return {
        **result,
        "pending_batches": len(tracker.meta["pending"]),
        "paper_only": True,
        "paper_observed": False,  # Ingestion alone is not a paper-fill observation.
        "source_complete_for_paper_execution": (
            set(tracker.meta.get("source_books", {})) == set(MANAGERS)
            and not tracker.meta.get("source_gaps")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-manifest", required=True, type=Path)
    parser.add_argument("--generation", required=True, type=Path)
    parser.add_argument("--paper-root", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.private_manifest, args.generation, args.paper_root),
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
