"""Operator-gated 0811/0911 source and PM03 financial recovery, issue #292.

The CLI NEVER stops/starts a service, deletes original evidence or rewrites a
finance ledger. The caller must separately quiesce every listed paper and
source unit before 'backup' or 'checkpoint'; this CLI independently rechecks
unit state and observable FDs before any write to its backup destination.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_v4_finance_recovery import (
    backup_financial_roots,
    replay_financial_roots,
)
from copytrade_pm.pm_v4_sqlite_recovery import (
    active_source_handles,
    backup_and_verify,
    checkpoint_verified_backup,
)

ROOT = Path("/home/quant/.local/share/copytrade/prospective")

CAMPAIGNS = {
    "0811": {
        "source": ROOT / "v4-selected-positions-0811" / "paper-events.sqlite3",
        "finance": (
            ROOT / "v4-paper-p1-0811",
            ROOT / "v4-paper-p14-0811",
            ROOT / "v4-paper-p16-0811",
            ROOT / "pydnative-v4-paper-p1-0911",
        ),
        "units": (
            "copytrade-v4-paper-p1-0811.service",
            "copytrade-v4-paper-p14-0811.service",
            "copytrade-v4-paper-p16-0811.service",
            "copytrade-pydnative-v4-paper-p1-0911.service",
            "copytrade-v4-selected-positions-0811.service",
        ),
    },
    "0911": {
        "source": ROOT / "v4-selected-sixteen-0911" / "paper-events.sqlite3",
        "finance": (
            ROOT / "v4-paper-sixteen-0911",
            ROOT / "pydnative-v4-paper-sixteen-0911",
        ),
        "units": (
            "copytrade-v4-sixteen-paper-0911.service",
            "copytrade-pydnative-v4-sixteen-paper-0911.service",
            "copytrade-v4-sixteen-source-0911.service",
        ),
    },
}


def snapshot_units(campaign: str) -> dict[str, dict[str, str]]:
    result = {}
    for unit in CAMPAIGNS[campaign]["units"]:
        p = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                unit,
                "-p",
                "ActiveState",
                "-p",
                "MainPID",
                "-p",
                "NRestarts",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        result[unit] = dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)
    return result


def gated_quiescence(campaign: str, *, approved: bool) -> dict[str, dict[str, str]]:
    if not approved:
        raise ValueError("V4_RECOVERY_EXPLICIT_QUIESCENCE_REQUIRED")
    units = snapshot_units(campaign)
    if any(
        row.get("ActiveState") not in ("inactive", "failed") or row.get("MainPID") != "0"
        for row in units.values()
    ):
        raise ValueError("V4_RECOVERY_CAMPAIGN_UNITS_STILL_ACTIVE")
    if active_source_handles(CAMPAIGNS[campaign]["source"]):
        raise ValueError("V4_RECOVERY_CAMPAIGN_DB_HANDLES_ACTIVE")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", choices=tuple(CAMPAIGNS), required=True)
    parser.add_argument(
        "--phase",
        choices=("inspect", "finance", "backup", "checkpoint"),
        required=True,
    )
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--quiescence-verified", action="store_true")
    parser.add_argument("--expected-head-sha", default="")
    parser.add_argument("--expected-finance-head-sha", default="")
    args = parser.parse_args()
    cfg = CAMPAIGNS[args.campaign]
    receipt = {
        "schema": "v4_292_operator_recovery_receipt_v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "campaign": args.campaign,
        "phase": args.phase,
        "units": snapshot_units(args.campaign),
        "trading_authorized": False,
        "broker_route": "NONE",
    }
    if args.phase == "inspect":
        receipt["open_db_handles"] = active_source_handles(cfg["source"])
    elif args.phase == "finance":
        receipt["finances"] = replay_financial_roots(cfg["finance"])
    else:
        receipt["units"] = gated_quiescence(args.campaign, approved=args.quiescence_verified)
        if args.destination is None or args.destination.is_symlink():
            raise ValueError("V4_RECOVERY_NEW_DESTINATION_REQUIRED")
        if args.phase == "backup":
            receipt["finance"] = backup_financial_roots(
                cfg["finance"],
                args.destination / "finance",
                quiescence_verified=True,
            )
            receipt["source"] = backup_and_verify(
                cfg["source"],
                args.destination / "source",
                quiescence_verified=True,
            )
            receipt["verified_source_head_sha"] = receipt["source"]["stream_head_sha"]
        else:
            if not args.expected_head_sha or not args.expected_finance_head_sha:
                raise ValueError("V4_RECOVERY_EXPECTED_SOURCE_AND_FINANCE_SHA_REQUIRED")
            finance_before = replay_financial_roots(cfg["finance"])
            if digest(finance_before["runs"]) != args.expected_finance_head_sha:
                raise ValueError("V4_RECOVERY_FINANCE_HEAD_CHANGED_SINCE_BACKUP")
            receipt["source"] = checkpoint_verified_backup(
                cfg["source"],
                args.destination / "source",
                quiescence_verified=True,
                expected_head_sha=args.expected_head_sha,
            )
            finance_after = replay_financial_roots(cfg["finance"])
            receipt["finance_head_sha_after"] = digest(finance_after["runs"])
            receipt["finance_run_count_after"] = finance_after["run_count"]
            if receipt["finance_head_sha_after"] != args.expected_finance_head_sha:
                raise ValueError("V4_RECOVERY_FINANCE_HEAD_CHANGED_DURING_CHECKPOINT")
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
