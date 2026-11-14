"""Read-only selected-source operational incident and separate private ack receipts.

The incident detector never calls source, Guardian, PM03/PM04, active k,
registry or broker writers. Its two-cycle notification policy must never delay
the existing immediate source GAP / pending-new-risk fence.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .pm03_account import digest, number
from .pm_private_io import atomic_private_output
from .production_manifest import canonical
from .strategy_health import (
    OperationalIncident,
    Strict,
    StrategyAssessment,
    ZERO_SHA,
    seal,
    utc,
)

SHA = r"^[0-9a-f]{64}$"


class CycleObservation(Strict):
    original_source_receipt_sha256: str = Field(pattern=SHA)
    fault_first_known_at: datetime
    failed_expected_cycles: int = Field(ge=0, le=10000)
    measured_cycle_seconds: int | None = Field(default=None, ge=1, le=86400)
    owner_alias: str | None = Field(default=None, min_length=1, max_length=80)
    route_alias: str | None = Field(default=None, min_length=1, max_length=80)
    delivery_verified: Literal[False] = False

    @model_validator(mode="after")
    def cycle_valid(self):
        utc(self.fault_first_known_at)
        return self


class AckReceipt(Strict):
    schema_version: Literal["strategy_operational_incident_ack_v1"] = Field(
        default="strategy_operational_incident_ack_v1", alias="schema"
    )
    incident_sha256: str = Field(pattern=SHA)
    delivered_at: datetime
    acknowledged_at: datetime
    owner_alias: str = Field(min_length=1, max_length=80)
    route_alias: str = Field(min_length=1, max_length=80)
    evidence_sha256: str = Field(pattern=SHA)
    result: Literal["PROVISIONAL_ACK_TARGET", "LATE_ACK_UNVERIFIED_SLA"]
    no_financial_mutation: Literal[True] = True
    trading_authorized: Literal[False] = False

    @model_validator(mode="after")
    def ack_valid(self):
        utc(self.delivered_at)
        utc(self.acknowledged_at)
        if self.acknowledged_at < self.delivered_at:
            raise ValueError("ACK_BEFORE_DELIVERY")
        delta = self.acknowledged_at - self.delivered_at
        status = (
            "PROVISIONAL_ACK_TARGET"
            if delta <= timedelta(minutes=10)
            else "LATE_ACK_UNVERIFIED_SLA"
        )
        if self.result != status:
            raise ValueError("INCIDENT_ACK_RESULT_INVALID")
        return self


def classify(
    report: StrategyAssessment,
    *,
    cycle: CycleObservation | None,
    original_finance: dict | None,
    quote_stale: bool,
) -> OperationalIncident | None:
    if report.strategy.tier != "SELECTED":
        return None
    source_gap = report.source_observability in {"GAP", "STALE", "INCOMPLETE_SCOPE"}
    if not source_gap and not quote_stale:
        return None
    cause = (
        "SOURCE_GAP"
        if report.source_observability == "GAP"
        else "SOURCE_STALE"
        if source_gap
        else "QUOTE_STALE"
    )
    source_start = None
    if cause == "SOURCE_GAP":
        gaps = [gap.started_at for gap in report.missing_intervals if gap.reason == "GAP"]
        if gaps:
            source_start = min(gaps)
    if cycle is not None:
        if cycle.fault_first_known_at > report.as_of:
            raise ValueError("FUTURE_SOURCE_INCIDENT")
        if source_start is not None and cycle.fault_first_known_at != source_start:
            raise ValueError("SOURCE_FAULT_FIRST_KNOWN_MISMATCH")
        if cause == "SOURCE_GAP" and not any(
            gap.reason == "GAP"
            and gap.started_at == cycle.fault_first_known_at
            and gap.original_source_receipt_sha256 == cycle.original_source_receipt_sha256
            for gap in report.missing_intervals
        ):
            raise ValueError("SOURCE_INCIDENT_ORIGINAL_RECEIPT_MISMATCH")
        source_start = cycle.fault_first_known_at
    if source_start is None:
        # No authenticated original interval -> no invented incident time.
        return None
    if original_finance is None:
        risk = "UNKNOWN"
    else:
        if original_finance.get("schema") != "strategy_pm03_original_verified_v1":
            raise ValueError("ORIGINAL_PM03_FINANCE_UNVERIFIED")
        snapshot = original_finance["account"]
        paper = snapshot.get("pm04", {}).get("paper_execution", {})
        alias = report.strategy.source_alias
        open_qty = snapshot.get("pm_quantities", {}).get(alias, {})
        pending = any(
            row.get("pod") == alias and row.get("status") == "PENDING_5M"
            for row in paper.get("history", {}).values()
        )
        unresolved = bool(paper.get("unresolved_exposures", {}).get(alias))
        risk = (
            "UNRESOLVED_EXIT"
            if unresolved
            else "OPEN"
            if any(number(q) != 0 for q in open_qty.values())
            else "PENDING_T300"
            if pending
            else "FLAT"
        )
    if risk in {"UNRESOLVED_EXIT", "OPEN", "PENDING_T300"}:
        priority = "CRITICAL_RISK_EXPOSED"
    elif risk == "UNKNOWN" or cause == "SOURCE_GAP":
        priority = "ELEVATED"
    else:
        priority = "OBSERVATION"
    failed = cycle.failed_expected_cycles if cycle else 0
    cadence = cycle.measured_cycle_seconds if cycle else None
    if cadence is None:
        delivery = "PENDING_UNVERIFIED_CADENCE"
    elif failed < 2:
        delivery = "PENDING_SECOND_CYCLE"
    elif not cycle.owner_alias or not cycle.route_alias:
        delivery = "PENDING_OWNER_ROUTE"
    else:
        delivery = "ELIGIBLE_NOT_SENT"
    incident_sha = digest(
        [
            report.strategy.strategy_sha256,
            cause,
            source_start.isoformat(),
            report.campaign.campaign_id,
        ]
    )
    return OperationalIncident(
        incident_sha256=incident_sha,
        first_known_at=source_start,
        selected_scope_sha256=report.strategy.strategy_sha256,
        cause=cause,
        priority=priority,
        failed_expected_cycles=failed,
        expected_cycle_seconds=cadence,
        risk_at_finding=risk,
        alert_delivery=delivery,
    )


def attach_incident(report: StrategyAssessment, incident: OperationalIncident | None):
    if incident is None:
        return report
    if (
        report.strategy.tier != "SELECTED"
        or incident.selected_scope_sha256 != report.strategy.strategy_sha256
        or incident.first_known_at > report.as_of
    ):
        raise ValueError("INCIDENT_REPORT_SCOPE_INVALID")
    previous = {row.incident_sha256: row for row in report.operational_incidents}
    if incident.incident_sha256 in previous and previous[incident.incident_sha256] != incident:
        raise ValueError("INCIDENT_REPLAY_CONFLICT")
    previous[incident.incident_sha256] = incident
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "operational_incidents": tuple(previous[k] for k in sorted(previous)),
            }
        )
    )


def publish_ack(directory: Path, receipt: AckReceipt) -> str:
    """Separate owner-private operational audit receipt; no financial write."""
    sha = digest(receipt.model_dump(mode="json"))
    target = directory / f"ack-{sha}.json"
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError("ACK_PRIVATE_DIRECTORY_REQUIRED")
    atomic_private_output(target, canonical(receipt.model_dump(mode="json")))
    return sha


def acknowledge(
    incident: OperationalIncident,
    *,
    delivered_at: datetime,
    acknowledged_at: datetime,
    owner_alias: str,
    route_alias: str,
    evidence_sha256: str,
    private_directory: Path,
) -> tuple[OperationalIncident, str]:
    if delivered_at < incident.first_known_at:
        raise ValueError("ACK_DELIVERY_PRECEDES_INCIDENT")
    status = (
        "PROVISIONAL_ACK_TARGET"
        if acknowledged_at - delivered_at <= timedelta(minutes=10)
        else "LATE_ACK_UNVERIFIED_SLA"
    )
    receipt = AckReceipt(
        incident_sha256=incident.incident_sha256,
        delivered_at=delivered_at,
        acknowledged_at=acknowledged_at,
        owner_alias=owner_alias,
        route_alias=route_alias,
        evidence_sha256=evidence_sha256,
        result=status,
    )
    sha = publish_ack(private_directory, receipt)
    return incident.model_copy(
        update={
            "owner_acknowledgement": "ACKNOWLEDGED",
            "acknowledged_at": acknowledged_at,
            "acknowledgement_evidence_sha256": sha,
        }
    ), sha
