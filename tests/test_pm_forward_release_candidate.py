"""Content-addressed, unsigned offline candidate release safety checks."""

from datetime import UTC, datetime
from io import BytesIO
import json
from pathlib import Path
import zipfile

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_release_candidate import (
    stage_unprotected_release_candidate,
    verify_unprotected_release_candidate,
)

HEAD = "a" * 40
AT = datetime(2026, 11, 4, 12, 0, tzinfo=UTC).isoformat()


def wheel(root: Path, filename: str = "copytrade_pm-0.1.0-py3-none-any.whl") -> Path:
    path = root / filename
    version = filename.split("-")[1]
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("copytrade_pm/__init__.py", f"__version__={version!r}\n")
        archive.writestr(
            f"copytrade_pm-{version}.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
    path.write_bytes(buffer.getvalue())
    return path


def staged(tmp_path: Path):
    root = tmp_path / "release-staging"
    root.mkdir(mode=0o700)
    result = stage_unprotected_release_candidate(
        wheel_path=wheel(tmp_path),
        candidate_root=root,
        source_commit_sha=HEAD,
        staged_at=AT,
    )
    return root, result


def test_unsigned_candidate_stage_is_exclusive_content_addressed_and_never_active(tmp_path):
    root, report = staged(tmp_path)
    candidate = root / report["candidate_name"]
    assert candidate.name == "candidate-" + report["wheel_sha256"]
    assert candidate.is_dir() and candidate.stat().st_mode & 0o077 == 0
    assert sorted(p.name for p in candidate.iterdir()) == [
        "copytrade_pm-0.1.0-py3-none-any.whl",
        "manifest.json",
    ]
    assert all(p.stat().st_mode & 0o077 == 0 for p in candidate.iterdir())
    assert report["status"] == "UNPROTECTED_UNSIGNED_CANDIDATE_VERIFIED"
    assert report["source_commit_sha"] == HEAD
    assert report["source_commit_build_provenance_verified"] is False
    assert report["operator_cutover_authorized"] is False
    assert report["release_immutable_verified"] is False
    assert report["signature_independently_verified"] is False
    assert report["systemd_activated"] is False
    assert not report["paper_observed"] and report["order_route"] == "NONE"
    assert verify_unprotected_release_candidate(candidate) == report
    with pytest.raises(FileExistsError, match="PAPER_RELEASE_CANDIDATE_ALREADY_STAGED"):
        stage_unprotected_release_candidate(
            wheel_path=wheel(tmp_path),
            candidate_root=root,
            source_commit_sha=HEAD,
            staged_at=AT,
        )
    assert len(list(root.iterdir())) == 1


def test_side_by_side_distinct_candidates_remain_independently_verified(tmp_path):
    root, old = staged(tmp_path)
    candidate_old = root / old["candidate_name"]
    upgraded_wheel = wheel(tmp_path, "copytrade_pm-0.1.1-py3-none-any.whl")
    new = stage_unprotected_release_candidate(
        wheel_path=upgraded_wheel,
        candidate_root=root,
        source_commit_sha="b" * 40,
        staged_at=AT,
    )
    assert old["candidate_name"] != new["candidate_name"]
    assert len(list(root.iterdir())) == 2
    assert verify_unprotected_release_candidate(candidate_old) == old
    assert verify_unprotected_release_candidate(root / new["candidate_name"]) == new
    assert old["source_commit_build_provenance_verified"] is False
    assert new["source_commit_build_provenance_verified"] is False
    assert old["operator_cutover_authorized"] is False
    assert new["operator_cutover_authorized"] is False
    assert old["release_immutable_verified"] is False
    assert new["release_immutable_verified"] is False


def test_candidate_verify_detects_wheel_bit_mutation_and_manifest_tamper(tmp_path):
    root, report = staged(tmp_path)
    candidate = root / report["candidate_name"]
    artifact = candidate / "copytrade_pm-0.1.0-py3-none-any.whl"
    before = artifact.read_bytes()
    artifact.write_bytes(before + b"x")
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_WHEEL_HASH_MISMATCH"):
        verify_unprotected_release_candidate(candidate)
    artifact.write_bytes(before)
    manifest = candidate / "manifest.json"
    saved = json.loads(manifest.read_text())
    saved["source_commit_sha"] = "f" * 40
    manifest.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_MANIFEST_TAMPERED"):
        verify_unprotected_release_candidate(candidate)
    saved["payload_sha"] = digest({k: v for k, v in saved.items() if k != "payload_sha"})
    saved["protected_service_authorized"] = True
    saved["payload_sha"] = digest({k: v for k, v in saved.items() if k != "payload_sha"})
    manifest.write_text(json.dumps(saved))
    with pytest.raises(
        ValueError, match="PAPER_RELEASE_CANDIDATE_POSITIVE_AUTHORITY_CLAIM_REFUSED"
    ):
        verify_unprotected_release_candidate(candidate)


def test_candidate_refuses_symlinks_extra_files_unprotected_modes_and_replacement(tmp_path):
    root, report = staged(tmp_path)
    candidate = root / report["candidate_name"]
    wheel_path = candidate / "copytrade_pm-0.1.0-py3-none-any.whl"
    wheel_path.chmod(0o644)
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_WHEEL_PERMISSION_INVALID"):
        verify_unprotected_release_candidate(candidate)
    wheel_path.chmod(0o600)
    (candidate / "untrusted.txt").write_text("inject")
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_UNEXPECTED_FILE"):
        verify_unprotected_release_candidate(candidate)
    (candidate / "untrusted.txt").unlink()
    manifest = candidate / "manifest.json"
    saved = manifest.read_bytes()
    manifest.unlink()
    external = tmp_path / "untrusted-manifest"
    external.write_bytes(saved)
    manifest.symlink_to(external)
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_MANIFEST_PERMISSION_INVALID"):
        verify_unprotected_release_candidate(candidate)
    assert external.read_bytes() == saved
    manifest.unlink()
    manifest.write_bytes(saved)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_ROOT_NOT_PRIVATE"):
        verify_unprotected_release_candidate(candidate)


def test_stage_preflight_rejects_bad_wheel_commit_and_worktree(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    source = wheel(tmp_path)
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_COMMIT_SHA_INVALID"):
        stage_unprotected_release_candidate(
            wheel_path=source, candidate_root=staging, source_commit_sha="bad", staged_at=AT
        )
    fake = tmp_path / "not-a-wheel.whl"
    fake.write_bytes(b"not a wheel")
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_WHEEL_NAME_INVALID"):
        stage_unprotected_release_candidate(
            wheel_path=fake, candidate_root=staging, source_commit_sha=HEAD, staged_at=AT
        )
    (tmp_path / "invalid").mkdir()
    bad = tmp_path / "invalid" / "copytrade_pm-0.1.0-py3-none-any.whl"
    bad.write_bytes(b"not a wheel")
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_WHEEL_INVALID"):
        stage_unprotected_release_candidate(
            wheel_path=bad, candidate_root=staging, source_commit_sha=HEAD, staged_at=AT
        )
    bad.unlink()
    bad.symlink_to(source)
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_SYMLINK_FORBIDDEN"):
        stage_unprotected_release_candidate(
            wheel_path=bad, candidate_root=staging, source_commit_sha=HEAD, staged_at=AT
        )
    unsafe = tmp_path / ".devspace" / "release-staging"
    unsafe.mkdir(parents=True, mode=0o700)
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_WORKTREE_FORBIDDEN"):
        stage_unprotected_release_candidate(
            wheel_path=source, candidate_root=unsafe, source_commit_sha=HEAD, staged_at=AT
        )
    assert list(staging.iterdir()) == []


def test_mismatched_wheel_metadata_fails_before_staging(tmp_path):
    root = tmp_path / "candidate-root"
    root.mkdir(mode=0o700)
    artifact = tmp_path / "copytrade_pm-0.1.1-py3-none-any.whl"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("copytrade_pm/__init__.py", "# source code")
        archive.writestr("copytrade_pm-0.1.0.dist-info/WHEEL", "Wheel-Version: 1.0")
    with pytest.raises(ValueError, match="PAPER_RELEASE_CANDIDATE_WHEEL_METADATA_MISSING"):
        stage_unprotected_release_candidate(
            wheel_path=artifact, candidate_root=root, source_commit_sha=HEAD, staged_at=AT
        )
    assert list(root.iterdir()) == []


def test_partial_candidate_not_treated_as_installed_release(tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    directory = root / ("candidate-" + "f" * 64)
    directory.mkdir(mode=0o700)
    wheel(directory)
    with pytest.raises((FileNotFoundError, ValueError)):
        verify_unprotected_release_candidate(directory)
    assert directory.is_dir()
