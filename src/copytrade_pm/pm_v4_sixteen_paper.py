"""One source/price tape, sixteen independent PM03/04 V4 virtual-paper ledgers.

Historical versions, excluded-wallet decisions and original P1/P14/P16 V4
runs remain untouched. No broker dependency or live order capability.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import time

from .pm03_account import clock
from .pm_forward_observed_paper import (
    PAPER_PROFILES,
    ObservedP1Paper,
    _exclusive_runner,
    now_utc,
)
from .pm_forward_stream_journal import verify_streams
from .pm_v4_sixteen_scenarios import IDENTITIES, MANIFEST_SHA256, load_campaign
from .pm_vike_market_catalog import load_propr_catalog, official_paper_contracts


def _sleep_to_deadline(runs: dict[str, ObservedP1Paper], poll_seconds: float) -> float:
    now = clock(now_utc())
    remaining: list[float] = []
    for run in runs.values():
        state = run.run.account.pm04_state.get("paper_execution", {})
        for intent in state.get("history", {}).values():
            if intent["status"] == "PENDING_5M":
                for at in (intent["due_at"], intent["deadline_at"]):
                    dt = (clock(at) - now).total_seconds()
                    if dt > 0:
                        remaining.append(dt)
        for exit_row in state.get("exits", {}).values():
            if exit_row["status"] == "PENDING_EXIT":
                dt = (clock(exit_row["deadline_at"]) - now).total_seconds()
                if dt > 0:
                    remaining.append(dt)
    return max(0.05, min(poll_seconds, min(remaining, default=poll_seconds)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-db", required=True, type=Path)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--price-db", required=True, type=Path)
    parser.add_argument("--propr-catalog", required=True, type=Path)
    parser.add_argument("--campaign-manifest", required=True, type=Path)
    parser.add_argument("--campaign-sha256", required=True)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--paper-min-notional", default="10")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 5:
        parser.error("poll seconds must be 0.1..5")
    if args.campaign_sha256 != MANIFEST_SHA256:
        parser.error("unreviewed campaign SHA")
    os.umask(0o077)
    started = now_utc()
    campaign = load_campaign(
        manifest=args.campaign_manifest,
        registry_db=args.registry_db,
        at=started,
        expected_sha256=args.campaign_sha256,
    )
    if tuple(campaign.profiles) != IDENTITIES:
        raise ValueError("V4_SIXTEEN_FROZEN_ROSTER_NOT_COMPLETE")
    print(
        json.dumps({"event": "PREFLIGHT", **campaign.public_status()}, sort_keys=True), flush=True
    )
    if args.dry_run:
        return 0

    if not args.source_db.is_file() or not args.price_db.is_file():
        raise ValueError("V4_SIXTEEN_SHARED_SOURCE_OR_PRICE_MISSING")
    # Full source-stream integrity precedes every ledger's admission.
    verify_streams(args.source_db)
    catalog = load_propr_catalog(args.propr_catalog)
    contracts = official_paper_contracts(
        catalog.native_symbols,
        observed_at=started,
        minimum_notional_usd=Decimal(args.paper_min_notional),
    )
    if not contracts:
        raise ValueError("V4_SIXTEEN_NO_VERIFIED_NATIVE_MARKETS")

    root = args.state_root
    if root.is_symlink() or (root.exists() and root.stat().st_mode & 0o077):
        raise PermissionError("V4_SIXTEEN_SHARED_ROOT_NOT_PRIVATE")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        runs: dict[str, ObservedP1Paper] = {}
        for pid in IDENTITIES:
            per_root = root / pid.lower()
            run_id = f"{pid.lower()}_v4_sixteen_0911"
            stack.enter_context(_exclusive_runner(per_root, run_id))
            runs[pid] = ObservedP1Paper(
                source_db=args.source_db,
                price_db=args.price_db,
                registry_db=args.registry_db,
                state_root=per_root,
                run_id=run_id,
                catalog={},
                portfolio_id=pid,
                price_mode="vike_minute",
                native_contracts=contracts,
                study_profile=campaign.profiles[pid],
                study_seal=(campaign.seals[pid] if pid not in PAPER_PROFILES else None),
                study_accounts=campaign.account_hashes[pid],
                started_at=started,
            )
        if len(runs) != 16 or len({p.run.ledger.path for p in runs.values()}) != 16:
            raise ValueError("V4_SIXTEEN_NON_ISOLATED_FINANCIAL_LEDGERS")
        print(
            json.dumps(
                {
                    "event": "ADMITTED_VIRTUAL_PAPER_ONLY",
                    "runs": {
                        pid: {
                            "run_id": paper.run_id,
                            "started_at": paper.started_at,
                            "selection": paper.portfolio_seal,
                            "broker_route": "NONE",
                        }
                        for pid, paper in runs.items()
                    },
                    "trading_authorized": False,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        stopped = False

        def stop(_sig: int, _frame: object) -> None:
            nonlocal stopped
            stopped = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        prior: dict[str, tuple] = {}
        last_log = 0.0
        quarantined: dict[str, str] = {}
        while not stopped:
            changed: dict[str, dict] = {}
            for pid, paper in runs.items():
                if pid in quarantined:
                    continue
                try:
                    result = paper.step()
                    state = (
                        result["tick"],
                        result["net_pnl"],
                        tuple(sorted(result["source_results"].items())),
                        tuple(sorted(result["execution_results"].items())),
                        result["risk"],
                        tuple(sorted(result["execution_outcomes"])),
                    )
                    if prior.get(pid) != state:
                        changed[pid] = {
                            "run_id": result["run_id"],
                            "tick": result["tick"],
                            "source_results": result["source_results"],
                            "execution_results": result["execution_results"],
                            "exit_results": result["exit_results"],
                            "net_pnl": result["net_pnl"],
                            "risk": result["risk"],
                            "real_broker_fills": 0,
                        }
                        prior[pid] = state
                except Exception as exc:
                    # One corrupt virtual ledger must never poison another.
                    # Its financial accounting stops; no synthetic close/permit.
                    quarantined[pid] = type(exc).__name__ + ":" + str(exc)[:160]
                    changed[pid] = {
                        "tick": "BLOCKED_PAPER_LEDGER",
                        "reason": quarantined[pid],
                        "order_route": "NONE",
                    }
            if changed or time.monotonic() - last_log > 60 or args.once:
                print(
                    json.dumps(
                        {
                            "event": "V4_SIXTEEN_PAPER",
                            "at": datetime.now(timezone.utc).isoformat(),
                            "active_ledgers": len(runs) - len(quarantined),
                            "quarantined": quarantined,
                            "changes": changed,
                            "order_route": "NONE",
                            "trading_authorized": False,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                last_log = time.monotonic()
            if args.once:
                return 0 if not quarantined else 2
            if len(quarantined) == len(runs):
                return 2
            time.sleep(
                _sleep_to_deadline(
                    {k: v for k, v in runs.items() if k not in quarantined}, args.poll_seconds
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
