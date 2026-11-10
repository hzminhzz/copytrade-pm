"""Optional Prefect 3 adapter for existing deterministic Track B private jobs.

Nothing in official source capture, PM03/04 finance, k release, Guardian or
Grafana imports Prefect. Tasks never contain private report contents as
parameters/results, and the flow never supplies trading authority.
"""

from __future__ import annotations

import argparse
import errno
import json
from pathlib import Path

from .strategy_health_jobs import output_receipt_json, read_manifest, run_private_job


def _retry_transient_io(task, task_run, state) -> bool:
    # Prefect manages retries; all research publication is content-addressed
    # and idempotent. Validation, hash mismatch and malformed evidence MUST
    # fail immediately instead of becoming an unbounded retry loop.
    error = state.result(raise_on_failure=False)
    return isinstance(error, OSError) and error.errno in {
        errno.EBUSY,
        errno.EAGAIN,
        errno.ETIMEDOUT,
        errno.EINTR,
    }


def run_prefect(manifest_path: Path, manifest_sha256: str) -> dict:
    """Run bounded, local-only Prefect tasks; opt-in, no persistent service."""
    # Fail closed on a configured remote Prefect API, including profiles.
    # No wallet aliases/data or private file contents may reach Prefect Cloud.
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
        raise RuntimeError("TRACK_B_PREFECT_EXTRA_REQUIRED: uv run --extra prefect") from exc

    if PREFECT_API_URL.value() is not None or PREFECT_API_KEY.value() is not None:
        raise ValueError("TRACK_B_REMOTE_PREFECT_API_DISABLED")

    # Do not resolve away a symlink before the private file guard sees it.
    manifest = read_manifest(manifest_path, manifest_sha256)

    @task(
        name="track-b-private-immutable-assessment",
        retries=2,
        retry_delay_seconds=[1, 2],
        retry_condition_fn=_retry_transient_io,
        persist_result=False,
        log_prints=False,
    )
    def work(index: int, pinned_sha256: str) -> dict:
        # Important: arguments and results contain no source/wallet private
        # data. Always re-read and verify *original* pinned input bytes.
        try:
            current = read_manifest(manifest_path, pinned_sha256)
            report = run_private_job(current.jobs[index], current.output_dir)
        except OSError as exc:
            if exc.errno in {errno.EBUSY, errno.EAGAIN, errno.ETIMEDOUT, errno.EINTR}:
                # Remove absolute private paths from Prefect's error metadata.
                raise OSError(exc.errno, "TRACK_B_TRANSIENT_PRIVATE_IO") from None
            raise ValueError("TRACK_B_PRIVATE_INPUT_UNAVAILABLE") from None
        except Exception:
            # Pydantic field errors can echo private wallet data. Log only
            # the error class across the orchestration seam; local operators
            # can reproduce the detailed failure using the pure job runner.
            raise ValueError("TRACK_B_PRIVATE_EVIDENCE_REJECTED") from None
        return output_receipt_json(report)

    @flow(
        name="track-b-private-health-research",
        task_runner=ThreadPoolTaskRunner(max_workers=2),
        retries=0,
        persist_result=False,
        log_prints=False,
    )
    def private_flow() -> dict:
        futures = [work.submit(i, manifest_sha256) for i in range(len(manifest.jobs))]
        reports = [item.result() for item in futures]
        return {
            "schema": "track_b_prefect_flow_receipt_v1",
            "status": "PRIVATE_RESEARCH_PUBLISHED",
            "manifest_sha256": manifest_sha256,
            "job_count": len(reports),
            "reports": reports,
            "read_only": True,
            "trading_authorized": False,
            "scientifically_qualified": False,
            "shadow_deployed": False,
        }

    # Private research stays on the host; disable Prefect server analytics
    # even for its temporary loopback API started for this local invocation.
    with temporary_settings(updates={PREFECT_SERVER_ANALYTICS_ENABLED: False}):
        return private_flow()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run pinned private Track B research jobs via optional local Prefect 3."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="SHA256 of original 0600 private manifest")
    args = parser.parse_args(argv)
    result = run_prefect(args.manifest, args.sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
