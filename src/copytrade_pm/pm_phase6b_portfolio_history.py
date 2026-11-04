"""Bounded, official Hyperliquid historical-portfolio inspection for Phase 6B.

Research-only public /info portfolio requests. Historical source timestamps are
retrospectively received, not first-known execution signals. Does not invent
account equity, reconcile funding, or assume perpAllTime equals unified NAV.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal as D, InvalidOperation
import json
from pathlib import Path
import time

from .pm_e4_prospective import _guarded_info, _safe_dir
from .pm_hyperx_account_triage import _write_immutable_private
from .pm_phase6b import END, START, fingerprint, safe_write_json

PERIODS = ("allTime", "perpAllTime")
MAX_WALLETS = 8
MIN_INTERVAL_SECONDS = 1.0


def _equity_points(period: object) -> dict:
    if not isinstance(period, dict):
        return {"status": "INVALID_PROVIDER_PERIOD", "observations_in_window": 0}
    values = period.get("accountValueHistory")
    if not isinstance(values, list) or len(values) > 20000:
        return {"status": "INVALID_PROVIDER_HISTORY", "observations_in_window": 0}
    last = None
    accepted = []
    for row in values:
        if not isinstance(row, list) or len(row) != 2 or type(row[0]) is not int:
            return {"status": "INVALID_PROVIDER_POINT", "observations_in_window": 0}
        t = datetime.fromtimestamp(row[0] / 1000, UTC)
        if last is not None and t <= last:
            return {"status": "NONMONOTONIC_PROVIDER_HISTORY", "observations_in_window": 0}
        last = t
        try:
            eq = D(str(row[1]))
        except TypeError, ValueError, InvalidOperation:
            return {"status": "INVALID_EQUITY", "observations_in_window": 0}
        if not eq.is_finite():
            return {"status": "NONFINITE_EQUITY", "observations_in_window": 0}
        if START <= t < END:
            accepted.append((t, eq))
    gaps = [(b[0] - a[0]).total_seconds() for a, b in zip(accepted, accepted[1:])]
    return {
        "status": "RETROSPECTIVE_SPARSE_HISTORY_NOT_RECONCILED",
        "observations_total": len(values),
        "observations_in_window": len(accepted),
        "positive_in_window": sum(eq > 0 for _, eq in accepted),
        "first_at": accepted[0][0].isoformat() if accepted else None,
        "last_at": accepted[-1][0].isoformat() if accepted else None,
        "maximum_gap_hours": round(max(gaps) / 3600, 4) if gaps else None,
        "last_positive_equity_usd": str(next((eq for _, eq in reversed(accepted) if eq > 0), "")),
        "point_in_time_first_known_verified": False,
        "reconciled_all_dex_funding_and_collateral": False,
    }


def inspect_portfolio(payload: object) -> dict:
    if not isinstance(payload, list):
        raise ValueError("INVALID_HYPERLIQUID_PORTFOLIO_RESPONSE")
    data = {}
    for entry in payload:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not isinstance(entry[1], dict)
            or entry[0] in data
        ):
            raise ValueError("INVALID_HYPERLIQUID_PORTFOLIO_ENTRY")
        data[entry[0]] = entry[1]
    return {key: _equity_points(data.get(key)) for key in PERIODS}


def collect(
    frozen_phase5: Path, generation: Path, *, min_interval_seconds: float = MIN_INTERVAL_SECONDS
) -> dict:
    manifest = json.loads(frozen_phase5.read_text())
    all_wallets = {}
    for portfolio in manifest["portfolios"]:
        for member in portfolio["members"]:
            alias = member["member_alias"]
            address = member["address"].lower()
            if alias in all_wallets and all_wallets[alias]["address"].lower() != address:
                raise ValueError("FROZEN_COHORT_ALIAS_CONFLICT")
            all_wallets[alias] = member
    if len(all_wallets) > MAX_WALLETS or min_interval_seconds < MIN_INTERVAL_SECONDS:
        raise ValueError("UNBOUNDED_PUBLIC_INFO_REQUESTS")
    _safe_dir(generation)
    report = {
        "schema": "phase6b_retrospective_hyperliquid_portfolio_history_v1",
        "frozen_phase5_sha256": fingerprint(frozen_phase5),
        "historical_first_known_verified": False,
        "portfolio_total_equity_reconciled": False,
        "account_scope_equity_exact": False,
        "source_equity_follower_scaling_qualified": False,
        "provider": "HYPERLIQUID_INFO_PORTFOLIO_READ_ONLY",
        "wallets": {},
    }
    for index, alias in enumerate(sorted(all_wallets)):
        wallet = all_wallets[alias]
        requested = datetime.now(UTC).isoformat()
        payload, raw, digest = _guarded_info({"type": "portfolio", "user": wallet["address"]})
        received = datetime.now(UTC).isoformat()
        if payload is None:
            raise ValueError("PROVIDER_NO_PORTFOLIO_RESPONSE")
        metadata = inspect_portfolio(payload)
        _write_immutable_private(generation / "raw" / alias / "portfolio.json", raw)
        report["wallets"][alias] = {
            "requested_at": requested,
            "received_at": received,
            "raw_sha256": digest,
            "account_abstraction": wallet["account_mode"],
            "account_scope_verified_historically": False,
            "history": metadata,
        }
        if index < len(all_wallets) - 1:
            time.sleep(min_interval_seconds)
    report["completed_at"] = datetime.now(UTC).isoformat()
    checksum = safe_write_json(generation / "report.json", report)
    return {
        "status": "RETROSPECTIVE_SPARSE_ACCOUNT_HISTORY_ONLY",
        "wallets": len(report["wallets"]),
        "report_sha256": checksum,
        "generation": str(generation),
        "point_counts": {
            k: {per: row["observations_in_window"] for per, row in data["history"].items()}
            for k, data in report["wallets"].items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase5", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=MIN_INTERVAL_SECONDS)
    args = parser.parse_args()
    print(
        json.dumps(
            collect(args.phase5, args.generation, min_interval_seconds=args.interval), indent=2
        )
    )


if __name__ == "__main__":
    main()
