"""Opt-in, crash-replay-safe Track B private assessment jobs.

Prefect schedules these jobs; this module owns deterministic execution and
idempotent *research-only* publication. Original V4, PM03/04, SQLite, Guardian
and Grafana remain independent authorities. No source/network/broker writes.
"""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .strategy_advisory import assess_weekly, with_recovery
from .strategy_health import (
    StrategyAssessment,
    WeeklyLook,
    canonical_report,
    publish,
    read,
)
from .strategy_windows import OpportunityEvidence, with_windows

SHA = r"^[a-f0-9]{64}$"
MAX_FILE_BYTES = 2_000_000


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class HealthJob(Strict):
    report_path: Path
    report_sha256: str = Field(pattern=SHA)
    evidence_path: Path | None = None
    evidence_sha256: str | None = Field(default=None, pattern=SHA)
    weekly_look_path: Path | None = None
    weekly_look_sha256: str | None = Field(default=None, pattern=SHA)

    @model_validator(mode="after")
    def validate_scope(self):
        for item in (self.report_path, self.evidence_path, self.weekly_look_path):
            if item is not None and (not item.is_absolute() or ".." in item.parts):
                raise ValueError("TRACK_B_PRIVATE_INPUT_ABSOLUTE_PATH_REQUIRED")
        if (self.evidence_path is None) != (self.evidence_sha256 is None):
            raise ValueError("TRACK_B_EVIDENCE_FILE_SHA_PAIR_REQUIRED")
        if (self.weekly_look_path is None) != (self.weekly_look_sha256 is None):
            raise ValueError("TRACK_B_WEEKLY_LOOK_FILE_SHA_PAIR_REQUIRED")
        return self

    @property
    def identity_sha256(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()


class HealthManifest(Strict):
    schema_version: Literal["track_b_prefect_job_manifest_v1"] = Field(
        default="track_b_prefect_job_manifest_v1", alias="schema"
    )
    output_dir: Path
    jobs: tuple[HealthJob, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_manifest(self):
        if not self.output_dir.is_absolute() or ".." in self.output_dir.parts:
            raise ValueError("TRACK_B_OUTPUT_ABSOLUTE_PATH_REQUIRED")
        ids = [job.identity_sha256 for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("TRACK_B_DUPLICATE_JOB")
        return self


class HealthReceipt(Strict):
    schema_version: Literal["track_b_prefect_job_receipt_v1"] = Field(
        default="track_b_prefect_job_receipt_v1", alias="schema"
    )
    job_sha256: str = Field(pattern=SHA)
    report_sha256: str = Field(pattern=SHA)
    output_sha256: str = Field(pattern=SHA)
    publication: Literal["PUBLISHED", "EXISTING_VERIFIED"]
    read_only: Literal[True] = True
    trading_authorized: Literal[False] = False
    source_finance_authenticated: Literal[False] = False
    scientifically_qualified: Literal[False] = False


def _read_private(path: Path, expected_sha256: str, *, limit: int = MAX_FILE_BYTES) -> bytes:
    """No symlinks/FIFOs, no world-readable files or unbounded reads."""
    if path.is_symlink() or path.parent.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError("TRACK_B_PRIVATE_SYMLINK_FORBIDDEN")
    parent = path.parent.stat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or parent.st_mode & 0o777 != 0o700
    ):
        raise ValueError("TRACK_B_PRIVATE_INPUT_DIRECTORY_INVALID")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        if (
            not stat.S_ISREG(meta.st_mode)
            or meta.st_mode & 0o777 != 0o600
            or meta.st_uid != os.getuid()
            or not 0 < meta.st_size <= limit
        ):
            raise ValueError("TRACK_B_PRIVATE_FILE_INVALID")
        data = os.read(fd, limit + 1)
        if len(data) != meta.st_size:
            raise ValueError("TRACK_B_PRIVATE_FILE_TRUNCATED")
    finally:
        os.close(fd)
    if sha256(data).hexdigest() != expected_sha256:
        raise ValueError("TRACK_B_PINNED_INPUT_SHA_MISMATCH")
    return data


def read_manifest(path: Path, sha: str) -> HealthManifest:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("TRACK_B_MANIFEST_ABSOLUTE_PATH_REQUIRED")
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("TRACK_B_MANIFEST_SHA_INVALID")
    return HealthManifest.model_validate_json(_read_private(path, sha), strict=True)


def _private_output(directory: Path) -> None:
    if directory.is_symlink() or directory.resolve(strict=True) != directory:
        raise ValueError("TRACK_B_OUTPUT_SYMLINK_FORBIDDEN")
    # A private owner may prepare staging anywhere except the protected
    # source/portfolio/release trees. Never write into a running journal root.
    if directory.name != "track-b-prefect-staging" or set(directory.parts) & {
        "prospective",
        "registry",
        "releases",
        "copytrade-grafana",
    }:
        raise ValueError("TRACK_B_OUTPUT_STAGING_ONLY")
    meta = directory.stat()
    if (
        not stat.S_ISDIR(meta.st_mode)
        or meta.st_uid != os.getuid()
        or meta.st_mode & 0o777 != 0o700
    ):
        raise ValueError("TRACK_B_OUTPUT_DIRECTORY_NOT_PRIVATE")


def _optional_evidence(job: HealthJob) -> tuple[OpportunityEvidence, ...]:
    if job.evidence_path is None:
        return ()
    raw = _read_private(job.evidence_path, job.evidence_sha256)
    evidence = TypeAdapter(tuple[OpportunityEvidence, ...]).validate_json(raw, strict=True)
    if len(evidence) > 10000:
        raise ValueError("TRACK_B_EVIDENCE_COUNT_LIMIT")
    return evidence


def _optional_look(job: HealthJob) -> WeeklyLook | None:
    if job.weekly_look_path is None:
        return None
    raw = _read_private(job.weekly_look_path, job.weekly_look_sha256)
    return WeeklyLook.model_validate_json(raw, strict=True)


def _computed(report: StrategyAssessment, job: HealthJob) -> StrategyAssessment:
    # Rebuild windows against the supplied causal claims. This is NEVER an
    # independent authenticity attestation or source/finance promotion.
    evidence = _optional_evidence(job)
    look = _optional_look(job)
    if report.strategy.tier == "SELECTED":
        report = with_windows(report, evidence=evidence)
    elif evidence or look is not None:
        raise ValueError("TRACK_B_DISCOVERY_CANNOT_USE_PROSPECTIVE_INPUTS")
    if look is not None:
        report = assess_weekly(report, look)
    return with_recovery(report)


def run_private_job(job: HealthJob, output_dir: Path) -> HealthReceipt:
    """Safe to rerun after crash at any point: same content or fail closed.

    Private input is never a Prefect result or task parameter; only file
    references and SHA identities cross the orchestration interface.
    """
    _private_output(output_dir)
    raw = _read_private(job.report_path, job.report_sha256)
    report = read(job.report_path)
    if canonical_report(report) != raw:
        raise ValueError("TRACK_B_REPORT_CANONICAL_MISMATCH")
    result = _computed(report, job)
    canonical = canonical_report(result)
    output_sha = sha256(canonical).hexdigest()
    target = output_dir / (output_sha + ".json")

    try:
        publish(result, target)  # original no-clobber private 0600 writer
        status = "PUBLISHED"
    except (FileExistsError, ValueError) as exc:
        # Only the exact already-published hash is idempotently accepted.
        # FileExistsError can arise when two runners race to publish.
        if not target.exists():
            raise
        existing = read(target)
        if canonical_report(existing) != canonical:
            raise ValueError("TRACK_B_OUTPUT_COLLISION_OR_TAMPER") from exc
        status = "EXISTING_VERIFIED"

    return HealthReceipt(
        job_sha256=job.identity_sha256,
        report_sha256=result.report_sha256,
        output_sha256=output_sha,
        publication=status,
    )


def output_receipt_json(receipt: HealthReceipt) -> dict:
    # Strictly no source alias/address, input path, finance amount or k.
    return receipt.model_dump(mode="json", by_alias=True)


def run_without_prefect(manifest_path: Path, manifest_sha256: str) -> list[HealthReceipt]:
    """Deterministic parity oracle, not a default scheduler."""
    manifest = read_manifest(manifest_path, manifest_sha256)
    return [run_private_job(job, manifest.output_dir) for job in manifest.jobs]
