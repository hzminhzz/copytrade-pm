"""Selected-source operational incident, acknowledgement and privacy tests."""

from datetime import timedelta

import pytest

from copytrade_pm.strategy_health import (
    MissingInterval,
    StrategyAssessment,
    ZERO_SHA,
    seal,
)
from copytrade_pm.strategy_incidents import (
    CycleObservation,
    acknowledge,
    attach_incident,
    classify,
)
from copytrade_pm.strategy_health_projection import project
from test_strategy_health_v2 import H, NOW, assessment


def _gap_report(*, selected=True):
    report = assessment(selected=selected)
    if not selected:
        return seal(report)
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "source_observability": "GAP",
                "missing_intervals": (
                    MissingInterval(
                        started_at=NOW - timedelta(seconds=2),
                        reason="GAP",
                        original_source_receipt_sha256=H,
                        original_source_cursor=5,
                        source_epoch="origin",
                    ),
                ),
            }
        )
    )


def test_discovery_missingness_never_operational_incident():
    report = _gap_report(selected=False)
    assert classify(report, cycle=None, original_finance=None, quote_stale=False) is None


def test_selected_gap_unknown_finance_prioritized_but_no_unverified_page(tmp_path):
    report = _gap_report()
    gap_at = report.missing_intervals[0].started_at
    incident = classify(report, cycle=None, original_finance=None, quote_stale=False)
    assert incident.cause == "SOURCE_GAP"
    assert incident.priority == "ELEVATED"
    assert incident.risk_at_finding == "UNKNOWN"
    assert incident.alert_delivery == "PENDING_UNVERIFIED_CADENCE"
    proof = CycleObservation(
        original_source_receipt_sha256=H,
        fault_first_known_at=gap_at,
        failed_expected_cycles=1,
        measured_cycle_seconds=10,
        owner_alias="ops",
        route_alias="console",
    )
    one = classify(report, cycle=proof, original_finance=None, quote_stale=True)
    assert one.alert_delivery == "PENDING_SECOND_CYCLE"
    two = classify(
        report,
        cycle=proof.model_copy(update={"failed_expected_cycles": 2}),
        original_finance=None,
        quote_stale=True,
    )
    assert two.priority == "ELEVATED"
    assert two.alert_delivery == "ELIGIBLE_NOT_SENT"
    assert two.incident_sha256 == one.incident_sha256 == incident.incident_sha256
    assert two.immediate_risk_fence_owned_by == "ORIGINAL_PM04_GUARDIAN"
    report2 = attach_incident(report, two)
    assert report2.operational_incidents[0] == two
    assert attach_incident(report2, two).operational_incidents == report2.operational_incidents
    with pytest.raises(ValueError, match="REPLAY_CONFLICT"):
        attach_incident(report2, one)
    assert b"ops" not in project(report2, published_at=NOW)
    assert b"source_account_sha256" not in project(report2, published_at=NOW)
    assert b"CRITICAL_RISK_EXPOSED" not in project(report2, published_at=NOW)
    with pytest.raises(ValueError, match="RECEIPT_MISMATCH"):
        classify(
            report,
            cycle=proof.model_copy(update={"original_source_receipt_sha256": "b" * 64}),
            original_finance=None,
            quote_stale=False,
        )


def test_genuine_pending_5m_and_open_risk_raise_severity_without_order():
    report = _gap_report()
    gap_at = report.missing_intervals[0].started_at
    original = {
        "schema": "strategy_pm03_original_verified_v1",
        "account": {
            "pm_quantities": {"S035": {}},
            "pm04": {
                "paper_execution": {
                    "history": {"intent": {"pod": "S035", "status": "PENDING_5M"}},
                    "unresolved_exposures": {},
                }
            },
        },
    }
    proof = CycleObservation(
        original_source_receipt_sha256=H,
        fault_first_known_at=gap_at,
        failed_expected_cycles=1,
        measured_cycle_seconds=15,
    )
    pending = classify(report, cycle=proof, original_finance=original, quote_stale=True)
    assert pending.priority == "CRITICAL_RISK_EXPOSED"
    assert pending.risk_at_finding == "PENDING_T300"
    assert pending.failed_expected_cycles == 1
    assert pending.alert_delivery == "PENDING_SECOND_CYCLE"
    original["account"]["pm_quantities"]["S035"] = {"HL:BTC": "-0.25"}
    opened = classify(report, cycle=proof, original_finance=original, quote_stale=True)
    assert opened.risk_at_finding == "OPEN"
    original["account"]["pm04"]["paper_execution"]["unresolved_exposures"]["S035"] = {
        "HL:BTC": "-0.1"
    }
    unresolved = classify(report, cycle=proof, original_finance=original, quote_stale=True)
    assert unresolved.risk_at_finding == "UNRESOLVED_EXIT"
    assert not unresolved.trading_authorized


def test_unchanged_complete_selected_book_no_new_page_or_signal():
    report = assessment(source_observability="VERIFIED_CONTINUOUS")
    assert classify(report, cycle=None, original_finance=None, quote_stale=False) is None
    assert not report.opportunities
    assert not report.operational_incidents


def test_ack_private_receipt_and_delivery_based_target(tmp_path):
    report = _gap_report()
    incident = classify(report, cycle=None, original_finance=None, quote_stale=False)
    root = tmp_path / "ops"
    root.mkdir(mode=0o700)
    delivered_at = NOW - timedelta(seconds=1)
    new, receipt_sha = acknowledge(
        incident,
        delivered_at=delivered_at,
        acknowledged_at=NOW,
        owner_alias="oncall-a",
        route_alias="private-console",
        evidence_sha256=H,
        private_directory=root,
    )
    assert new.owner_acknowledgement == "ACKNOWLEDGED"
    assert len(receipt_sha) == 64
    files = list(root.glob("ack-*.json"))
    assert len(files) == 1
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert b"no_financial_mutation" in files[0].read_bytes()
    with pytest.raises(ValueError, match="EXISTS"):
        acknowledge(
            incident,
            delivered_at=delivered_at,
            acknowledged_at=NOW,
            owner_alias="oncall-a",
            route_alias="private-console",
            evidence_sha256=H,
            private_directory=root,
        )
    with pytest.raises(ValueError, match="PRECEDES_INCIDENT"):
        acknowledge(
            incident,
            delivered_at=NOW - timedelta(days=1),
            acknowledged_at=NOW,
            owner_alias="oncall-a",
            route_alias="private-console",
            evidence_sha256=H,
            private_directory=root,
        )
