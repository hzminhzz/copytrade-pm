"""Reproducible PM-03 fixture benchmark and raw resource accounting."""

import json
import subprocess
import sys

import pytest

pytest.importorskip("polars")

from copytrade_pm.pm_offline_benchmark import SCHEMA, run_benchmark
from copytrade_pm.pm_offline_manifest import ManifestInvalid
from test_pm_offline_job import _fixture_job


def test_benchmark_same_input_cold_app_cache_warm_and_metadata(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    report = run_benchmark(
        job,
        input_root=root,
        source_root=None,
        market_root=root,
        cache_root=cache,
        workers=2,
        repeats=3,
    )
    assert report["schema"] == SCHEMA
    assert report["status"] == "VERIFIED_SAME_INPUT_BENCHMARK"
    assert report["repeats"] == 3
    assert report["wall_p50_seconds"] >= 0
    assert report["wall_p95_nearest_rank_seconds"] >= report["wall_p50_seconds"]
    assert report["cache_bytes_final"] > 0
    assert report["first_invocation_cache_status"] == "CACHE_CREATED"
    assert report["warm_application_cache_runs"] == 2
    assert report["warm_wall_p50_seconds"] >= 0
    assert report["warm_wall_p95_nearest_rank_seconds"] >= report["warm_wall_p50_seconds"]
    assert report["polars_scratch_high_water_bytes"] is None
    assert report["matched_input_counts"] == {
        "requested_scenarios": 15,
        "completed_scenarios": 15,
        "blocked_scenarios": 0,
    }
    assert report["samples"][0]["application_cache_status"] == "CACHE_CREATED"
    assert all(s["application_cache_status"] == "CACHE_HIT" for s in report["samples"][1:])
    assert len({s["report_sha256"] for s in report["samples"]}) == 1
    assert len(report["report_sha256"]) == 64
    assert report["financial_certified_real"] is False
    assert report["scientifically_qualified"] is False


def test_benchmark_bounded_workers_and_repetitions(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    for key, value in (("repeats", 1), ("repeats", 41), ("workers", 0), ("workers", 8)):
        options = {"repeats": 2, "workers": 1}
        options[key] = value
        with pytest.raises(ManifestInvalid):
            run_benchmark(
                job,
                input_root=root,
                market_root=root,
                cache_root=cache,
                source_root=None,
                **options,
            )


def test_benchmark_separate_process_cli_has_stable_result(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    cmd = [
        sys.executable,
        "-m",
        "copytrade_pm.pm_offline_benchmark",
        str(job),
        "--input-root",
        str(root),
        "--market-root",
        str(root),
        "--cache-root",
        str(cache),
        "--repeats",
        "2",
    ]
    first = json.loads(
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=45).stdout
    )
    second = json.loads(
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=45).stdout
    )
    assert first["status"] == "VERIFIED_SAME_INPUT_BENCHMARK"
    assert second["status"] == first["status"]
    assert second["report_sha256"] == first["report_sha256"]
    assert all(x["application_cache_status"] == "CACHE_HIT" for x in second["samples"])
