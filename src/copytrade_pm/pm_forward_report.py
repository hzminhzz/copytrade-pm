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
    verified = PaperJournal._verify(db, run_id)
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
        result = PaperJournal._apply(account, event)
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


def build_report(
    db_path: Path, run_ids: tuple[str, ...], *, as_of: str, cost_stress: bool = False
) -> dict:
    if not run_ids or len(set(run_ids)) != len(run_ids):
        raise ValueError("PAPER_REPORT_RUNS_REQUIRED_UNIQUE")
    clock(as_of)
    db_path = Path(db_path)
    uri = "file:" + str(db_path.resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = [report_one(db, run_id, as_of, cost_stress=cost_stress) for run_id in run_ids]
    return {
        "schema": "paper_campaign_report_v1",
        "as_of": as_of,
        "run_count": len(rows),
        "runs": rows,
        "matched_p1_p14": "NOT_QUALIFIED_NO_INDEPENDENT_PROSPECTIVE_COVERAGE",
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
