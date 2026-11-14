"""Bounded retrospective Hyperliquid /info portfolio-equity acquisition.

No fills, no broker keys, no orders. The official 'perpAllTime' portfolio
equity history may be sparse and is NOT first-known source risk in Q3.
Retain raw provider replies in a private immutable generation; never backfill
missing intervals or call this a complete account/collateral reconciliation.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal as D
import json
from pathlib import Path
import time

from .pm_e4_prospective import canonical, guarded_info, safe_dir
from .pm_hyperx_account_triage import write_immutable_private
from .pm_portfolio_e0 import PORTFOLIOS
from .pm_research import _write_private_evidence
from .pm_sources import load_cohort

START_MS = int(datetime(2026, 7, 1, tzinfo=UTC).timestamp() * 1000)
END_MS = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)
MAX_WALLETS = 6
MIN_REQUEST_INTERVAL_SECONDS = 2
DEFAULT_ALIASES = tuple(dict.fromkeys(PORTFOLIOS["A"] + PORTFOLIOS["B"]))


def inspect_portfolio(payload: object) -> dict:
    """Inspect NAV timeline metadata only; reject aliased spot/perp history."""
    if not isinstance(payload, list):
        raise ValueError("INVALID_HL_PORTFOLIO_FORMAT")
    lookup: dict[str, dict] = {}
    for part in payload:
        if (
            not isinstance(part, list)
            or len(part) != 2
            or not isinstance(part[0], str)
            or not isinstance(part[1], dict)
            or part[0] in lookup
        ):
            raise ValueError("INVALID_HL_PORTFOLIO_PERIOD")
        lookup[part[0]] = part[1]
    if "perpAllTime" not in lookup:
        raise ValueError("HL_PERP_EQUITY_HISTORY_ABSENT")
    values = lookup["perpAllTime"].get("accountValueHistory")
    if not isinstance(values, list) or len(values) > 20_000:
        raise ValueError("HL_PERP_EQUITY_HISTORY_INVALID")
    latest_at = None
    seen = set()
    q3 = []
    for row in values:
        if not isinstance(row, list) or len(row) != 2 or type(row[0]) is not int:
            raise ValueError("HL_EQUITY_POINT_SCHEMA_INVALID")
        timestamp = row[0]
        if timestamp in seen or (latest_at is not None and timestamp <= latest_at):
            raise ValueError("HL_EQUITY_CLOCK_CONFLICT")
        seen.add(timestamp)
        latest_at = timestamp
        try:
            equity = D(str(row[1]))
        except (ValueError, ArithmeticError, TypeError) as exc:
            raise ValueError("HL_EQUITY_VALUE_INVALID") from exc
        if not equity.is_finite():
            raise ValueError("HL_EQUITY_NONFINITE")
        if START_MS <= timestamp < END_MS:
            q3.append((timestamp, equity))
    maximum_gap = max((b[0] - a[0] for a, b in zip(q3, q3[1:])), default=None)
    return {
        "period": "perpAllTime",
        "total_points": len(values),
        "q3_points": len(q3),
        "q3_first_observed_source_timestamp_ms": q3[0][0] if q3 else None,
        "q3_last_observed_source_timestamp_ms": q3[-1][0] if q3 else None,
        "q3_positive_equity_points": sum(v > 0 for _, v in q3),
        "q3_max_gap_hours_between_samples": (
            round(maximum_gap / 3_600_000, 3) if maximum_gap is not None else None
        ),
        "q3_hourly_equity_denominator_continuous": False,
        "account_dex_subaccount_scope_reconciled": False,
        "follower_first_known_in_q3": False,
    }


def collect(
    research_root: Path,
    generation: Path,
    aliases: tuple[str, ...] = DEFAULT_ALIASES,
    *,
    min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
) -> dict:
    if (
        not 1 <= len(aliases) <= MAX_WALLETS
        or len(set(aliases)) != len(aliases)
        or not set(aliases).issubset(DEFAULT_ALIASES)
        or min_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS
    ):
        raise ValueError("UNBOUNDED_EQUITY_PROVIDER_REQUEST")
    entries, source = load_cohort(research_root)
    roster = {e.alias: e for e in entries}
    safe_dir(generation)
    report = {
        "schema": "pm_q3_retrospective_hyperliquid_portfolio_inspection_v1",
        "provider": "HYPERLIQUID_INFO_PORTFOLIO_READ_ONLY",
        "request_count_max": len(aliases),
        "request_count": 0,
        "source_manifests_sha256": source,
        "retrospective_only": True,
        "reconstructed_source_equity_hourly": False,
        "scientifically_qualified": False,
        "raw_fills_changed": False,
        "rows": [],
    }
    for index, alias in enumerate(aliases):
        entry = roster[alias]
        requested = datetime.now(UTC).isoformat()
        report["request_count"] += 1
        info = guarded_info({"type": "portfolio", "user": entry.address})
        data, raw, response_sha = info
        metadata = inspect_portfolio(data)
        received = datetime.now(UTC).isoformat()
        location = generation / "raw" / alias / "portfolio.json"
        write_immutable_private(location, raw)
        write_immutable_private(
            generation / "metadata" / alias / "portfolio.json",
            canonical(
                {
                    "wallet": alias,
                    "wallet_identity_sha256": entry.address_sha256,
                    "requested_at": requested,
                    "received_at": received,
                    "raw_sha256": response_sha,
                    "source_event_time_is_not_first_known": True,
                    **metadata,
                }
            ),
        )
        report["rows"].append(
            {
                "wallet": alias,
                "wallet_identity_sha256": entry.address_sha256,
                "source_raw_sha256": response_sha,
                "requested_at": requested,
                "received_at": received,
                "source_metadata": metadata,
            }
        )
        if index < len(aliases) - 1:
            time.sleep(min_interval_seconds)
    report["completed_at"] = datetime.now(UTC).isoformat()
    path, checksum = _write_private_evidence(generation, report)
    return {
        "status": "RETROSPECTIVE_SPARSE_SOURCE_NAV_ONLY",
        "report_path": str(path),
        "report_sha256": checksum,
        "requested_wallets": len(aliases),
        "queries": report["request_count"],
        "wallet_point_counts": {
            row["wallet"]: row["source_metadata"]["q3_points"] for row in report["rows"]
        },
        "hourly_source_equity_validated": False,
        "historical_follower_sizing_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--aliases", nargs="+", default=list(DEFAULT_ALIASES))
    parser.add_argument("--interval", type=float, default=MIN_REQUEST_INTERVAL_SECONDS)
    args = parser.parse_args()
    print(
        json.dumps(
            collect(
                args.research_root,
                args.generation,
                tuple(args.aliases),
                min_interval_seconds=args.interval,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
