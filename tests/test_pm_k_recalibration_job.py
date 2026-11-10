"""Immutable offline Track C publication and provenance negative tests."""

from __future__ import annotations

from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_k_recalibration_job import run_k_job
from test_pm_k_recalibration import _input


def _json_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def test_manifest_to_immutable_report_and_replay(tmp_path):
    original = tmp_path / "input"
    original.mkdir()
    cache = tmp_path / "cache"
    body = _input().model_dump(mode="json", by_alias=True)
    data = _json_bytes(body)
    (original / "research.json").write_bytes(data)
    request = {
        "schema": "track_c_k_research_job_v1",
        "study_id": "portfolio-1",
        "research_input": "research.json",
        "research_input_sha256": sha256(data).hexdigest(),
    }
    (original / "job.json").write_bytes(_json_bytes(request))
    first = run_k_job(original / "job.json", input_root=original, cache_root=cache)
    second = run_k_job(original / "job.json", input_root=original, cache_root=cache)
    assert first["report_sha256"] == second["report_sha256"]
    assert first["cache_status"] == "CACHE_CREATED"
    assert second["cache_status"] == "CACHE_HIT"
    assert first["proposal"]["decision"] == "INSUFFICIENT_EVIDENCE"
    assert first["release_eligible"] is False
    assert first["finance_report_authenticity_independently_verified"] is False
    assert first["order_route"] == "NONE"
    assert first["economic_qualification"].startswith("NOT_QUALIFIED")
    assert len(list(cache.rglob("*.data"))) == 1
    assert len(list(cache.rglob("*.manifest.json"))) == 1
    (original / "research.json").write_bytes(data + b" ")
    with pytest.raises(ValueError, match="TRACK_C_RESEARCH_INPUT_HASH_MISMATCH"):
        run_k_job(original / "job.json", input_root=original, cache_root=cache)


def test_manifest_rejects_outside_root_and_symlink(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    external = tmp_path / "other.json"
    external.write_text("{}")
    (root / "job.json").symlink_to(external)
    with pytest.raises(ValueError, match="TRACK_C_INPUT_OUTSIDE_PINNED_ROOT"):
        run_k_job(root / "job.json", input_root=root, cache_root=tmp_path / "cache")


def test_invalid_input_must_not_publish(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    job = {
        "schema": "track_c_k_research_job_v1",
        "study_id": "test",
        "research_input": "data.json",
        "research_input_sha256": "a" * 64,
    }
    (root / "job.json").write_bytes(_json_bytes(job))
    (root / "data.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        run_k_job(root / "job.json", input_root=root, cache_root=tmp_path / "cache")
    assert not (tmp_path / "cache").exists()
