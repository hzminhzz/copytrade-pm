"""Reproducible, source-read-only benchmark for a sealed offline research job.

The benchmark compares repeated executions of the SAME job and SAME input
lineage. "Cold" refers ONLY to an unpopulated application cache, not a cold
OS page cache. Source days are never modified or acquired. Historical
oracle output is screening-only; no finance/alpha assertion is possible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import resource
from statistics import median
from time import perf_counter

from .pm_offline_job import run_offline_job
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid

SCHEMA = "pm_offline_benchmark_report_v1"


def _proc_io() -> dict[str, int] | None:
    """Linux /proc counters: read_bytes is actual process I/O, not file bytes."""
    try:
        recorded = {}
        for line in Path("/proc/self/io").read_text().splitlines():
            key, raw = line.split(":", 1)
            if key in {"rchar", "read_bytes", "wchar", "write_bytes", "syscr", "syscw"}:
                recorded[key] = int(raw.strip())
        return recorded if len(recorded) == 6 else None
    except OSError, ValueError:
        return None


def _disk_bytes(path: Path) -> int:
    """Owner-private benchmark cache only, no authoritative lake traversal."""
    if not path.exists():
        return 0
    if path.is_symlink() or not path.is_dir():
        raise ManifestInvalid("INVALID_BENCHMARK_CACHE_ROOT")
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def _nearest_rank_95(values: list[float]) -> float:
    return sorted(values)[(95 * len(values) + 99) // 100 - 1]


def run_benchmark(
    job: Path,
    *,
    input_root: Path,
    market_root: Path,
    source_root: Path | None,
    cache_root: Path,
    repeats: int = 5,
    workers: int = 1,
) -> dict:
    if type(repeats) is not int or not 2 <= repeats <= 40:
        raise ManifestInvalid("INVALID_BENCHMARK_REPETITIONS")
    if type(workers) is not int or not 1 <= workers <= 2:
        raise ManifestInvalid("INVALID_BENCHMARK_WORKERS")
    samples = []
    fingerprints = set()
    for index in range(repeats):
        user_before = resource.getrusage(resource.RUSAGE_SELF)
        io_before = _proc_io()
        cache_before = _disk_bytes(cache_root)
        begin = perf_counter()
        result = run_offline_job(
            job,
            input_root=input_root,
            market_root=market_root,
            source_root=source_root,
            cache_root=cache_root,
            workers=workers,
        )
        wall = perf_counter() - begin
        user_after = resource.getrusage(resource.RUSAGE_SELF)
        io_after = _proc_io()
        cache_after = _disk_bytes(cache_root)
        digest = result["report_sha256"]
        fingerprints.add(digest)
        if not result["status"].startswith(("COMPLETE_", "PARTIAL_")):
            raise ManifestBlocked("BENCHMARK_NONTERMINAL_JOB")
        if result["financial_certified_real"] or result["scientifically_qualified"]:
            raise ManifestBlocked("UNEXPECTED_FINANCIAL_OR_SCIENCE_PROMOTION")
        samples.append(
            {
                "run": index,
                "application_cache_status": result["report_cache_status"],
                "wall_seconds": round(wall, 6),
                "cpu_user_seconds": round(user_after.ru_utime - user_before.ru_utime, 6),
                "cpu_system_seconds": round(user_after.ru_stime - user_before.ru_stime, 6),
                "minor_faults": user_after.ru_minflt - user_before.ru_minflt,
                "major_faults": user_after.ru_majflt - user_before.ru_majflt,
                "peak_process_rss_kib_high_water": user_after.ru_maxrss,
                "cache_bytes_before": cache_before,
                "cache_bytes_after": cache_after,
                "process_io_counters_delta": (
                    {field: io_after[field] - io_before[field] for field in io_before}
                    if io_before is not None and io_after is not None
                    else None
                ),
                "report_sha256": digest,
            }
        )
    if len(fingerprints) != 1:
        raise ManifestBlocked("BENCHMARK_SAME_INPUT_RESULT_DRIFT")
    times = [row["wall_seconds"] for row in samples]
    cpu = [row["cpu_user_seconds"] + row["cpu_system_seconds"] for row in samples]
    warm = [row for row in samples if row["application_cache_status"] == "CACHE_HIT"]
    warm_wall = [row["wall_seconds"] for row in warm]
    warm_cpu = [row["cpu_user_seconds"] + row["cpu_system_seconds"] for row in warm]
    sample = {
        "schema": SCHEMA,
        "status": "VERIFIED_SAME_INPUT_BENCHMARK",
        "job_path": Path(job).name,
        "job_kind": result["job_kind"],
        "clock_basis": result["clock_basis"],
        "job_sha256": result["job_sha256"],
        "report_sha256": samples[0]["report_sha256"],
        "repeats": repeats,
        "workers": workers,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "wall_p50_seconds": round(median(times), 6),
        "wall_p95_nearest_rank_seconds": round(_nearest_rank_95(times), 6),
        "cpu_p50_seconds": round(median(cpu), 6),
        "cpu_p95_nearest_rank_seconds": round(_nearest_rank_95(cpu), 6),
        "peak_process_rss_kib_high_water": max(
            row["peak_process_rss_kib_high_water"] for row in samples
        ),
        "cache_bytes_final": samples[-1]["cache_bytes_after"],
        "first_invocation_wall_seconds": samples[0]["wall_seconds"],
        "first_invocation_cache_status": samples[0]["application_cache_status"],
        "warm_application_cache_runs": len(warm),
        "warm_wall_p50_seconds": round(median(warm_wall), 6) if warm_wall else None,
        "warm_wall_p95_nearest_rank_seconds": (
            round(_nearest_rank_95(warm_wall), 6) if warm_wall else None
        ),
        "warm_cpu_p50_seconds": round(median(warm_cpu), 6) if warm_cpu else None,
        "warm_cpu_p95_nearest_rank_seconds": (
            round(_nearest_rank_95(warm_cpu), 6) if warm_cpu else None
        ),
        "polars_scratch_high_water_bytes": None,
        "real_pm03_comparable_baseline_status": (
            "BLOCKED_REAL_WORKLOAD"
            if result["job_kind"] == "HISTORICAL_ORACLE_NATIVE"
            else "DIFFERENT_PM01_POLICY_SYNTHETIC_FIXTURE"
        ),
        "samples": samples,
        "matched_input_counts": {
            key: result["evidence"][key]
            for key in (
                "valid_source_fills",
                "candidate_batches",
                "matched_batches",
                "requested_scenarios",
                "completed_scenarios",
                "blocked_scenarios",
            )
            if key in result["evidence"]
        },
        "cache_and_spill_precision": (
            "Application cache size recorded; OS page cache was not purged. "
            "Neither Polars scratch high-water nor physical cold-disk I/O "
            "can be inferred from process counters alone."
        ),
        "scientifically_qualified": False,
        "financial_certified_real": False,
        "broker_authorized": False,
    }
    # Process wall and CPU measurements are deliberately excluded from stable
    # upstream report SHA. This envelope itself is not a sealed trading result.
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    try:
        out = run_benchmark(
            args.job,
            input_root=args.input_root,
            source_root=args.source_root,
            market_root=args.market_root,
            cache_root=args.cache_root,
            repeats=args.repeats,
            workers=args.workers,
        )
    except (ManifestBlocked, ManifestInvalid) as exc:
        out = {"schema": SCHEMA, "status": exc.status, "reason": exc.code}
    print(json.dumps(out, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
