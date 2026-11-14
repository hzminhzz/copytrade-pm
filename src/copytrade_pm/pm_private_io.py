"""Owner-private and redacted-public atomic file I/O primitives (stdlib-only)."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import time


def private_input(path: Path) -> bytes:
    """Read an operator-provisioned regular file enforcing mode 0600 and no symlinks."""
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("V4_PRIVATE_INPUT_REQUIRED")
    return path.read_bytes()


def atomic_private_output(path: Path, payload: bytes, *, replace: bool = False) -> None:
    """Atomically publish complete durable mode-0600 bytes with file and directory fsync."""
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise ValueError("V4_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    if path.is_symlink() or (path.exists() and not replace):
        raise ValueError("V4_PRIVATE_OUTPUT_EXISTS")
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=".v4-stage-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # Atomic no-clobber publication.
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_atomic_public(directory: Path, payload: bytes, *, name: str) -> None:
    """Atomically publish a redacted public snapshot with 0644 permissions and fsync."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o755)
    temp = directory / f".{name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, directory / name)
        dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        temp.unlink(missing_ok=True)


_private_input = private_input
_atomic_private_output = atomic_private_output
