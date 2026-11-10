"""Conservative 7/30/90 v2 research windows over original opportunity identities.

No marks, pods, retries or reconnects create independent opportunities.
A report hash or caller-supplied proof identifier never upgrades source/finance
authentication; inference requires separately verified original evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .strategy_health import (
    Strict,
    WindowStats,
    StrategyAssessment,
    ZERO_SHA,
    seal,
    utc,
)

SHA = r"^[0-9a-f]{64}$"
D = Decimal


class OpportunityEvidence(Strict):
    opportunity_id: str = Field(pattern=SHA)
    first_known_at: datetime
    outcome_known_at: datetime | None = None
    causal_cluster_sha256: str = Field(pattern=SHA)
    original_source_receipt_sha256: str = Field(pattern=SHA)
    original_market_sha256: str | None = Field(default=None, pattern=SHA)
    original_pm03_head_sha256: str | None = Field(default=None, pattern=SHA)
    matched_control_sha256: str | None = Field(default=None, pattern=SHA)
    matched_adverse_r: D | None = None
    source_complete: bool = False
    quote_complete: bool = False
    costs_complete: bool = False
    funding_complete: bool = False
    original_finance_verified: bool = False
    unresolved_effect: bool = True
    evidence_class: Literal[
        "RESEARCH_SYNTHETIC",
        "PROSPECTIVE_SHADOW",
        "AUTHENTIC_BROKER",
    ] = "RESEARCH_SYNTHETIC"
    marker: Literal["LAST_OUTCOME", "OPEN_MTM", "NO_FILL"] = "LAST_OUTCOME"

    @model_validator(mode="after")
    def causal(self):
        utc(self.first_known_at)
        if self.outcome_known_at is not None:
            utc(self.outcome_known_at)
            if self.outcome_known_at < self.first_known_at:
                raise ValueError("OUTCOME_BEFORE_SOURCE")
        if self.matched_adverse_r is not None and not self.matched_adverse_r.is_finite():
            raise ValueError("NONFINITE_ADVERSE_R")
        if self.marker == "OPEN_MTM" and self.outcome_known_at is None:
            # A sampled open mark requires an original mark receipt time.
            raise ValueError("OPEN_MARK_TIME_REQUIRED")
        return self


def _lag1_design_effect(clusters: list[tuple[datetime, str, D]]) -> tuple[D | None, D | None]:
    """Pearson lag-one (non-negative penalty only) on ordered independent roots."""
    n = len(clusters)
    if n < 4:
        return None, None
    data = [v for _, _, v in sorted(clusters)]
    x, y = data[:-1], data[1:]
    mx, my = sum(x, D(0)) / (n - 1), sum(y, D(0)) / (n - 1)
    cov = sum(((a - mx) * (b - my) for a, b in zip(x, y, strict=True)), D(0))
    vx = sum(((a - mx) ** 2 for a in x), D(0))
    vy = sum(((b - my) ** 2 for b in y), D(0))
    if vx <= 0 or vy <= 0:
        return None, None
    rho = max(D(-1), min(D(1), cov / (vx * vy).sqrt()))
    # Keep N_e bounded by unique causal roots regardless of correlation.
    effective = D(n) / (D(1) + D(2) * max(D(0), rho))
    return min(D(n), effective), rho


def compute_windows(
    report: StrategyAssessment,
    *,
    evidence: tuple[OpportunityEvidence, ...],
    source_observed_days: tuple[datetime, ...] = (),
) -> tuple[WindowStats, ...]:
    if report.strategy.tier != "SELECTED":
        raise ValueError("NO_PROSPECTIVE_WINDOWS_FOR_DISCOVERY")
    by_id = {op.opportunity_id: op for op in report.opportunities}
    joined = {}
    for point in evidence:
        if point.opportunity_id in joined or point.opportunity_id not in by_id:
            raise ValueError("WINDOW_OPPORTUNITY_ID_INVALID")
        original = by_id[point.opportunity_id]
        if (
            point.original_source_receipt_sha256 != original.source_receipt_sha256
            or point.first_known_at != original.first_known_at
        ):
            raise ValueError("WINDOW_SOURCE_PROVENANCE_OR_CLOCK_DRIFT")
        if point.outcome_known_at is not None and point.outcome_known_at > report.as_of:
            raise ValueError("WINDOW_FUTURE_FINANCE")
        if point.evidence_class != report.follower_economics.evidence_class:
            raise ValueError("WINDOW_FINANCE_CLASS_MISMATCH")
        joined[point.opportunity_id] = point
    days = set()
    for at in source_observed_days:
        utc(at)
        if at > report.as_of:
            raise ValueError("WINDOW_FUTURE_SOURCE_OBSERVATION")
        days.add(at.date())
    result = []
    for span in (7, 30, 90):
        since = report.as_of - timedelta(days=span)
        cohort = [op for op in report.opportunities if since < op.first_known_at <= report.as_of]
        observed = len(cohort)
        active_gaps = any(
            gap.started_at <= report.as_of and (gap.recovered_at or report.as_of) > since
            for gap in report.missing_intervals
        )
        comparable = []
        missing_price = missing_finance = 0
        censored = 0
        for op in cohort:
            point = joined.get(op.opportunity_id)
            if point is None:
                censored += 1
                if op.state in {"OPEN", "PARTIAL", "UNRESOLVED", "ADMITTED", "REALIZED"}:
                    missing_price += 1
                    missing_finance += 1
                continue
            price = point.quote_complete and point.original_market_sha256 is not None
            if not price and op.state in {"OPEN", "PARTIAL", "UNRESOLVED", "ADMITTED", "REALIZED"}:
                missing_price += 1
            financial = (
                point.costs_complete
                and point.funding_complete
                and point.original_finance_verified
                and point.original_pm03_head_sha256 is not None
                and point.matched_control_sha256 is not None
                and point.matched_adverse_r is not None
                and point.outcome_known_at is not None
                and point.source_complete
                and not point.unresolved_effect
            )
            if not financial and op.state in {
                "OPEN",
                "PARTIAL",
                "UNRESOLVED",
                "ADMITTED",
                "REALIZED",
            }:
                missing_finance += 1
            if price and financial:
                comparable.append(point)
            else:
                censored += 1
        # One economic effect per independent causal source cluster.
        clusters = {}
        duplicate_clusters = set()
        for point in comparable:
            key = point.causal_cluster_sha256
            if key in clusters:
                duplicate_clusters.add(key)
            else:
                clusters[key] = (
                    point.first_known_at,
                    point.opportunity_id,
                    point.matched_adverse_r,
                )
        # Duplicate pods, marks or overlapping variants cannot multiply N.
        cluster_values = [v for k, v in clusters.items() if k not in duplicate_clusters]
        effective, lag1 = _lag1_design_effect(cluster_values)
        unique_n = len(cluster_values)
        # Missing unknown source intervals invalidate the implied total
        # denominator; observed opportunities cannot fill unknown GAPs.
        coverage = D(len(comparable)) / D(observed) if observed and not active_gaps else None
        # Incomplete critical finance leaves descriptive but not inferential effect.
        matched = (
            sum((v[2] for v in cluster_values), D(0))
            if comparable
            and missing_finance == 0
            and missing_price == 0
            and not active_gaps
            and not duplicate_clusters
            else None
        )
        observed_days_count = (
            len({day for day in days if since.date() <= day <= report.as_of.date()})
            if source_observed_days
            else len({op.first_known_at.date() for op in cohort})
        )
        result.append(
            WindowStats(
                window_days=span,
                as_of=report.as_of,
                observed_opportunities=observed,
                observed_days=min(span, observed_days_count),
                comparable_opportunities=len(comparable),
                comparable_coverage=coverage,
                independent_clusters=unique_n,
                effective_opportunities=effective,
                estimated_lag1=lag1,
                matched_adverse_r=matched,
                source_gap_unknown=active_gaps,
                missing_critical_prices=missing_price,
                missing_critical_finance=missing_finance,
                open_opportunities=sum(
                    op.state in {"OPEN", "PARTIAL", "UNRESOLVED"} for op in cohort
                ),
                rejected_opportunities=sum(
                    op.state in {"REJECTED", "CANCELED", "EXPIRED"} for op in cohort
                ),
                censored_opportunities=censored,
            )
        )
    return tuple(result)


def with_windows(
    report: StrategyAssessment,
    *,
    evidence: tuple[OpportunityEvidence, ...],
    source_observed_days: tuple[datetime, ...] = (),
) -> StrategyAssessment:
    windows = compute_windows(report, evidence=evidence, source_observed_days=source_observed_days)
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "windows": windows,
            }
        )
    )
