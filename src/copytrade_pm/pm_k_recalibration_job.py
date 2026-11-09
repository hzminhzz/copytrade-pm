"""Offline manifest-to-immutable-report adapter for Track C.

No service installation, portfolio registry mutation, broker or journal writes.
Caller-supplied finance windows are *research assertions*, not authenticated
prospective fills. Only independently verified source reports may qualify later.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from .pm_k_recalibration import KResearchInput, evaluate_k
from .pm_offline_cache import ImmutableCache

SCHEMA = "track_c_k_research_job_v1"
REPORT = "track_c_k_research_report_v1"


def _read_input(path: Path, root: Path) -> bytes:
    root = root.resolve(strict=True)
    path = Path(path)
    if path.is_symlink() or path.resolve(strict=True).parent != root:
        raise ValueError("TRACK_C_INPUT_OUTSIDE_PINNED_ROOT")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2 * 1024 * 1024:
            raise ValueError("TRACK_C_INVALID_INPUT_FILE")
        content = f.read(2 * 1024 * 1024 + 1)
    if len(content) != info.st_size:
        raise ValueError("TRACK_C_INPUT_FILE_CHANGED")
    return content


def run_k_job(manifest_path: Path, *, input_root: Path, cache_root: Path) -> dict:
    """Explicit versioned research adapter; no actual k release ever activated."""
    raw = _read_input(manifest_path, input_root)
    job = json.loads(raw)
    required = {"schema", "study_id", "research_input", "research_input_sha256"}
    optional = {"screen_report_path", "screen_report_sha256"}
    if (
        not isinstance(job, dict)
        or not required <= set(job)
        or not set(job) <= required | optional
        or job["schema"] != SCHEMA
    ):
        raise ValueError("TRACK_C_JOB_SCHEMA_INVALID")
    if ("screen_report_path" in job) != ("screen_report_sha256" in job):
        raise ValueError("TRACK_C_JOB_SCHEMA_INVALID")
    if not isinstance(job["study_id"], str) or not (
        1 <= len(job["study_id"]) <= 96 and all(c.isalnum() or c in "-_." for c in job["study_id"])
    ):
        raise ValueError("TRACK_C_STUDY_ID_INVALID")
    data = _read_input(Path(input_root) / job["research_input"], input_root)
    if sha256(data).hexdigest() != job["research_input_sha256"]:
        raise ValueError("TRACK_C_RESEARCH_INPUT_HASH_MISMATCH")
    evidence = KResearchInput.model_validate_json(data)
    screen_handoff = None
    if "screen_report_path" in job:
        from .pm_v4_fast_screen import shortlist_for_pm03

        screen_raw = _read_input(Path(input_root) / job["screen_report_path"], input_root)
        if sha256(screen_raw).hexdigest() != job["screen_report_sha256"]:
            raise ValueError("TRACK_C_SCREEN_REPORT_HASH_MISMATCH")
        screen_report = json.loads(screen_raw)
        # Reports returned from #255 include volatile runtime fields; the
        # established handoff validates its canonical immutable core.
        if evidence.screen_report_sha256 != screen_report.get("report_sha256"):
            raise ValueError("TRACK_C_SCREEN_REPORT_IDENTITY_MISMATCH")
        screen_handoff = shortlist_for_pm03(screen_report, [evidence.selected_account_sha256])
    elif evidence.screen_report_sha256 is not None:
        raise ValueError("TRACK_C_SCREEN_REPORT_NOT_SUPPLIED")
    proposal = evaluate_k(evidence)
    # Imported finance assertions are not an independently authenticated PM03
    # report. A raw-JSON report cannot itself prove prospective economic results.
    report = {
        "schema": REPORT,
        "study_id": job["study_id"],
        "proposal": proposal.model_dump(mode="json", by_alias=True),
        "screen_handoff": screen_handoff,
        "input_sha256": sha256(data).hexdigest(),
        "manifest_sha256": sha256(raw).hexdigest(),
        "finance_report_authenticity_independently_verified": False,
        "economic_qualification": "NOT_QUALIFIED_IMPORTED_FINANCE_ASSERTIONS",
        "scientifically_qualified": False,
        "trading_authorized": False,
        "shadow_deployed": False,
        "order_route": "NONE",
    }
    # An economic recommendation from an input-only adapter is provisional.
    # Fail closed at release selection until original PM03/PM04 reports validated.
    if proposal.decision == "INCREASE":
        report["release_eligible"] = False
        report["verification_blockers"] = ["INDEPENDENT_FINANCE_REPORT_ATTESTATION_MISSING"]
    else:
        report["release_eligible"] = False
        report["verification_blockers"] = ["SEPARATE_RELEASE_AUTHORIZATION_REQUIRED"]
    content = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    published = ImmutableCache(
        cache_root, max_object_bytes=4 * 1024 * 1024, min_free_bytes=1024 * 1024
    ).publish(
        "track_c_k_report",
        {"job": sha256(raw).hexdigest(), "input": sha256(data).hexdigest()},
        version=REPORT,
        content=content,
    )
    return {
        **report,
        "report_sha256": sha256(content).hexdigest(),
        "cache_key": published["key"],
        "cache_status": published["status"],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Read-only Track C k research report")
    p.add_argument("job", type=Path)
    p.add_argument("--input-root", type=Path, required=True)
    p.add_argument("--cache-root", type=Path, required=True)
    args = p.parse_args()
    print(
        json.dumps(
            run_k_job(args.job, input_root=args.input_root, cache_root=args.cache_root),
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
