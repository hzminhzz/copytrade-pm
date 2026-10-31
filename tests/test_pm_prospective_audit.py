"""Independent signer must attest first-known receipt chain before outcomes."""

from datetime import timedelta
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from copytrade_pm.pm_prospective_ledger import ProspectiveLedger
from test_pm_prospective_ledger import (
    IMPORTED,
    IDENTITY,
    MANIFEST,
    first_receipt,
)


def signing():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def signature(private, value):
    return private.sign(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hex()


def setup_receipt(tmp_path, *, snapshot=False):
    folder = tmp_path / "producer"
    first_receipt(folder, snapshot=snapshot)
    private, public = signing()
    now = [IMPORTED]
    journal = ProspectiveLedger(
        tmp_path / "research-ledger",
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        audit_public_key=public,
        clock_source=lambda: now[0],
    )
    journal.ingest_folder(folder)
    row = journal.receipts_asof(IMPORTED.isoformat())[0]
    now[0] = IMPORTED + timedelta(seconds=4)
    evidence = {
        "schema": "pm01_independent_receipt_audit_v1",
        "event_id": row["event_id"],
        "raw_receipt_sha256": row["raw_receipt_sha256"],
        "receipt_event_sha256": journal.read()[0]["sha"],
        "first_known_at": row["first_known_at"],
        "independent_clock_anchor_sha256": "1" * 64,
        "auditor_id": "off-process-reviewer",
        "auditor_role": "INDEPENDENT_REVIEWER",
        "clock_reconciled": True,
        "continuity_reviewed": True,
        "audited_at": (IMPORTED + timedelta(seconds=2)).isoformat(),
    }
    return journal, private, evidence, now


def test_independent_signed_receipt_audit_does_not_invent_outcomes(tmp_path):
    journal, signer, evidence, now = setup_receipt(tmp_path)
    head = journal.audit_receipt(evidence, signature(signer, evidence))
    assert len(journal.read()) == 2
    assert journal.read()[-1]["sha"] == head
    assert journal.pm02_rows_asof(now[0].isoformat()) == {}
    assert journal.audit_receipt(evidence, signature(signer, evidence)) == head


def test_false_signature_and_historical_snapshot_cannot_be_audited(tmp_path):
    journal, signer, evidence, _ = setup_receipt(tmp_path)
    bad = dict(evidence, clock_reconciled=False)
    with pytest.raises(ValueError, match="INVALID_AUDIT_SIGNATURE"):
        journal.audit_receipt(bad, signature(signer, evidence))
    assert len(journal.read()) == 1
    stale, signer2, stale_evidence, _ = setup_receipt(tmp_path / "other", snapshot=True)
    with pytest.raises(ValueError, match="RECOVERED_OR_SNAPSHOT"):
        stale.audit_receipt(stale_evidence, signature(signer2, stale_evidence))
    assert stale.pm02_rows_asof(IMPORTED.isoformat()) == {}


def test_cannot_reopen_journal_with_a_different_auditor_trust_root(tmp_path):
    journal, _signer, _evidence, _ = setup_receipt(tmp_path)
    _, other_public = signing()
    with pytest.raises(ValueError, match="IMMUTABLE_COHORT_MANIFEST"):
        ProspectiveLedger(
            journal.root,
            cohort={"W001": IDENTITY},
            cohort_manifest_sha=MANIFEST,
            audit_public_key=other_public,
        )
