"""Adversarial integration of independently anchored source verification.

Runs only against temporary synthetic originals and an isolated backup used for
the initial full audit. No live journals, signing keys, or services.
"""

from __future__ import annotations

from hashlib import sha256
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm_forward_stream_anchor import (
    anchor_file_bytes,
    full_audit_anchor,
    load_anchor,
)
from copytrade_pm.strategy_evidence_reconciler import ReconciliationRequest, reconcile_manifest
from copytrade_pm.strategy_health import read
from copytrade_pm.strategy_source_verify import verify_packet
from copytrade_pm.v4_source_export import export_signed_events
from test_pm_forward_stream_anchor import _offline_snapshot
from test_strategy_health_v2 import ADDRESSES, NOW, campaign, observer, scope, source_event


def _private(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)
    return sha256(raw).hexdigest()


def _anchored_fixture(tmp_path):
    journal, source = observer(tmp_path / "original-journal")
    auditor = Ed25519PrivateKey.generate()
    original_snapshot = _offline_snapshot(journal.path, tmp_path)
    seal = full_audit_anchor(
        original_snapshot,
        alias="S035",
        account=ADDRESSES["S035"],
        auditor=auditor,
        offline_snapshot_confirmed=True,
    )
    private = tmp_path / "trusted-private"
    private.mkdir(mode=0o700)
    seal_path = private / "audit.json"
    seal_sha = _private(seal_path, anchor_file_bytes(seal))
    auditor_pub_path = private / "audit-public.raw"
    auditor_sha = _private(auditor_pub_path, auditor.public_key().public_bytes_raw())
    verified = load_anchor(
        seal_path,
        seal_sha,
        auditor.public_key(),
        expected_auditor_public_key_sha256=auditor_sha,
    )
    source_event(source, 10, 20)
    source_key = Ed25519PrivateKey.generate()
    selected = {"S035": ADDRESSES["S035"]}
    packet = export_signed_events(
        journal.path,
        selected=selected,
        signer=source_key,
        after={"S035": 2},
        verified_anchor=verified,
    )
    # Bounded and old full-history paths must produce equivalent existing wire.
    legacy = export_signed_events(
        journal.path, selected=selected, signer=source_key, after={"S035": 2}
    )
    assert packet == legacy
    assert len(packet["events"]["S035"]) == 1
    packet_path = private / "packet.json"
    packet_sha = _private(packet_path, json.dumps(packet).encode())
    source_pub_path = private / "source-public.raw"
    source_sha = _private(source_pub_path, source_key.public_key().public_bytes_raw())
    staging = tmp_path / "track-b-prefect-staging"
    staging.mkdir(mode=0o700)
    request = ReconciliationRequest(
        packet_path=packet_path,
        packet_sha256=packet_sha,
        source_public_key_path=source_pub_path,
        source_public_key_sha256=source_sha,
        original_source_journal=journal.path,
        selected=selected,
        source_after={"S035": 2},
        scope=scope(),
        campaign=campaign(),
        as_of=NOW,
        created_at=NOW,
        output_dir=staging,
        original_audit_anchor_path=seal_path,
        original_audit_anchor_sha256=seal_sha,
        audit_public_key_path=auditor_pub_path,
        audit_public_key_sha256=auditor_sha,
    )
    manifest_path = private / "manifest.json"
    manifest_sha = _private(manifest_path, request.model_dump_json(by_alias=True).encode())
    return request, manifest_path, manifest_sha, auditor_sha, staging, source


def _reconcile(request, path, sha, auditor, *, source_key=None):
    return reconcile_manifest(
        path,
        sha,
        trusted_source_public_key_sha256=source_key or request.source_public_key_sha256,
        trusted_auditor_public_key_sha256=auditor,
    )


