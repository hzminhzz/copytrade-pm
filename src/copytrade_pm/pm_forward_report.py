"""Evidence-tiered, read-only PM-03 forward-paper financial report (FP-13 partial).

Replays the same PM-03/PM-04 event interpreter after verifying the private
SQLite chain. This never creates positions, paper orders, or scientific alpha.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from .pm03_account import Account, Rulebook, clock, number
from .pm_forward_journal import PaperJournal
from .pm_sqlite_readonly import connect_readonly


def _values(account: Account) -> dict:
    snapshot = account.snapshot()
    exposure = Decimal("0")
    net = Decimal("0")
    for key, qty in account.quantities.items():
        notion = qty * account.marks[key]
        exposure += abs(notion)
        net += notion
    return {
        "balance": snapshot["balance"],
        "cash": snapshot["cash"],
        "equity": snapshot["equity"],
        "realized_pnl": snapshot["realized_pnl"],
        "unrealized_pnl": str(account.unrealized_pnl),
        "fees": snapshot["costs"],
        "funding": snapshot["funding"],
        "gross_notional": str(exposure),
        "net_notional": str(net),
        "risk": snapshot["risk"],
        "halt_reason": snapshot["halt_reason"],
        "breached": snapshot["breached"],
        "pm_costs": snapshot["pm_costs"],
        "pm_funding": snapshot["pm_funding"],
        "pm_pnl": {pm: str(pnl) for pm, pnl in account.pm_equity_pnl().items()},
        "signed_positions": snapshot["quantities"],
    }


def report_one(
    db: sqlite3.Connection, run_id: str, report_at: str, *, cost_stress: bool = False
) -> dict:
    verified = PaperJournal.verify(db, run_id)
    if clock(verified["last_event_at"]) > clock(report_at):
        raise ValueError("PAPER_REPORT_ASOF_PRECEDES_COMMITTED_STATE")
    row = db.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
    manifest = json.loads(row[0])
    rulebook = Rulebook.from_dict(manifest["rulebook"])
    account = Account.start(rulebook, manifest["started_at"])
    initial = account.snapshot()
    equity_high = number(initial["equity"])
    max_drawdown = Decimal("0")
    unknown_funding = 0
    unknown_margin = 0
    simulated_fills = 0
    modeled_spread_slippage_impact = Decimal("0")
    rejected_events = 0
    quote_qualities: set[str] = set()
    timeline: list[dict] = [
        {"at": manifest["started_at"], "equity": initial["equity"], "risk": initial["risk"]}
    ]
    event_rows = db.execute(
        "SELECT input FROM events WHERE run_id=? ORDER BY seq", (run_id,)
    ).fetchall()
    for (payload,) in event_rows:
        event = json.loads(payload)
        result = PaperJournal.apply(account, event)
        account.verify()
        equity_high = max(equity_high, account.equity)
        max_drawdown = max(max_drawdown, equity_high - account.equity)
        if result.get("status") == "UNKNOWN_FUNDING":
            unknown_funding += 1
        if result.get("margin", {}).get("status") == "UNKNOWN_LIQUIDATION":
            unknown_margin += 1
        if (
            result.get("status", "").startswith("BLOCKED")
            or result.get("status") == "UNKNOWN_FUNDING"
        ):
            rejected_events += 1
        execution = result.get("execution", {})
        if isinstance(execution, dict):
            fills = execution.get("fills", [])
            if isinstance(fills, list):
                simulated_fills += len(fills)
                for fill in fills:
                    modeled_spread_slippage_impact += abs(
                        number(fill["quantity"])
                        * (number(fill["execution_price"]) - number(fill["mid_price"]))
                    )
        for observation in event.get(
            "observations", event.get("input", {}).get("observations", [])
        ):
            quote_qualities.add(observation.get("quality", "UNKNOWN"))
        timeline.append(
            {
                "at": event["event_at"],
                "equity": str(account.equity),
                "risk": account.risk.value,
            }
        )
    if account.snapshot() != verified["account"]:
        raise ValueError("PAPER_REPORT_REPLAY_DIVERGENCE")
    stresses = {2: "NOT_COMPUTED", 3: "NOT_COMPUTED"}
    if cost_stress:
        from .pm_forward_cost_sensitivity import replay_cost_sensitivity

        parsed_events = [json.loads(item[0]) for item in event_rows]
        stresses = {
            factor: replay_cost_sensitivity(
                rulebook,
                started_at=manifest["started_at"],
                events=parsed_events,
                factor=factor,
            )
            for factor in (2, 3)
        }
    status = _values(account)
    account_end = account.equity - rulebook.initial_balance
    coverage = {
        "actual_source_coverage": "UNKNOWN",
        "actual_market_coverage": "UNKNOWN",
        "actual_funding_coverage": "UNKNOWN" if unknown_funding else "NOT_ATTESTED",
        "first_known_prospective_verified": False,
        "source_cursors": verified["source_cursors"],
        "event_count": len(event_rows),
        "blocked_or_unknown_events": rejected_events,
        "unknown_funding_intervals": unknown_funding,
        "unknown_liquidation_assessments": unknown_margin,
        "quote_quality_labels": sorted(quote_qualities),
    }
    return {
        "schema": "paper_economics_report_v1",
        "run_id": run_id,
        "report_as_of": report_at,
        "manifest_sha": verified["manifest_sha"],
        "portfolio_sha": manifest["portfolio_sha"],
        "policy_sha": manifest["policy_sha"],
        "release_sha": manifest["release_sha"],
        "journal_head_sha": verified["journal_head_sha"],
        "journal_cursor": verified["cursor"],
        "order_route": "NONE",
        "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
        "paper_observed": False,
        "scientifically_qualified": False,
        "broker_executed": False,
        "reported_pnl_scope": "HYPOTHETICAL_MODELED_ONLY",
        "initial_equity": initial["equity"],
        "net_modeled_pnl": str(account_end),
        "max_observed_model_drawdown": str(max_drawdown),
        "modeled_spread_slippage_impact_cash": str(modeled_spread_slippage_impact),
        "modeled_external_fill_count": simulated_fills,
        "financial_state": status,
        "coverage": coverage,
        "cost_sensitivity_2x": stresses[2],
        "cost_sensitivity_3x": stresses[3],
        "timeline": timeline,
    }


def _matched_modeled_p1_p14(rows: list[dict]) -> dict:
    """Compare sealed synthetic model outputs only; never manufacture live TE."""
    from .pm_forward_portfolios import P1, P14

    if len(rows) != 2 or {item["run_id"] for item in rows} != {"P1", "P14"}:
        return {
            "status": "NOT_MATCHED_P1_P14_RUNS",
            "paper_observed": False,
            "real_tracking_error": "UNKNOWN",
        }
    by_id = {item["run_id"]: item for item in rows}
    p1, p14 = by_id["P1"], by_id["P14"]
    if p1["portfolio_sha"] != P1.sha or p14["portfolio_sha"] != P14.sha:
        raise ValueError("PAPER_MATCHED_FROZEN_PORTFOLIO_IDENTITY_MISMATCH")
    a, b = p1["timeline"], p14["timeline"]
    aligned = len(a) == len(b) and all(x["at"] == y["at"] for x, y in zip(a, b))
    modeled_dispersion = None
    if aligned and len(a) >= 3:
        diffs = []
        for index in range(1, len(a)):
            old_a = number(a[index - 1]["equity"])
            old_b = number(b[index - 1]["equity"])
            if old_a <= 0 or old_b <= 0:
                aligned = False
                break
            model_return_a = (number(a[index]["equity"]) - old_a) / old_a
            model_return_b = (number(b[index]["equity"]) - old_b) / old_b
            diffs.append((model_return_b - model_return_a) * Decimal("10000"))
        if aligned and len(diffs) >= 2:
            center = sum(diffs, Decimal("0")) / Decimal(len(diffs))
            sample_variance = sum(
                ((delta - center) ** 2 for delta in diffs), Decimal("0")
            ) / Decimal(len(diffs) - 1)
            modeled_dispersion = str(sample_variance.sqrt())
    scenarios = {}
    for factor in (2, 3):
        left = p1[f"cost_sensitivity_{factor}x"]
        right = p14[f"cost_sensitivity_{factor}x"]
        if (
            isinstance(left, dict)
            and isinstance(right, dict)
            and ("net_modeled_pnl" in left and "net_modeled_pnl" in right)
        ):
            scenarios[f"{factor}x"] = str(
                number(right["net_modeled_pnl"]) - number(left["net_modeled_pnl"])
            )
        else:
            scenarios[f"{factor}x"] = "NOT_COMPUTED"
    return {
        "status": "SYNTHETIC_MATCHED_OUTPUT_ONLY_NO_PROSPECTIVE_COVERAGE",
        "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
        "p1_model_equity": p1["financial_state"]["equity"],
        "p14_model_equity": p14["financial_state"]["equity"],
        "p14_minus_p1_model_pnl": str(
            number(p14["net_modeled_pnl"]) - number(p1["net_modeled_pnl"])
        ),
        "p14_minus_p1_model_drawdown": str(
            number(p14["max_observed_model_drawdown"]) - number(p1["max_observed_model_drawdown"])
        ),
        "model_event_clocks_aligned": aligned,
        "model_event_return_dispersion_bps": modeled_dispersion if aligned else None,
        "not_annualized": True,
        "scenario_p14_minus_p1_model_pnl": scenarios,
        "real_tracking_error": "NOT_ESTIMABLE_WITHOUT_MATCHED_PROSPECTIVE_PAPER",
        "real_coverage": "UNKNOWN",
        "scientifically_qualified": False,
        "paper_observed": False,
    }


def build_report(
    db_path: Path, run_ids: tuple[str, ...], *, as_of: str, cost_stress: bool = False
) -> dict:
    if not run_ids or len(set(run_ids)) != len(run_ids):
        raise ValueError("PAPER_REPORT_RUNS_REQUIRED_UNIQUE")
    clock(as_of)
    with closing(connect_readonly(db_path, timeout=0)) as db:
        rows = [report_one(db, run_id, as_of, cost_stress=cost_stress) for run_id in run_ids]
    return {
        "schema": "paper_campaign_report_v1",
        "as_of": as_of,
        "run_count": len(rows),
        "runs": rows,
        "matched_p1_p14": "NOT_QUALIFIED_NO_INDEPENDENT_PROSPECTIVE_COVERAGE",
        "matched_model_comparison": _matched_modeled_p1_p14(rows),
        "cost_sensitivity_status": (
            "SYNTHETIC_REPLAY_ONLY_NO_ALPHA" if cost_stress else "NOT_COMPUTED"
        ),
        "alpha_claim": False,
        "challenge_pass_probability_claim": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only virtual paper economics")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--cost-stress", action="store_true")
    parser.add_argument("--as-of", default=datetime.now(UTC).isoformat())
    args = parser.parse_args()
    print(
        json.dumps(
            build_report(
                args.db, tuple(args.run_id), as_of=args.as_of, cost_stress=args.cost_stress
            ),
            sort_keys=True,
            indent=2,
        )
    )
