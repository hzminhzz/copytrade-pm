"""Offline, unsigned, never-activated Forward-Paper release candidate.

Prepares a content-addressed Python wheel for separate operator review. This
module intentionally has no systemctl, sudo, chown, active-release symlink,
financial DB mutation or broker transport. A coder-owned candidate is NOT an
immutable, independently signed, or deployed release.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import zipfile

from .pm03_account import clock, digest

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CANDIDATE = re.compile(r"candidate-[0-9a-f]{64}\Z")
_WHEEL = re.compile(r"copytrade_pm-(?P<version>[0-9][A-Za-z0-9._+]*)-py[0-9]+-none-any\.whl\Z")
_MAX_WHEEL = 128 * 1024 * 1024
_MAX_MANIFEST = 8192


def _private_directory(path: Path) -> None:
    if (
        not path.is_absolute()
        or any(part.is_symlink() for part in (path, *path.parents))
        or not path.is_dir()
        or path.stat().st_uid != os.geteuid()
        or path.stat().st_mode & 0o077
    ):
        raise ValueError("PAPER_RELEASE_CANDIDATE_ROOT_NOT_PRIVATE")


def _safe_file(path: Path, *, max_size: int) -> bytes:
    if path.is_symlink():
        raise ValueError("PAPER_RELEASE_CANDIDATE_SYMLINK_FORBIDDEN")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise ValueError("PAPER_RELEASE_CANDIDATE_FILE_NOT_ACCESSIBLE") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size <= 0
            or info.st_size > max_size
            or info.st_nlink != 1
        ):
            raise ValueError("PAPER_RELEASE_CANDIDATE_FILE_NOT_SINGLE_REGULAR")
        with os.fdopen(os.dup(fd), "rb") as source:
            data = source.read(max_size + 1)
        if not data or len(data) != info.st_size:
            raise ValueError("PAPER_RELEASE_CANDIDATE_FILE_SIZE_CHANGED")
        if len(data) > max_size:
            raise ValueError("PAPER_RELEASE_CANDIDATE_FILE_TOO_LARGE")
        if os.fstat(fd).st_size != info.st_size:
            raise ValueError("PAPER_RELEASE_CANDIDATE_FILE_SIZE_CHANGED")
        return data
    finally:
        os.close(fd)


def _wheel_payload(wheel_path: Path) -> bytes:
    matched = _WHEEL.fullmatch(wheel_path.name)
    if matched is None:
        raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_NAME_INVALID")
    data = _safe_file(wheel_path, max_size=_MAX_WHEEL)
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            expected_metadata = f"copytrade_pm-{matched.group('version')}.dist-info/WHEEL"
            if not any(name.startswith("copytrade_pm/") and name.endswith(".py") for name in names):
                raise ValueError("PAPER_RELEASE_CANDIDATE_PACKAGE_MISSING")
            if expected_metadata not in names:
                raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_METADATA_MISSING")
            if len(names) > 10_000 or len(names) != len(set(names)):
                raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_MEMBERS_INVALID")
            if sum(item.file_size for item in members) > 256 * 1024 * 1024:
                raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_UNPACKED_SIZE_UNSAFE")
            if any(
                name.startswith("/") or ".." in Path(name).parts or "\\" in name for name in names
            ):
                raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_PATH_UNSAFE")
            if any(stat.S_ISLNK(item.external_attr >> 16) for item in members):
                raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_SYMLINK_UNSAFE")
    except (zipfile.BadZipFile, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_INVALID") from exc
    return data


def _write_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def _sync_directory(root: Path) -> None:
    fd = os.open(root, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage_unprotected_release_candidate(
    *,
    wheel_path: Path,
    candidate_root: Path,
    source_commit_sha: str,
    staged_at: str,
) -> dict:
    """Stage one *new* unsigned wheel; never reuse, replace or activate a slot."""
    root = Path(candidate_root)
    _private_directory(root)
    if any(item in {".devspace", ".git"} for item in root.resolve().parts):
        raise ValueError("PAPER_RELEASE_CANDIDATE_WORKTREE_FORBIDDEN")
    if not isinstance(source_commit_sha, str) or not _COMMIT.fullmatch(source_commit_sha):
        raise ValueError("PAPER_RELEASE_CANDIDATE_COMMIT_SHA_INVALID")
    clock(staged_at)
    wheel = Path(wheel_path)
    data = _wheel_payload(wheel)
    content_sha = sha256(data).hexdigest()
    name = "candidate-" + content_sha
    destination = root / name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("PAPER_RELEASE_CANDIDATE_ALREADY_STAGED")
    # mkdir is an exclusive create; a partially written stage is forever
    # unverified, not silently replaced on retry. Preserve it for forensics.
    destination.mkdir(mode=0o700)
    _sync_directory(root)
    _write_once(destination / wheel.name, data)
    payload = {
        "schema": "paper_release_candidate_v1",
        "source_commit_sha": source_commit_sha,
        "source_commit_build_provenance_verified": False,
        "candidate_directory": name,
        "wheel_filename": wheel.name,
        "wheel_sha256": content_sha,
        "staged_at": staged_at,
        "operator_signature": None,
        "independent_review_verified": False,
        "release_immutable_verified": False,
        "protected_service_authorized": False,
        "systemd_activated": False,
        "financial_data_mutated": False,
        "order_route": "NONE",
    }
    envelope = {**payload, "payload_sha": digest(payload)}
    _write_once(
        destination / "manifest.json",
        (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    _sync_directory(destination)
    _sync_directory(root)
    return verify_unprotected_release_candidate(destination)


def verify_unprotected_release_candidate(path: Path) -> dict:
    """Read-only exact SHA and filename verifier, not an immutable-file claim."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("PAPER_RELEASE_CANDIDATE_SYMLINK_FORBIDDEN")
    _private_directory(path)
    _private_directory(path.parent)
    if not _CANDIDATE.fullmatch(path.name):
        raise ValueError("PAPER_RELEASE_CANDIDATE_DIRECTORY_NAME_INVALID")
    manifest = path / "manifest.json"
    if manifest.is_symlink() or manifest.stat().st_mode & 0o077:
        raise ValueError("PAPER_RELEASE_CANDIDATE_MANIFEST_PERMISSION_INVALID")
    data = _safe_file(manifest, max_size=_MAX_MANIFEST)
    try:
        record = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("PAPER_RELEASE_CANDIDATE_MANIFEST_INVALID") from exc
    body = {key: value for key, value in record.items() if key != "payload_sha"}
    if record.get("payload_sha") != digest(body):
        raise ValueError("PAPER_RELEASE_CANDIDATE_MANIFEST_TAMPERED")
    if (
        body.get("schema") != "paper_release_candidate_v1"
        or body.get("candidate_directory") != path.name
        or body.get("wheel_sha256") != path.name.removeprefix("candidate-")
        or not isinstance(body.get("source_commit_sha"), str)
        or not _COMMIT.fullmatch(body["source_commit_sha"])
        or body.get("source_commit_build_provenance_verified") is not False
        or body.get("operator_signature") is not None
        or body.get("independent_review_verified") is not False
        or body.get("release_immutable_verified") is not False
        or body.get("protected_service_authorized") is not False
        or body.get("systemd_activated") is not False
        or body.get("financial_data_mutated") is not False
        or body.get("order_route") != "NONE"
    ):
        raise ValueError("PAPER_RELEASE_CANDIDATE_POSITIVE_AUTHORITY_CLAIM_REFUSED")
    clock(body["staged_at"])
    wheel_name = body["wheel_filename"]
    if not isinstance(wheel_name, str) or not _WHEEL.fullmatch(wheel_name):
        raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_NAME_INVALID")
    files = {item.name for item in path.iterdir()}
    if files != {"manifest.json", wheel_name}:
        raise ValueError("PAPER_RELEASE_CANDIDATE_UNEXPECTED_FILE")
    wheel = path / wheel_name
    if wheel.is_symlink() or wheel.stat().st_mode & 0o077:
        raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_PERMISSION_INVALID")
    saved_wheel = _wheel_payload(wheel)
    if sha256(saved_wheel).hexdigest() != body["wheel_sha256"]:
        raise ValueError("PAPER_RELEASE_CANDIDATE_WHEEL_HASH_MISMATCH")
    return {
        "schema": "paper_release_candidate_verification_v1",
        "status": "UNPROTECTED_UNSIGNED_CANDIDATE_VERIFIED",
        "candidate_name": path.name,
        "source_commit_sha": body["source_commit_sha"],
        "source_commit_build_provenance_verified": False,
        "wheel_sha256": body["wheel_sha256"],
        "manifest_sha": record["payload_sha"],
        "candidate_bytes": len(saved_wheel),
        "signature_independently_verified": False,
        "release_immutable_verified": False,
        "operator_cutover_authorized": False,
        "financial_backup_restored": False,
        "systemd_activated": False,
        "paper_observed": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline unsigned Forward-Paper candidate verification"
    )
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_unprotected_release_candidate(args.candidate), indent=2))


def write_once(path: Path, data: bytes) -> None:
    _write_once(path, data)


def sync_directory(root: Path) -> None:
    _sync_directory(root)


if __name__ == "__main__":
    main()
