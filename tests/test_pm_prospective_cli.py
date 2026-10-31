"""CLI contract: only reviewed producer receipts may become PM-02 evidence."""

from datetime import timedelta
from hashlib import sha256
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from copytrade_pm.pm_prospective_cli import run
from copytrade_pm.pm_prospective_ledger import ProspectiveLedger, digest
from copytrade_pm.pm_sources import CohortEntry
from test_pm_prospective_ledger import IMPORTED, first_receipt, IDENTITY, ADDRESS
from test_pm_prospective_outcomes import make_outcome
from test_pm_prospective_audit import signature

COHORT = tuple(
    CohortEntry(
        f"W{i:03d}",
        "original" if i <= 6 else "wave1" if i <= 16 else "wave2",
        ADDRESS if i == 1 else f"0x{i:040x}",
        IDENTITY if i == 1 else sha256(f"0x{i:040x}".encode()).hexdigest(),
        "HISTORICAL_ONLY",
        1,
        2,
    )
    for i in range(1, 37)
)
FINGERPRINTS = {"source-a": "1" * 64, "source-b": "2" * 64}


def init_cli(monkeypatch, tmp_path):
    import copytrade_pm.pm_prospective_cli as cli

    monkeypatch.setattr(cli, "load_cohort", lambda _: (COHORT, FINGERPRINTS))
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    key_path = tmp_path / "auditor.pub"
    key_path.write_bytes(public)
    root = tmp_path / "ledger"
    arguments = [
        "--research-root",
        str(tmp_path),
        "--ledger",
        str(root),
        "--auditor-public-key",
        str(key_path),
    ]
    return arguments, root, private, public


def synthetic_time(monkeypatch, root, public):
    import copytrade_pm.pm_prospective_cli as cli

    now = [IMPORTED]

    def opened(**kwargs):
        return ProspectiveLedger.open_existing(
            root,
            cohort={a.alias: a.address_sha256 for a in COHORT},
            cohort_manifest_sha=digest(FINGERPRINTS),
            audit_public_key=public,
            clock_source=lambda: now[0],
        )

    monkeypatch.setattr(cli, "open_ledger", opened)
    return now


def write_signed(tmp_path, label, evidence, key):
    file = tmp_path / f"{label}.json"
    file.write_text(
        json.dumps(
            {
                "attestation": evidence,
                "signature_hex": signature(key, evidence),
            }
        )
    )
    file.chmod(0o600)
    return file


def test_cli_import_refuses_missing_and_rejects_unverified_promotion(monkeypatch, tmp_path):
    args, root, _signer, public = init_cli(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="LEDGER_NOT_INITIALIZED"):
        run(["inspect", *args, "--asof", IMPORTED.isoformat()])
    source = tmp_path / "producer"
    first_receipt(source)
    init = run(["init", *args])
    assert init["status"] == "INITIALIZED"
    assert root.exists()
    synthetic_time(monkeypatch, root, public)
    imported = run(["ingest", *args, "--receipts", str(source)])
    assert imported["ingested"] == 1
    assert imported["receipt_only_not_follower_economics"]
    report = run(["inspect", *args, "--asof", IMPORTED.isoformat()])
    assert report["pm02_episode_count"] == 0
    assert report["prospective_research_only"]
    assert "0xaaaaaaaa" not in json.dumps(report)


def test_cli_independent_signed_receipt_and_economics_yield_one_row(monkeypatch, tmp_path):
    args, root, signer, public = init_cli(monkeypatch, tmp_path)
    run(["init", *args])
    now = synthetic_time(monkeypatch, root, public)
    source = tmp_path / "producer"
    first_receipt(source)
    run(["ingest", *args, "--receipts", str(source)])
    journal = ProspectiveLedger.open_existing(
        root,
        cohort={a.alias: a.address_sha256 for a in COHORT},
        cohort_manifest_sha=digest(FINGERPRINTS),
        audit_public_key=public,
    )
    receipt = journal.receipts_asof(IMPORTED.isoformat())[0]
    attestation = {
        "schema": "pm01_independent_receipt_audit_v1",
        "event_id": receipt["event_id"],
        "raw_receipt_sha256": receipt["raw_receipt_sha256"],
        "receipt_event_sha256": journal.read()[0]["sha"],
        "first_known_at": receipt["first_known_at"],
        "independent_clock_anchor_sha256": "1" * 64,
        "auditor_id": "independent-fixture",
        "auditor_role": "INDEPENDENT_REVIEWER",
        "clock_reconciled": True,
        "continuity_reviewed": True,
        "audited_at": (IMPORTED + timedelta(seconds=2)).isoformat(),
    }
    now[0] = IMPORTED + timedelta(seconds=3)
    signed = write_signed(tmp_path, "audit", attestation, signer)
    outcome1 = run(["audit", *args, "--attestation-file", str(signed)])
    assert outcome1["status"] == "SEALED"
    now[0] = IMPORTED + timedelta(minutes=6)
    economic = make_outcome(journal, outcome1["event_sha256"])
    signed_economic = write_signed(tmp_path, "matched", economic, signer)
    outcome2 = run(["outcome", *args, "--attestation-file", str(signed_economic)])
    assert outcome2["status"] == "SEALED"
    assert run(["inspect", *args, "--asof", IMPORTED.isoformat()])["pm02_episode_count"] == 0
    assert run(["inspect", *args, "--asof", now[0].isoformat()])["pm02_episode_count"] == 1
    assert run(["outcome", *args, "--attestation-file", str(signed_economic)]) == outcome2


def test_cli_requires_exact_36_wallet_roster_and_auditor_key(monkeypatch, tmp_path):
    args, _root, _signer, public = init_cli(monkeypatch, tmp_path)
    keypath = tmp_path / "auditor.pub"
    keypath.write_bytes(b"not-a-key")
    with pytest.raises(ValueError, match="INVALID_AUDITOR_PUBLIC_KEY"):
        run(["init", *args])
    keypath.write_bytes(public)
    import copytrade_pm.pm_prospective_cli as cli

    monkeypatch.setattr(cli, "load_cohort", lambda _: (COHORT[:-1], FINGERPRINTS))
    with pytest.raises(ValueError, match="COHORT"):
        run(["init", *args])
