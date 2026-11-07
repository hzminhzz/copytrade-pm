"""Build and exercise reversible *unprivileged staging* dashboard candidates.

Never touches systemd, production symlinks, broker or Guardian directories.
Release installation on the protected VPS is deliberately not implemented here.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

SHA = re.compile(r"[a-f0-9]{40}\Z")
SCHEMA = "dashboard_staging_candidate_v1"


class ReleaseError(ValueError):
    pass


def _secure_root(root: Path) -> Path:
    if root.is_symlink():
        raise ReleaseError("STAGING_SYMLINK_REFUSED")
    path = root.resolve(strict=True)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ReleaseError("STAGING_NOT_OWNED_DIRECTORY")
    if path.stat().st_mode & 0o022:
        raise ReleaseError("STAGING_WRITABLE_BY_GROUP_OR_OTHER")
    # An operator must provide a standalone disposable staging area.
    if path.is_relative_to(Path("/etc")) or path.is_relative_to(Path("/var")):
        raise ReleaseError("PROTECTED_PATH_REFUSED")
    if path.is_relative_to(Path("/opt")):
        raise ReleaseError("PROTECTED_PATH_REFUSED")
    if "prop-production" in path.parts or "copytrade-pm" in path.parts:
        raise ReleaseError("PROTECTED_PATH_REFUSED")
    if not (path / ".dashboard-staging-only").is_file():
        raise ReleaseError("EXPLICIT_STAGING_MARKER_REQUIRED")
    return path


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ReleaseError("ARTIFACT_MUST_BE_REGULAR_FILE")
    return sha256(path.read_bytes()).hexdigest()


def prepare(
    root: Path,
    wheel: Path,
    *,
    source_sha: str,
    guardian_sha: str,
    connector_sha: str,
) -> dict[str, Any]:
    """Create an immutable SHA-bound candidate; never activate it."""
    path = _secure_root(root)
    for value in (source_sha, guardian_sha, connector_sha):
        if not SHA.fullmatch(value):
            raise ReleaseError("UNPINNED_SOURCE_REVISION")
    wheel_sha = _digest(wheel)
    candidate_id = source_sha[:12] + "-" + wheel_sha[:12]
    releases = path / "candidates"
    releases.mkdir(mode=0o700, exist_ok=True)
    destination = releases / candidate_id
    if destination.exists():
        report = verify(destination)
        if (
            report["source_sha"] != source_sha
            or report["guardian_sha"] != guardian_sha
            or report["connector_sha"] != connector_sha
            or report["wheel_sha256"] != wheel_sha
        ):
            raise ReleaseError("EXISTING_CANDIDATE_CONFLICT")
        return report
    destination.mkdir(mode=0o700)
    try:
        target = destination / "dashboard.whl"
        shutil.copyfile(wheel, target)
        os.chmod(target, 0o400)
        data: dict[str, Any] = {
            "schema": SCHEMA,
            "source_sha": source_sha,
            "guardian_sha": guardian_sha,
            "connector_sha": connector_sha,
            "wheel_sha256": wheel_sha,
            "candidate": candidate_id,
            "scope": "ISOLATED_STAGING_ONLY",
            "trading_authorized": False,
            "installed": False,
        }
        manifest = destination / "manifest.json"
        manifest.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(manifest, 0o400)
        return verify(destination)
    except Exception:
        shutil.rmtree(destination)
        raise


def verify(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ReleaseError("RELEASE_DIRECTORY_INVALID")
    manifest = directory / "manifest.json"
    if manifest.is_symlink():
        raise ReleaseError("RELEASE_MANIFEST_SYMLINK")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        data.get("schema") != SCHEMA
        or data.get("scope") != "ISOLATED_STAGING_ONLY"
        or data.get("installed") is not False
        or data.get("trading_authorized") is not False
        or data.get("candidate") != directory.name
        or not all(
            isinstance(data.get(name), str) and SHA.fullmatch(data[name])
            for name in ("source_sha", "guardian_sha", "connector_sha")
        )
        or not isinstance(data.get("wheel_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", data["wheel_sha256"])
    ):
        raise ReleaseError("RELEASE_MANIFEST_INVALID")
    if data["candidate"] != f"{data['source_sha'][:12]}-{data['wheel_sha256'][:12]}":
        raise ReleaseError("RELEASE_MANIFEST_INVALID")
    if _digest(directory / "dashboard.whl") != data.get("wheel_sha256"):
        raise ReleaseError("RELEASE_WHEEL_SHA_MISMATCH")
    return data


def select_staging(root: Path, candidate: str) -> str | None:
    """Atomic disposable pointer replacement with previous-target return."""
    path = _secure_root(root)
    if not re.fullmatch(r"[a-f0-9]{12}-[a-f0-9]{12}", candidate):
        raise ReleaseError("INVALID_CANDIDATE_ID")
    verify(path / "candidates" / candidate)
    current = path / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    if current.exists() and not current.is_symlink():
        raise ReleaseError("UNMANAGED_POINTER_REFUSED")
    if previous is not None and not previous.startswith("candidates/"):
        raise ReleaseError("UNMANAGED_POINTER_REFUSED")
    pending = path / f".current.{os.getpid()}"
    try:
        pending.symlink_to("candidates/" + candidate)
        os.replace(pending, current)
        return previous
    finally:
        if pending.is_symlink():
            pending.unlink()
