"""Opt-in local Prefect 3 orchestration of one proof-bound Track B assessment.

No persistent scheduler, remote Prefect API, original journal writes, release
promotion, financial owner, or broker route. The independently signed source
and audit input authority remains with the original proof-bound reconciler.
"""

from __future__ import annotations

import argparse
import errno
import json
from pathlib import Path
import re

from .strategy_evidence_reconciler import ReconciliationRequest, reconcile_manifest
from .strategy_health_jobs import _read_private
from .strategy_health_prefect import _retry_transient_io

_SHA = re.compile(r"[0-9a-f]{64}")


def _check_pin(value: str, label: str) -> None:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(label)


def _preflight(
    path: Path,
    manifest_sha256: str,
    source_key_sha256: str,
    auditor_key_sha256: str,
) -> None:
    """Reject unanchored, untrusted and unsafe requests before Prefect starts."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("EVIDENCE_PREFECT_MANIFEST_ABSOLUTE_PATH_REQUIRED")
    _check_pin(manifest_sha256, "EVIDENCE_PREFECT_MANIFEST_PIN_INVALID")
    _check_pin(source_key_sha256, "EVIDENCE_PREFECT_SOURCE_KEY_PIN_INVALID")
    _check_pin(auditor_key_sha256, "EVIDENCE_PREFECT_AUDITOR_KEY_PIN_INVALID")
    data = _read_private(path, manifest_sha256)
    request = ReconciliationRequest.model_validate_json(data, strict=True)
    if (
        request.original_audit_anchor_path is None
        or request.source_public_key_sha256 != source_key_sha256
        or request.audit_public_key_sha256 != auditor_key_sha256
    ):
        raise ValueError("EVIDENCE_PREFECT_INDEPENDENT_AUDITED_SOURCE_REQUIRED")


def run_prefect_reconciliation(
    manifest_path: Path,
    manifest_sha256: str,
    *,
    trusted_source_public_key_sha256: str,
    trusted_auditor_public_key_sha256: str,
) -> dict:
    """Run one independently pinned, audited, read-only private assessment.

    The original immutable request is reread and checked for every retry.
    Only manifest SHA and sanitized SHAs/statuses enter Prefect task metadata.
    """
    _preflight(
        manifest_path,
        manifest_sha256,
        trusted_source_public_key_sha256,
        trusted_auditor_public_key_sha256,
    )
    try:
        from prefect import flow, task
        from prefect.settings import (
            PREFECT_API_KEY,
            PREFECT_API_URL,
            PREFECT_SERVER_ANALYTICS_ENABLED,
            temporary_settings,
        )
        from prefect.task_runners import ThreadPoolTaskRunner
    except ImportError as exc:
        raise RuntimeError(
            "EVIDENCE_PREFECT_EXTRA_REQUIRED: uv run --frozen --extra prefect"
        ) from exc

    if PREFECT_API_URL.value() is not None or PREFECT_API_KEY.value() is not None:
        raise ValueError("EVIDENCE_PREFECT_REMOTE_API_DISABLED")

    @task(
        name="track-b-proof-bound-private-assessment",
        retries=2,
        retry_delay_seconds=[1, 2],
        retry_condition_fn=_retry_transient_io,
        persist_result=False,
        log_prints=False,
    )
    def run_pinned(pinned_manifest_sha: str) -> dict:
        try:
            receipt = reconcile_manifest(
                manifest_path,
                pinned_manifest_sha,
                trusted_source_public_key_sha256=trusted_source_public_key_sha256,
                trusted_auditor_public_key_sha256=trusted_auditor_public_key_sha256,
            )
        except OSError as exc:
            if exc.errno in {errno.EBUSY, errno.EAGAIN, errno.ETIMEDOUT, errno.EINTR}:
                raise OSError(exc.errno, "EVIDENCE_PREFECT_TRANSIENT_PRIVATE_IO") from None
            raise ValueError("EVIDENCE_PREFECT_PRIVATE_INPUT_UNAVAILABLE") from None
        except Exception:
            # Prevent Pydantic field errors and original path details from
            # leaking into local Prefect metadata, logs or task failures.
            raise ValueError("EVIDENCE_PREFECT_PRIVATE_PROOF_REJECTED") from None
        # Only externally safe hash identities and nonpromoting status fields.
        return receipt.model_dump(by_alias=True, mode="json")

    @flow(
        name="track-b-proof-bound-offline-reconciliation",
        task_runner=ThreadPoolTaskRunner(max_workers=1),
        retries=0,
        persist_result=False,
        log_prints=False,
    )
    def offline_flow() -> dict:
        result = run_pinned.submit(manifest_sha256).result()
        return {
            "schema": "track_b_proof_bound_prefect_receipt_v1",
            "manifest_sha256": manifest_sha256,
            "job_count": 1,
            "status": "PRIVATE_PROOF_BOUND_ASSESSMENT_PUBLISHED",
            "assessment": result,
            "read_only": True,
            "source_finance_authenticated": False,
            "scientifically_qualified": False,
            "shadow_deployed": False,
            "trading_authorized": False,
        }

    with temporary_settings(updates={PREFECT_SERVER_ANALYTICS_ENABLED: False}):
        return offline_flow()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One offline audited Track B reconciliation with opt-in local Prefect 3."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--trusted-source-public-key-sha256", required=True)
    parser.add_argument("--trusted-auditor-public-key-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_prefect_reconciliation(
        args.manifest,
        args.sha256,
        trusted_source_public_key_sha256=args.trusted_source_public_key_sha256,
        trusted_auditor_public_key_sha256=args.trusted_auditor_public_key_sha256,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
