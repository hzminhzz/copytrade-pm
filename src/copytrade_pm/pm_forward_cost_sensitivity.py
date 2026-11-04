"""Pure PM03/PM04 synthetic-cost replay, isolated from committed paper journals.

Reprice the *same sealed hypothetical decisions* under 2x/3x fee, spread,
slippage and impact assumptions. The replay is a diagnostic, not a new
strategy, historical Gemini rerun, prospective fill or OOS qualification.
"""

from __future__ import annotations

from copy import deepcopy

from .pm03_account import Account, Rulebook, digest, number
from .pm_forward_journal import PaperJournal

COST_KEYS = (
    "fee_bps",
    "full_spread_bps",
    "slippage_bps",
    "impact_bps_at_full_participation",
)


def stress_cost_event(event: dict, *, factor: int) -> dict:
    if factor not in (2, 3):
        raise ValueError("UNSUPPORTED_PAPER_COST_MULTIPLIER")
    row = deepcopy(event)
    inputs = row.get("input")
    container = inputs if isinstance(inputs, dict) and "costs" in inputs else row
    costs = container.get("costs")
    if costs is None:
        return row
    if not isinstance(costs, dict) or any(key not in costs for key in COST_KEYS):
        raise ValueError("PAPER_COST_STRESS_EVIDENCE_INCOMPLETE")
    for name in COST_KEYS:
        old = number(costs[name])
        if old < 0:
            raise ValueError("PAPER_COST_STRESS_NEGATIVE_ASSUMPTION")
        costs[name] = str(old * factor)
    for contract in row.get("market_contracts", {}).values():
        if not isinstance(contract, dict):
            raise ValueError("PAPER_COST_STRESS_CONTRACT_INVALID")
        contract["costs_sha"] = digest(costs)
        if contract.get("modeled_spread_bps") is not None:
            contract["modeled_spread_bps"] = str(number(costs["full_spread_bps"]))
        contract.pop("contract_sha", None)
        contract["contract_sha"] = digest(contract)
    return row


def replay_cost_sensitivity(
    rulebook: Rulebook,
    *,
    started_at: str,
    events: list[dict],
    factor: int,
) -> dict:
    account = Account.start(rulebook, started_at)
    cost_events = 0
    rejected = 0
    for raw in events:
        adjusted = stress_cost_event(raw, factor=factor)
        if adjusted != raw:
            cost_events += 1
        result = PaperJournal._apply(account, adjusted)
        account.verify()
        if result.get("status", "").startswith("BLOCKED"):
            rejected += 1
    if not cost_events:
        return {
            "status": "NO_MODELED_EXECUTION_EVIDENCE",
            "multiplier": factor,
            "evidence_class": "SYNTHETIC_COST_STRESS_ONLY",
            "scientifically_qualified": False,
        }
    return {
        "status": "SYNTHETIC_COST_STRESS_REPLAY_ONLY",
        "multiplier": factor,
        "net_modeled_pnl": str(account.equity - rulebook.initial_balance),
        "ending_equity": str(account.equity),
        "total_fees": str(account.costs),
        "total_funding": str(account.funding),
        "rejected_events": rejected,
        "repriced_cost_events": cost_events,
        "source_events_reused": len(events),
        "evidence_class": "SYNTHETIC_COST_STRESS_ONLY",
        "paper_observed": False,
        "scientifically_qualified": False,
        "broker_executed": False,
    }
