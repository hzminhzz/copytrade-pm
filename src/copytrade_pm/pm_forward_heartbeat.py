"""Local OS-identity-bound paper-worker liveness evidence (FP-11).

This is a TEST-ONLY heartbeat producer/independent read-only inspector.
The producer records its own PID, Linux process start ticks, boot ID and
private financial head. A separate inspector checks OS identity, process
reuse, clocks, quote/source/transport and file integrity.

A coder-writable heartbeat remains UNPROTECTED and never grants PAPER_RUNNING.
No service installation, private exchange client, broker or trading authority.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

from .pm03_account import clock, digest
from .pm_forward_journal import PaperJournal


_RUN = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def _process_identity(pid: int) -> dict:
    if type(pid) is not int or pid <= 0:
        raise ValueError("HEARTBEAT_PID_INVALID")
    base = Path("/proc") / str(pid)
    try:
        raw = (base / "stat").read_text()
        stat_after_name = raw.rsplit(") ", 1)[1].split()
        start_ticks = int(stat_after_name[19])  # Linux /proc stat field 22
        uid = base.stat().st_uid
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except (OSError, IndexError, ValueError) as exc:
        raise ValueError("HEARTBEAT_PROCESS_IDENTITY_UNAVAILABLE") from exc
    if not boot or start_ticks <= 0:
        raise ValueError("HEARTBEAT_PROCESS_IDENTITY_INVALID")
    return {
        "pid": pid,
        "uid": uid,
        "start_ticks": start_ticks,
        "boot_id": boot,
    }


def _private_dir(root: Path) -> None:
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("HEARTBEAT_ROOT_NOT_ABSOLUTE_PRIVATE")
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError("HEARTBEAT_ROOT_NOT_PRIVATE")
    if root.stat().st_uid != os.geteuid():
        raise ValueError("HEARTBEAT_WRONG_OS_OWNER")


def _heartbeat_path(root: Path, run_id: str) -> Path:
    if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
        raise ValueError("HEARTBEAT_UNSAFE_RUN_ID")
    return root / (run_id + ".heartbeat.json")


def _sealed_release_sha(journal: PaperJournal, run_id: str) -> str:
    # The run manifest has already been verified by journal.restore().
    uri = "file:" + str(journal.path.resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as connection:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise ValueError("HEARTBEAT_UNKNOWN_RUN")
    return json.loads(row[0])["release_sha"]


def publish_observer_heartbeat(
    root: Path,
    *,
    journal: PaperJournal,
    run_id: str,
    release_sha: str,
    transport_recv_at: str | None,
    source_book_at: str | None,
    market_quote_at: str | None,
    observed_at: str | None = None,
) -> dict:
    """Publish only SELF process identity; never accept caller-supplied PID."""
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private_dir(root)
    observed = observed_at or datetime.now(UTC).isoformat()
    clock(observed)
    if not isinstance(release_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", release_sha):
        raise ValueError("HEARTBEAT_RELEASE_SHA_INVALID")
    for candidate in (transport_recv_at, source_book_at, market_quote_at):
        if candidate is not None and clock(candidate) > clock(observed):
            raise ValueError("HEARTBEAT_FUTURE_INPUT")
    financial = journal.restore(run_id)
    if release_sha != _sealed_release_sha(journal, run_id):
        raise ValueError("HEARTBEAT_RELEASE_MANIFEST_MISMATCH")
    process = _process_identity(os.getpid())
    payload = {
        "schema": "paper_worker_observer_heartbeat_v1",
        "run_id": run_id,
        "release_sha": release_sha,
        "manifest_sha": financial["manifest_sha"],
        "journal_head_sha": financial["journal_head_sha"],
        "financial_cursor": financial["cursor"],
        "heartbeat_at": observed,
        "transport_recv_at": transport_recv_at,
        "source_book_at": source_book_at,
        "market_quote_at": market_quote_at,
        "process_identity": process,
        "operating_mode": "OBSERVER_ONLY_NO_TRADE",
        "paper_admitted": False,
        "order_route": "NONE",
        "independently_signed": False,
    }
    envelope = {**payload, "payload_sha": digest(payload)}
    path = _heartbeat_path(root, run_id)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("HEARTBEAT_DESTINATION_NOT_REGULAR")
    data = (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix="." + run_id + "-", delete=False
        ) as temp:
            temp_name = temp.name
            os.fchmod(temp.fileno(), 0o600)
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
        temp_name = None
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temp_name is not None:
            os.unlink(temp_name)
    return {"status": "OBSERVER_HEARTBEAT_RECORDED", "payload_sha": envelope["payload_sha"]}


def inspect_observer_heartbeat(
    root: Path,
    *,
    journal: PaperJournal,
    run_id: str,
    as_of: str,
    max_heartbeat_age: float = 90,
    max_transport_age: float = 90,
    max_source_age: float = 180,
    max_market_age: float = 90,
) -> dict:
    clock(as_of)
    root = Path(root)
    try:
        _private_dir(root)
        path = _heartbeat_path(root, run_id)
        if path.is_symlink() or not path.is_file():
            raise ValueError("HEARTBEAT_NOT_PRESENT")
        info = path.stat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.geteuid()
            or info.st_size > 16_384
        ):
            raise ValueError("HEARTBEAT_FILE_PERMISSION_OR_SIZE")
        envelope = json.loads(path.read_text())
        source = {key: value for key, value in envelope.items() if key != "payload_sha"}
        if envelope.get("payload_sha") != digest(source):
            raise ValueError("HEARTBEAT_TAMPERED")
        if (
            source.get("schema") != "paper_worker_observer_heartbeat_v1"
            or source.get("run_id") != run_id
            or source.get("paper_admitted") is not False
            or source.get("operating_mode") != "OBSERVER_ONLY_NO_TRADE"
            or source.get("order_route") != "NONE"
            or source.get("independently_signed") is not False
        ):
            raise ValueError("HEARTBEAT_UNTRUSTED_MODE")
        if source["process_identity"] != _process_identity(source["process_identity"]["pid"]):
            raise ValueError("HEARTBEAT_PROCESS_RESTART_OR_SPOOFED")
        actual = journal.restore(run_id)
        if (
            source["release_sha"] != _sealed_release_sha(journal, run_id)
            or actual["manifest_sha"] != source["manifest_sha"]
            or actual["cursor"] != source["financial_cursor"]
            or actual["journal_head_sha"] != source["journal_head_sha"]
        ):
            raise ValueError("HEARTBEAT_FINANCIAL_HEAD_CHANGED")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {
            "schema": "paper_observer_health_v1",
            "run_id": run_id,
            "health": "UNKNOWN",
            "reasons": [str(exc)[:130] or "UNKNOWN_HEARTBEAT_FAILURE"],
            "protected_worker_attested": False,
            "paper_admitted": False,
            "order_route": "NONE",
        }

    now = clock(as_of)
    reasons = ["PROTECTED_OS_IDENTITY_NOT_VERIFIED"]
    ages: dict[str, float | None] = {}
    for name, limit in (
        ("heartbeat", max_heartbeat_age),
        ("transport_recv", max_transport_age),
        ("source_book", max_source_age),
        ("market_quote", max_market_age),
    ):
        key = name + "_at"
        when = source.get(key)
        if when is None:
            ages[name] = None
            reasons.append(name.upper() + "_NOT_OBSERVED")
            continue
        age = (now - clock(when)).total_seconds()
        ages[name] = age
        if age < 0 or age > limit:
            reasons.append(name.upper() + "_STALE_OR_FUTURE")
    if actual["account"]["risk"] == "HALT":
        reasons.append("PM03_HALT_LATCHED")
    return {
        "schema": "paper_observer_health_v1",
        "run_id": run_id,
        "health": "HALT" if actual["account"]["risk"] == "HALT" else "DEGRADED",
        "reasons": reasons,
        "ages_seconds": ages,
        "observer_process_verified": True,
        "protected_worker_attested": False,
        "paper_admitted": False,
        "order_route": "NONE",
        "financial_cursor": actual["cursor"],
        "journal_head_sha": actual["journal_head_sha"],
        "release_sha": source["release_sha"],
        "heartbeats_cryptographically_signed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only local paper-worker PID, financial-head and feed-health check"
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--heartbeat-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--as-of", default=datetime.now(UTC).isoformat())
    args = parser.parse_args()
    # Construct only a read-only verification view. Never instantiate
    # PaperJournal(), which creates SQLite/schema/lock files.
    from .pm_forward_journal import PaperJournal

    class ReadOnlyJournalView:
        path = args.db

        def restore(self, run_id: str) -> dict:
            uri = "file:" + str(self.path.resolve()) + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
                db.execute("PRAGMA query_only=ON")
                return PaperJournal._verify(db, run_id)

    result = inspect_observer_heartbeat(
        args.heartbeat_root,
        journal=ReadOnlyJournalView(),
        run_id=args.run_id,
        as_of=args.as_of,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
