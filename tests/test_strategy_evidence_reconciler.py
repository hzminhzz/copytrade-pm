"""Proof-bound reconciler adversarial tests: genuine signed original source fixture."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.strategy_evidence_reconciler import (
    MAX_OFFLINE_JOURNAL_BYTES,
    ReconciliationRequest,
    reconcile_manifest,
)
from copytrade_pm.strategy_health import read
from copytrade_pm.v4_source_export import export_signed_events
from test_strategy_health_v2 import (
    ADDRESSES,
    NOW,
    campaign,
    observer,
    scope,
    source_event,
)


def _private(path, content: bytes) -> str:
    path.write_bytes(content)
    path.chmod(0o600)
    return sha256(content).hexdigest()


def _inputs(tmp_path):
    journal, source = observer(tmp_path / "observer")
    source_event(source, 10, 20)
    signer = Ed25519PrivateKey.generate()
    source_selection = {"S035": ADDRESSES["S035"]}
    packet = export_signed_events(
        journal.path, selected=source_selection, signer=signer, after={"S035": 2}
    )
    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    staging = tmp_path / "track-b-prefect-staging"
    staging.mkdir(mode=0o700)
    packet_path = original / "source-packet.json"
    packet_sha = _private(packet_path, json.dumps(packet).encode())
    public_path = original / "source-public.raw"
    public_sha = _private(public_path, signer.public_key().public_bytes_raw())
    request = ReconciliationRequest(
        packet_path=packet_path,
        packet_sha256=packet_sha,
        source_public_key_path=public_path,
        source_public_key_sha256=public_sha,
        original_source_journal=journal.path,
        selected=source_selection,
        source_after={"S035": 2},
        scope=scope(),
        campaign=campaign(),
        as_of=NOW,
        created_at=NOW,
        output_dir=staging,
    )
    request_path = original / "request.json"
    request_sha = _private(request_path, request.model_dump_json(by_alias=True).encode())
    return request, request_path, request_sha, staging


def _reconcile(path, sha, trusted_key=None, trusted_auditor=None):
    # The independent trust anchor is supplied by the caller.
    pinned = json.loads(path.read_text())["source_public_key_sha256"]
    return reconcile_manifest(
        path,
        sha,
        trusted_source_public_key_sha256=trusted_key or pinned,
        trusted_auditor_public_key_sha256=trusted_auditor,
    )


def test_signed_original_reconciles_idempotently_without_financial_promotion(tmp_path):
    request, path, sha, stage = _inputs(tmp_path)
    source_before = request.original_source_journal.read_bytes()
    result = _reconcile(path, sha)
    again = _reconcile(path, sha)
    assert (result.operational_execution, again.operational_execution) == (
        "PUBLISHED",
        "EXISTING_VERIFIED",
    )
    assert result.private_report_bytes_sha256 == again.private_report_bytes_sha256
    assert result.evidence_availability == "INCOMPLETE_SCOPE"
    assert result.economic_comparability == "UNKNOWN"
    assert result.scientific_qualification == "NOT_QUALIFIED"
    assert result.publication_status == "PRIVATE_ONLY"
    assert result.trading_authorized is False
    assert result.reasons == (
        "SELECTED_REGISTRY_SEAL_NOT_INDEPENDENTLY_VERIFIED",
        "ORIGINAL_PM03_FINANCE_NOT_SUPPLIED",
    )
    files = list(stage.iterdir())
    assert len(files) == 1
    report = read(files[0])
    assert len(report.opportunities) == 1
    assert report.opportunities[0].due_at - report.opportunities[0].first_known_at == timedelta(
        seconds=300
    )
    assert report.source_observability == "INCOMPLETE_SCOPE"
    assert report.follower_economics.net_comparable is False
    assert request.original_source_journal.read_bytes() == source_before


def test_invalid_packet_signature_and_private_pin_fail_without_output(tmp_path):
    request, path, sha, stage = _inputs(tmp_path)
    original = json.loads(request.packet_path.read_bytes())
    original["events"]["S035"][0]["proof"]["payload"]["first_known_ms"] += 1
    request.packet_path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        _reconcile(path, sha)
    assert not list(stage.iterdir())


def test_packet_with_new_hash_but_forged_original_proof_fails(tmp_path):
    request, path, _, stage = _inputs(tmp_path)
    packet = json.loads(request.packet_path.read_bytes())
    packet["events"]["S035"][0]["proof"]["payload"]["first_known_ms"] += 1
    new_sha = _private(request.packet_path, json.dumps(packet).encode())
    changed = request.model_copy(update={"packet_sha256": new_sha})
    sha = _private(path, changed.model_dump_json(by_alias=True).encode())
    with pytest.raises(ValueError):
        _reconcile(path, sha)
    assert not list(stage.iterdir())


def test_manifest_scope_and_original_path_gates(tmp_path):
    request, path, sha, stage = _inputs(tmp_path)
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        _reconcile(path, "0" * 64)
    with pytest.raises(ValueError, match="INDEPENDENT_SOURCE_KEY_PIN_REQUIRED"):
        _reconcile(path, sha, trusted_key="b" * 64)
    with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
        ReconciliationRequest.model_validate(
            {**request.model_dump(by_alias=True), "source_after": {"OTHER": 2}}
        )
    with pytest.raises(ValueError, match="PM03_PATH_HEAD_PAIR"):
        ReconciliationRequest.model_validate(
            {**request.model_dump(by_alias=True), "original_pm03_root": tmp_path}
        )
    assert not list(stage.iterdir())


def test_crash_after_publish_replay_and_tamper_fail_closed(tmp_path, monkeypatch):
    from copytrade_pm import strategy_evidence_reconciler as module

    _, path, sha, stage = _inputs(tmp_path)
    original = module.publish

    def crash(report, destination):
        original(report, destination)
        raise OSError("CRASH_AFTER_DURABLE_PUBLICATION")

    monkeypatch.setattr(module, "publish", crash)
    with pytest.raises(OSError, match="CRASH_AFTER"):
        _reconcile(path, sha)
    monkeypatch.setattr(module, "publish", original)
    result = _reconcile(path, sha)
    assert result.operational_execution == "EXISTING_VERIFIED"
    target = next(stage.iterdir())
    target.write_bytes(target.read_bytes().replace(b"campaign-1", b"campaign-2"))
    with pytest.raises(ValueError):
        _reconcile(path, sha)


def test_existing_pm03_reducer_is_reused_without_claiming_comparability(tmp_path):
    from test_strategy_proof import _original_bundle

    report, ref, params, _ = _original_bundle(tmp_path / "proof")
    original = tmp_path / "pinned-original"
    original.mkdir(mode=0o700)
    staging = tmp_path / "track-b-prefect-staging"
    staging.mkdir(mode=0o700)
    signer = Ed25519PrivateKey.generate()
    # Use the original fixture source and mint a real signed packet with a
    # separately pinned key. No simulated PM03 output is promoted to real PnL.
    packet = export_signed_events(
        params["pinned_source_journal"],
        selected={"S035": ADDRESSES["S035"]},
        signer=signer,
        after={"S035": 2},
    )
    packet_path = original / "packet.json"
    packet_sha = _private(packet_path, json.dumps(packet).encode())
    public_path = original / "source-key.raw"
    public_sha = _private(public_path, signer.public_key().public_bytes_raw())
    request = ReconciliationRequest(
        packet_path=packet_path,
        packet_sha256=packet_sha,
        source_public_key_path=public_path,
        source_public_key_sha256=public_sha,
        original_source_journal=params["pinned_source_journal"],
        selected={"S035": ADDRESSES["S035"]},
        source_after={"S035": 2},
        scope=scope(),
        campaign=campaign(),
        as_of=NOW,
        created_at=NOW,
        output_dir=staging,
        original_pm03_root=params["pinned_pm03_root"],
        original_pm03_head_sha256=ref.original_pm03_head_sha256,
    )
    path = original / "request.json"
    sha = _private(path, request.model_dump_json(by_alias=True).encode())
    result = _reconcile(path, sha)
    final = read(staging / (result.private_report_bytes_sha256 + ".json"))
    assert result.operational_execution == "PUBLISHED"
    assert "FOLLOWER_MARKET_COST_FUNDING_COMPLETENESS_UNVERIFIED" in result.reasons
    assert final.follower_economics.evidence_class == "RESEARCH_SYNTHETIC"
    assert final.follower_economics.net_comparable is False
    assert final.scientifically_qualified is False
    assert final.trading_authorized is False


def test_large_original_is_refused_before_full_chain_verification(tmp_path, monkeypatch):
    from copytrade_pm import strategy_evidence_reconciler as module

    request, path, sha, stage = _inputs(tmp_path)
    monkeypatch.setattr(module, "MAX_OFFLINE_JOURNAL_BYTES", 1)
    with pytest.raises(ValueError, match="TOO_LARGE_FOR_FULL_CHAIN_SCAN"):
        _reconcile(path, sha)
    assert not list(stage.iterdir())
    assert MAX_OFFLINE_JOURNAL_BYTES > 1
