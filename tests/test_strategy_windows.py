"""Declared clustered window and provisional weekly/recovery threshold tests."""

from datetime import timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.strategy_health import (
    Campaign,
    FollowerEconomics,
    Opportunity,
    StrategyAssessment,
    WeeklyLook,
    ZERO_SHA,
    seal,
)
from copytrade_pm.strategy_windows import OpportunityEvidence, compute_windows, with_windows
from copytrade_pm.strategy_advisory import gate, recovery, assess_weekly
from test_strategy_health_v2 import NOW, H, scope


def h(i):
    return f"{i:064x}"


def suite(
    n, *, day_span=7, complete=None, as_of=NOW, amount=D("0.05"), class_name="RESEARCH_SYNTHETIC"
):
    complete = n if complete is None else complete
    opportunities, points = [], []
    for i in range(n):
        offset = (i * day_span) // n
        t = as_of - timedelta(days=day_span - 1 - offset, hours=0, minutes=1)
        op = Opportunity(
            opportunity_id=h(1000 + i),
            source_event_sha256=h(2000 + i),
            source_receipt_sha256=h(3000 + i),
            source_event_at=t - timedelta(seconds=1),
            first_known_at=t,
            due_at=t + timedelta(seconds=300),
            stream_cursor=1 + i,
            source_epoch="origin",
            frozen_k_version="k1",
            frozen_k=D("0.125"),
            state="OPEN" if i < complete else "REJECTED",
        )
        opportunities.append(op)
        if i < complete:
            points.append(
                OpportunityEvidence(
                    opportunity_id=op.opportunity_id,
                    first_known_at=t,
                    outcome_known_at=t + timedelta(seconds=301),
                    causal_cluster_sha256=h(4000 + i),
                    original_source_receipt_sha256=op.source_receipt_sha256,
                    original_market_sha256=H,
                    original_pm03_head_sha256=H,
                    matched_control_sha256=H,
                    matched_adverse_r=amount + D("0.001") * (i % 2),
                    source_complete=True,
                    quote_complete=True,
                    costs_complete=True,
                    funding_complete=True,
                    original_finance_verified=True,
                    unresolved_effect=False,
                    evidence_class=class_name,
                )
            )
    campaign = Campaign(
        campaign_id="c",
        trial_family_sha256=H,
        frozen_at=as_of - timedelta(days=100),
        trial_count=3,
        rejected_trials=1,
    )
    report = seal(
        StrategyAssessment(
            as_of=as_of,
            created_at=as_of,
            strategy=scope(),
            campaign=campaign,
            source_observability="VERIFIED_CONTINUOUS",
            opportunities=tuple(opportunities),
            follower_economics=FollowerEconomics(evidence_class=class_name),
        )
    )
    return report, tuple(points)


def test_early_8_7_80_boundaries_and_effect():
    report, points = suite(10, complete=8, day_span=7)
    windows = compute_windows(report, evidence=points)
    w = windows[0]
    assert w.window_days == 7
    assert w.observed_opportunities == 10
    assert w.independent_clusters == 8
    assert w.effective_opportunities == D(8)
    assert w.observed_days == 7
    assert w.comparable_coverage == D("0.8")
    assert not w.missing_critical_finance
    assert gate(w, persistent=False)[0] == "EARLY_WARNING"
    assert gate(windows[1], persistent=True)[0] == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValueError, match="WINDOW_NOT_PREDECLARED"):
        gate(w, persistent=True)


def test_persistent_20_14_90_boundary_exact():
    report, points = suite(22, complete=20, day_span=14)
    windows = compute_windows(report, evidence=points)
    persistent = windows[1]
    assert persistent.window_days == 30
    assert persistent.observed_days == 14
    assert persistent.comparable_coverage == D(20) / D(22)
    assert persistent.effective_opportunities == D(20)
    assert gate(persistent, persistent=True)[0] == "PERSISTENT_WARNING"
    less = persistent.model_copy(update={"effective_opportunities": D("19.99")})
    assert gate(less, persistent=True)[0] == "INSUFFICIENT_EVIDENCE"
    less = persistent.model_copy(update={"observed_days": 13})
    assert gate(less, persistent=True)[0] == "INSUFFICIENT_EVIDENCE"
    less = persistent.model_copy(update={"comparable_coverage": D("0.8999")})
    assert gate(less, persistent=True)[0] == "INSUFFICIENT_EVIDENCE"
    less = persistent.model_copy(update={"matched_adverse_r": D("0.4999")})
    assert gate(less, persistent=True)[0] == "NONE"
    exact = persistent.model_copy(update={"matched_adverse_r": D("0.50")})
    assert gate(exact, persistent=True)[0] == "PERSISTENT_WARNING"


