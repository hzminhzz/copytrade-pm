"""Bounded approved P1/P14 read-only source-observation campaign.

Reuses the audited WR-06 frozen alias/address table and native E4 public
all-DEX parser. Each parent is observed in turn; no portfolio is admitted
from historical locator files, incomplete subaccounts or guessed equity.
Never starts private subscriptions, long-running services or broker routes.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from .pm_forward_journal import PaperJournal
from .pm_forward_registry_identity import (
    P1,
    P14,
    _private_locator,
    audit_frozen_member_resolution,
)
from .pm_forward_source_stream import (
    bounded_source_family_capture,
    bounded_source_scope_capture,
)
from .pm_e4_prospective import _guarded_info

_ALIAS = {
    "S035-ENA": "S035",
    "S051-BTC": "S051",
    "S053-HYPE": "S053",
    "S064-xyz:BRENTOIL": "S064",
    "Whale_0x5f94": "Whale_0x5f94",
}


async def observe_frozen_portfolio_readonly(
    *,
    portfolio_id: str,
    registry_db: Path,
    primary_dir: Path,
    secondary_dir: Path,
    journal: PaperJournal,
    seconds_per_wallet: float = 8,
    max_frames: int = 10,
    include_subaccounts: bool = False,
    info: Callable = _guarded_info,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
) -> dict:
    identity = audit_frozen_member_resolution(
        registry_db=registry_db,
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        portfolio_id=portfolio_id,
    )
    # Observation is permitted while identity-link admission is blocked.
    # Never infer authorized paper execution or mutate the registry.
    members = P1 if portfolio_id == "P1" else P14
    attempts = []
    for member in members:
        _, address, _sha = _private_locator(
            member, primary_dir=primary_dir, secondary_dir=secondary_dir
        )
        alias = _ALIAS[member]
        try:
            if include_subaccounts:
                capture = await bounded_source_family_capture(
                    alias=alias,
                    parent_address=address,
                    journal=journal,
                    seconds_per_account=seconds_per_wallet,
                    max_frames=max_frames,
                    info=info,
                    connect=connect,
                    now=now,
                )
                attempts.append(
                    {
                        "member": member,
                        "status": capture["status"],
                        "account_observations": capture["accounts"],
                        "expected_account_count": capture["expected_account_count"],
                        "observed_account_count": capture["observed_account_count"],
                        "partial_receipts": sum(
                            item["partial_receipts"] for item in capture["accounts"]
                        ),
                        "source_cursor": capture["source_cursor"],
                        "errors": [
                            error for item in capture["accounts"] for error in item["errors"]
                        ],
                        "whole_wallet_equity_attested": False,
                    }
                )
            else:
                capture = await bounded_source_scope_capture(
                    alias=alias,
                    address=address,
                    journal=journal,
                    seconds=seconds_per_wallet,
                    max_frames=max_frames,
                    info=info,
                    connect=connect,
                    now=now,
                )
                attempts.append(
                    {
                        "member": member,
                        "status": capture["transport_status"],
                        "frames_received": capture["frames_received"],
                        "partial_receipts": capture["per_account_receipts"],
                        "source_cursor": capture["source_cursor"],
                        "errors": capture["errors"],
                        "whole_wallet_equity_attested": False,
                    }
                )
        except Exception as exc:
            attempts.append(
                {
                    "member": member,
                    "status": "BLOCKED_SOURCE_ACQUISITION",
                    "partial_receipts": 0,
                    "errors": [type(exc).__name__ + ":" + str(exc)[:130]],
                    "whole_wallet_equity_attested": False,
                }
            )
    return {
        "schema": "paper_frozen_public_scope_capture_v1",
        "portfolio": portfolio_id,
        "registry_version": identity["registry_version"],
        "frozen_member_count": len(members),
        "frozen_wallet_id_resolved": len(identity["unresolved_aliases"]) == 0,
        "unresolved_members": identity["unresolved_aliases"],
        "partial_account_observations": attempts,
        "status": "BLOCKED_OBSERVATION_ONLY_NO_TRADE",
        "all_parent_books_complete": False,
        "whole_wallet_equity_attested": False,
        "source_first_known_complete": False,
        "paper_observed": False,
        "broker_orders": 0,
        "registry_mutated": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", required=True, choices=("P1", "P14"))
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--primary-dir", required=True, type=Path)
    parser.add_argument("--secondary-dir", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--seconds-per-wallet", type=float, default=8)
    parser.add_argument("--max-frames", type=int, default=10)
    parser.add_argument("--include-subaccounts", action="store_true")
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        name in (".git", ".devspace") for name in args.state_root.resolve().parts
    ):
        parser.error("private source root must be canonical, outside worktrees")
    result = asyncio.run(
        observe_frozen_portfolio_readonly(
            portfolio_id=args.portfolio,
            registry_db=args.registry,
            primary_dir=args.primary_dir,
            secondary_dir=args.secondary_dir,
            journal=PaperJournal(args.state_root),
            seconds_per_wallet=args.seconds_per_wallet,
            max_frames=args.max_frames,
            include_subaccounts=args.include_subaccounts,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
