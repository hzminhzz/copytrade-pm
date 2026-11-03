"""Read-only TI qualification gate must never turn signed fixtures into alpha."""

from datetime import timedelta
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import pytest

from copytrade_pm.trader_intelligence_qualification import audit_prospective_evidence
from copytrade_pm.trader_intelligence_qualification_cli import run
from test_pm_prospective_audit import setup_receipt, signature
from test_pm_prospective_ledger import IMPORTED
from test_pm02_whole_account_outcomes import whole

PLAN = "b" * 64
START = IMPORTED - timedelta(minutes=1)
END = IMPORTED + timedelta(minutes=3)


def readiness(journal, *, asof=IMPORTED + timedelta(hours=1), plan=PLAN):
    return audit_prospective_evidence(
        journal,
        asof=asof.isoformat(),
        holdout_start=START.isoformat(),
        holdout_end=END.isoformat(),
        selection_plan_sha256=plan,
    )


def test_empty_verified_ledger_reports_missing_prospective_evidence(tmp_path):
    journal, _signer, _audit, _now = setup_receipt(tmp_path)
    report = readiness(journal)
    assert report.status == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert report.receipt_count == 1
    assert report.independent_receipt_audits == 0
    assert report.signed_matched_outcomes == 0
    assert report.eligible_whole_account_outcomes == 0
    assert "NO_SIGNED_MATURE_WHOLE_ACCOUNT_OUTCOMES" in report.reasons
    assert report == readiness(journal)


def test_signed_v2_outcome_remains_scientifically_unqualified(tmp_path):
    journal, signer, audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(audit, signature(signer, audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = whole(journal, head)
    journal.record_matched_outcome(outcome, signature(signer, outcome))
    report = readiness(journal)
    assert report.independent_receipt_audits == 1
    assert report.signed_matched_outcomes == 1
    assert report.eligible_whole_account_outcomes == 1
    assert report.distinct_wallets == 1
    assert report.distinct_source_events == 1
    assert report.matched_horizon_groups == 0
    assert report.status == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert "OOS_SKILL_AND_CALIBRATION_NOT_TESTED" in report.reasons
    assert report.complete_group_incremental_mean_r is None
    one_horizon = audit_prospective_evidence(
        journal,
        asof=(IMPORTED + timedelta(hours=1)).isoformat(),
        holdout_start=START.isoformat(),
        holdout_end=END.isoformat(),
        selection_plan_sha256=PLAN,
        required_horizons=(5,),
    )
    assert one_horizon.matched_horizon_groups == 1
    assert one_horizon.complete_group_incremental_mean_r == "0.25"
    assert one_horizon.complete_group_worst_incremental_r == "0.25"
    assert one_horizon.status == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert readiness(journal, plan="c" * 64).eligible_whole_account_outcomes == 0
    assert readiness(journal, asof=IMPORTED + timedelta(minutes=5)).signed_matched_outcomes == 0


def test_v1_signed_outcome_excluded_from_whole_account_gate(tmp_path):
    journal, signer, audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(audit, signature(signer, audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = whole(journal, head)
    outcome["schema"] = "pm02_independent_matched_outcome_v1"
    outcome["signed_exposures_r"] = {"hyperliquid:mainnet:perp:default:BTC": "0.4"}
    journal.record_matched_outcome(outcome, signature(signer, outcome))
    report = readiness(journal)
    assert report.signed_matched_outcomes == 1
    assert report.eligible_whole_account_outcomes == 0
    assert "MISSING_MATCHED_WHOLE_ACCOUNT_EVIDENCE" in report.reasons


def test_cli_reads_existing_immutable_signed_ledger_without_mutating(tmp_path):
    journal, signer, receipt_audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(receipt_audit, signature(signer, receipt_audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = whole(journal, head)
    journal.record_matched_outcome(outcome, signature(signer, outcome))
    public = signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    key = tmp_path / "auditor.pub"
    key.write_bytes(public)
    key.chmod(0o600)
    before = journal.head_sha
    result = run(
        [
            "--ledger",
            str(journal.root),
            "--auditor-public-key",
            str(key),
            "--asof",
            (IMPORTED + timedelta(hours=1)).isoformat(),
            "--holdout-start",
            START.isoformat(),
            "--holdout-end",
            END.isoformat(),
            "--selection-plan-sha256",
            PLAN,
            "--horizons",
            "5",
        ]
    )
    assert result["matched_horizon_groups"] == 1
    assert result["status"] == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert journal.head_sha == before
    key.write_bytes(b"0" * 32)
    with pytest.raises(ValueError, match="TRUST_ROOT_MISMATCH"):
        run(
            [
                "--ledger",
                str(journal.root),
                "--auditor-public-key",
                str(key),
                "--asof",
                (IMPORTED + timedelta(hours=1)).isoformat(),
                "--holdout-start",
                START.isoformat(),
                "--holdout-end",
                END.isoformat(),
                "--selection-plan-sha256",
                PLAN,
            ]
        )


def test_bad_window_and_invalid_plan_fail_closed(tmp_path):
    journal, _signer, _audit, _now = setup_receipt(tmp_path)
    with pytest.raises(ValueError, match="INVALID_PIT_HOLDOUT_CLOCKS"):
        audit_prospective_evidence(
            journal,
            asof=IMPORTED.isoformat(),
            holdout_start=END.isoformat(),
            holdout_end=START.isoformat(),
            selection_plan_sha256=PLAN,
        )
    with pytest.raises(ValueError):
        readiness(journal, plan="bad")
