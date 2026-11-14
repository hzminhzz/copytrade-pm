"""Track B v2: immutable strategy-scoped, nonactivating research assessment.

Source evidence, PM03 finance, SQLite selection and Track C remain independent
authorities. This module only validates, seals and reads an owner-private report.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .pm_private_io import atomic_private_output
from .production_manifest import canonical, digest

SCHEMA = "strategy_health_assessment_v1"
POLICY = "track_b_strategy_health_v2_policy_v1"
SHA = r"^[a-f0-9]{64}$"
IDENT = r"^[A-Za-z0-9_.:-]{1,128}$"
MAX_BYTES = 2_000_000
ZERO_SHA = "0" * 64


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, serialize_by_alias=True)


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("STRATEGY_HEALTH_UTC_REQUIRED")
    return value.astimezone(UTC)


class StrategyScope(Strict):
    tier: Literal["DISCOVERY", "SELECTED"]
    source_alias: str = Field(pattern=IDENT)
    source_account_sha256: str = Field(pattern=SHA)
    registry_asof_sha256: str = Field(pattern=SHA)
    selected_portfolio: str | None = Field(default=None, max_length=128)
    selection_seal_sha256: str | None = Field(default=None, pattern=SHA)
    dex_census_sha256: str | None = Field(default=None, pattern=SHA)
    selection_known_at: datetime | None = None
    sizing_policy: Literal["FIXED_K_NATIVE_QUANTITY"] | None = None
    k_version: str | None = Field(default=None, pattern=IDENT)
    k_policy_sha256: str | None = Field(default=None, pattern=SHA)
    frozen_k: Decimal | None = None

    @model_validator(mode="after")
    def valid_scope(self):
        if self.selection_known_at is not None:
            utc(self.selection_known_at)
        fields = (
            self.selected_portfolio,
            self.selection_seal_sha256,
            self.dex_census_sha256,
            self.selection_known_at,
            self.sizing_policy,
            self.k_version,
            self.k_policy_sha256,
            self.frozen_k,
        )
        if self.tier == "SELECTED":
            if any(value is None for value in fields):
                raise ValueError("SELECTED_SCOPE_PROOF_REQUIRED")
            if not self.frozen_k.is_finite() or self.frozen_k == 0:
                raise ValueError("INVALID_FROZEN_K")
        elif any(value is not None for value in fields):
            raise ValueError("DISCOVERY_CANNOT_CLAIM_SELECTION")
        return self

    @property
    def strategy_sha256(self) -> str:
        return digest(self.model_dump(mode="json"))


class Campaign(Strict):
    campaign_id: str = Field(pattern=IDENT)
    trial_family_sha256: str = Field(pattern=SHA)
    frozen_at: datetime
    trial_count: int = Field(ge=1, le=100000)
    rejected_trials: int = Field(ge=0, le=100000)
    held_out_from: datetime | None = None
    weekly_look_ids: tuple[str, ...] = Field(default=(), max_length=104)
    weekly_look_schedule: tuple[datetime, ...] = Field(default=(), max_length=104)

    @model_validator(mode="after")
    def valid_campaign(self):
        utc(self.frozen_at)
        if self.rejected_trials > self.trial_count:
            raise ValueError("CAMPAIGN_TRIAL_COUNT_INVALID")
        if self.held_out_from is not None:
            utc(self.held_out_from)
            if self.held_out_from < self.frozen_at:
                raise ValueError("CAMPAIGN_HOLDOUT_PRECEDES_FREEZE")
        if len(self.weekly_look_ids) != len(set(self.weekly_look_ids)):
            raise ValueError("CAMPAIGN_LOOK_REUSED")
        if any(re.fullmatch(IDENT, x) is None for x in self.weekly_look_ids):
            raise ValueError("CAMPAIGN_LOOK_INVALID")
        if self.weekly_look_schedule:
            if len(self.weekly_look_schedule) != len(self.weekly_look_ids):
                raise ValueError("CAMPAIGN_LOOK_SCHEDULE_INCOMPLETE")
            for at in self.weekly_look_schedule:
                utc(at)
                if at < self.frozen_at:
                    raise ValueError("CAMPAIGN_LOOK_PREDATES_FREEZE")
            if any(
                b - a < timedelta(days=7)
                for a, b in zip(self.weekly_look_schedule, self.weekly_look_schedule[1:])
            ):
                raise ValueError("CAMPAIGN_REPEATED_DAILY_INFERENCE")
        return self


class Opportunity(Strict):
    opportunity_id: str = Field(pattern=SHA)
    source_event_sha256: str = Field(pattern=SHA)
    source_receipt_sha256: str = Field(pattern=SHA)
    source_event_at: datetime
    first_known_at: datetime
    due_at: datetime
    stream_cursor: int = Field(ge=1)
    source_epoch: str = Field(min_length=1, max_length=80)
    frozen_k_version: str = Field(pattern=IDENT)
    frozen_k: Decimal
    state: Literal[
        "OBSERVED",
        "PENDING",
        "ADMITTED",
        "REJECTED",
        "EXPIRED",
        "CANCELED",
        "OPEN",
        "PARTIAL",
        "UNRESOLVED",
        "REALIZED",
    ] = "OBSERVED"
    attempt_id: str | None = Field(default=None, max_length=128)
    attempt_receipt_sha256: str | None = Field(default=None, pattern=SHA)
    reason: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def causal(self):
        if not self.source_event_at <= self.first_known_at <= self.due_at:
            raise ValueError("OPPORTUNITY_CLOCK_ORDER")
        for field in ("source_event_at", "first_known_at", "due_at"):
            utc(getattr(self, field))
        if self.due_at != self.first_known_at + timedelta(seconds=300):
            raise ValueError("T300_MUST_USE_ORIGINAL_T0")
        if not self.frozen_k.is_finite() or self.frozen_k == 0:
            raise ValueError("OPPORTUNITY_FROZEN_K_INVALID")
        return self


class MissingInterval(Strict):
    started_at: datetime
    recovered_at: datetime | None = None
    reason: Literal["GAP", "BASELINE", "INCOMPLETE_SCOPE", "UNSAMPLED"]
    missed_opportunities: Literal["UNKNOWN"] = "UNKNOWN"
    original_source_receipt_sha256: str | None = Field(default=None, pattern=SHA)
    original_source_cursor: int | None = Field(default=None, ge=1)
    source_epoch: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def ordered(self):
        utc(self.started_at)
        if self.recovered_at is not None:
            utc(self.recovered_at)
            if self.recovered_at < self.started_at:
                raise ValueError("INVALID_MISSING_INTERVAL")
        return self


class FollowerEconomics(Strict):
    evidence_class: Literal[
        "UNKNOWN", "RESEARCH_SYNTHETIC", "PROSPECTIVE_SHADOW", "AUTHENTIC_BROKER"
    ] = "UNKNOWN"
    net_comparable: bool = False
    evidence_sha256: str | None = Field(default=None, pattern=SHA)
    original_pm03_head_sha256: str | None = Field(default=None, pattern=SHA)
    market_sha256: str | None = Field(default=None, pattern=SHA)
    as_of: datetime | None = None
    marked_equity_usd: Decimal | None = None
    realized_pnl_usd: Decimal | None = None
    unrealized_pnl_usd: Decimal | None = None
    costs_usd: Decimal | None = None
    funding_usd: Decimal | None = None
    open_risk_usd: Decimal | None = None
    matched_net_r: Decimal | None = None
    pod_marked_net_usd: Decimal | None = None
    pod_open_gross_usd: Decimal | None = None
    pod_budget_usd: Decimal | None = None
    pod_marked_net_r: Decimal | None = None
    account_risk_state: Literal["GREEN", "YELLOW", "ORANGE", "RED", "HALT"] | None = None
    original_halt_reason: str | None = Field(default=None, max_length=128)
    reasons: tuple[str, ...] = Field(default=("MISSING_AUTHENTIC_FOLLOWER_FINANCE",), max_length=32)

    @model_validator(mode="after")
    def valid_finance(self):
        if self.as_of is not None:
            utc(self.as_of)
        for k in (
            "marked_equity_usd",
            "realized_pnl_usd",
            "unrealized_pnl_usd",
            "costs_usd",
            "funding_usd",
            "open_risk_usd",
            "matched_net_r",
            "pod_marked_net_usd",
            "pod_open_gross_usd",
            "pod_budget_usd",
            "pod_marked_net_r",
        ):
            amount = getattr(self, k)
            if amount is not None and not amount.is_finite():
                raise ValueError("NONFINITE_FOLLOWER_FINANCE")
        if self.pod_marked_net_r is not None and (
            self.pod_budget_usd is None
            or self.pod_budget_usd <= 0
            or self.pod_marked_net_usd is None
            or abs(self.pod_marked_net_r * self.pod_budget_usd - self.pod_marked_net_usd)
            > Decimal("0.00000000001")
        ):
            raise ValueError("POD_R_MUST_MATCH_PM03_DOLLARS")
        if self.net_comparable and (
            self.evidence_class == "UNKNOWN"
            or any(
                x is None
                for x in (
                    self.evidence_sha256,
                    self.market_sha256,
                    self.original_pm03_head_sha256,
                    self.as_of,
                    self.costs_usd,
                    self.funding_usd,
                )
            )
        ):
            raise ValueError("UNPROVEN_NET_COMPARABILITY")
        return self


class MatchedContribution(Strict):
    status: Literal["UNKNOWN", "SYNTHETIC_COMPARISON", "VERIFIED_PROSPECTIVE"] = "UNKNOWN"
    comparison_sha256: str | None = Field(default=None, pattern=SHA)
    candidate_portfolio: str | None = Field(default=None, max_length=128)
    common_account_sha256: str | None = Field(default=None, pattern=SHA)
    marginal_pnl_usd: Decimal | None = None
    rulebook_sha256: str | None = Field(default=None, pattern=SHA)
    risk_policy_sha256: str | None = Field(default=None, pattern=SHA)
    market_manifest_sha256: str | None = Field(default=None, pattern=SHA)
    input_sha256: str | None = Field(default=None, pattern=SHA)
    with_pm03_head_sha256: str | None = Field(default=None, pattern=SHA)
    without_pm03_head_sha256: str | None = Field(default=None, pattern=SHA)
    reasons: tuple[str, ...] = ("NO_MATCHED_SHARED_ACCOUNT_COMPARISON",)

    @model_validator(mode="after")
    def valid_contribution(self):
        if self.marginal_pnl_usd is not None and not self.marginal_pnl_usd.is_finite():
            raise ValueError("NONFINITE_MARGINAL_PNL")
        if self.status == "UNKNOWN" and self.marginal_pnl_usd is not None:
            raise ValueError("UNKNOWN_CANNOT_SUPPLY_MARGINAL_PNL")
        if self.status != "UNKNOWN" and any(
            x is None
            for x in (
                self.comparison_sha256,
                self.common_account_sha256,
                self.marginal_pnl_usd,
                self.rulebook_sha256,
                self.risk_policy_sha256,
                self.market_manifest_sha256,
                self.input_sha256,
                self.with_pm03_head_sha256,
                self.without_pm03_head_sha256,
            )
        ):
            raise ValueError("MARGINAL_COMPARISON_PROOF_REQUIRED")
        return self


class WindowStats(Strict):
    window_days: Literal[7, 30, 90]
    as_of: datetime
    observed_opportunities: int = Field(ge=0)
    observed_days: int = Field(ge=0)
    comparable_opportunities: int = Field(ge=0)
    comparable_coverage: Decimal | None = Field(default=None, ge=0, le=1)
    independent_clusters: int = Field(ge=0)
    effective_opportunities: Decimal | None = Field(default=None, ge=0)
    estimated_lag1: Decimal | None = Field(default=None, ge=-1, le=1)
    matched_adverse_r: Decimal | None = None
    source_gap_unknown: bool
    missing_critical_prices: int = Field(ge=0)
    missing_critical_finance: int = Field(ge=0)
    open_opportunities: int = Field(ge=0)
    rejected_opportunities: int = Field(ge=0)
    censored_opportunities: int = Field(ge=0)
    method: Literal["clustered_lag1_design_effect_v1"] = "clustered_lag1_design_effect_v1"
    scientific_calibration: Literal[False] = False

    @model_validator(mode="after")
    def valid_window(self):
        utc(self.as_of)
        if (
            self.comparable_opportunities > self.observed_opportunities
            or self.independent_clusters > self.observed_opportunities
            or self.observed_days > self.window_days
        ):
            raise ValueError("WINDOW_CENSUS_IMPOSSIBLE")
        if (
            self.effective_opportunities is not None
            and self.effective_opportunities > self.independent_clusters
        ):
            raise ValueError("WINDOW_INDEPENDENCE_INFLATED")
        if self.source_gap_unknown and self.comparable_coverage is not None:
            raise ValueError("GAP_COVERAGE_CANNOT_BE_KNOWN")
        if self.matched_adverse_r is not None and not self.matched_adverse_r.is_finite():
            raise ValueError("NONFINITE_MATCHED_ADVERSE")
        return self


class Advisory(Strict):
    status: Literal["INSUFFICIENT_EVIDENCE", "NONE", "EARLY_WARNING", "PERSISTENT_WARNING"] = (
        "INSUFFICIENT_EVIDENCE"
    )
    calibration: Literal["UNCALIBRATED_ADVISORY"] = "UNCALIBRATED_ADVISORY"
    assessed_at: datetime | None = None
    performed_weekly_look_id: str | None = Field(default=None, pattern=IDENT)
    last_warning_at: datetime | None = None
    last_warning_sha256: str | None = Field(default=None, pattern=SHA)
    current_assessability: Literal[
        "UNKNOWN",
        "STALE",
        "INSUFFICIENT_EVIDENCE",
        "PROVISIONAL_LOOK_AVAILABLE",
        "INSUFFICIENT_EVIDENCE_FOR_WARNING_CLEARANCE",
    ] = "UNKNOWN"
    reasons: tuple[str, ...] = Field(default=(), max_length=32)
    false_warning_fraction_target: Decimal = Decimal("0.10")
    observed_false_warning_fraction: None = None
    trading_authorized: Literal[False] = False

    @model_validator(mode="after")
    def valid_advisory(self):
        if self.assessed_at is not None:
            utc(self.assessed_at)
        if self.last_warning_at is not None:
            utc(self.last_warning_at)
            if self.last_warning_sha256 is None:
                raise ValueError("WARNING_ORIGINAL_SHA_REQUIRED")
        if self.status != "INSUFFICIENT_EVIDENCE" and (
            self.performed_weekly_look_id is None or self.assessed_at is None
        ):
            raise ValueError("DAILY_REFRESH_NOT_WEEKLY_INFERENCE")
        return self


class RecoveryStatus(Strict):
    status: Literal[
        "NO_HISTORICAL_WARNING",
        "WARNING_RETAINED",
        "INSUFFICIENT_EVIDENCE_FOR_WARNING_CLEARANCE",
        "PROVISIONAL_RECOVERY",
    ] = "NO_HISTORICAL_WARNING"
    warning_as_of: datetime | None = None
    warning_evidence_cutoff_sha256: str | None = Field(default=None, pattern=SHA)
    eligible_look_ids: tuple[str, ...] = Field(default=(), max_length=2)
    new_effective_opportunities: Decimal | None = None
    new_distinct_days: int | None = Field(default=None, ge=0)
    matched_coverage: Decimal | None = Field(default=None, ge=0, le=1)
    reasons: tuple[str, ...] = Field(default=(), max_length=32)
    calibrated: Literal[False] = False

    @model_validator(mode="after")
    def recovery_valid(self):
        if self.warning_as_of is not None:
            utc(self.warning_as_of)
        if self.status == "PROVISIONAL_RECOVERY" and len(self.eligible_look_ids) != 2:
            raise ValueError("TWO_WEEKLY_LOOKS_REQUIRED")
        return self


class WeeklyLook(Strict):
    look_id: str = Field(pattern=IDENT)
    scheduled_at: datetime
    performed_at: datetime
    evidence_sha256: str = Field(pattern=SHA)
    source_original_sha256: str | None = Field(default=None, pattern=SHA)
    market_original_sha256: str | None = Field(default=None, pattern=SHA)
    pm03_original_head_sha256: str | None = Field(default=None, pattern=SHA)
    control_original_sha256: str | None = Field(default=None, pattern=SHA)
    evidence_class: Literal[
        "UNKNOWN", "RESEARCH_SYNTHETIC", "PROSPECTIVE_SHADOW", "AUTHENTIC_BROKER"
    ] = "UNKNOWN"
    new_opportunity_ids: tuple[str, ...] = Field(default=(), max_length=10000)
    new_cluster_sha256: tuple[str, ...] = Field(default=(), max_length=10000)
    effective_opportunities_since_warning: Decimal | None = Field(default=None, ge=0)
    observed_days_since_warning: int = Field(default=0, ge=0)
    comparable_coverage_since_warning: Decimal | None = Field(default=None, ge=0, le=1)
    matched_adverse_r: Decimal | None = None
    critical_finance_complete: bool = False
    original_proof_independently_checked: bool = False
    analytical_status: Literal["INSUFFICIENT", "PROVISIONAL"] = "INSUFFICIENT"

    @model_validator(mode="after")
    def look_valid(self):
        utc(self.scheduled_at)
        utc(self.performed_at)
        if self.performed_at < self.scheduled_at:
            raise ValueError("LOOK_BEFORE_SCHEDULE")
        if len(self.new_opportunity_ids) != len(set(self.new_opportunity_ids)):
            raise ValueError("LOOK_OPPORTUNITIES_DUPLICATE")
        if len(self.new_cluster_sha256) != len(set(self.new_cluster_sha256)):
            raise ValueError("LOOK_CLUSTERS_DUPLICATE")
        if any(
            re.fullmatch(SHA, value) is None
            for value in self.new_opportunity_ids + self.new_cluster_sha256
        ):
            raise ValueError("LOOK_PROOF_SHA_INVALID")
        if len(self.new_cluster_sha256) > len(self.new_opportunity_ids):
            raise ValueError("LOOK_CLUSTER_OPPORTUNITY_MISMATCH")
        if self.matched_adverse_r is not None and not self.matched_adverse_r.is_finite():
            raise ValueError("LOOK_FINANCE_NONFINITE")
        return self


class OperationalIncident(Strict):
    incident_sha256: str = Field(pattern=SHA)
    first_known_at: datetime
    selected_scope_sha256: str = Field(pattern=SHA)
    cause: Literal["SOURCE_GAP", "SOURCE_STALE", "QUOTE_STALE", "PROOF_DIVERGENCE"]
    priority: Literal["OBSERVATION", "ELEVATED", "CRITICAL_RISK_EXPOSED"]
    failed_expected_cycles: int = Field(ge=0, le=10000)
    expected_cycle_seconds: int | None = Field(default=None, ge=1, le=86400)
    risk_at_finding: Literal["UNKNOWN", "FLAT", "PENDING_T300", "OPEN", "UNRESOLVED_EXIT"]
    alert_delivery: Literal[
        "PENDING_UNVERIFIED_CADENCE",
        "PENDING_SECOND_CYCLE",
        "PENDING_OWNER_ROUTE",
        "ELIGIBLE_NOT_SENT",
    ]
    owner_acknowledgement: Literal["NOT_ACKNOWLEDGED", "ACKNOWLEDGED"] = "NOT_ACKNOWLEDGED"
    acknowledged_at: datetime | None = None
    acknowledgement_evidence_sha256: str | None = Field(default=None, pattern=SHA)
    immediate_risk_fence_owned_by: Literal["ORIGINAL_PM04_GUARDIAN"] = "ORIGINAL_PM04_GUARDIAN"
    trading_authorized: Literal[False] = False

    @model_validator(mode="after")
    def incident_valid(self):
        utc(self.first_known_at)
        if self.acknowledged_at is not None:
            utc(self.acknowledged_at)
            if self.acknowledged_at < self.first_known_at:
                raise ValueError("INCIDENT_ACK_PRECEDES_FAULT")
            if self.acknowledgement_evidence_sha256 is None:
                raise ValueError("INCIDENT_ACK_RECEIPT_REQUIRED")
        if self.owner_acknowledgement == "ACKNOWLEDGED" and self.acknowledged_at is None:
            raise ValueError("ACK_OWNER_PROOF_MISSING")
        return self


class StrategyAssessment(Strict):
    schema_version: Literal["strategy_health_assessment_v1"] = Field(default=SCHEMA, alias="schema")
    policy_version: Literal["track_b_strategy_health_v2_policy_v1"] = POLICY
    report_sha256: str = Field(default=ZERO_SHA, pattern=SHA)
    created_at: datetime
    as_of: datetime
    strategy: StrategyScope
    campaign: Campaign
    source_observability: Literal[
        "UNKNOWN", "VERIFIED_CONTINUOUS", "GAP", "INCOMPLETE_SCOPE", "STALE"
    ] = "UNKNOWN"
    opportunities: tuple[Opportunity, ...] = Field(default=(), max_length=10000)
    missing_intervals: tuple[MissingInterval, ...] = Field(default=(), max_length=10000)
    follower_economics: FollowerEconomics = Field(default_factory=FollowerEconomics)
    portfolio_contribution: MatchedContribution = Field(default_factory=MatchedContribution)
    windows: tuple[WindowStats, ...] = Field(default=(), max_length=3)
    advisory: Advisory = Field(default_factory=Advisory)
    weekly_looks: tuple[WeeklyLook, ...] = Field(default=(), max_length=104)
    recovery: RecoveryStatus = Field(default_factory=RecoveryStatus)
    operational_incidents: tuple[OperationalIncident, ...] = Field(default=(), max_length=512)
    warnings: tuple[str, ...] = Field(default=(), max_length=32)
    scientifically_qualified: Literal[False] = False
    source_finance_authenticated: Literal[False] = False
    read_only: Literal[True] = True
    trading_authorized: Literal[False] = False
    active_k_changed: Literal[False] = False
    registry_mutated: Literal[False] = False
    journal_mutated: Literal[False] = False

    @model_validator(mode="after")
    def valid_assessment(self):
        utc(self.created_at)
        utc(self.as_of)
        if self.created_at < self.as_of or self.created_at > datetime.now(UTC) + timedelta(
            seconds=1
        ):
            raise ValueError("FUTURE_OR_BACKDATED_ASSESSMENT")
        if self.campaign.frozen_at > self.as_of:
            raise ValueError("FUTURE_CAMPAIGN_FREEZE")
        if (
            self.strategy.selection_known_at is not None
            and self.strategy.selection_known_at > self.as_of
        ):
            raise ValueError("FUTURE_SELECTION_PROOF")
        if self.strategy.tier == "DISCOVERY" and (
            self.operational_incidents
            or self.source_observability != "UNKNOWN"
            or self.opportunities
            or self.follower_economics.evidence_class != "UNKNOWN"
            or self.portfolio_contribution.status != "UNKNOWN"
        ):
            raise ValueError("DISCOVERY_CANNOT_CLAIM_PROSPECTIVE_ECONOMICS")
        if self.windows and {w.window_days for w in self.windows} != {7, 30, 90}:
            raise ValueError("WINDOWS_NOT_FULL_SEVEN_THIRTY_NINETY")
        if self.windows and any(w.as_of != self.as_of for w in self.windows):
            raise ValueError("WINDOW_ASOF_MISMATCH")
        ids = [look.look_id for look in self.weekly_looks]
        if len(ids) != len(set(ids)) or any(x not in self.campaign.weekly_look_ids for x in ids):
            raise ValueError("LOOK_UNDECLARED_OR_REPEATED")
        if any(look.performed_at > self.as_of for look in self.weekly_looks):
            raise ValueError("FUTURE_INFERENTIAL_LOOK")
        if any(
            a.performed_at >= b.performed_at
            for a, b in zip(self.weekly_looks, self.weekly_looks[1:])
        ):
            raise ValueError("INFERENTIAL_LOOK_ORDER")
        seen: set[str] = set()
        original_proof_keys: set[tuple] = set()
        for item in self.opportunities:
            if (
                item.opportunity_id in seen
                or item.first_known_at > self.as_of
                or item.frozen_k_version != self.strategy.k_version
                or item.frozen_k != self.strategy.frozen_k
            ):
                raise ValueError("OPPORTUNITY_DUPLICATED_OR_VERSION_DRIFT")
            seen.add(item.opportunity_id)
            key = (item.source_event_sha256, item.stream_cursor, item.first_known_at)
            if key in original_proof_keys:
                raise ValueError("DUPLICATE_ORIGINAL_OPPORTUNITY")
            original_proof_keys.add(key)
        if self.follower_economics.as_of is not None and self.follower_economics.as_of > self.as_of:
            raise ValueError("FUTURE_FINANCIAL_EVIDENCE")
        for gap in self.missing_intervals:
            if gap.started_at > self.as_of or (
                gap.recovered_at is not None and gap.recovered_at > self.as_of
            ):
                raise ValueError("FUTURE_MISSING_INTERVAL")
        return self


def _body(report: StrategyAssessment) -> dict:
    return report.model_dump(mode="json", exclude={"report_sha256"})


def seal(report: StrategyAssessment) -> StrategyAssessment:
    if report.report_sha256 != ZERO_SHA:
        raise ValueError("ALREADY_SEALED")
    return report.model_copy(update={"report_sha256": digest(_body(report))})


def canonical_report(report: StrategyAssessment) -> bytes:
    if report.report_sha256 != digest(_body(report)):
        raise ValueError("REPORT_SHA_MISMATCH")
    data = canonical(report.model_dump(mode="json"))
    if len(data) > MAX_BYTES:
        raise ValueError("REPORT_SIZE_LIMIT")
    return data


def publish(report: StrategyAssessment, path: Path) -> str:
    """Atomic no-clobber 0600 publication in an operator-owned 0700 directory."""
    raw = canonical_report(report)
    atomic_private_output(path, raw)
    if path.stat().st_mode & 0o777 != 0o600:
        raise ValueError("REPORT_PERMISSION_DRIFT")
    return sha256(raw).hexdigest()


def read(path: Path) -> StrategyAssessment:
    if path.is_symlink():
        raise ValueError("REPORT_SYMLINK_FORBIDDEN")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o777 != 0o600:
            raise ValueError("REPORT_PRIVATE_MODE_REQUIRED")
        if not 0 < meta.st_size <= MAX_BYTES:
            raise ValueError("REPORT_SIZE_LIMIT")
        raw = os.read(fd, MAX_BYTES + 1)
        if len(raw) != meta.st_size:
            raise ValueError("TRUNCATED_STRATEGY_REPORT")
    finally:
        os.close(fd)
    report = StrategyAssessment.model_validate_json(raw, strict=True)
    if canonical_report(report) != raw:
        raise ValueError("NONCANONICAL_STRATEGY_REPORT")
    return report