def test_anchored_proof_no_full_scan_and_private_report(tmp_path, monkeypatch):
    request, path, manifest_sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    from copytrade_pm import strategy_source_verify, v4_source_export, strategy_evidence_reconciler

    def forbid(*args, **kwargs):
        raise AssertionError("MUST_NOT_RESCAN_FULL_HISTORICAL_ORIGINAL")

    monkeypatch.setattr(strategy_source_verify, "verify_streams", forbid)
    monkeypatch.setattr(v4_source_export, "verify_streams", forbid)
    monkeypatch.setattr(strategy_evidence_reconciler, "MAX_OFFLINE_JOURNAL_BYTES", 1)
    result = _reconcile(request, path, manifest_sha, auditor_sha)
    replay = _reconcile(request, path, manifest_sha, auditor_sha)
    assert result.operational_execution == "PUBLISHED"
    assert replay.operational_execution == "EXISTING_VERIFIED"
    assert result.private_report_bytes_sha256 == replay.private_report_bytes_sha256
    assert result.reasons[0] == "SOURCE_ORIGINAL_FULL_AUDIT_ANCHORED_SUFFIX_VERIFIED"
    assert result.economic_comparability == "UNKNOWN"
    assert result.trading_authorized is False
    assert len(list(staging.iterdir())) == 2
    assert result.private_proof_binding_sha256 is not None
    proof = staging / (result.private_proof_binding_sha256 + ".proof.json")
    binding = json.loads(proof.read_bytes())
    assert binding["source_packet_sha256"] == request.packet_sha256
    assert binding["original_audit_anchor_sha256"] == request.original_audit_anchor_sha256
    assert binding["private_report_bytes_sha256"] == result.private_report_bytes_sha256
    assert binding["trading_authorized"] is False
    report = read(staging / (result.private_report_bytes_sha256 + ".json"))
    assert len(report.opportunities) == 1
    assert report.source_finance_authenticated is False
    assert report.scientifically_qualified is False


def test_bounded_original_source_proof_explicit_v2_not_masquerading_as_full(tmp_path):
    request, path, sha, auditor_sha, stage, _ = _anchored_fixture(tmp_path)
    from copytrade_pm.strategy_evidence_reconciler import _read_private

    packet = json.loads(_read_private(request.packet_path, request.packet_sha256))
    # Use independently pinned original key path, not an invented key.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    auditor = Ed25519PublicKey.from_public_bytes(
        _read_private(request.audit_public_key_path, request.audit_public_key_sha256)
    )
    trusted = load_anchor(
        request.original_audit_anchor_path,
        request.original_audit_anchor_sha256,
        auditor,
        expected_auditor_public_key_sha256=auditor_sha,
    )
    original = Ed25519PublicKey.from_public_bytes(
        _read_private(request.source_public_key_path, request.source_public_key_sha256)
    )
    proof = verify_packet(
        packet,
        original,
        selected=request.selected,
        original_journal=request.original_source_journal,
        after=request.source_after,
        as_of=request.as_of,
        policy_version=request.scope.k_version,
        frozen_k=str(request.scope.frozen_k),
        verified_anchor=trusted,
    )
    assert proof["schema"] == "strategy_source_verification_v2_anchored"
    assert proof["read_only"] is True
    assert proof["trading_authorized"] is False
    assert len(proof["opportunities"]) == 1


def test_anchor_trust_pin_wrong_and_missing_fail_before_publish(tmp_path):
    request, path, sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    with pytest.raises(ValueError, match="AUDITOR_TRUST_PIN_REQUIRED"):
        reconcile_manifest(
            path, sha, trusted_source_public_key_sha256=request.source_public_key_sha256
        )
    with pytest.raises(ValueError, match="AUDITOR_TRUST_PIN_MISMATCH"):
        _reconcile(request, path, sha, "0" * 64)
    with pytest.raises(ValueError, match="SOURCE_KEY_PIN_REQUIRED|INDEPENDENT_SOURCE_KEY_PIN"):
        _reconcile(request, path, sha, auditor_sha, source_key="f" * 64)
    assert not list(staging.iterdir())


def test_source_moved_after_signed_packet_fails_no_publication(tmp_path):
    request, path, sha, auditor_sha, staging, source = _anchored_fixture(tmp_path)
    source_event(source, 20, 25)
    with pytest.raises(ValueError, match="SOURCE_ORIGINAL_HEAD_DIVERGED"):
        _reconcile(request, path, sha, auditor_sha)
    assert not list(staging.iterdir())


def test_anchored_cursor_cannot_replay_pre_anchor_history(tmp_path):
    request, path, _, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    changed = request.model_copy(update={"source_after": {"S035": 1}})
    sha = _private(path, changed.model_dump_json(by_alias=True).encode())
    with pytest.raises(ValueError, match="ANCHORED_CURSOR_OUTSIDE_AUDITED_SUFFIX"):
        _reconcile(changed, path, sha, auditor_sha)
    assert not list(staging.iterdir())
