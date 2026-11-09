"""Fail-closed, read-only scientific readiness audit over the existing signed ledger.

This module deliberately cannot issue A/B grades or an authorization to trade.
ProspectiveLedger.read() verifies the existing SHA chain and Ed25519 attestations.
A signature verifies a declaration, not independent truth of economic measurements.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from .pm_research_contracts import Count

from .pm02_outcomes import CLAIM_FIELDS, DIGEST_FIELDS, SCHEMA as WHOLE_ACCOUNT_SCHEMA
from .pm_prospective_ledger import ProspectiveLedger, digest, utc


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class EvidenceReadiness:
    schema: Literal["ti_prospective_evidence_readiness_v1"]
    status: Literal["NOT_SCIENTIFICALLY_QUALIFIED"]
    asof: str
    holdout_start: str
    holdout_end: str
    selection_plan_sha256: str
    ledger_head_asof_sha256: str
    receipt_count: Count
    independent_receipt_audits: Count
    signed_matched_outcomes: Count
    eligible_whole_account_outcomes: Count
    distinct_wallets: Count
    distinct_source_events: Count
    matched_horizon_groups: Count
    complete_group_incremental_mean_r: str | None
    complete_group_worst_incremental_r: str | None
    reasons: tuple[str, ...]
    eligible_evidence_sha256: str

    def as_wire(self) -> dict:
        return asdict(self)


def audit_prospective_evidence(
    ledger: ProspectiveLedger,
    *,
    asof: str,
    holdout_start: str,
    holdout_end: str,
    selection_plan_sha256: str,
    required_horizons: tuple[int, ...] = (5, 15, 60),
) -> EvidenceReadiness:
    """Audit sealed outcomes; never backdate an audit or promote a model.

    The holdout and selection digest are *caller-declared*, not asserted to
    have been externally pre-registered. That external pre-registration,
    independent execution economics, and robust statistical testing remain
    separate scientific gates.
    """
    from .trader_intelligence import _sha

    _sha(selection_plan_sha256)
    cut, start, end = utc(asof), utc(holdout_start), utc(holdout_end)
    if not start < end <= cut:
        raise ValueError("INVALID_PIT_HOLDOUT_CLOCKS")
    if not required_horizons or len(required_horizons) != len(set(required_horizons)):
        raise ValueError("INVALID_REQUIRED_HORIZONS")
    if any(h not in (5, 15, 60) for h in required_horizons):
        raise ValueError("UNSUPPORTED_OUTCOME_HORIZON")

    # read() independently verifies ALL events, including tampering outside
    # the evaluation window. Never bypass its full chain/signature validation.
    rows = ledger.read()
    visible = [row for row in rows if utc(row["payload"]["recorded_at"]) <= cut]
    receipts = {row["payload"]["event_id"]: row for row in visible if row["kind"] == "RECEIPT"}
    audits = {row["payload"]["event_id"]: row for row in visible if row["kind"] == "AUDIT"}
    outcome_rows = [row for row in visible if row["kind"] == "OUTCOME"]
    eligible: list[dict] = []
    wallet_set: set[str] = set()
    source_set: set[str] = set()
    horizon_sets: dict[str, set[int]] = {}
    deltas_by_source: dict[str, dict[int, Decimal]] = {}
    failures: set[str] = set()
    for row in outcome_rows:
        att = row["payload"]["attestation"]
        source_id = att["source_event_id"]
        receipt_row = receipts.get(source_id)
        audit_row = audits.get(source_id)
        if receipt_row is None or audit_row is None:
            failures.add("OUTCOME_WITHOUT_ASOF_RECEIPT_AUDIT")
            continue
        receipt = receipt_row["payload"]
        first_known = utc(receipt["first_known_at"])
        decision = utc(att["decision_at"])
        outcome_time = utc(att["outcome_known_at"])
        sealed_time = utc(row["payload"]["recorded_at"])
        if not start <= first_known <= decision < end:
            continue
        if (
            att["schema"] != WHOLE_ACCOUNT_SCHEMA
            or att.get("selection_plan_sha256") != selection_plan_sha256
            or any(att.get(name) is not True for name in CLAIM_FIELDS)
            or any(
                not isinstance(att.get(name), str) or len(att[name]) != 64 for name in DIGEST_FIELDS
            )
        ):
            failures.add("MISSING_MATCHED_WHOLE_ACCOUNT_EVIDENCE")
            continue
        horizon = att["horizon_minutes"]
        if horizon not in required_horizons:
            continue
        if (
            not first_known <= decision <= outcome_time <= sealed_time <= cut
            or outcome_time < decision + timedelta(minutes=horizon)
            or receipt.get("verified_first_known") is not False
            or receipt.get("source_snapshot") is not False
        ):
            failures.add("UNVERIFIED_PROSPECTIVE_CLOCK_OR_COVERAGE")
            continue
        if (
            Decimal(str(att["follower_net_r"])).is_nan()
            or Decimal(str(att["control_net_r"])).is_nan()
        ):
            failures.add("INVALID_FOLLOWER_CONTROL_ECONOMICS")
            continue
        eligible.append(
            {
                "row_sha": row["sha"],
                "wallet": receipt["wallet"],
                "source_event_id": source_id,
                "horizon": horizon,
                "outcome_known_at": sealed_time.isoformat(),
            }
        )
        wallet_set.add(receipt["wallet"])
        source_set.add(source_id)
        horizon_sets.setdefault(source_id, set()).add(horizon)
        # One source episode is a dependence unit, not three independent wins.
        deltas_by_source.setdefault(source_id, {})[horizon] = Decimal(
            str(att["follower_net_r"])
        ) - Decimal(str(att["control_net_r"]))
    complete_deltas = [
        min(values[h] for h in required_horizons)
        for _source, values in sorted(deltas_by_source.items())
        if set(required_horizons).issubset(values)
    ]
    complete = len(complete_deltas)
    reasons = set(failures)
    if not receipts:
        reasons.add("NO_PROSPECTIVE_RECEIPTS")
    if not audits:
        reasons.add("NO_INDEPENDENT_RECEIPT_AUDITS")
    if not eligible:
        reasons.add("NO_SIGNED_MATURE_WHOLE_ACCOUNT_OUTCOMES")
    if complete == 0:
        reasons.add("NO_COMPLETE_DECLARED_HORIZON_GROUP")
    reasons.update(
        (
            "PREDECLARED_INDEPENDENT_HOLDOUT_NOT_ESTABLISHED",
            "INDEPENDENT_ECONOMIC_TRUTH_NOT_ESTABLISHED_BY_SIGNATURE",
            "OOS_SKILL_AND_CALIBRATION_NOT_TESTED",
        )
    )
    return EvidenceReadiness(
        schema="ti_prospective_evidence_readiness_v1",
        status="NOT_SCIENTIFICALLY_QUALIFIED",
        asof=cut.isoformat(),
        holdout_start=start.isoformat(),
        holdout_end=end.isoformat(),
        selection_plan_sha256=selection_plan_sha256,
        ledger_head_asof_sha256=visible[-1]["sha"] if visible else "0" * 64,
        receipt_count=sum(row["kind"] == "RECEIPT" for row in visible),
        independent_receipt_audits=len(audits),
        signed_matched_outcomes=len(outcome_rows),
        eligible_whole_account_outcomes=len(eligible),
        distinct_wallets=len(wallet_set),
        distinct_source_events=len(source_set),
        matched_horizon_groups=complete,
        complete_group_incremental_mean_r=(
            str(sum(complete_deltas) / complete) if complete_deltas else None
        ),
        complete_group_worst_incremental_r=(str(min(complete_deltas)) if complete_deltas else None),
        reasons=tuple(sorted(reasons)),
        eligible_evidence_sha256=digest(sorted(eligible, key=lambda v: v["row_sha"])),
    )
