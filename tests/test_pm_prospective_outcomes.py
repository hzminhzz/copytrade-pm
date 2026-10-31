"""PM-02 consumer contract: only independently attested matched outcomes are admitted."""

from datetime import timedelta

import pytest

from copytrade_pm.pm_manager import _prospective_evidence, timestamp
from test_pm_prospective_audit import setup_receipt, signature
from test_pm_prospective_ledger import IMPORTED

FIVE = timedelta(minutes=5)


def make_outcome(journal, audit_sha, *, time=IMPORTED + FIVE + timedelta(seconds=2)):
    row = journal.receipts_asof(IMPORTED.isoformat())[0]
    return {
        "schema": "pm02_independent_matched_outcome_v1",
        "episode_id": "W001-BTC-12-5m",
        "source_event_id": row["event_id"],
        "receipt_audit_sha256": audit_sha,
        "decision_at": (IMPORTED + timedelta(seconds=1)).isoformat(),
        "outcome_known_at": time.isoformat(),
        "audited_at": (time + timedelta(seconds=1)).isoformat(),
        "horizon_minutes": 5,
        "follower_economics_kind": "AUDITED_MATCHED_FOLLOWER",
        "independent_source_digest": "2" * 64,
        "market_source_digest": "3" * 64,
        "follower_fill_evidence_sha256": "4" * 64,
        "matched_control": True,
        "source_conflict": False,
        "missing_market": False,
        "follower_net_r": "1.25",
        "control_net_r": "1.00",
        "tail_loss_r": "0.20",
        "turnover_r": "0.15",
        "signed_exposures_r": {"hyperliquid:mainnet:perp:default:BTC": "0.4"},
    }


def test_audited_receipt_plus_matched_economics_produce_exact_pm02_row(tmp_path):
    journal, signer, receipt_audit, now = setup_receipt(tmp_path)
    audit_sha = journal.audit_receipt(receipt_audit, signature(signer, receipt_audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = make_outcome(journal, audit_sha)
    signed = signature(signer, outcome)
    outcome_sha = journal.record_matched_outcome(outcome, signed)
    assert outcome_sha == journal.read()[-1]["sha"]
    assert journal.pm02_rows_asof((IMPORTED + timedelta(minutes=5)).isoformat()) == {}
    result = journal.pm02_rows_asof(now[0].isoformat())
    assert list(result) == ["W001"]
    rows = result["W001"]
    assert len(rows) == 1
    r = rows[0]
    assert set(r) == {
        "episode_id",
        "event_at",
        "known_at",
        "outcome_known_at",
        "verified_first_known",
        "oracle_hindsight",
        "matched_control",
        "independent_source_digest",
        "market_source_digest",
        "source_conflict",
        "missing_market",
        "follower_net_r",
        "control_net_r",
        "tail_loss_r",
        "turnover_r",
        "signed_exposures_r",
    }
    assert r["event_at"] == journal.receipts_asof(IMPORTED.isoformat())[0]["source_event_at"]
    assert r["known_at"] == IMPORTED.isoformat()
    assert timestamp(r["outcome_known_at"]) == now[0]
    assert r["verified_first_known"] is True
    assert r["oracle_hindsight"] is False and r["matched_control"] is True
    assert float(r["follower_net_r"]) == 1.25
    assert len(_prospective_evidence(rows, timestamp(now[0].isoformat()))) == 1
    assert journal.record_matched_outcome(outcome, signed) == outcome_sha
    assert len(journal.read()) == 3


def test_unverified_economics_cannot_invent_pm02_qualifications(tmp_path):
    journal, signer, receipt_audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(receipt_audit, signature(signer, receipt_audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    good = make_outcome(journal, head)
    with pytest.raises(ValueError, match="INVALID_OUTCOME_SIGNATURE"):
        journal.record_matched_outcome({**good, "follower_net_r": "900"}, signature(signer, good))
    with pytest.raises(ValueError, match="UNKNOWN_FOLLOWER_ECONOMICS"):
        bad = {**good, "independent_source_digest": None}
        journal.record_matched_outcome(bad, signature(signer, bad))
    with pytest.raises(ValueError, match="OUTCOME_CLOCK"):
        future = make_outcome(journal, head, time=IMPORTED + timedelta(days=1))
        journal.record_matched_outcome(future, signature(signer, future))
    with pytest.raises(ValueError, match="OUTCOME_HORIZON_NOT_MATURE"):
        premature = make_outcome(journal, head, time=IMPORTED + timedelta(minutes=1))
        journal.record_matched_outcome(premature, signature(signer, premature))
    assert journal.pm02_rows_asof(now[0].isoformat()) == {}


def test_reopen_requires_same_signed_contract_and_detects_economic_revision(tmp_path):
    journal, signer, receipt_audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(receipt_audit, signature(signer, receipt_audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = make_outcome(journal, head)
    journal.record_matched_outcome(outcome, signature(signer, outcome))
    revised = dict(outcome, follower_net_r="999")
    with pytest.raises(ValueError, match="CONFLICTING_MATCHED_OUTCOME"):
        journal.record_matched_outcome(revised, signature(signer, revised))
    restored = type(journal)(
        journal.root,
        cohort={"W001": journal.manifest["cohort"]["W001"]},
        cohort_manifest_sha=journal.manifest["cohort_manifest_sha"],
        audit_public_key=journal.audit_public_key,
        clock_source=lambda: now[0],
    )
    assert restored.pm02_rows_asof(now[0].isoformat()) == journal.pm02_rows_asof(now[0].isoformat())
