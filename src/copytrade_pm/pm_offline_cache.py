"""Private immutable content-addressed offline research cache.

Publishing uses same-filesystem fsynced hard links (exclusive creation).
A payload without its sealed metadata is never a cache hit. Existing payloads
are never overwritten, including after a failed/crashed publisher.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .pm_offline_manifest import ManifestBlocked, ManifestInvalid

SHA = re.compile(r"^[0-9a-f]{64}$")
KIND = re.compile(r"^[a-z][a-z0-9_]{1,55}$")
SCHEMA = "pm_offline_cache_v1"


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish_exclusive(destination: Path, content: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if _checksum(destination) != sha256(content).hexdigest():
                raise ManifestBlocked("IMMUTABLE_CACHE_KEY_CONFLICT") from None
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


class ImmutableCache:
    """Owner-private cache; key contains dependency SHAs and declared semantics."""

    def __init__(
        self,
        root: Path,
        *,
        max_object_bytes: int = 64 * 1024 * 1024,
        min_free_bytes: int = 10 * 1024 * 1024 * 1024,
    ):
        self.root = Path(root)
        if self.root.is_symlink():
            raise ManifestInvalid("SYMLINK_CACHE_ROOT")
        if max_object_bytes <= 0 or min_free_bytes < 0:
            raise ManifestInvalid("INVALID_CACHE_BUDGET")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_mode & 0o077:
            raise ManifestInvalid("INSECURE_CACHE_DIRECTORY")
        self.max_object_bytes = max_object_bytes
        self.min_free_bytes = min_free_bytes

    @staticmethod
    def identity(kind: str, dependencies: dict[str, str], *, version: str) -> str:
        if not isinstance(kind, str) or not KIND.fullmatch(kind):
            raise ManifestInvalid("INVALID_CACHE_KIND")
        if (
            not isinstance(dependencies, dict)
            or not dependencies
            or any(
                not isinstance(k, str)
                or not KIND.fullmatch(k)
                or not isinstance(v, str)
                or not SHA.fullmatch(v)
                for k, v in dependencies.items()
            )
            or not isinstance(version, str)
            or not version
        ):
            raise ManifestInvalid("INVALID_CACHE_DEPENDENCIES")
        return sha256(
            _canonical(
                {
                    "schema": SCHEMA,
                    "kind": kind,
                    "dependencies": dependencies,
                    "version": version,
                }
            )
        ).hexdigest()

    def _paths(self, kind: str, key: str) -> tuple[Path, Path]:
        namespace = self.root / kind
        if namespace.is_symlink():
            raise ManifestInvalid("SYMLINK_CACHE_NAMESPACE")
        namespace.mkdir(mode=0o700, exist_ok=True)
        if namespace.stat().st_mode & 0o077:
            raise ManifestInvalid("INSECURE_CACHE_NAMESPACE")
        folder = namespace / key[:2]
        folder.mkdir(mode=0o700, exist_ok=True)
        if folder.is_symlink() or folder.stat().st_mode & 0o077:
            raise ManifestInvalid("INSECURE_CACHE_FOLDER")
        return folder / f"{key}.data", folder / f"{key}.manifest.json"

    def load(self, kind: str, dependencies: dict[str, str], *, version: str) -> bytes | None:
        key = self.identity(kind, dependencies, version=version)
        content_path, metadata_path = self._paths(kind, key)
        if not metadata_path.exists():
            return None
        if content_path.is_symlink() or metadata_path.is_symlink():
            raise ManifestBlocked("SYMLINK_CACHE_OBJECT")
        if not content_path.is_file():
            raise ManifestBlocked("CACHE_MANIFEST_WITHOUT_PAYLOAD")
        try:
            doc = json.loads(metadata_path.read_text())
        except (OSError, ValueError, TypeError) as exc:
            raise ManifestBlocked("CORRUPT_CACHE_MANIFEST") from exc
        if (
            doc.get("schema") != SCHEMA
            or doc.get("key") != key
            or doc.get("kind") != kind
            or doc.get("dependencies") != dependencies
            or doc.get("version") != version
        ):
            raise ManifestBlocked("CACHE_DEPENDENCY_MISMATCH")
        size = content_path.stat().st_size
        if size > self.max_object_bytes or size != doc.get("bytes"):
            raise ManifestBlocked("CACHE_SIZE_MISMATCH")
        actual = _checksum(content_path)
        if actual != doc.get("sha256"):
            raise ManifestBlocked("CORRUPT_CACHE_SHA")
        return content_path.read_bytes()

    def publish(
        self,
        kind: str,
        dependencies: dict[str, str],
        *,
        version: str,
        content: bytes,
    ) -> dict:
        if not isinstance(content, bytes) or len(content) > self.max_object_bytes:
            raise ManifestInvalid("CACHE_OBJECT_TOO_LARGE")
        key = self.identity(kind, dependencies, version=version)
        old = self.load(kind, dependencies, version=version)
        if old is not None:
            if old != content:
                raise ManifestBlocked("IMMUTABLE_CACHE_KEY_CONFLICT")
            return {
                "status": "CACHE_HIT",
                "key": key,
                "sha256": sha256(content).hexdigest(),
                "bytes": len(content),
            }
        if shutil.disk_usage(self.root).free < self.min_free_bytes + len(content):
            raise ManifestBlocked("INSUFFICIENT_SCRATCH_HEADROOM")
        data_path, manifest_path = self._paths(kind, key)
        metadata = {
            "schema": SCHEMA,
            "key": key,
            "kind": kind,
            "dependencies": dependencies,
            "version": version,
            "sha256": sha256(content).hexdigest(),
            "bytes": len(content),
        }
        _publish_exclusive(data_path, content)
        _publish_exclusive(manifest_path, _canonical(metadata))
        if self.load(kind, dependencies, version=version) != content:
            raise ManifestBlocked("CACHE_POST_PUBLISH_VERIFY_FAILED")
        return {
            "status": "CACHE_CREATED",
            "key": key,
            "sha256": metadata["sha256"],
            "bytes": len(content),
        }
