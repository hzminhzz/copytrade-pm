"""Isolated release/restart/rollback tests without privileged services."""
from __future__ import annotations

from pathlib import Path

import pytest

from copytrade_pm.dashboard.release import (
    ReleaseError, prepare, select_staging, verify,
)

SOURCE = "a" * 40
GUARDIAN = "b" * 40
CONNECTOR = "c" * 40


@pytest.fixture
def staging(tmp_path: Path):
    root = tmp_path / "private-staging"
    root.mkdir(mode=0o700)
    (root / ".dashboard-staging-only").touch(mode=0o600)
    return root


def test_candidate_pin_restart_failure_and_rollback(staging: Path, tmp_path: Path):
    wheel = tmp_path / "app-1.whl"
    wheel.write_bytes(b"source wheel candidate 1")
    first = prepare(staging, wheel, source_sha=SOURCE,
                    guardian_sha=GUARDIAN, connector_sha=CONNECTOR)
    assert first["scope"] == "ISOLATED_STAGING_ONLY"
    assert first["trading_authorized"] is False
    assert first["installed"] is False
    assert select_staging(staging, first["candidate"]) is None
    assert verify((staging / "current").resolve()) == first
    # Restart verification is idempotent and never touches protected services.
    assert prepare(staging, wheel, source_sha=SOURCE,
                   guardian_sha=GUARDIAN, connector_sha=CONNECTOR) == first
    second_wheel = tmp_path / "app-2.whl"
    second_wheel.write_bytes(b"source wheel candidate 2")
    second = prepare(staging, second_wheel, source_sha=SOURCE,
                     guardian_sha=GUARDIAN, connector_sha=CONNECTOR)
    previous = select_staging(staging, second["candidate"])
    assert previous == "candidates/" + first["candidate"]
    # Simulate a failed startup: no systemd or Guardian process is involved.
    with pytest.raises(ReleaseError):
        select_staging(staging, "0" * 12 + "-" + "1" * 12)
    assert verify((staging / "current").resolve()) == second
    select_staging(staging, first["candidate"])
    assert verify((staging / "current").resolve()) == first
    assert not (staging / "guardian").exists()


def test_actual_built_wheel_candidate_stage_rollback(staging: Path):
    from subprocess import check_output

    repo = Path(__file__).resolve().parents[1]
    wheel = repo / "dist" / "copytrade_pm-0.1.0-py3-none-any.whl"
    if not wheel.exists():
        pytest.skip("build wheel first for optional artifact acceptance")
    if not all(Path(path).is_dir() for path in (
        "/home/quant/dev/prop-production", "/home/quant/dev/trading-connector"
    )):
        pytest.skip("pinned VPS companion worktrees unavailable")
    source = check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    guardian = check_output(["git", "-C", "/home/quant/dev/prop-production",
                             "rev-parse", "HEAD"], text=True).strip()
    connector = check_output(["git", "-C", "/home/quant/dev/trading-connector",
                              "rev-parse", "HEAD"], text=True).strip()
    candidate = prepare(staging, wheel, source_sha=source,
                        guardian_sha=guardian, connector_sha=connector)
    assert candidate["source_sha"] == source
    assert candidate["wheel_sha256"] == verify(
        staging / "candidates" / candidate["candidate"]
    )["wheel_sha256"]
    assert select_staging(staging, candidate["candidate"]) is None
    assert verify((staging / "current").resolve()) == candidate


def test_corrupt_artifact_and_protected_locations_rejected(staging: Path, tmp_path: Path):
    wheel = tmp_path / "bundle.whl"
    wheel.write_bytes(b"wheel bytes")
    candidate = prepare(staging, wheel, source_sha=SOURCE,
                        guardian_sha=GUARDIAN, connector_sha=CONNECTOR)
    target = staging / "candidates" / candidate["candidate"] / "dashboard.whl"
    target.chmod(0o600)
    target.write_bytes(b"tampered")
    with pytest.raises(ReleaseError, match="MISMATCH"):
        verify(target.parent)
    with pytest.raises(ReleaseError):
        prepare(staging, wheel, source_sha=SOURCE, guardian_sha=GUARDIAN,
                connector_sha=CONNECTOR)
    without_marker = tmp_path / "not-marked"
    without_marker.mkdir(mode=0o700)
    with pytest.raises(ReleaseError, match="MARKER"):
        prepare(without_marker, wheel, source_sha=SOURCE,
                guardian_sha=GUARDIAN, connector_sha=CONNECTOR)
    with pytest.raises(ReleaseError):
        prepare(staging, wheel, source_sha="main",
                guardian_sha=GUARDIAN, connector_sha=CONNECTOR)


def test_candidate_reuse_must_match_every_companion_pin(staging: Path, tmp_path: Path):
    wheel = tmp_path / "dashboard.whl"
    wheel.write_bytes(b"exact wheel, exact source, immutable companion pins")
    original = prepare(staging, wheel, source_sha=SOURCE,
                       guardian_sha=GUARDIAN, connector_sha=CONNECTOR)
    for guardian, connector in (("d" * 40, CONNECTOR),
                                (GUARDIAN, "e" * 40)):
        with pytest.raises(ReleaseError, match="EXISTING_CANDIDATE_CONFLICT"):
            prepare(staging, wheel, source_sha=SOURCE,
                    guardian_sha=guardian, connector_sha=connector)
    assert verify(staging / "candidates" / original["candidate"]) == original


def test_verifier_rejects_manifest_candidate_identity_spoof(
        staging: Path, tmp_path: Path):
    import json

    wheel = tmp_path / "dashboard.whl"
    wheel.write_bytes(b"pin test")
    receipt = prepare(staging, wheel, source_sha=SOURCE,
                      guardian_sha=GUARDIAN, connector_sha=CONNECTOR)
    manifest = staging / "candidates" / receipt["candidate"] / "manifest.json"
    manifest.chmod(0o600)
    payload = json.loads(manifest.read_text())
    payload["source_sha"] = "d" * 40
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ReleaseError, match="RELEASE_MANIFEST_INVALID"):
        verify(manifest.parent)
