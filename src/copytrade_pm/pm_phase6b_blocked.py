"""Blocked Phase 6B result schemas; do not represent missing economics as zero.

These are coverage and research decision artifacts, NOT completed stress runs.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

from .pm_phase6b import WALLETS, fingerprint, safe_write_json


SCENARIOS = (
    "S1_hist_sync",
    "S2_corr_break",
    "S3_crash_minus10",
    "S3_crash_minus20",
    "S3_crash_minus30",
    "S4_short_squeeze",
    "S5_execution_delay_slippage",
    "S6_stale_missing",
    "S7_leave_one_out",
    "S8_temporal_stability",
)
POLICIES = ("P0_account_only", "P1_pod_loss", "P2_pod_and_supervisor")
FIELDS = (
    "portfolio",
    "allocation",
    "risk_policy",
    "scenario",
    "scenario_evidence_class",
    "net_pnl_usd",
    "max_daily_dd_pct",
    "max_trailing_dd_pct",
    "profit_target_hit_first",
    "breach_first",
    "kill_trigger_at",
    "flatten_execution_verified",
    "status",
    "blockers",
)


def _immutable_csv(path: Path, rows: list[dict]) -> str:
    import io

    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError("IMMUTABLE_SCENARIO_MATRIX_CONFLICT")
    else:
        path.write_bytes(raw)
        path.chmod(0o600)
    return sha256(raw).hexdigest()


def _empty_parquet(path: Path, columns: dict[str, str]) -> str:
    import polars as pl

    schema = {name: getattr(pl, kind) for name, kind in columns.items()}
    expected = pl.DataFrame(schema=schema)
    if path.exists():
        # Polars normalizes Datetime to a concrete time unit on serialization.
        existing = pl.read_parquet(path)
        if existing.schema != expected.schema or existing.height:
            raise FileExistsError("IMMUTABLE_EMPTY_PARQUET_CONFLICT")
    else:
        expected.write_parquet(path, compression="zstd")
        path.chmod(0o600)
    return fingerprint(path)


def run(coverage: Path, exact_minute: Path, output: Path) -> dict:
    source = json.loads(coverage.read_text())
    minute = json.loads(exact_minute.read_text())
    if source["schema"] != "phase6b_source_coverage_v1":
        raise ValueError("UNSUPPORTED_COVERAGE")
    if minute["original_coverage_sha256"] != fingerprint(coverage):
        raise ValueError("MARKET_COVERAGE_SOURCE_MISMATCH")
    if set(source["market_day_inventory"]) != set(minute["instruments"]):
        raise ValueError("MISSING_MARKET_SOURCE_COIN")
    if set(x["portfolio"] for x in source["portfolios"]) != set(WALLETS):
        raise ValueError("FROZEN_PORTFOLIO_SCOPE_MISMATCH")
    if not all(row["faithful_equity_account_pnl"] is None for row in source["portfolios"]):
        raise ValueError("UNEXPECTED_ACCOUNT_EQUITY_PRODUCER")

    result_rows = []
    for portfolio in source["portfolios"]:
        for policy in POLICIES:
            for scenario in SCENARIOS:
                result_rows.append(
                    {
                        "portfolio": portfolio["portfolio"],
                        "allocation": "frozen_phase5"
                        if portfolio["portfolio"][0] in "AB"
                        else "equal_capital_control_not_equal_risk",
                        "risk_policy": policy,
                        "scenario": scenario,
                        "scenario_evidence_class": (
                            "HISTORICAL_REQUIRED"
                            if scenario in ("S1_hist_sync", "S8_temporal_stability")
                            else "MODEL_DEPENDENT_REQUIRED"
                        ),
                        "net_pnl_usd": "",
                        "max_daily_dd_pct": "",
                        "max_trailing_dd_pct": "",
                        "profit_target_hit_first": "",
                        "breach_first": "",
                        "kill_trigger_at": "",
                        "flatten_execution_verified": "",
                        "status": "BLOCKED_NOT_RUN",
                        "blockers": "MISSING_COMPLETE_BOOK;HISTORICAL_COMPATIBLE_EQUITY_UNKNOWN;"
                        "PIT_FOLLOWER_FIRST_KNOWN_UNKNOWN",
                    }
                )
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    artifacts = {
        "scenario_results.csv": _immutable_csv(output / "scenario_results.csv", result_rows),
        "portfolio_equity.parquet": _empty_parquet(
            output / "portfolio_equity.parquet",
            {
                "portfolio": "String",
                "policy": "String",
                "timestamp": "Datetime",
                "account_equity_usd": "Float64",
                "drawdown_pct": "Float64",
            },
        ),
        "pod_attribution.parquet": _empty_parquet(
            output / "pod_attribution.parquet",
            {
                "portfolio": "String",
                "policy": "String",
                "wallet_alias": "String",
                "timestamp": "Datetime",
                "realized_pnl_usd": "Float64",
                "unrealized_pnl_usd": "Float64",
                "gross_notional_usd": "Float64",
            },
        ),
        "kill_events.parquet": _empty_parquet(
            output / "kill_events.parquet",
            {
                "portfolio": "String",
                "policy": "String",
                "timestamp": "Datetime",
                "trigger_type": "String",
                "attempted_action": "String",
                "outcome": "String",
            },
        ),
    }
    manifest = {
        "schema": "phase6b_blocked_scenario_contract_v1",
        "status": "BLOCKED_NOT_RUN",
        "source_coverage_sha256": fingerprint(coverage),
        "minute_coverage_sha256": fingerprint(exact_minute),
        "artifacts_sha256": artifacts,
        "scenario_rows": len(result_rows),
        "attempted_stresses": 0,
        "successful_account_replays": 0,
        "empty_parquets_are_missing_evidence_not_zero_drawdown": True,
        "orders_sent": False,
        "scientifically_qualified": False,
    }
    safe_write_json(output / "manifest.json", manifest)
    return {
        "status": "BLOCKED_NOT_RUN",
        "scenarios": len(result_rows),
        "output": str(output),
        "attempted_stresses": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--exact-minute", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.coverage, args.exact_minute, args.output), indent=2))


if __name__ == "__main__":
    main()
