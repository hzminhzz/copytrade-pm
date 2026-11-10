"""Predeclared weekly research warnings and conservative two-look recovery.

All outputs remain uncalibrated advisory. No k, Guardian, broker, account or
registry interface exists in this module.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from .pm03_account import digest
from .strategy_health import (
    Advisory,
    RecoveryStatus,
    StrategyAssessment,
    WeeklyLook,
    WindowStats,
    ZERO_SHA,
    seal,
)

D = Decimal
EARLY = {"window": 7, "effective": D(8), "days": 7, "coverage": D("0.8"), "adverse": D("0.25")}
PERSISTENT = {
    "window": 30,
    "effective": D(20),
    "days": 14,
    "coverage": D("0.9"),
    "adverse": D("0.50"),
}


def gate(window: WindowStats, *, persistent: bool) -> tuple[str, tuple[str, ...]]:
    """Deterministic provisional diagnostic, never statistical qualification."""
    criteria = PERSISTENT if persistent else EARLY
    if window.window_days != criteria["window"]:
        raise ValueError("WINDOW_NOT_PREDECLARED")
    reasons = []
    if window.source_gap_unknown:
        reasons.append("SOURCE_GAP_UNKNOWN_DENOMINATOR")
    if window.effective_opportunities is None:
        reasons.append("INDEPENDENCE_UNESTIMABLE")
    elif window.effective_opportunities < criteria["effective"]:
        reasons.append("EFFECTIVE_OPPORTUNITIES_BELOW_GATE")
    if window.observed_days < criteria["days"]:
        reasons.append("DISTINCT_OBSERVED_DAYS_BELOW_GATE")
    if window.comparable_coverage is None:
        reasons.append("COVERAGE_UNKNOWN")
    elif window.comparable_coverage < criteria["coverage"]:
        reasons.append("COMPARABLE_COVERAGE_BELOW_GATE")
    if window.missing_critical_prices:
        reasons.append("CRITICAL_INDEPENDENT_QUOTE_MISSING")
    if window.missing_critical_finance:
        reasons.append("CRITICAL_FEES_FUNDING_OR_ACCOUNT_MISSING")
    if window.matched_adverse_r is None:
        reasons.append("MATCHED_INCREMENTAL_EFFECT_UNKNOWN")
    if reasons:
        return "INSUFFICIENT_EVIDENCE", tuple(reasons)
    if window.matched_adverse_r >= criteria["adverse"]:
        return ("PERSISTENT_WARNING" if persistent else "EARLY_WARNING"), ()
    return "NONE", ()


def _preflight(report: StrategyAssessment, look: WeeklyLook) -> tuple[str, ...]:
    reasons = []
    campaign = report.campaign
    if not campaign.weekly_look_schedule:
        raise ValueError("WEEKLY_INFERENTIAL_SCHEDULE_NOT_DECLARED")
    if look.look_id not in campaign.weekly_look_ids:
        raise ValueError("UNDECLARED_INFERENTIAL_LOOK")
    target = campaign.weekly_look_ids.index(look.look_id)
    if look.scheduled_at != campaign.weekly_look_schedule[target]:
        raise ValueError("LOOK_SCHEDULE_DRIFT")
    previous_ids = [x.look_id for x in report.weekly_looks]
    if previous_ids and target <= campaign.weekly_look_ids.index(previous_ids[-1]):
        raise ValueError("INFERENTIAL_LOOK_REPLAY_OR_REORDER")
    if look.performed_at > report.as_of:
        raise ValueError("LOOK_FUTURE_OUTCOME")
    if look.evidence_sha256 in {x.evidence_sha256 for x in report.weekly_looks}:
        reasons.append("REPEATED_LOOK_EVIDENCE")
    known = {op.opportunity_id: op for op in report.opportunities}
    if any(x not in known for x in look.new_opportunity_ids):
        raise ValueError("LOOK_INVENTED_OR_OUT_OF_SCOPE_OPPORTUNITY")
    if any(known[x].first_known_at > look.performed_at for x in look.new_opportunity_ids):
        raise ValueError("LOOK_FUTURE_OPPORTUNITY")
    if report.source_observability != "VERIFIED_CONTINUOUS":
        reasons.append("SELECTED_SOURCE_NOT_CONTINUOUS")
    if report.follower_economics.evidence_class != look.evidence_class:
        reasons.append("FOLLOWER_FINANCE_CLASS_DRIFT")
    if not report.follower_economics.net_comparable:
        reasons.append("PM03_NET_COMPARABILITY_UNVERIFIED")
    if report.portfolio_contribution.status != "VERIFIED_PROSPECTIVE":
        reasons.append("MATCHED_COMMON_ACCOUNT_NOT_PROSPECTIVELY_VERIFIED")
    if not look.critical_finance_complete or not look.original_proof_independently_checked:
        reasons.append("ORIGINAL_MARKET_FINANCE_NOT_VERIFIED")
    if look.evidence_class in {"UNKNOWN", "RESEARCH_SYNTHETIC"}:
        reasons.append("NO_AUTHENTIC_PROSPECTIVE_INFERENCE")
    if not report.windows:
        reasons.append("WINDOW_EVIDENCE_UNAVAILABLE")
    return tuple(reasons)


def assess_weekly(report: StrategyAssessment, look: WeeklyLook) -> StrategyAssessment:
    """Append immutable predeclared look. A new report SHA is created; old is intact."""
    reasons = list(_preflight(report, look))
    windows = {w.window_days: w for w in report.windows}
    persistent, persistent_reasons = (
        gate(windows[30], persistent=True)
        if 30 in windows
        else ("INSUFFICIENT_EVIDENCE", ("MISSING_THIRTY_DAY_WINDOW",))
    )
    early, early_reasons = (
        gate(windows[7], persistent=False)
        if 7 in windows
        else ("INSUFFICIENT_EVIDENCE", ("MISSING_SEVEN_DAY_WINDOW",))
    )
    if reasons:
        status = "INSUFFICIENT_EVIDENCE"
        reasons.extend(persistent_reasons)
        reasons.extend(early_reasons)
    elif persistent == "PERSISTENT_WARNING":
        status = persistent
    elif early == "EARLY_WARNING":
        status = early
    elif persistent == "NONE" or early == "NONE":
        status = "NONE"
    else:
        status = "INSUFFICIENT_EVIDENCE"
        reasons.extend(persistent_reasons)
        reasons.extend(early_reasons)
    prior = report.advisory
    dated_at = prior.last_warning_at
    dated_sha = prior.last_warning_sha256
    if status in {"PERSISTENT_WARNING", "EARLY_WARNING"}:
        dated_at = look.performed_at
        dated_sha = digest(
            [
                report.strategy.strategy_sha256,
                report.campaign.campaign_id,
                look.look_id,
                look.evidence_sha256,
                status,
            ]
        )
    advisory = Advisory(
        status=status,
        assessed_at=look.performed_at,
        performed_weekly_look_id=look.look_id,
        last_warning_at=dated_at,
        last_warning_sha256=dated_sha,
        current_assessability=(
            "INSUFFICIENT_EVIDENCE"
            if status == "INSUFFICIENT_EVIDENCE"
            else "PROVISIONAL_LOOK_AVAILABLE"
        ),
        reasons=tuple(sorted(set(reasons))),
    )
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "weekly_looks": report.weekly_looks + (look,),
                "advisory": advisory,
            }
        )
    )


def recovery(report: StrategyAssessment) -> RecoveryStatus:
    """Never clear a historical warning from old marks, time or policy rollover."""
    warning = report.advisory
    if warning.last_warning_at is None:
        return RecoveryStatus()
    reason = []
    looks = [x for x in report.weekly_looks if x.performed_at > warning.last_warning_at]
    if len(looks) < 2:
        return RecoveryStatus(
            status="INSUFFICIENT_EVIDENCE_FOR_WARNING_CLEARANCE",
            warning_as_of=warning.last_warning_at,
            warning_evidence_cutoff_sha256=warning.last_warning_sha256,
            reasons=("TWO_POST_WARNING_WEEKLY_LOOKS_REQUIRED",),
        )
    a, b = looks[-2:]
    if b.scheduled_at - a.scheduled_at != timedelta(days=7):
        reason.append("NONCONSECUTIVE_PREDECLARED_LOOKS")
    if b.evidence_sha256 == a.evidence_sha256:
        reason.append("SAME_ECONOMIC_PROOF_REPLAYED")
    if not set(b.new_opportunity_ids) - set(a.new_opportunity_ids):
        reason.append("NO_NEW_SECOND_LOOK_OPPORTUNITY")
    original = {x.opportunity_id: x for x in report.opportunities}
    union_ids = set(a.new_opportunity_ids) | set(b.new_opportunity_ids)
    union_ids = {
        i
        for i in union_ids
        if i in original and original[i].first_known_at > warning.last_warning_at
    }
    all_clusters = set(a.new_cluster_sha256) | set(b.new_cluster_sha256)
    unique_count = min(len(union_ids), len(all_clusters))
    days = len({original[i].first_known_at.date() for i in union_ids})
    estimated_effective = b.effective_opportunities_since_warning
    if (
        a.effective_opportunities_since_warning is None
        or estimated_effective is None
        or estimated_effective > unique_count
        or a.effective_opportunities_since_warning > len(a.new_cluster_sha256)
        or estimated_effective < a.effective_opportunities_since_warning
    ):
        reason.append("INDEPENDENT_EFFECTIVE_N_UNVERIFIED")
    if estimated_effective is None or estimated_effective < 8 or unique_count < 8:
        reason.append("EIGHT_NEW_EFFECTIVE_OPPORTUNITIES_REQUIRED")
    if days < 7:
        reason.append("SEVEN_NEW_OBSERVED_DAYS_REQUIRED")
    if any(
        look.comparable_coverage_since_warning is None
        or look.comparable_coverage_since_warning < D("0.90")
        for look in (a, b)
    ):
        reason.append("NINETY_PERCENT_MATCHED_COVERAGE_REQUIRED")
    if any(
        look.matched_adverse_r is None or look.matched_adverse_r >= D("0.25") for look in (a, b)
    ):
        reason.append("MATCHED_RECOVERY_EFFECT_NOT_STRICTLY_BELOW_025R")
    if any(
        not look.critical_finance_complete or not look.original_proof_independently_checked
        for look in (a, b)
    ):
        reason.append("ORIGINAL_FINANCE_NOT_INDEPENDENTLY_VERIFIED")
    if (
        report.source_observability != "VERIFIED_CONTINUOUS"
        or not report.follower_economics.net_comparable
    ):
        reason.append("SOURCE_OR_FINANCE_STALE")
    if report.portfolio_contribution.status != "VERIFIED_PROSPECTIVE":
        reason.append("MATCHED_CONTROL_UNVERIFIED")
    if any(x.evidence_class not in {"PROSPECTIVE_SHADOW", "AUTHENTIC_BROKER"} for x in (a, b)):
        reason.append("PROSPECTIVE_CLASS_NOT_AUTHENTIC")
    return RecoveryStatus(
        status=(
            "INSUFFICIENT_EVIDENCE_FOR_WARNING_CLEARANCE" if reason else "PROVISIONAL_RECOVERY"
        ),
        warning_as_of=warning.last_warning_at,
        warning_evidence_cutoff_sha256=warning.last_warning_sha256,
        eligible_look_ids=(a.look_id, b.look_id),
        new_effective_opportunities=(
            min(estimated_effective, D(unique_count)) if estimated_effective is not None else None
        ),
        new_distinct_days=days,
        matched_coverage=min((x.comparable_coverage_since_warning or D(0) for x in (a, b))),
        reasons=tuple(sorted(set(reason))),
    )


def with_recovery(report: StrategyAssessment) -> StrategyAssessment:
    result = recovery(report)
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "recovery": result,
            }
        )
    )
