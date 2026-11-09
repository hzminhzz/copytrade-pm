"""Public versioned, read-only offline research job facade.

One job manifest -> a reproducible SHA-sealed report. The two permitted
routes are (a) a complete synthetic PM-03 financial fixture, or (b) an
unqualified real historical-oracle timing and native 1m screening path.
There is deliberately no route from historical vendor fill timestamps to
prospective first-known receipts or a real financial PASS/BREACH.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from .pm_offline_cache import ImmutableCache
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid, _safe_file
from .pm_offline_oracle import compile_real_historical_oracle
from .pm_offline_oracle_market import match_real_oracle_native
from .pm_offline_sweep import run_synthetic_fixture_study

SCHEMA = "pm_offline_research_job_v1"
REPORT = "pm_offline_research_job_report_v1"
KINDS = frozenset({"SEALED_SYNTHETIC_PM03", "HISTORICAL_ORACLE_NATIVE"})
SHA = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
DELAYS = [0, 1, 2, 5, 10]


def _encode(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _inspect(job: object) -> dict:
    if not isinstance(job, dict):
        raise ManifestInvalid("INVALID_RESEARCH_JOB")
    common = {"schema", "study_id", "kind", "clock_basis", "delays_minutes"}
    if not common <= set(job) or job["schema"] != SCHEMA:
        raise ManifestInvalid("INVALID_RESEARCH_JOB_SCHEMA")
    if not isinstance(job["study_id"], str) or not ID.fullmatch(job["study_id"]):
        raise ManifestInvalid("INVALID_RESEARCH_JOB_ID")
    if job["delays_minutes"] != DELAYS:
        raise ManifestInvalid("RESEARCH_JOB_REQUIRES_FIVE_FROZEN_DELAYS")
    if job["kind"] == "SEALED_SYNTHETIC_PM03":
        required = common | {"study_manifest_path", "study_manifest_sha256"}
        if set(job) != required or job["clock_basis"] not in {
            "HISTORICAL_ORACLE",
            "PROSPECTIVE_FIRST_KNOWN",
        }:
            raise ManifestInvalid("INVALID_SYNTHETIC_JOB_SCHEMA")
        if not isinstance(job["study_manifest_sha256"], str) or not SHA.fullmatch(
            job["study_manifest_sha256"]
        ):
            raise ManifestInvalid("INVALID_SEALED_STUDY_SHA")
    elif job["kind"] == "HISTORICAL_ORACLE_NATIVE":
        required = common | {"start", "end", "source_collection_sha256"}
        if set(job) != required or job["clock_basis"] != "HISTORICAL_ORACLE":
            raise ManifestInvalid("INVALID_ORACLE_JOB_CLOCK_OR_SCHEMA")
        if not isinstance(job["source_collection_sha256"], str) or not SHA.fullmatch(
            job["source_collection_sha256"]
        ):
            raise ManifestInvalid("INVALID_REAL_SOURCE_COLLECTION_SHA")
    else:
        raise ManifestInvalid("UNKNOWN_RESEARCH_JOB_KIND")
    return job


def run_offline_job(
    job_path: Path,
    *,
    input_root: Path,
    market_root: Path,
    cache_root: Path,
    source_root: Path | None = None,
    workers: int = 1,
) -> dict:
    """Run read-only study and seal a canonical versioned report.

    The top-level report contains NO financial outcome for a real oracle job.
    Environment times/cache hits are deliberately omitted from report SHA;
    immutable upstream results and their source/market fingerprints remain
    part of the content-addressed lineage.
    """
    root = Path(input_root).resolve(strict=True)
    requested = Path(job_path)
    if requested.is_symlink():
        raise ManifestInvalid("UNSAFE_RESEARCH_JOB_PATH")
    jobfile = requested.resolve(strict=True)
    if root not in jobfile.parents or any(
        parent.is_symlink()
        for parent in (requested, *requested.parents)
        if parent == root or root in parent.parents
    ):
        raise ManifestInvalid("UNSAFE_RESEARCH_JOB_PATH")
    if type(workers) is not int or not 1 <= workers <= 2:
        raise ManifestInvalid("INVALID_BOUNDED_WORKER_COUNT")
    if jobfile.stat().st_size > 1024 * 1024:
        raise ManifestInvalid("OVERSIZED_RESEARCH_JOB")
    try:
        raw_job = json.loads(jobfile.read_bytes())
        if isinstance(raw_job, dict) and raw_job.get("schema") == "pm_v4_wallet_screen_job_v2":
            from .pm_v4_fast_screen import _job as inspect_v4, run_from_manifest

            return run_from_manifest(
                inspect_v4(raw_job),
                input_root=root,
                source_root=source_root,
                market_root=market_root,
                cache_root=cache_root,
                workers=workers,
            )
        job = _inspect(raw_job)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, (ManifestBlocked, ManifestInvalid)):
            raise
        raise ManifestInvalid("MALFORMED_RESEARCH_JOB_JSON") from exc
    digest = sha256(_encode(job)).hexdigest()
    if job["kind"] == "SEALED_SYNTHETIC_PM03":
        path = _safe_file(root, job["study_manifest_path"])
        if sha256(path.read_bytes()).hexdigest() != job["study_manifest_sha256"]:
            raise ManifestBlocked("SEALED_STUDY_MANIFEST_SHA_MISMATCH")
        result = run_synthetic_fixture_study(
            path,
            input_root=root,
            market_root=market_root,
            cache_root=cache_root,
            workers=workers,
        )
        # Do not silently select a nonfrozen policy/mode from an input bundle.
        manifest = json.loads(path.read_bytes())
        if (
            manifest["clock_basis"] != job["clock_basis"]
            or sorted(manifest["delays_minutes"]) != DELAYS
        ):
            raise ManifestInvalid("NESTED_STUDY_CLOCK_OR_DELAY_MISMATCH")
        market_lineage = sha256(_encode(result["market_day_shas"])).hexdigest()
        sealed_inputs = job["study_manifest_sha256"]
        sealed_market = market_lineage
        software_identity = result["software_sha256"]
        evidence = {
            "input_manifest_sha256": job["study_manifest_sha256"],
            "market_day_lineage_sha256": market_lineage,
            "replay_logical_sha256": result["logical_sha256"],
            "source_tape_sha256": result["source_tape_sha256"],
            "software_sha256": result["software_sha256"],
            "scenario_results": result["scenarios"],
            "completed_scenarios": result["completed_scenarios"],
            "blocked_scenarios": result["blocked_scenarios"],
            "requested_scenarios": result["requested_scenarios"],
        }
        status = (
            "COMPLETE_ENGINEERING_FIXTURE"
            if not result["blocked_scenarios"]
            else "PARTIAL_ENGINEERING_FIXTURE_BLOCKED"
        )
        financial = "SYNTHETIC_PM03_FIXTURE_ONLY"
        engineering = not result["blocked_scenarios"]
        blockers = sorted(
            {row["reason"] for row in result["scenarios"] if row["status"] == "BLOCKED"}
        )
    else:
        if source_root is None:
            raise ManifestInvalid("MISSING_REAL_SOURCE_ROOT")
        historical = compile_real_historical_oracle(
            source_root, cache_root, start=job["start"], end=job["end"]
        )
        if historical["source_collection_sha256"] != job["source_collection_sha256"]:
            raise ManifestBlocked("REAL_SOURCE_COLLECTION_SHA_MISMATCH")
        native = match_real_oracle_native(
            source_root=source_root,
            market_root=market_root,
            cache_root=cache_root,
            start=job["start"],
            end=job["end"],
        )
        if historical["batch_parquet_sha256"] != native["batch_parquet_sha256"]:
            raise ManifestBlocked("REAL_ORACLE_SOURCE_AND_NATIVE_TAPE_CONFLICT")
        sealed_inputs = historical["source_collection_sha256"]
        sealed_market = native["market_fingerprint_sha256"]
        software_identity = sha256(
            b"".join(
                (Path(__file__).resolve().parent / path).read_bytes()
                for path in (
                    "pm_offline_job.py",
                    "pm_offline_oracle.py",
                    "pm_offline_oracle_market.py",
                    "pm_offline_repository.py",
                )
            )
        ).hexdigest()
        evidence = {
            "source_collection_sha256": historical["source_collection_sha256"],
            "eligible_tape_sha256": historical["batch_parquet_sha256"],
            "native_context_sha256": native["context_tape_sha256"],
            "native_market_lineage_sha256": native["market_fingerprint_sha256"],
            "valid_source_fills": historical["input_fills_in_window"],
            "candidate_batches": native["candidate_batches"],
            "matched_batches": native["matched_batches"],
            "matched_coverage_complete": native["matched_batches"] == native["candidate_batches"],
            "native_status_counts": native["status_counts_by_delay"],
        }
        status = "COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY"
        financial = "BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN"
        engineering = True
        blockers = [
            "NO_INDEPENDENT_FIRST_KNOWN",
            "NO_HISTORICAL_SOURCE_EQUITY_SERIES",
            "NO_VERIFIED_ATOMIC_WHOLE_ACCOUNT_OPENING_BOOK",
        ]
        if native["matched_batches"] != native["candidate_batches"]:
            blockers.append("NATIVE_ONE_MINUTE_MARKET_COVERAGE_INCOMPLETE")
    report = {
        "schema": REPORT,
        "job_id": job["study_id"],
        "job_sha256": digest,
        "job_kind": job["kind"],
        "status": status,
        "clock_basis": job["clock_basis"],
        "policy": "PER_FILL_ELIGIBILITY",
        "delays_minutes": DELAYS,
        "engineering_path_verified": engineering,
        "financial_status": financial,
        "financial_certified_real": False,
        "scientifically_qualified": False,
        "authorized_for_trading": False,
        "deployed": False,
        "blockers": blockers,
        "evidence": evidence,
    }
    output = _encode(report)
    published = ImmutableCache(
        cache_root, max_object_bytes=16 * 1024 * 1024, min_free_bytes=1024 * 1024 * 1024
    ).publish(
        "job_report",
        {
            "job": digest,
            "input": sealed_inputs,
            "market": sealed_market,
            "software": software_identity,
        },
        version=REPORT,
        content=output,
    )
    return {
        **report,
        "report_sha256": sha256(output).hexdigest(),
        "report_cache_key": published["key"],
        "report_cache_status": published["status"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    try:
        report = run_offline_job(
            args.job,
            input_root=args.input_root,
            source_root=args.source_root,
            market_root=args.market_root,
            cache_root=args.cache_root,
            workers=args.workers,
        )
    except (ManifestInvalid, ManifestBlocked) as exc:
        report = {
            "schema": REPORT,
            "status": exc.status,
            "reason": exc.code,
            "financial_certified_real": False,
            "scientifically_qualified": False,
            "authorized_for_trading": False,
            "deployed": False,
        }
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