def test_gap_funding_quote_veto_and_censored_denominator():
    report, points = suite(10, complete=8, day_span=7)
    w = compute_windows(report, evidence=points)[0]
    assert (
        gate(
            w.model_copy(
                update={
                    "missing_critical_finance": 1,
                    "matched_adverse_r": D("1"),
                }
            ),
            persistent=False,
        )[0]
        == "INSUFFICIENT_EVIDENCE"
    )
    assert (
        gate(
            w.model_copy(
                update={
                    "missing_critical_prices": 1,
                    "matched_adverse_r": D("1"),
                }
            ),
            persistent=False,
        )[0]
        == "INSUFFICIENT_EVIDENCE"
    )
    altered = report.model_copy(
        update={
            "missing_intervals": (
                __import__(
                    "copytrade_pm.strategy_health", fromlist=["MissingInterval"]
                ).MissingInterval(started_at=NOW - timedelta(days=1), reason="GAP"),
            ),
        }
    )
    gapw = compute_windows(altered, evidence=points)[0]
    assert gapw.comparable_coverage is None
    assert gapw.matched_adverse_r is None
    assert gate(gapw, persistent=False)[0] == "INSUFFICIENT_EVIDENCE"


def test_causal_cluster_duplicates_cannot_multiply_n_or_adverse():
    report, points = suite(10, complete=8, day_span=7)
    second = points[1].model_copy(update={"causal_cluster_sha256": points[0].causal_cluster_sha256})
    windows = compute_windows(report, evidence=(points[0], second, *points[2:]))
    assert windows[0].independent_clusters == 6
    assert windows[0].effective_opportunities is not None
    assert windows[0].effective_opportunities <= 6
    assert windows[0].matched_adverse_r is None
    assert gate(windows[0], persistent=False)[0] == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValueError, match="SOURCE_PROVENANCE"):
        compute_windows(
            report,
            evidence=(
                points[0].model_copy(update={"original_source_receipt_sha256": H}),
                *points[1:],
            ),
        )
    with pytest.raises(ValueError, match="WINDOW_OPPORTUNITY_ID"):
        compute_windows(report, evidence=(points[0], points[0]))


def test_long_hold_one_opportunity_and_refresh_not_weekly_look():
    report, points = suite(1, day_span=90)
    assert compute_windows(report, evidence=points)[0].observed_opportunities == 0
    assert compute_windows(report, evidence=points)[2].observed_opportunities == 1
    assert compute_windows(report, evidence=points)[2].effective_opportunities is None
    report = with_windows(report, evidence=points)
    assert not report.weekly_looks
    assert report.advisory.status == "INSUFFICIENT_EVIDENCE"
    assert not report.scientifically_qualified


def test_weekly_schedule_refuses_daily_test_replay():
    report, points = suite(10, complete=8)
    report = with_windows(report, evidence=points)
    schedule = (NOW - timedelta(days=7), NOW)
    campaign = Campaign(
        campaign_id="c",
        trial_family_sha256=H,
        frozen_at=NOW - timedelta(days=100),
        trial_count=3,
        rejected_trials=1,
        weekly_look_ids=("w1", "w2"),
        weekly_look_schedule=schedule,
    )
    report = seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "campaign": campaign,
            }
        )
    )
    look = WeeklyLook(
        look_id="w2",
        scheduled_at=NOW,
        performed_at=NOW,
        evidence_sha256=H,
    )
    updated = assess_weekly(report, look)
    assert updated.advisory.status == "INSUFFICIENT_EVIDENCE"
    assert updated.advisory.observed_false_warning_fraction is None
    assert updated.advisory.false_warning_fraction_target == D("0.10")
    assert len(updated.weekly_looks) == 1
    with pytest.raises(ValueError, match="REPLAY_OR_REORDER"):
        assess_weekly(updated, look)
    with pytest.raises(ValueError, match="SCHEDULE_DRIFT"):
        assess_weekly(report, look.model_copy(update={"scheduled_at": NOW - timedelta(days=1)}))
    with pytest.raises(ValueError, match="REPEATED_DAILY_INFERENCE"):
        Campaign(
            campaign_id="c",
            trial_family_sha256=H,
            frozen_at=NOW - timedelta(days=100),
            trial_count=1,
            rejected_trials=0,
            weekly_look_ids=("x", "y"),
            weekly_look_schedule=(NOW - timedelta(days=1), NOW),
        )


def test_recovery_does_not_clear_without_new_independent_evidence():
    report, points = suite(10, complete=8, day_span=7)
    warning = report.advisory.model_copy(
        update={
            "last_warning_at": NOW - timedelta(days=14),
            "last_warning_sha256": H,
        }
    )
    report = report.model_copy(update={"advisory": warning})
    result = recovery(report)
    assert result.status == "INSUFFICIENT_EVIDENCE_FOR_WARNING_CLEARANCE"
    assert "TWO_POST_WARNING_WEEKLY_LOOKS_REQUIRED" in result.reasons
