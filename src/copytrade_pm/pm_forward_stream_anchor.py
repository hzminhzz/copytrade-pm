"""Independently sealed, bounded original V4 source-chain audits.

A trusted audit seal is made only AFTER a full verification of an offline,
operator-isolated original. Later receipts verify a contiguous suffix under a
single read transaction, with separately signed parent/child identities.

Neither a fast head preflight nor a producer-signed packet is an audit anchor.
This module never writes the SQLite source journal or financial state.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import re
import sqlite3
from tempfile import NamedTemporaryFile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .pm03_account import clock, digest
from .pm_forward_stream_journal import (
    _head,
    _receipt,
    _verified_frame_sha,
    validate_event,
    verify_streams,
)
from .production_manifest import canonical, sign, verify

ZERO = "0" * 64
AUTHORITY = "independent-original-stream-audit-v1"
SCHEMA = "paper_original_stream_audit_anchor_v1"
MAX_SUFFIX_EVENTS = 256
MAX_SUFFIX_RECEIPTS = 256
MAX_INITIAL_AUDIT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class VerifiedAnchor:
    payload: dict
    seal_file_sha256: str
    auditor_key_sha256: str


def _reader(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_ANCHOR_ORIGINAL_INVALID")
    db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=1.0)
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def _source_head(db: sqlite3.Connection, alias: str) -> tuple[int, str]:
    row = db.execute(
        "SELECT seq,chain_sha FROM source_receipts WHERE source_id=? ORDER BY seq DESC LIMIT 1",
        (alias,),
    ).fetchone()
    return (0, ZERO) if row is None else (row[0], row[1])


def _audit_source_rows(
    db: sqlite3.Connection,
    alias: str,
    *,
    start_cursor: int,
    start_sha: str,
    target_cursor: int,
) -> str:
    if target_cursor < start_cursor or target_cursor - start_cursor > MAX_SUFFIX_RECEIPTS:
        raise ValueError("SOURCE_ANCHOR_RECEIPT_SUFFIX_LIMIT")
    previous = start_sha
    cursor = start_cursor
    for seq, rid, raw, content_sha, prior, chained in db.execute(
        "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
        "FROM source_receipts WHERE source_id=? AND seq>? AND seq<=? ORDER BY seq",
        (alias, start_cursor, target_cursor),
    ):
        event = json.loads(raw)
        cursor += 1
        if (
            seq != cursor
            or event.get("source_id") != alias
            or digest(event) != content_sha
            or prior != previous
            or chained != digest([alias, seq, rid, previous, content_sha])
        ):
            raise ValueError("SOURCE_ANCHOR_RECEIPT_CHAIN_DIVERGENCE")
        # The original producer enforces this clock order at capture.
        if not (
            clock(event["source_event_at"])
            <= clock(event["first_known_at"])
            <= clock(event["captured_at"])
        ):
            raise ValueError("SOURCE_ANCHOR_RECEIPT_CLOCK_DIVERGENCE")
        previous = chained
    if cursor != target_cursor:
        raise ValueError("SOURCE_ANCHOR_RECEIPT_GAP")
    return previous


def _anchor_snapshot(
    db: sqlite3.Connection,
    *,
    alias: str,
    account_sha: str,
    stream_cursor: int,
    stream_chain_sha: str,
    source_cursor: int,
    source_chain_sha: str,
    last_known_at: str,
    last_commit_at: str,
    parent_anchor_sha256: str | None,
) -> dict:
    return {
        "schema": SCHEMA,
        "stream_id": "account:" + alias,
        "account_sha256": account_sha,
        "stream_cursor": stream_cursor,
        "stream_chain_sha": stream_chain_sha,
        "last_known_at": last_known_at,
        "last_commit_at": last_commit_at,
        "source_cursor": source_cursor,
        "source_chain_sha": source_chain_sha,
        "parent_anchor_sha256": parent_anchor_sha256,
        "trading_authorized": False,
        "original_source_history_audited": True,
    }


def _validate_payload(data: dict) -> None:
    if not isinstance(data, dict) or set(data) != {
        "schema",
        "stream_id",
        "account_sha256",
        "stream_cursor",
        "stream_chain_sha",
        "last_known_at",
        "last_commit_at",
        "source_cursor",
        "source_chain_sha",
        "parent_anchor_sha256",
        "trading_authorized",
        "original_source_history_audited",
    }:
        raise ValueError("SOURCE_ANCHOR_SCHEMA")
    if (
        data["schema"] != SCHEMA
        or data["trading_authorized"] is not False
        or data["original_source_history_audited"] is not True
    ):
        raise ValueError("SOURCE_ANCHOR_AUTHORITY_INVALID")
    if not re.fullmatch(r"account:[A-Za-z0-9_-]{1,70}", data["stream_id"]):
        raise ValueError("SOURCE_ANCHOR_ALIAS_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", data["account_sha256"]):
        raise ValueError("SOURCE_ANCHOR_ACCOUNT_INVALID")
    for field in ("stream_chain_sha", "source_chain_sha"):
        if not isinstance(data[field], str) or not re.fullmatch(r"[0-9a-f]{64}", data[field]):
            raise ValueError("SOURCE_ANCHOR_SHA_INVALID")
    for field in ("stream_cursor", "source_cursor"):
        if type(data[field]) is not int or data[field] < 1:
            raise ValueError("SOURCE_ANCHOR_CURSOR_INVALID")
    parent = data["parent_anchor_sha256"]
    if parent is not None and (
        not isinstance(parent, str) or not re.fullmatch(r"[0-9a-f]{64}", parent)
    ):
        raise ValueError("SOURCE_ANCHOR_PARENT_INVALID")
    clock(data["last_known_at"])
    clock(data["last_commit_at"])
    if clock(data["last_known_at"]) > clock(data["last_commit_at"]):
        raise ValueError("SOURCE_ANCHOR_CLOCK_INVALID")


def full_audit_anchor(
    journal_db: Path,
    *,
    alias: str,
    account: str,
    auditor: Ed25519PrivateKey,
    offline_snapshot_confirmed: bool = False,
) -> dict:
    """Full original audit, explicitly limited to small operator-isolated copies.

    The caller, not the source producer, provisions the independent auditor
    key and confirms the journal is an offline immutable snapshot.
    """
    if not offline_snapshot_confirmed:
        raise ValueError("SOURCE_ANCHOR_OFFLINE_SNAPSHOT_REQUIRED")
    if journal_db.is_symlink() or not journal_db.is_file():
        raise ValueError("SOURCE_ANCHOR_ORIGINAL_INVALID")
    wal = Path(str(journal_db) + "-wal")
    if wal.exists():
        raise ValueError("SOURCE_ANCHOR_INITIAL_WAL_NOT_ALLOWED")
    if journal_db.stat().st_size > MAX_INITIAL_AUDIT_BYTES:
        raise ValueError("SOURCE_ANCHOR_INITIAL_FULL_AUDIT_TOO_LARGE")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,70}", alias) or not re.fullmatch(
        r"0x[0-9a-f]{40}", account.lower()
    ):
        raise ValueError("SOURCE_ANCHOR_SELECTED_IDENTITY_INVALID")
    account_sha = sha256(account.lower().encode()).hexdigest()
    complete = verify_streams(journal_db)
    sid = "account:" + alias
    if sid not in complete["streams"]:
        raise ValueError("SOURCE_ANCHOR_SELECTED_STREAM_MISSING")
    anchor_head = complete["streams"][sid]
    with closing(_reader(journal_db)) as db:
        current = _head(db, sid)
        if (
            current["cursor"] != anchor_head["cursor"]
            or current["chain_sha"] != anchor_head["chain_sha"]
        ):
            raise ValueError("SOURCE_ANCHOR_AUDIT_SNAPSHOT_DRIFT")
        event = current["event"]
        if event is None or event["checkpoint"].get("account_sha") != account_sha:
            raise ValueError("SOURCE_ANCHOR_SELECTED_ACCOUNT_DRIFT")
        source_cursor, source_sha = _source_head(db, alias)
        # Initialization is deliberately a full original source-receipt audit.
        # Do not silently enforce the incremental 256-receipt limit here.
        previous = ZERO
        cursor = 0
        for seq, rid, raw, payload_sha, prior, chain in db.execute(
            "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
            "FROM source_receipts WHERE source_id=? ORDER BY seq",
            (alias,),
        ):
            cursor += 1
            event_source = json.loads(raw)
            if (
                seq != cursor
                or event_source.get("source_id") != alias
                or digest(event_source) != payload_sha
                or prior != previous
                or chain != digest([alias, seq, rid, previous, payload_sha])
            ):
                raise ValueError("SOURCE_ANCHOR_INITIAL_SOURCE_CHAIN_DIVERGENCE")
            if not (
                clock(event_source["source_event_at"])
                <= clock(event_source["first_known_at"])
                <= clock(event_source["captured_at"])
            ):
                raise ValueError("SOURCE_ANCHOR_INITIAL_SOURCE_CLOCK_DIVERGENCE")
            previous = chain
        if cursor != source_cursor or previous != source_sha or cursor == 0:
            raise ValueError("SOURCE_ANCHOR_INITIAL_SOURCE_HEAD_DIVERGENCE")
        payload = _anchor_snapshot(
            db,
            alias=alias,
            account_sha=account_sha,
            stream_cursor=current["cursor"],
            stream_chain_sha=current["chain_sha"],
            source_cursor=source_cursor,
            source_chain_sha=source_sha,
            last_known_at=current["event"]["first_known_at"],
            last_commit_at=current["committed_at"],
            parent_anchor_sha256=None,
        )
    _validate_payload(payload)
    return sign(payload, auditor, AUTHORITY)


def _read_sealed_anchor(path: Path, expected_file_sha256: str) -> bytes:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.is_symlink()
        or path.parent.is_symlink()
        or path.resolve(strict=True) != path
    ):
        raise ValueError("SOURCE_ANCHOR_PRIVATE_PATH_INVALID")
    directory = path.parent.stat()
    if (
        not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != os.getuid()
        or directory.st_mode & 0o777 != 0o700
    ):
        raise ValueError("SOURCE_ANCHOR_PRIVATE_DIRECTORY_INVALID")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o777 != 0o600
            or not 0 < metadata.st_size <= 16_384
        ):
            raise ValueError("SOURCE_ANCHOR_PRIVATE_FILE_INVALID")
        raw = os.read(fd, 16_385)
        if len(raw) != metadata.st_size:
            raise ValueError("SOURCE_ANCHOR_PRIVATE_FILE_TRUNCATED")
    finally:
        os.close(fd)
    if sha256(raw).hexdigest() != expected_file_sha256:
        raise ValueError("SOURCE_ANCHOR_PINNED_SHA_MISMATCH")
    return raw


def load_anchor(
    path: Path,
    expected_file_sha256: str,
    auditor_public: Ed25519PublicKey,
    *,
    expected_auditor_public_key_sha256: str,
) -> VerifiedAnchor:
    if sha256(auditor_public.public_bytes_raw()).hexdigest() != expected_auditor_public_key_sha256:
        raise ValueError("SOURCE_ANCHOR_INDEPENDENT_AUDITOR_PIN_REQUIRED")
    contents = _read_sealed_anchor(path, expected_file_sha256)
    envelope = json.loads(contents)
    payload = verify(envelope, auditor_public, AUTHORITY)
    _validate_payload(payload)
    return VerifiedAnchor(
        payload=payload,
        seal_file_sha256=sha256(contents).hexdigest(),
        auditor_key_sha256=expected_auditor_public_key_sha256,
    )


def verify_suffix(
    db: sqlite3.Connection,
    anchor: VerifiedAnchor,
    *,
    alias: str,
    account: str,
    target_cursor: int | None = None,
) -> dict:
    """Verify a contiguous bounded original suffix in the caller's transaction.

    Does not certify changed prefixes unless the independent full-audit seal
    establishes their earlier validity. No unanchored fast-tail fallback.
    """
    payload = anchor.payload
    if not db.in_transaction:
        raise ValueError("SOURCE_ANCHOR_READ_TRANSACTION_REQUIRED")
    account_sha = sha256(account.lower().encode()).hexdigest()
    sid = "account:" + alias
    if sid != payload["stream_id"] or account_sha != payload["account_sha256"]:
        raise ValueError("SOURCE_ANCHOR_SELECTION_MISMATCH")
    cursor = payload["stream_cursor"]
    head = _head(db, sid)
    end = head["cursor"] if target_cursor is None else target_cursor
    if (
        type(end) is not int
        or end < cursor
        or end > head["cursor"]
        or end - cursor > MAX_SUFFIX_EVENTS
    ):
        raise ValueError("SOURCE_ANCHOR_STREAM_SUFFIX_LIMIT")
    bound = db.execute(
        "SELECT event_sha,payload,receipt_refs,prior_sha,chain_sha,committed_at "
        "FROM observer_stream_events WHERE stream_id=? AND seq=?",
        (sid, cursor),
    ).fetchone()
    if bound is None or bound[4] != payload["stream_chain_sha"]:
        raise ValueError("SOURCE_ANCHOR_BASE_STREAM_DIVERGENCE")
    bound_event = json.loads(bound[1])
    if (
        bound_event.get("first_known_at") != payload["last_known_at"]
        or bound[5] != payload["last_commit_at"]
    ):
        raise ValueError("SOURCE_ANCHOR_BASE_CLOCK_DIVERGENCE")
    source_cursor, source_sha = _source_head(db, alias)
    source_bound = db.execute(
        "SELECT chain_sha FROM source_receipts WHERE source_id=? AND seq=?",
        (alias, payload["source_cursor"]),
    ).fetchone()
    if source_bound is None or source_bound[0] != payload["source_chain_sha"]:
        raise ValueError("SOURCE_ANCHOR_BASE_RECEIPT_DIVERGENCE")
    checked_sha = _audit_source_rows(
        db,
        alias,
        start_cursor=payload["source_cursor"],
        start_sha=payload["source_chain_sha"],
        target_cursor=source_cursor,
    )
    if checked_sha != source_sha:
        raise ValueError("SOURCE_ANCHOR_RECEIPT_HEAD_DIVERGENCE")
    previous = payload["stream_chain_sha"]
    last_known = clock(payload["last_known_at"])
    last_commit = clock(payload["last_commit_at"])
    rows = []
    for row in db.execute(
        "SELECT seq,event_sha,payload,receipt_refs,prior_sha,chain_sha,committed_at "
        "FROM observer_stream_events WHERE stream_id=? AND seq>? AND seq<=? ORDER BY seq",
        (sid, cursor, end),
    ):
        seq, event_sha, raw, refs_raw, prior, chain, committed_at = row
        event = json.loads(raw)
        refs = json.loads(refs_raw)
        validate_event(event)
        known, committed = clock(event["first_known_at"]), clock(committed_at)
        if (
            seq != cursor + 1
            or event["stream_id"] != sid
            or event["expected_cursor"] != cursor
            or digest(event) != event_sha
            or prior != previous
            or chain != digest([sid, seq, event_sha, prior, committed_at, refs])
            or known > committed
            or known < last_known
            or committed < last_commit
            or event["checkpoint"].get("account_sha") != account_sha
        ):
            raise ValueError("SOURCE_ANCHOR_STREAM_CHAIN_DIVERGENCE")
        if event["schema"] == "paper_observer_stream_event_v2" and event["kind"] in (
            "BASELINE",
            "OBSERVATION",
        ):
            _verified_frame_sha(db, event)
        for ref in refs:
            _receipt(db, ref)
        previous, last_known, last_commit, cursor = chain, known, committed, seq
        rows.append((seq, event_sha, raw, refs_raw, prior, chain, committed_at))
    if cursor != end or (end == head["cursor"] and previous != head["chain_sha"]):
        raise ValueError("SOURCE_ANCHOR_STREAM_HEAD_DIVERGENCE")
    return {
        "status": "INDEPENDENT_FULL_AUDIT_ANCHORED_SUFFIX_VERIFIED",
        "stream_cursor": cursor,
        "stream_chain_sha": previous,
        "source_cursor": source_cursor,
        "source_chain_sha": source_sha,
        "last_known_at": last_known.isoformat(),
        "last_commit_at": last_commit.isoformat(),
        "rows": rows,
        "anchor_file_sha256": anchor.seal_file_sha256,
        "original_head_audit_is_anchored": True,
        "trading_authorized": False,
    }


def advance_anchor(
    journal_db: Path,
    anchor: VerifiedAnchor,
    *,
    alias: str,
    account: str,
    auditor: Ed25519PrivateKey,
    target_cursor: int | None = None,
) -> dict:
    """Sign next head ONLY after bounded proof with the matching audit key."""
    if sha256(auditor.public_key().public_bytes_raw()).hexdigest() != anchor.auditor_key_sha256:
        raise ValueError("SOURCE_ANCHOR_AUDITOR_ROTATION_NOT_APPROVED")
    with closing(_reader(journal_db)) as db:
        verified = verify_suffix(
            db, anchor, alias=alias, account=account, target_cursor=target_cursor
        )
        if (
            verified["stream_cursor"] == anchor.payload["stream_cursor"]
            and verified["source_cursor"] == anchor.payload["source_cursor"]
        ):
            raise ValueError("SOURCE_ANCHOR_NO_PROGRESS")
        payload = _anchor_snapshot(
            db,
            alias=alias,
            account_sha=anchor.payload["account_sha256"],
            stream_cursor=verified["stream_cursor"],
            stream_chain_sha=verified["stream_chain_sha"],
            source_cursor=verified["source_cursor"],
            source_chain_sha=verified["source_chain_sha"],
            last_known_at=verified["last_known_at"],
            last_commit_at=verified["last_commit_at"],
            parent_anchor_sha256=anchor.seal_file_sha256,
        )
    _validate_payload(payload)
    return sign(payload, auditor, AUTHORITY)


def anchor_file_bytes(envelope: dict) -> bytes:
    """External owner-private publisher may commit these immutable sealed bytes."""
    payload = envelope.get("payload")
    _validate_payload(payload)
    return canonical(envelope)


def publish_anchor(directory: Path, envelope: dict) -> tuple[Path, str]:
    """Durably publish signed anchors into an explicit owner-private sidecar.

    Idempotent crash replay never overwrites a prior anchor or touches SQLite.
    The consumer still independently verifies the audit signature and key pin.
    """
    if (
        not directory.is_absolute()
        or ".." in directory.parts
        or directory.name != "source-audit-anchors"
        or directory.is_symlink()
        or directory.resolve(strict=True) != directory
        or set(directory.parts) & {"prospective", "registry", "releases", "copytrade-grafana"}
    ):
        raise ValueError("SOURCE_ANCHOR_OUTPUT_DIRECTORY_UNSAFE")
    metadata = directory.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o777 != 0o700
    ):
        raise ValueError("SOURCE_ANCHOR_OUTPUT_DIRECTORY_UNSAFE")
    raw = anchor_file_bytes(envelope)
    identity = sha256(raw).hexdigest()
    destination = directory / (identity + ".json")
    temporary = None
    try:
        with NamedTemporaryFile(dir=directory, prefix=".audit-", delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            existing = _read_sealed_anchor(destination, identity)
            if existing != raw:
                raise ValueError("SOURCE_ANCHOR_OUTPUT_TAMPER") from None
        folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination, identity
