"""Quiescent recovery and independently verified source-only backup (issue #292).

No service action is initiated here. Offline operations require an explicit
quiescence assertion AND a real /proc FD check, plus a nonblocking writer lease.
No production finance journal, source receipt, or broker order is mutated.
"""

from __future__ import annotations

from contextlib import closing
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3

from .pm_forward_stream_journal import verify_streams
from .pm_v4_evidence import read_wire


def active_source_handles(source: Path) -> list[dict[str, str | int]]:
    """Observe every accessible same-user file handle to DB/WAL/SHM.

    This is an additional process-level gate, NOT an exhaustive guarantee that
    privileged or remote readers do not exist. Those require OS supervision.
    """
    source = Path(source).resolve()
    wanted = {str(source) + suffix for suffix in ("", "-wal", "-shm")}
    matches: list[dict[str, str | int]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        raise ValueError("V4_RECOVERY_PROC_UNAVAILABLE")
    for process in proc.iterdir():
        if not process.name.isdecimal():
            continue
        try:
            owner = process.stat().st_uid
        except FileNotFoundError, PermissionError:
            continue
        if owner != os.getuid():
            continue
        fdroot = process / "fd"
        try:
            entries = list(fdroot.iterdir())
        except FileNotFoundError:
            continue
        except PermissionError:
            # Linux ptrace/Yama can hide FDs even for same-UID processes.
            # This remains supplemental to service identity and writer lease.
            continue
        for fd in entries:
            try:
                target = os.readlink(fd)
            except FileNotFoundError:
                continue
            except PermissionError:
                continue
            clean = target.removesuffix(" (deleted)")
            if clean in wanted:
                matches.append({"pid": int(process.name), "fd": fd.name, "file": clean})
    return sorted(matches, key=lambda row: (row["pid"], row["fd"]))


def _verify_no_handles(path: Path) -> None:
    active = active_source_handles(path)
    if active:
        # Never expose private paths or file content in an error string.
        raise ValueError("V4_RECOVERY_JOURNAL_ACTIVE_HANDLES")


def _check_evidence_tree(root: Path) -> int:
    """Reject symlinks and independently decode every original wire blob."""
    if not root.exists():
        return 0
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError("V4_RECOVERY_SIDECAR_TREE_INVALID")
    total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        for entry in (*dirs, *files):
            path = Path(parent) / entry
            if path.is_symlink():
                raise ValueError("V4_RECOVERY_SIDECAR_SYMLINK")
        for name in files:
            path = Path(parent) / name
            if path.suffix != ".zlib" or len(path.stem) != 64:
                raise ValueError("V4_RECOVERY_UNEXPECTED_SIDECAR")
            # read_wire reconstructs content from a synthetic DB path with
            # this exact parent tree, then checks the original raw SHA.
            read_wire(root.parent / "paper-events.sqlite3", path.stem)
            total += 1
    return total


def _assert_quiescence(path: Path, approved: bool) -> None:
    if not approved:
        raise ValueError("V4_RECOVERY_QUIESCENCE_NOT_VERIFIED")
    if path.is_symlink() or not path.is_file():
        raise ValueError("V4_RECOVERY_SOURCE_INVALID")
    _verify_no_handles(path)


def backup_and_verify(source: Path, backup_dir: Path, *, quiescence_verified: bool) -> dict:
    """Make a fresh SQLite online backup and verify restored chains and sidecars.

    The destination must not exist and must share no directory with the source.
    In particular, never accidentally back up into the same live evidence tree.
    """
    source, backup_dir = Path(source), Path(backup_dir)
    _assert_quiescence(source, quiescence_verified)
    if backup_dir.exists() or backup_dir.is_symlink():
        raise FileExistsError("V4_RECOVERY_BACKUP_DESTINATION_EXISTS")
    if backup_dir.resolve().is_relative_to(source.parent.resolve()):
        raise ValueError("V4_RECOVERY_BACKUP_MUST_BE_ISOLATED")
    # Reserve capacity for BOTH independent copies before starting. The live
    # WAL is not counted as reclaimable until a verified checkpoint succeeds.
    disk = os.statvfs(backup_dir.parent)
    free_bytes = disk.f_bavail * disk.f_frsize
    reserved_bytes = max(1024**3, min(8 * 1024**3, source.stat().st_size))
    minimum_required = 2 * source.stat().st_size + reserved_bytes
    if free_bytes < minimum_required:
        raise ValueError("V4_RECOVERY_INSUFFICIENT_BACKUP_RESTORE_CAPACITY")
    # A dedicated writer lease ensures that another journal writer cannot
    # enter between the FD check and backup. This cannot block non-cooperating
    # readers; we recheck their FDs before and after the backup.
    lock = source.parent / "paper-events.lock"
    with closing(open(lock, "a+b")) as fd:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("V4_RECOVERY_WRITER_LEASE_HELD") from exc
        try:
            _verify_no_handles(source)
            before = verify_streams(source)
            backup_dir.mkdir(mode=0o700, parents=True)
            backup_db = backup_dir / source.name
            with closing(sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)) as original:
                with closing(sqlite3.connect(backup_db)) as target:
                    original.backup(target, pages=2048, sleep=0.02)
            evidence = source.parent / "source-evidence-v2"
            if evidence.exists():
                _check_evidence_tree(evidence)
                shutil.copytree(evidence, backup_dir / evidence.name, symlinks=True)
            backup_audit = verify_streams(backup_db)
            if backup_audit["head_sha"] != before["head_sha"]:
                raise ValueError("V4_RECOVERY_BACKUP_STREAM_HEAD_MISMATCH")
            # Prove physical restore independently of the original backup DB.
            restore_dir = backup_dir / "independent-restore"
            restore_dir.mkdir(mode=0o700)
            restore_db = restore_dir / source.name
            with closing(sqlite3.connect(f"file:{backup_db.resolve()}?mode=ro", uri=True)) as saved:
                with closing(sqlite3.connect(restore_db)) as target:
                    saved.backup(target, pages=2048, sleep=0.02)
            if (backup_dir / "source-evidence-v2").exists():
                shutil.copytree(
                    backup_dir / "source-evidence-v2",
                    restore_dir / "source-evidence-v2",
                    symlinks=False,
                )
            restored = verify_streams(restore_db)
            sidecars = _check_evidence_tree(restore_dir / "source-evidence-v2")
            _verify_no_handles(source)
            if before["head_sha"] != restored["head_sha"]:
                raise ValueError("V4_RECOVERY_STREAM_HEAD_MISMATCH")
            return {
                "status": "RESTORED_VERIFIED_SOURCE_ONLY",
                "backup_db": str(backup_db),
                "independent_restore_db": str(restore_db),
                "stream_head_sha": restored["head_sha"],
                "original_db_bytes": source.stat().st_size,
                "backup_db_bytes": backup_db.stat().st_size,
                "restored_db_bytes": restore_db.stat().st_size,
                "sidecars": sidecars,
                "financial_ledger_verified": False,
                "source_service_cutover_authorized": False,
            }
        finally:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)


