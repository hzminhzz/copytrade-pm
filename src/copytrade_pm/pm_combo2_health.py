"""Read-only Combo2 account-source health; never authorizes paper or live orders."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from .pm03_account import clock
from .pm_combo2_capture import _private_file


def status(report: dict, *, observed_at: str, max_age_seconds: int = 900) -> dict:
    if not 60 <= max_age_seconds <= 86400:
        raise ValueError("INVALID_HEALTH_MAX_AGE")
    if not isinstance(report, dict) or report.get("schema") != "combo2_rest_account_capture_v1":
        raise ValueError("INVALID_SOURCE_HEALTH_SCHEMA")
    if report.get("network_order_mutations") != 0:
        raise ValueError("UNEXPECTED_REMOTE_ORDER_MUTATION")
    finish = report.get("finished_at")
    if not isinstance(finish, str):
        raise ValueError("MISSING_CAPTURE_COMPLETION")
    lag = (clock(observed_at) - clock(finish)).total_seconds()
    fresh = 0 <= lag <= max_age_seconds
    full = (
        report.get("account_count") == 10
        and report.get("all_subjects_captured") is True
        and not report.get("errors")
        and len(report.get("subjects", {})) == 10
    )
    modes = sorted(
        {row.get("account_mode", "UNKNOWN") for row in report.get("subjects", {}).values()}
    )
    return {
        "schema": "combo2_readonly_source_health_v1",
        "source_acquisition_health": (
            "HEALTHY" if fresh and full else "STALE" if not fresh else "DEGRADED"
        ),
        "account_count": report.get("account_count"),
        "dex_count": report.get("dex_count"),
        "account_modes": modes,
        "last_completed_at": finish,
        "last_completed_age_seconds": max(lag, 0),
        "paper_opening_status": "BLOCKED_SOURCE_EQUITY_AND_MARKET_ATTESTATION",
        "unattended_paper_service_deployed": False,
        "scientifically_qualified": False,
        "live_trading_authorized": False,
        "network_order_mutations": 0,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generation", type=Path, required=True)
    p.add_argument("--max-age-seconds", type=int, default=900)
    args = p.parse_args()
    row = json.loads(_private_file(args.generation / "report.json"))
    print(
        json.dumps(
            status(
                row,
                observed_at=datetime.now(UTC).isoformat(),
                max_age_seconds=args.max_age_seconds,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
