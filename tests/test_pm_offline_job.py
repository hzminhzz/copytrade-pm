"""Public offline job: one manifest, sealed report, no real finance promotion."""

from hashlib import sha256
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("polars")

from copytrade_pm.pm_offline_job import REPORT, SCHEMA, run_offline_job
from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid
from copytrade_pm.pm_offline_oracle import _source_digest
from test_pm_offline_oracle_market import _native_fixture
from test_pm_offline_sweep_pipeline import sample


FIVE_DELAYS = [0, 1, 2, 5, 10]
START = "2026-10-20T00:00:00+00:00"
END = "2026-10-21T00:00:00+00:00"


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True))
    return path


def _fixture_job(tmp_path):
    path, root, cache, payload = sample(tmp_path)
    bundle = root / "study.json"
    bundle.write_bytes(path.read_bytes())
    job = _write(
        root / "job.json",
        {
            "schema": SCHEMA,
            "study_id": "fixture-5w-3cost",
            "kind": "SEALED_SYNTHETIC_PM03",
            "clock_basis": "HISTORICAL_ORACLE",
            "delays_minutes": FIVE_DELAYS,
            "study_manifest_path": "study.json",
            "study_manifest_sha256": sha256(bundle.read_bytes()).hexdigest(),
        },
    )
    return job, root, cache


def _oracle_job(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    job = _write(
        tmp_path / "job.json",
        {
            "schema": SCHEMA,
            "study_id": "recovered-local-1day",
            "kind": "HISTORICAL_ORACLE_NATIVE",
            "clock_basis": "HISTORICAL_ORACLE",
            "delays_minutes": FIVE_DELAYS,
            "start": START,
            "end": END,
            "source_collection_sha256": _source_digest(source),
        },
    )
    return job, source, market


def test_one_manifest_to_completed_pm03_fixture_report_is_restart_stable(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    first = run_offline_job(job, input_root=root, market_root=root, cache_root=cache, workers=1)
    second = run_offline_job(job, input_root=root, market_root=root, cache_root=cache, workers=2)
    assert first["schema"] == REPORT
    assert first["status"] == "COMPLETE_ENGINEERING_FIXTURE"
    assert first["evidence"]["requested_scenarios"] == 15
    assert first["evidence"]["completed_scenarios"] == 15
    assert first["report_sha256"] == second["report_sha256"]
    assert second["report_cache_status"] == "CACHE_HIT"
    assert first["financial_status"] == "SYNTHETIC_PM03_FIXTURE_ONLY"
    assert not first["financial_certified_real"]
    assert not first["scientifically_qualified"]
    assert not first["authorized_for_trading"]


def test_historical_oracle_complete_screening_remains_financial_blocker(tmp_path):
    job, source, market = _oracle_job(tmp_path)
    cache = tmp_path / "private-cache"
    result = run_offline_job(
        job,
        input_root=tmp_path,
        source_root=source,
        market_root=market,
        cache_root=cache,
    )
    warm = run_offline_job(
        job,
        input_root=tmp_path,
        source_root=source,
        market_root=market,
        cache_root=cache,
    )
    assert result["engineering_path_verified"] is True
    assert result["status"] == "COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY"
    assert result["financial_status"].startswith("BLOCKED_")
    assert result["evidence"]["matched_batches"] == 15
    assert result["report_sha256"] == warm["report_sha256"]
    assert warm["report_cache_status"] == "CACHE_HIT"
    assert result["financial_certified_real"] is False


def test_separate_process_manifest_cli_replay_hash_parity(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    command = [
        sys.executable,
        "-m",
        "copytrade_pm.pm_offline_job",
        str(job),
        "--input-root",
        str(root),
        "--market-root",
        str(root),
        "--cache-root",
        str(cache),
        "--workers",
        "2",
    ]
    runs = []
    for _ in range(2):
        proc = subprocess.run(command, capture_output=True, text=True, check=True, timeout=40)
        runs.append(json.loads(proc.stdout))
    assert runs[0]["report_sha256"] == runs[1]["report_sha256"]
    assert runs[0]["status"] == "COMPLETE_ENGINEERING_FIXTURE"
    assert runs[1]["report_cache_status"] == "CACHE_HIT"


def test_symlink_job_inside_input_root_is_rejected(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    alias = root / "alias-job.json"
    alias.symlink_to(job)
    with pytest.raises(ManifestInvalid, match="UNSAFE_RESEARCH_JOB_PATH"):
        run_offline_job(alias, input_root=root, market_root=root, cache_root=cache)


def test_real_source_sha_change_fails_closed(tmp_path):
    job, source, market = _oracle_job(tmp_path)
    source_file = source / "wallet_fills_90d" / "one.json"
    source_file.write_text(source_file.read_text() + " ")
    with pytest.raises(ManifestBlocked, match="REAL_SOURCE_COLLECTION_SHA_MISMATCH"):
        run_offline_job(
            job,
            input_root=tmp_path,
            source_root=source,
            market_root=market,
            cache_root=tmp_path / "cache",
        )


def test_same_sealed_study_cannot_publish_a_conflicting_financial_result(tmp_path, monkeypatch):
    from copytrade_pm import pm_offline_job as target

    job, root, cache = _fixture_job(tmp_path)
    first = run_offline_job(job, input_root=root, market_root=root, cache_root=cache)
    original = target.run_synthetic_fixture_study

    def divergent(*args, **kwargs):
        good = original(*args, **kwargs)
        good["scenarios"][0]["fees"] = "1000000"
        good["logical_sha256"] = "a" * 64
        return good

    monkeypatch.setattr(target, "run_synthetic_fixture_study", divergent)
    with pytest.raises(ManifestBlocked, match="IMMUTABLE_CACHE_KEY_CONFLICT"):
        run_offline_job(job, input_root=root, market_root=root, cache_root=cache)
    assert first["status"] == "COMPLETE_ENGINEERING_FIXTURE"


def test_nested_manifest_hash_mismatch_prevents_promotion(tmp_path):
    job, root, cache = _fixture_job(tmp_path)
    file = root / "study.json"
    file.write_text(file.read_text() + " ")
    with pytest.raises(ManifestBlocked, match="SEALED_STUDY_MANIFEST_SHA_MISMATCH"):
        run_offline_job(
            job,
            input_root=root,
            market_root=root,
            cache_root=cache,
        )


def test_unknown_kind_and_oracle_clock_rejected(tmp_path):
    job, source, market = _oracle_job(tmp_path)
    content = json.loads(job.read_text())
    content["clock_basis"] = "PROSPECTIVE_FIRST_KNOWN"
    _write(job, content)
    with pytest.raises(ManifestInvalid, match="INVALID_ORACLE_JOB_CLOCK_OR_SCHEMA"):
        run_offline_job(
            job,
            input_root=tmp_path,
            source_root=source,
            market_root=market,
            cache_root=tmp_path / "cache",
        )
    content["clock_basis"] = "HISTORICAL_ORACLE"
    content["kind"] = "LIVE_TRADING"
    _write(job, content)
    with pytest.raises(ManifestInvalid, match="UNKNOWN_RESEARCH_JOB_KIND"):
        run_offline_job(
            job,
            input_root=tmp_path,
            source_root=source,
            market_root=market,
            cache_root=tmp_path / "cache",
        )
