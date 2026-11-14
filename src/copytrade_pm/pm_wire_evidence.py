"""Private, crash-safe, content-addressed original-wire sidecar store.

Sidecars are published before the SQLite event references them. The original
wire SHA is computed over uncompressed UTF-8 bytes; compression is storage only.
"""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import zlib

from .pm03_account import digest

MAX_ORIGINAL_WIRE = 2_000_000
SHA = re.compile(r"[0-9a-f]{64}\Z")


def compact_official_receipt(receipt: dict[str, Any], *, raw_sha: str) -> dict[str, Any]:
    """Project a verified source receipt, keeping raw diagnostics in the sidecar."""
    book = receipt.get("source_book")
    if (
        receipt.get("schema") != "paper_first_known_source_v1"
        or not isinstance(book, dict)
        or book.get("schema") != "paper_source_book_v1"
        or not isinstance(book.get("per_dex_margin_diagnostics"), list)
        or not isinstance(book.get("position_margin_diagnostics"), dict)
        or book.get("snapshot_sha")
        != digest({k: v for k, v in book.items() if k != "snapshot_sha"})
        or SHA.fullmatch(raw_sha) is None
    ):
        raise ValueError("V4_COMPACT_RECEIPT_UNVERIFIED_ORIGINAL")
    minimum = {
        key: value
        for key, value in book.items()
        if key not in ("per_dex_margin_diagnostics", "position_margin_diagnostics", "snapshot_sha")
    }
    minimum["schema"] = "paper_source_book_v2"
    minimum["diagnostics_in_raw_wire"] = True
    minimum["diagnostics_sha"] = digest(
        [book["per_dex_margin_diagnostics"], book["position_margin_diagnostics"]]
    )
    minimum["original_snapshot_sha"] = book["snapshot_sha"]
    minimum["wire_raw_sha"] = raw_sha
    minimum["snapshot_sha"] = digest(minimum)
    return {
        **receipt,
        "schema": "paper_first_known_source_v2",
        "payload_sha": minimum["snapshot_sha"],
        "source_book": minimum,
        "original_source_book_sha": book["snapshot_sha"],
        "wire_raw_sha": raw_sha,
    }


def evidence_path(db_path: Path, raw_sha: str) -> Path:
    if SHA.fullmatch(raw_sha) is None:
        raise ValueError("V4_EVIDENCE_SHA_INVALID")
    return db_path.parent / "source-evidence-v2" / raw_sha[:2] / (raw_sha + ".zlib")


def read_wire(db_path: Path, raw_sha: str) -> str:
    path = evidence_path(db_path, raw_sha)
    if path.is_symlink() or not path.is_file():
        raise ValueError("V4_EVIDENCE_SIDECAR_MISSING")
    if path.stat().st_size > MAX_ORIGINAL_WIRE + 1024:
        raise ValueError("V4_EVIDENCE_SIDECAR_OVERSIZED")
    compressed = path.read_bytes()
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, MAX_ORIGINAL_WIRE + 1)
        if len(raw) > MAX_ORIGINAL_WIRE or not decoder.eof or decoder.unused_data:
            raise ValueError("V4_EVIDENCE_SIDECAR_INVALID")
    except zlib.error as exc:
        raise ValueError("V4_EVIDENCE_SIDECAR_CORRUPT") from exc
    if sha256(raw).hexdigest() != raw_sha:
        raise ValueError("V4_EVIDENCE_SIDECAR_SHA_MISMATCH")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("V4_EVIDENCE_SIDECAR_UTF8_INVALID") from exc


def publish_wire(db_path: Path, raw_text: str, raw_sha: str) -> Path:
    if not isinstance(raw_text, str):
        raise ValueError("V4_EVIDENCE_ORIGINAL_WIRE_REQUIRED")
    raw = raw_text.encode("utf-8")
    if len(raw) > MAX_ORIGINAL_WIRE or sha256(raw).hexdigest() != raw_sha:
        raise ValueError("V4_EVIDENCE_ORIGINAL_WIRE_SHA_MISMATCH")
    path = evidence_path(db_path, raw_sha)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise PermissionError("V4_EVIDENCE_DIRECTORY_NOT_PRIVATE")
    if path.exists() or path.is_symlink():
        if read_wire(db_path, raw_sha) != raw_text:
            raise ValueError("V4_EVIDENCE_EXISTING_CONFLICT")
        return path
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".pending-", suffix=".zlib")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(zlib.compress(raw, level=6))
            stream.flush()
            os.fsync(stream.fileno())
        # Publish once; link() does not overwrite a concurrent immutable file.
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if read_wire(db_path, raw_sha) != raw_text:
                raise ValueError("V4_EVIDENCE_CONCURRENT_CONFLICT") from None
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)
    if read_wire(db_path, raw_sha) != raw_text:
        raise ValueError("V4_EVIDENCE_PUBLICATION_INVALID")
    return path
