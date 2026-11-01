"""Only independently signed whole-account outcomes can satisfy the new contract."""

from datetime import timedelta

import pytest

from copytrade_pm.pm02_outcomes import SCHEMA, DIGEST_FIELDS, CLAIM_FIELDS
from test_pm_prospective_audit import setup_receipt, signature
from test_pm_prospective_ledger import IMPORTED
from test_pm_prospective_outcomes import make_outcome


def whole(journal, head):
    return {
        **make_outcome(journal, head),
        "schema": SCHEMA,
        **dict.fromkeys(DIGEST_FIELDS, "b" * 64),
        **dict.fromkeys(CLAIM_FIELDS, True),
        "source_net_r": "1.7",
        "risk_unit_usd": "100",
        "source_scale_factor": "0.02",
        "signed_exposures_r": {"hyperliquid/mainnet:perp:default/BTC": ".4"},
    }


def test_v2_preserves_separate_source_economics_and_predeclared_lineage(tmp_path):
    journal, signer, audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(audit, signature(signer, audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = whole(journal, head)
    journal.record_matched_outcome(outcome, signature(signer, outcome))
    row = journal.pm02_rows_asof(now[0].isoformat())["W001"][0]
    assert row["whole_account_verified"] is True
    assert row["source_net_r"] == "1.7"
    assert row["selection_plan_sha256"] == "b" * 64
    assert row["horizon_minutes"] == 5
    assert row["source_event_id"] == outcome["source_event_id"]
    duplicate = {**outcome, "episode_id": "different-name-same-evidence"}
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_HORIZON"):
        journal.record_matched_outcome(duplicate, signature(signer, duplicate))


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_equity_evidence_sha256", None),
        ("whole_account_reconciled", "true"),
        ("risk_unit_usd", "0"),
        ("source_net_r", "NaN"),
        ("capacity_verified", False),
    ],
)
def test_a_signature_cannot_replace_required_account_evidence(tmp_path, field, value):
    journal, signer, audit, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(audit, signature(signer, audit))
    now[0] = IMPORTED + timedelta(minutes=6)
    outcome = {**whole(journal, head), field: value}
    with pytest.raises(ValueError):
        journal.record_matched_outcome(outcome, signature(signer, outcome))
    assert journal.pm02_rows_asof(now[0].isoformat()) == {}
