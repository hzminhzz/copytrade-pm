"""Optional local Prefect adapter for independently audited Track B assessments.

These tests never access live 0811/0911 SQLite, systemd, or broker services.
"""

from __future__ import annotations

import errno
from hashlib import sha256
import json
from pathlib import Path

import pytest

from copytrade_pm.strategy_evidence_prefect import _preflight, run_prefect_reconciliation
from copytrade_pm.strategy_evidence_reconciler import ReconciliationRequest
from test_strategy_anchored_reconciler import _anchored_fixture, _reconcile


@pytest.fixture(scope="module", autouse=True)
def _quiet_local_prefect_logs():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PREFECT_LOGGING_LEVEL", "CRITICAL")
        patch.setenv("PREFECT_LOGGING_INTERNAL_LEVEL", "CRITICAL")
        yield


def _args(request, path, manifest_sha, auditor_sha):
    return dict(
        manifest_path=path,
        manifest_sha256=manifest_sha,
        trusted_source_public_key_sha256=request.source_public_key_sha256,
        trusted_auditor_public_key_sha256=auditor_sha,
    )


def test_preflight_refuses_mismatched_independent_trust_and_unsafe_manifest(tmp_path):
    request, path, manifest_sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    options = _args(request, path, manifest_sha, auditor_sha)
    _preflight(path, manifest_sha, request.source_public_key_sha256, auditor_sha)
    with pytest.raises(ValueError, match="INDEPENDENT_AUDITED_SOURCE_REQUIRED"):
        _preflight(path, manifest_sha, "a" * 64, auditor_sha)
    with pytest.raises(ValueError, match="INDEPENDENT_AUDITED_SOURCE_REQUIRED"):
        _preflight(path, manifest_sha, request.source_public_key_sha256, "b" * 64)
    with pytest.raises(ValueError, match="MANIFEST_PIN_INVALID"):
        _preflight(path, "invalid", request.source_public_key_sha256, auditor_sha)
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        _preflight(path, "0" * 64, request.source_public_key_sha256, auditor_sha)
    with pytest.raises(ValueError, match="ABSOLUTE_PATH_REQUIRED"):
        _preflight(
            Path("relative.json"), manifest_sha, request.source_public_key_sha256, auditor_sha
        )

    # An unaudited request must not enter a Prefect task and cannot silently
    # fall back to the legacy full-history source scan.
    data = request.model_dump(by_alias=True)
    for field in (
        "original_audit_anchor_path",
        "original_audit_anchor_sha256",
        "audit_public_key_path",
        "audit_public_key_sha256",
    ):
        data[field] = None
    unaudited = ReconciliationRequest.model_validate(data, strict=True)
    replacement = json.dumps(unaudited.model_dump(by_alias=True, mode="json")).encode()
    path.write_bytes(replacement)
    new_sha = sha256(replacement).hexdigest()
    with pytest.raises(ValueError, match="INDEPENDENT_AUDITED_SOURCE_REQUIRED"):
        run_prefect_reconciliation(**{**options, "manifest_sha256": new_sha})
    assert not list(staging.iterdir())


def test_true_local_prefect_parity_and_idempotence(tmp_path):
    pytest.importorskip("prefect")
    request, path, manifest_sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    options = _args(request, path, manifest_sha, auditor_sha)
    result = run_prefect_reconciliation(**options)
    assert result["schema"] == "track_b_proof_bound_prefect_receipt_v1"
    assert result["job_count"] == 1
    assert result["read_only"] is True
    assert result["trading_authorized"] is False
    assert result["scientifically_qualified"] is False
    assert result["shadow_deployed"] is False
    assert result["source_finance_authenticated"] is False
    report = result["assessment"]
    assert report["operational_execution"] == "PUBLISHED"
    assert report["economic_comparability"] == "UNKNOWN"
    assert report["evidence_availability"] == "INCOMPLETE_SCOPE"
    assert report["private_proof_binding_sha256"]
    assert len(list(staging.iterdir())) == 2

    direct = _reconcile(request, path, manifest_sha, auditor_sha)
    assert direct.operational_execution == "EXISTING_VERIFIED"
    assert direct.private_report_bytes_sha256 == report["private_report_bytes_sha256"]
    assert direct.private_proof_binding_sha256 == report["private_proof_binding_sha256"]
    again = run_prefect_reconciliation(**options)
    assert again["assessment"]["operational_execution"] == "EXISTING_VERIFIED"
    assert (
        again["assessment"]["private_report_bytes_sha256"] == report["private_report_bytes_sha256"]
    )
    assert len(list(staging.iterdir())) == 2
    raw = json.dumps(result)
    assert str(tmp_path) not in raw
    assert request.scope.source_alias not in raw
    assert request.selected[request.scope.source_alias] not in raw


def test_prefect_retry_only_transient_local_io_no_duplicate(tmp_path, monkeypatch):
    pytest.importorskip("prefect")
    from prefect.settings import PREFECT_SERVER_ANALYTICS_ENABLED
    from copytrade_pm import strategy_evidence_prefect as adapter

    request, path, sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    original = adapter.reconcile_manifest
    calls = []

    def fail_once(*args, **kwargs):
        assert PREFECT_SERVER_ANALYTICS_ENABLED.value() is False
        calls.append(1)
        if len(calls) == 1:
            raise OSError(errno.EBUSY, "PRIVATE_WALLET_IDENTIFIER_DO_NOT_LOG")
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter, "reconcile_manifest", fail_once)
    result = adapter.run_prefect_reconciliation(**_args(request, path, sha, auditor_sha))
    assert len(calls) == 2
    assert result["assessment"]["operational_execution"] == "PUBLISHED"
    assert len(list(staging.iterdir())) == 2


def test_prefect_rejects_nontransient_validation_without_retry(tmp_path, monkeypatch):
    pytest.importorskip("prefect")
    from copytrade_pm import strategy_evidence_prefect as adapter

    request, path, sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    calls = []

    def invalid(*args, **kwargs):
        calls.append(1)
        raise ValueError("PRIVATE_WALLET_IDENTIFIER_DO_NOT_LOG")

    monkeypatch.setattr(adapter, "reconcile_manifest", invalid)
    with pytest.raises(ValueError, match="EVIDENCE_PREFECT_PRIVATE_PROOF_REJECTED"):
        adapter.run_prefect_reconciliation(**_args(request, path, sha, auditor_sha))
    assert len(calls) == 1
    assert not list(staging.iterdir())


def test_remote_prefect_api_fails_closed_before_any_output(tmp_path):
    pytest.importorskip("prefect")
    from prefect.settings import PREFECT_API_URL, temporary_settings

    request, path, sha, auditor_sha, staging, _ = _anchored_fixture(tmp_path)
    with temporary_settings(updates={PREFECT_API_URL: "https://prefect.example.invalid/api"}):
        with pytest.raises(ValueError, match="EVIDENCE_PREFECT_REMOTE_API_DISABLED"):
            run_prefect_reconciliation(**_args(request, path, sha, auditor_sha))
    assert not list(staging.iterdir())
