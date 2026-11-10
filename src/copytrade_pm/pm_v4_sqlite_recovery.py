"""Offline backup/restore verifier for V4 source journals (issue #292).

No live service operations or checkpoint are performed by this module.
The operator must independently quiesce and confirm all source/paper readers.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import shutil
import sqlite3

from .pm_forward_stream_journal import verify_streams
from .pm_v4_evidence import read_wire


def backup_and_verify(source: Path, backup_dir: Path, *, quiescence_verified: bool) -> dict:
    """Copy one complete source journal and independently audit its restore.

    This is intentionally fail-closed and refuses to overwrite any destination.
    Requires a separate operator service/FD fence before invoking.
    """
    if not quiescence_verified:
        raise ValueError("V4_RECOVERY_QUIESCENCE_NOT_VERIFIED")
    source = Path(source)
    backup_dir = Path(backup_dir)
    if source.is_symlink() or not source.is_file():
        raise ValueError("V4_RECOVERY_SOURCE_INVALID")
    if backup_dir.exists() or backup_dir.is_symlink():
        raise FileExistsError("V4_RECOVERY_BACKUP_DESTINATION_EXISTS")
    before = verify_streams(source)
    backup_dir.mkdir(mode=0o700, parents=True)
    backup_db = backup_dir / source.name
    with closing(sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(backup_db)) as target:
            original.backup(target)
    # The cold tree is part of the journal's proof, not a disposable cache.
    evidence = source.parent / "source-evidence-v2"
    if evidence.exists():
        if evidence.is_symlink() or not evidence.is_dir():
            raise ValueError("V4_RECOVERY_EVIDENCE_ROOT_INVALID")
        shutil.copytree(evidence, backup_dir / evidence.name, symlinks=False)
    with closing(sqlite3.connect(f"file:{backup_db.resolve()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("V4_RECOVERY_SQLITE_INTEGRITY_FAILED")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("V4_RECOVERY_FOREIGN_KEYS_FAILED")
    after = verify_streams(backup_db)
    if before["head_sha"] != after["head_sha"]:
        raise ValueError("V4_RECOVERY_STREAM_HEAD_MISMATCH")
    # Verify independent sidecar bytes and their SHA on the restored tree.
    for file in sorted((backup_dir / "source-evidence-v2").glob("*/*.zlib")):
        if file.is_symlink():
            raise ValueError("V4_RECOVERY_EVIDENCE_SYMLINK")
        raw = read_wire(backup_db, file.stem)
        if sha256(raw.encode()).hexdigest() != file.stem:
            raise ValueError("V4_RECOVERY_EVIDENCE_DIVERGENCE")
    return {
        "status": "RESTORED_VERIFIED_SOURCE_ONLY",
        "backup_db": str(backup_db),
        "stream_head_sha": after["head_sha"],
        "original_db_bytes": source.stat().st_size,
        "restored_db_bytes": backup_db.stat().st_size,
        "sidecars": sum(1 for _ in (backup_dir / "source-evidence-v2").glob("*/*.zlib")),
        "financial_ledger_verified": False,
        "source_service_cutover_authorized": False,
    }
