"""Strict PM-02 -> PM-03 research-only evidence boundary.

A ranking/risk-budget proposal is NOT a position target or loss guarantee.
UNKNOWN source positions never get turned into flat exposure.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path

from .pm03_account import clock, digest, number


@dataclass(frozen=True)
class ManagerGate:
    artifact_sha: str
    raw_sha: str
    as_of: str
    wallet_count: int
    scientifically_qualified: int
    seats: tuple[tuple[str | None, D], ...]
    reserve_r: D
    status: str

    @property
    def actionable_budgets(self) -> dict[str, D]:
        if self.status != "HAS_RESEARCH_BUDGET_PROPOSALS":
            return {}
        return {name: r for name, r in self.seats if name is not None and r > 0}


def inspect_pm02(path: Path, *, decision_at: str, expected_sha: str) -> ManagerGate:
    raw = path.read_bytes()
    obj = json.loads(raw)
    if obj.get("schema") != "pm02_manager_governance_v1":
        raise ValueError("PM02_SCHEMA_MISMATCH")
    provided = obj.get("sha256")
    without_hash = {k: v for k, v in obj.items() if k != "sha256"}
    if provided != digest(without_hash) or provided != expected_sha:
        raise ValueError("PM02_ARTIFACT_HASH_MISMATCH")
    if clock(obj["asof"]) > clock(decision_at):
        raise ValueError("PM02_PROPOSALS_FROM_FUTURE")
    if obj.get("live_trading_authorized") is not False:
        raise ValueError("PM02_LIVE_AUTHORITY_CONTAMINATION")
    if obj["policy"].get("risk_authority") != "PM03_ACCOUNT_SUPERVISOR_ONLY":
        raise ValueError("INVALID_RISK_AUTHORITY")
    qualified = int(obj["qualified_count"])
    seat_rows = obj["five_seats"]
    if len(seat_rows) != 5 or len(obj["cards"]) != 36:
        raise ValueError("PM02_COHORT_OR_SEAT_DRIFT")
    seats = []
    for row in seat_rows:
        if row.get("authority") != "RESEARCH_PROPOSAL_ONLY":
            raise ValueError("PM02_UNAUTHORIZED_SEAT")
        wallet, risk = row.get("wallet"), number(row["risk_budget_r"])
        if risk < 0 or (wallet is None and risk != 0):
            raise ValueError("INCONSISTENT_EMPTY_SEAT")
        if wallet and row.get("state") == "EMPTY":
            raise ValueError("INVALID_MANAGER_LIFECYCLE")
        seats.append((wallet, risk))
    if len({name for name, _ in seats if name is not None}) != sum(
        name is not None for name, _ in seats
    ):
        raise ValueError("DUPLICATE_PM_SEAT")
    used = sum((r for _, r in seats), D("0"))
    if used != number(obj["research_risk_allocated_r"]):
        raise ValueError("PM02_BUDGET_RECONCILIATION")
    if qualified == 0 and (
        used != 0
        or any(name is not None for name, _ in seats)
        or obj["scientifically_qualified_from_pm01"] != 0
    ):
        raise ValueError("UNQUALIFIED_ACTIVE_MANAGER")
    if qualified < 0 or qualified > 36:
        raise ValueError("INVALID_QUALIFIED_COUNT")
    if number(obj["reserve_r"]) < 0:
        raise ValueError("INVALID_RESERVE")
    return ManagerGate(
        artifact_sha=provided,
        raw_sha=sha256(raw).hexdigest(),
        as_of=obj["asof"],
        wallet_count=36,
        scientifically_qualified=qualified,
        seats=tuple(seats),
        reserve_r=number(obj["reserve_r"]),
        status="ZERO_ACTIONABLE_RISK" if not used else "HAS_RESEARCH_BUDGET_PROPOSALS",
    )


def require_external_targets(
    gate: ManagerGate,
    *,
    position_artifact_sha: str | None,
    position_first_known_at: str | None,
    decision_at: str,
) -> dict:
    """Only confirms availability; positional targets need another sealed PM-01 artifact."""
    if not gate.actionable_budgets:
        return {"status": "NO_QUALIFIED_SEATS", "actionable": False, "targets": {}}
    if not position_artifact_sha or not position_first_known_at:
        return {"status": "UNKNOWN_SOURCE_POSITIONS", "actionable": False, "targets": None}
    if len(position_artifact_sha) != 64 or clock(position_first_known_at) > clock(decision_at):
        raise ValueError("UNVERIFIED_PROSPECTIVE_POSITION_SOURCE")
    # This adapter cannot infer quantities from R budgets or reconstruct
    # the missing signed per-instrument positions.
    return {"status": "NEEDS_SEALED_POSITION_CONTRACT", "actionable": False, "targets": None}
