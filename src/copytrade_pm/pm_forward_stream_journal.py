"""Additive stream progress in the existing PaperJournal SQLite database.

Receipt owners retain their schemas and hash algorithms. They call
append_checkpoint inside their own transaction. This module never owns a
second database, financial state, wallet selection or provider transport.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sqlite3

from .pm03_account import clock, digest

SCHEMA = """
CREATE TABLE IF NOT EXISTS observer_stream_heads (
    stream_id TEXT PRIMARY KEY,
    cursor INTEGER NOT NULL,
    chain_sha TEXT NOT NULL,
    checkpoint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observer_stream_events (
    stream_id TEXT NOT NULL REFERENCES observer_stream_heads(stream_id),
    seq INTEGER NOT NULL,
    event_sha TEXT NOT NULL,
    payload TEXT NOT NULL,
    receipt_refs TEXT NOT NULL,
    prior_sha TEXT NOT NULL,
    chain_sha TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    PRIMARY KEY(stream_id, seq),
    UNIQUE(stream_id, event_sha)
);
"""
KINDS = frozenset(
    {
        "START",
        "BASELINE",
        "OBSERVATION",
        "UNCHANGED",
        "TRANSPORT",
        "GAP",
        "RECONCILIATION",
        "SCOPE",
        "STOP",
        "DIAGNOSTIC",
    }
)
ZERO = "0" * 64


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stream_event(
    *,
    stream_id: str,
    epoch: str,
    kind: str,
    known_at: str,
    expected_cursor: int,
    checkpoint: dict,
    source_at: str | None = None,
    raw_sha: str | None = None,
    details: dict | None = None,
) -> dict:
    result = {
        "schema": "paper_observer_stream_event_v1",
        "stream_id": stream_id,
        "epoch": epoch,
        "kind": kind,
        "first_known_at": known_at,
        "source_event_at": source_at,
        "expected_cursor": expected_cursor,
        "checkpoint": checkpoint,
        "raw_sha": raw_sha,
        "details": details or {},
        "source_nav_attested": False,
        "paper_admitted": False,
        "order_route": "NONE",
    }
    validate_event(result)
    return result


def validate_event(event: dict) -> None:
    if (
        not isinstance(event, dict)
        or event.get("schema") != "paper_observer_stream_event_v1"
        or event.get("kind") not in KINDS
        or not isinstance(event.get("stream_id"), str)
        or re.fullmatch(r"[A-Za-z0-9_:./-]{1,256}", event["stream_id"]) is None
        or not isinstance(event.get("epoch"), str)
        or re.fullmatch(r"[0-9a-f]{32}", event["epoch"]) is None
        or type(event.get("expected_cursor")) is not int
        or event["expected_cursor"] < 0
        or not isinstance(event.get("checkpoint"), dict)
        or not isinstance(event.get("details"), dict)
        or event.get("source_nav_attested") is not False
        or event.get("paper_admitted") is not False
        or event.get("order_route") != "NONE"
    ):
        raise ValueError("STREAM_EVENT_INVALID")
    try:
        known = clock(event["first_known_at"])
        if event["source_event_at"] is not None and clock(event["source_event_at"]) > known:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("STREAM_CAUSAL_CLOCK_INVALID") from exc
    if event["raw_sha"] is not None and (
        not isinstance(event["raw_sha"], str)
        or re.fullmatch(r"[0-9a-f]{64}", event["raw_sha"]) is None
    ):
        raise ValueError("STREAM_RAW_SHA_INVALID")
    wire = event["details"].get("native_wire")
    if wire is not None:
        from hashlib import sha256

        if not isinstance(wire, str) or sha256(wire.encode()).hexdigest() != event["raw_sha"]:
            raise ValueError("STREAM_NATIVE_WIRE_SHA_MISMATCH")
    if len(_json(event).encode()) > 2_000_000:
        raise ValueError("STREAM_EVENT_TOO_LARGE")


def _receipt(db: sqlite3.Connection, ref: dict) -> None:
    """Verify immutable references, using each original table's hash contract."""
    kind, key, sha = ref["kind"], ref["key"], ref["sha"]
    if kind == "source":
        row = db.execute(
            "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
            "FROM source_receipts WHERE source_id=? AND receipt_id=?",
            key,
        ).fetchone()
        expected = None if row is None else digest([key[0], row[0], row[1], row[4], row[3]])
    elif kind == "collateral":
        row = db.execute(
            "SELECT seq,receipt_id,payload,payload_sha,prior_sha,chain_sha "
            "FROM source_scope_receipts WHERE account_sha=? AND receipt_id=?",
            key,
        ).fetchone()
        expected = None if row is None else digest([key[0], row[0], row[3], row[4]])
    elif kind == "quote":
        row = db.execute(
            "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha "
            "FROM market_quote_receipts WHERE instrument=? AND quote_id=?",
            key,
        ).fetchone()
        expected = None if row is None else digest([key[0], row[0], row[3], row[4]])
    elif kind == "trades":
        row = db.execute(
            "SELECT seq,batch_sha,payload,batch_sha,prior_sha,chain_sha "
            "FROM market_trade_batches WHERE instrument=? AND batch_sha=?",
            key,
        ).fetchone()
        expected = None if row is None else digest([key[0], row[0], row[3], row[4]])
    elif kind == "public":
        row = db.execute(
            "SELECT seq,event_key,payload,payload_sha,prior_sha,chain_sha,committed_at "
            "FROM public_wallet_trade_receipts WHERE wallet_key=? AND instrument=? AND event_key=?",
            key,
        ).fetchone()
        expected = None if row is None else digest([key[0], key[1], row[0], row[3], row[4], row[6]])
    else:
        raise ValueError("STREAM_RECEIPT_OWNER_UNKNOWN")
    if row is None or row[3] != sha or digest(json.loads(row[2])) != sha or row[5] != expected:
        raise ValueError("STREAM_RECEIPT_DIVERGENCE")


def _head(db: sqlite3.Connection, stream_id: str) -> dict:
    row = db.execute(
        "SELECT cursor,chain_sha,checkpoint FROM observer_stream_heads WHERE stream_id=?",
        (stream_id,),
    ).fetchone()
    if row is None:
        return {"cursor": 0, "chain_sha": ZERO, "checkpoint": {}, "event": None}
    cursor, chain, checkpoint = row
    tail = db.execute(
        "SELECT event_sha,payload,receipt_refs,prior_sha,chain_sha,committed_at "
        "FROM observer_stream_events WHERE stream_id=? AND seq=?",
        (stream_id, cursor),
    ).fetchone()
    if tail is None:
        raise ValueError("STREAM_HEAD_DIVERGENCE")
    event_sha, raw, refs, prior, saved, at = tail
    event = json.loads(raw)
    if (
        digest(event) != event_sha
        or saved != chain
        or chain != digest([stream_id, cursor, event_sha, prior, at, json.loads(refs)])
        or _json(event["checkpoint"]) != checkpoint
    ):
        raise ValueError("STREAM_HEAD_DIVERGENCE")
    return {
        "cursor": cursor,
        "chain_sha": chain,
        "checkpoint": json.loads(checkpoint),
        "event": event,
        "committed_at": at,
    }


def append_checkpoint(db: sqlite3.Connection, event: dict | None, refs: list[dict]) -> dict | None:
    """Must run inside the caller's WAL/FULL transaction, before its COMMIT."""
    if event is None:
        return None
    if not db.in_transaction:
        raise ValueError("STREAM_ATOMIC_TRANSACTION_REQUIRED")
    validate_event(event)
    sid, event_sha = event["stream_id"], digest(event)
    head = _head(db, sid)
    duplicate = db.execute(
        "SELECT payload,receipt_refs,seq FROM observer_stream_events WHERE stream_id=? AND event_sha=?",
        (sid, event_sha),
    ).fetchone()
    if duplicate:
        if duplicate[0] != _json(event) or duplicate[1] != _json(refs):
            raise ValueError("STREAM_EVENT_REPLAY_CONFLICT")
        return {"cursor": duplicate[2], "status": "DUPLICATE_STREAM_EVENT"}
    if event["expected_cursor"] != head["cursor"]:
        raise ValueError("STREAM_CURSOR_CONFLICT")
    if head["event"] and clock(event["first_known_at"]) < clock(head["event"]["first_known_at"]):
        raise ValueError("STREAM_KNOWN_TIME_REGRESSION")
    committed_at = datetime.now(UTC).isoformat(timespec="microseconds")
    if clock(event["first_known_at"]) > clock(committed_at):
        raise ValueError("STREAM_RECEIPT_IN_FUTURE")
    for ref in refs:
        _receipt(db, ref)
    seq, previous = head["cursor"] + 1, head["chain_sha"]
    chain = digest([sid, seq, event_sha, previous, committed_at, refs])
    db.execute(
        "INSERT INTO observer_stream_heads VALUES (?,?,?,?) "
        "ON CONFLICT(stream_id) DO UPDATE SET cursor=excluded.cursor,"
        "chain_sha=excluded.chain_sha,checkpoint=excluded.checkpoint",
        (sid, seq, chain, _json(event["checkpoint"])),
    )
    db.execute(
        "INSERT INTO observer_stream_events VALUES (?,?,?,?,?,?,?,?)",
        (sid, seq, event_sha, _json(event), _json(refs), previous, chain, committed_at),
    )
    return {"cursor": seq, "chain_sha": chain, "status": "STREAM_COMMITTED"}


def read_stream_head(path: Path, stream_id: str) -> dict:
    with closing(sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        return _head(db, stream_id)



def verify_official_position_transition(
    db: sqlite3.Connection, *,
    alias: str, receipt_id: str, receipt_sha: str, receipt: dict,
    require_current_positions: bool = False,
) -> bool:
    """Require an atomic, first-known official OBSERVATION receipt reference.

    Caller supplies the same SQLite read transaction as the source receipt.
    An unsigned flag added by a foreign source writer is not transition proof.
    This is virtual-paper provenance, not an exchange signature or broker permit.
    """
    if (
        receipt.get("observation_kind") != "OBSERVED_STATE_CHANGE"
        or receipt.get("position_transition_eligible") is not True
        or receipt.get("signal_eligible") is not False
        or not isinstance(receipt.get("stream_epoch"), str)
    ):
        return False
    sid = "account:" + alias
    try:
        matches = db.execute(
            "SELECT e.seq,e.event_sha,e.payload,e.receipt_refs,e.prior_sha,"
            "e.chain_sha,e.committed_at FROM observer_stream_events e "
            "WHERE e.stream_id=? AND EXISTS ("
            "SELECT 1 FROM json_each(e.receipt_refs) r WHERE "
            "json_extract(r.value,'$.kind')='source' AND "
            "json_extract(r.value,'$.key[0]')=? AND "
            "json_extract(r.value,'$.key[1]')=? AND "
            "json_extract(r.value,'$.sha')=?)",
            (sid, alias, receipt_id, receipt_sha),
        ).fetchall()
        if len(matches) != 1:
            return False
        seq, event_sha, payload, refs, prior, chain, committed_at = matches[0]
        event, receipt_refs = json.loads(payload), json.loads(refs)
        if (
            digest(event) != event_sha
            or chain != digest([sid, seq, event_sha, prior, committed_at, receipt_refs])
            or event.get("kind") != "OBSERVATION"
            or event.get("epoch") != receipt["stream_epoch"]
            or event.get("first_known_at") != receipt.get("first_known_at")
            or event.get("source_event_at") != receipt.get("source_event_at")
            or event.get("raw_sha") != receipt.get("source_sha")
            or event.get("details", {}).get("classification") != "OBSERVED_STATE_CHANGE"
            or not event.get("details", {}).get("position_changes")
            or event.get("checkpoint", {}).get("positions")
            != receipt.get("source_book", {}).get("positions")
            or event.get("checkpoint", {}).get("last_receipt_sha") != digest(receipt)
        ):
            return False
        # A subsequent connection gap invalidates all earlier queued entry
        # opportunities. A fresh BASELINE is recovery, never a new signal.
        head = _head(db, sid)
        state = head["checkpoint"]
        return (
            state.get("baseline_valid") is True
            and state.get("transport") == "CONNECTED"
            and head["event"] is not None
            and head["event"]["epoch"] == event["epoch"]
            and (
                not require_current_positions
                or state.get("positions") == receipt.get("source_book", {}).get("positions")
            )
        )
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        return False

class StreamProgress:
    """Publish in-memory projection only after durable receipt/checkpoint success."""

    def __init__(self, journal, stream_id: str):
        self.journal, self.stream_id = journal, stream_id
        self.head = read_stream_head(journal.path, stream_id)

    @property
    def checkpoint(self) -> dict:
        # Return a copy: a proposed change cannot mutate committed state.
        return json.loads(_json(self.head["checkpoint"]))

    def propose(
        self,
        *,
        epoch: str,
        kind: str,
        known_at: str,
        checkpoint: dict,
        source_at: str | None = None,
        raw_sha: str | None = None,
        details: dict | None = None,
    ) -> dict:
        return stream_event(
            stream_id=self.stream_id,
            epoch=epoch,
            kind=kind,
            known_at=known_at,
            expected_cursor=self.head["cursor"],
            checkpoint=checkpoint,
            source_at=source_at,
            raw_sha=raw_sha,
            details=details,
        )

    def commit(self, event: dict, append=None) -> dict:
        result = self.journal.append_stream_event(event) if append is None else append(event)
        self.head = read_stream_head(self.journal.path, self.stream_id)
        return result


def verify_streams(path: Path) -> dict:
    """Separate read-only full-chain verifier, suitable for a watchdog process."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("STREAM_JOURNAL_FILE_INVALID")
    streams = {}
    with closing(sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("STREAM_SQLITE_INTEGRITY_FAILED")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("STREAM_SQLITE_FOREIGN_KEY_FAILED")
        ids = [
            row[0]
            for row in db.execute("SELECT stream_id FROM observer_stream_heads ORDER BY stream_id")
        ]
        for sid in ids:
            head = _head(db, sid)
            previous, last_known, last_commit = ZERO, None, None
            gaps, observations, baselines, epochs = 0, 0, 0, set()
            seq = 0
            for row in db.execute(
                "SELECT seq,event_sha,payload,receipt_refs,prior_sha,chain_sha,committed_at "
                "FROM observer_stream_events WHERE stream_id=? ORDER BY seq",
                (sid,),
            ):
                ordinal, sha, raw, raw_refs, prior, chain, at = row
                event, refs = json.loads(raw), json.loads(raw_refs)
                validate_event(event)
                known, committed = clock(event["first_known_at"]), clock(at)
                seq += 1
                if (
                    ordinal != seq
                    or event["expected_cursor"] != seq - 1
                    or event["stream_id"] != sid
                    or digest(event) != sha
                    or prior != previous
                    or chain != digest([sid, seq, sha, prior, at, refs])
                    or known > committed
                    or (last_known is not None and known < last_known)
                    or (last_commit is not None and committed < last_commit)
                ):
                    raise ValueError("STREAM_CHAIN_DIVERGENCE")
                for ref in refs:
                    _receipt(db, ref)
                previous, last_known, last_commit = chain, known, committed
                gaps += event["kind"] == "GAP"
                baselines += event["kind"] == "BASELINE"
                observations += event["kind"] == "OBSERVATION"
                epochs.add(event["epoch"])
            if seq != head["cursor"] or previous != head["chain_sha"]:
                raise ValueError("STREAM_HEAD_DIVERGENCE")
            streams[sid] = {
                **head,
                "gap_count": gaps,
                "baseline_count": baselines,
                "observation_count": observations,
                "epoch_count": len(epochs),
            }
        if db.execute(
            "SELECT 1 FROM observer_stream_events e LEFT JOIN observer_stream_heads h "
            "ON e.stream_id=h.stream_id WHERE h.stream_id IS NULL LIMIT 1"
        ).fetchone():
            raise ValueError("STREAM_ORPHANED_EVENT")
    return {
        "schema": "paper_observer_stream_audit_v1",
        "integrity": "VERIFIED",
        "streams": streams,
        "head_sha": digest(streams),
        "paper_admitted": False,
        "order_route": "NONE",
    }
