"""Proof-bound Track B evidence reconciliation (offline, nonactivating).

This is an assembly seam, NOT a new source of evidence or financial state.
It consumes a pinned private signed packet and checks its original V4 journal,
selected registry seal (when available), and optional original PM03 ledger.
Large live databases must not be fully scanned by this experimental path.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .pm_forward_stream_anchor import load_anchor
from .production_manifest import canonical as canonical_binding
from .strategy_advisory import with_recovery
from .strategy_census import assess_verified_packet
from .strategy_finance import (
    inspect_pm03_original,
    reconcile_source_attempts,
    summarize_pm03_economics,
)
from .strategy_health import (
    Campaign,
    StrategyAssessment,
    StrategyScope,
    ZERO_SHA,
    canonical_report,
    publish,
    read,
    seal,
)
from .strategy_health_jobs import _private_output, _read_private
from .strategy_windows import with_windows
from .v4_source_export import _atomic_private_output

SHA = r"^[a-f0-9]{64}$"
# Existing V4 proof functions verify complete chains. Never run them on large
# live journals until an independently anchored bounded verification exists.
MAX_OFFLINE_JOURNAL_BYTES = 64 * 1024 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class ReconciliationRequest(Strict):
    schema_version: Literal["track_b_evidence_reconcile_request_v1"] = Field(
        default="track_b_evidence_reconcile_request_v1", alias="schema"
    )
    mode: Literal["READ_ONLY_SHADOW"] = "READ_ONLY_SHADOW"
    packet_path: Path
    packet_sha256: str = Field(pattern=SHA)
    source_public_key_path: Path
    source_public_key_sha256: str = Field(pattern=SHA)
    original_source_journal: Path
    selected: dict[str, str] = Field(min_length=1, max_length=1)
    source_after: dict[str, int]
    scope: StrategyScope
    campaign: Campaign
    as_of: datetime
    created_at: datetime
    output_dir: Path
    registry_db: Path | None = None
    original_pm03_root: Path | None = None
    original_pm03_head_sha256: str | None = Field(default=None, pattern=SHA)
    original_audit_anchor_path: Path | None = None
    original_audit_anchor_sha256: str | None = Field(default=None, pattern=SHA)
    audit_public_key_path: Path | None = None
    audit_public_key_sha256: str | None = Field(default=None, pattern=SHA)

    @model_validator(mode="after")
    def validate_contract(self):
        if (
            self.as_of.utcoffset() != timedelta(0)
            or self.created_at.utcoffset() != timedelta(0)
            or self.created_at < self.as_of
        ):
            raise ValueError("EVIDENCE_RECONCILE_NONCAUSAL_CLOCK")
        for path in (
            self.packet_path,
            self.source_public_key_path,
            self.original_source_journal,
            self.output_dir,
            self.registry_db,
            self.original_pm03_root,
            self.original_audit_anchor_path,
            self.audit_public_key_path,
        ):
            if path is not None and (not path.is_absolute() or ".." in path.parts):
                raise ValueError("EVIDENCE_RECONCILE_ABSOLUTE_PATH_REQUIRED")
        if (self.original_pm03_root is None) != (self.original_pm03_head_sha256 is None):
            raise ValueError("EVIDENCE_RECONCILE_PM03_PATH_HEAD_PAIR_REQUIRED")
        pins = (
            self.original_audit_anchor_path,
            self.original_audit_anchor_sha256,
            self.audit_public_key_path,
            self.audit_public_key_sha256,
        )
        if any(value is None for value in pins) and any(value is not None for value in pins):
            raise ValueError("EVIDENCE_RECONCILE_ANCHOR_FOUR_PINS_REQUIRED")
        if (
            self.scope.tier != "SELECTED"
            or set(self.selected) != {self.scope.source_alias}
            or set(self.source_after) != set(self.selected)
        ):
            raise ValueError("EVIDENCE_RECONCILE_SELECTED_SCOPE_MISMATCH")
        if any(type(cursor) is not int or cursor < 0 for cursor in self.source_after.values()):
            raise ValueError("EVIDENCE_RECONCILE_CURSOR_INVALID")
        return self


class ReconciliationReceipt(Strict):
    schema_version: Literal["track_b_evidence_reconcile_receipt_v1"] = Field(
        default="track_b_evidence_reconcile_receipt_v1", alias="schema"
    )
    request_sha256: str = Field(pattern=SHA)
    evidence_availability: Literal["VERIFIED_SOURCE", "INCOMPLETE_SCOPE"]
    operational_execution: Literal["PUBLISHED", "EXISTING_VERIFIED"]
    economic_comparability: Literal["UNKNOWN"] = "UNKNOWN"
    scientific_qualification: Literal["NOT_QUALIFIED"] = "NOT_QUALIFIED"
    publication_status: Literal["PRIVATE_ONLY"] = "PRIVATE_ONLY"
    trading_authorized: Literal[False] = False
    private_report_sha256: str = Field(pattern=SHA)
    private_report_bytes_sha256: str = Field(pattern=SHA)
    private_proof_binding_sha256: str | None = Field(default=None, pattern=SHA)
    reasons: tuple[str, ...] = ()


def _check_offline_original(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("EVIDENCE_ORIGINAL_JOURNAL_UNAVAILABLE")
    total = path.stat().st_size
    wal = Path(str(path) + "-wal")
    if wal.exists():
        if wal.is_symlink() or not wal.is_file():
            raise ValueError("EVIDENCE_ORIGINAL_WAL_UNSAFE")
        total += wal.stat().st_size
    if total > MAX_OFFLINE_JOURNAL_BYTES:
        raise ValueError("EVIDENCE_ORIGINAL_TOO_LARGE_FOR_FULL_CHAIN_SCAN")


def _rebuild(report: StrategyAssessment, **changes) -> StrategyAssessment:
    return seal(
        StrategyAssessment.model_validate(
            {**report.model_dump(), **changes, "report_sha256": ZERO_SHA}
        )
    )


def reconcile(
    request: ReconciliationRequest,
    *,
    request_sha256: str,
    trusted_source_public_key_sha256: str,
    trusted_auditor_public_key_sha256: str | None = None,
) -> ReconciliationReceipt:
    """Reconcile one immutable request, with no source/registry/finance writes.

    This offline experiment cannot dispatch Prefect, sign a public release,
    mutate Guardian, or grant economic/scientific qualification.
    """
    if (
        len(trusted_source_public_key_sha256) != 64
        or any(c not in "0123456789abcdef" for c in trusted_source_public_key_sha256)
        or trusted_source_public_key_sha256 != request.source_public_key_sha256
    ):
        raise ValueError("EVIDENCE_INDEPENDENT_SOURCE_KEY_PIN_REQUIRED")
    _private_output(request.output_dir)
    anchored = request.original_audit_anchor_path is not None
    if anchored != (trusted_auditor_public_key_sha256 is not None):
        raise ValueError("EVIDENCE_RECONCILE_AUDITOR_TRUST_PIN_REQUIRED")
    verified_anchor = None
    if anchored:
        if trusted_auditor_public_key_sha256 != request.audit_public_key_sha256:
            raise ValueError("EVIDENCE_RECONCILE_AUDITOR_TRUST_PIN_MISMATCH")
        audit_public = Ed25519PublicKey.from_public_bytes(
            _read_private(request.audit_public_key_path, request.audit_public_key_sha256, limit=64)
        )
        verified_anchor = load_anchor(
            request.original_audit_anchor_path,
            request.original_audit_anchor_sha256,
            audit_public,
            expected_auditor_public_key_sha256=trusted_auditor_public_key_sha256,
        )
    else:
        _check_offline_original(request.original_source_journal)
    public = Ed25519PublicKey.from_public_bytes(
        _read_private(request.source_public_key_path, request.source_public_key_sha256, limit=64)
    )
    packet = json.loads(_read_private(request.packet_path, request.packet_sha256))
    report = assess_verified_packet(
        packet,
        public,
        source_journal=request.original_source_journal,
        selected=request.selected,
        source_after=request.source_after,
        scope=request.scope,
        campaign=request.campaign,
        as_of=request.as_of,
        created_at=request.created_at,
        registry_db=request.registry_db,
        verified_anchor=verified_anchor,
    )
    reasons: list[str] = []
    if verified_anchor is not None:
        reasons.append("SOURCE_ORIGINAL_FULL_AUDIT_ANCHORED_SUFFIX_VERIFIED")
    if request.registry_db is None:
        reasons.append("SELECTED_REGISTRY_SEAL_NOT_INDEPENDENTLY_VERIFIED")
    if request.original_pm03_root is None:
        reasons.append("ORIGINAL_PM03_FINANCE_NOT_SUPPLIED")
    else:
        original = inspect_pm03_original(
            request.original_pm03_root,
            as_of=request.as_of,
            expected_head=request.original_pm03_head_sha256,
        )
        report = reconcile_source_attempts(report, original)
        economic = summarize_pm03_economics(
            original, as_of=request.as_of, pod_alias=request.scope.source_alias
        )
        report = _rebuild(report, follower_economics=economic)
        reasons.append("FOLLOWER_MARKET_COST_FUNDING_COMPLETENESS_UNVERIFIED")

    report = with_windows(report, evidence=())
    report = with_recovery(report)
    canonical = canonical_report(report)
    output_sha = sha256(canonical).hexdigest()
    destination = request.output_dir / (output_sha + ".json")
    try:
        publish(report, destination)
        state = "PUBLISHED"
    except (FileExistsError, ValueError) as exc:
        if not destination.exists() or destination.is_symlink():
            raise
        existing = read(destination)
        if canonical_report(existing) != canonical:
            raise ValueError("EVIDENCE_RECONCILE_OUTPUT_COLLISION_OR_TAMPER") from exc
        state = "EXISTING_VERIFIED"
    binding_sha = None
    if verified_anchor is not None:
        # Preserve the original signed packet/independent audit/report lineage
        # as an immutable owner-private reference. No research or publisher
        # signatory is inferred from this content-addressed local sidecar.
        binding = {
            "schema": "track_b_original_evidence_binding_v1",
            "request_sha256": request_sha256,
            "source_packet_sha256": request.packet_sha256,
            "source_public_key_sha256": request.source_public_key_sha256,
            "original_audit_anchor_sha256": verified_anchor.seal_file_sha256,
            "auditor_public_key_sha256": verified_anchor.auditor_key_sha256,
            "private_report_sha256": report.report_sha256,
            "private_report_bytes_sha256": output_sha,
            "read_only": True,
            "scientifically_qualified": False,
            "trading_authorized": False,
        }
        raw = canonical_binding(binding)
        binding_sha = sha256(raw).hexdigest()
        proof_path = request.output_dir / (binding_sha + ".proof.json")
        try:
            _atomic_private_output(proof_path, raw)
        except ValueError as exc:
            if not proof_path.exists() or proof_path.is_symlink():
                raise
            existing = _read_private(proof_path, binding_sha, limit=4096)
            if existing != raw:
                raise ValueError("EVIDENCE_RECONCILE_PROOF_BINDING_TAMPER") from exc
    return ReconciliationReceipt(
        request_sha256=request_sha256,
        evidence_availability=(
            "VERIFIED_SOURCE" if request.registry_db is not None else "INCOMPLETE_SCOPE"
        ),
        operational_execution=state,
        private_report_sha256=report.report_sha256,
        private_report_bytes_sha256=output_sha,
        private_proof_binding_sha256=binding_sha,
        reasons=tuple(reasons),
    )


def reconcile_manifest(
    path: Path,
    expected_sha256: str,
    *,
    trusted_source_public_key_sha256: str,
    trusted_auditor_public_key_sha256: str | None = None,
) -> ReconciliationReceipt:
    """Request and source trust pin must be supplied independently."""
    raw = _read_private(path, expected_sha256)
    request = ReconciliationRequest.model_validate_json(raw, strict=True)
    return reconcile(
        request,
        request_sha256=sha256(raw).hexdigest(),
        trusted_source_public_key_sha256=trusted_source_public_key_sha256,
        trusted_auditor_public_key_sha256=trusted_auditor_public_key_sha256,
    )


def main(argv: list[str] | None = None) -> int:
    """Run one read-only offline reconciliation; stdout has no private identifiers."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--trusted-source-public-key-sha256", required=True)
    parser.add_argument("--trusted-auditor-public-key-sha256")
    args = parser.parse_args(argv)
    receipt = reconcile_manifest(
        args.manifest,
        args.manifest_sha256,
        trusted_source_public_key_sha256=args.trusted_source_public_key_sha256,
        trusted_auditor_public_key_sha256=args.trusted_auditor_public_key_sha256,
    )
    print(receipt.model_dump_json(by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