def checkpoint_verified_backup(
    source: Path,
    backup_dir: Path,
    *,
    quiescence_verified: bool,
    expected_head_sha: str,
) -> dict:
    """Conditionally TRUNCATE only WAL, never original v1 data or source DB."""
    source, backup_dir = Path(source), Path(backup_dir)
    _assert_quiescence(source, quiescence_verified)
    if (
        backup_dir.is_symlink()
        or not (backup_dir / source.name).is_file()
        or len(expected_head_sha) != 64
    ):
        raise ValueError("V4_RECOVERY_VERIFIED_BACKUP_REQUIRED")
    backup_head = verify_streams(backup_dir / source.name)["head_sha"]
    if backup_head != expected_head_sha:
        raise ValueError("V4_RECOVERY_BACKUP_SHA_MISMATCH")
    lock = source.parent / "paper-events.lock"
    with closing(open(lock, "a+b")) as fd:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("V4_RECOVERY_WRITER_LEASE_HELD") from exc
        try:
            _verify_no_handles(source)
            old = verify_streams(source)["head_sha"]
            if old != backup_head:
                raise ValueError("V4_RECOVERY_LIVE_DB_CHANGED_SINCE_BACKUP")
            wal = Path(str(source) + "-wal")
            before_wal = wal.stat().st_size if wal.exists() else 0
            with closing(sqlite3.connect(source, timeout=1, isolation_level=None)) as db:
                db.execute("PRAGMA busy_timeout=1000")
                busy, log, checkpointed = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy or log or checkpointed:
                raise ValueError("V4_RECOVERY_CHECKPOINT_BUSY_OR_INCOMPLETE")
            after = verify_streams(source)["head_sha"]
            if after != old:
                raise ValueError("V4_RECOVERY_CHECKPOINT_CHANGED_SOURCE_HEAD")
            after_wal = wal.stat().st_size if wal.exists() else 0
            if after_wal > before_wal:
                raise ValueError("V4_RECOVERY_WAL_DID_NOT_SHRINK")
            return {
                "status": "QUIESCENT_WAL_ONLY_RECOVERED",
                "source_head_sha": after,
                "wal_before_bytes": before_wal,
                "wal_after_bytes": after_wal,
                "checkpoint": {"busy": busy, "log": log, "checkpointed": checkpointed},
                "main_db_unpruned": True,
                "source_evidence_retained": True,
            }
        finally:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
