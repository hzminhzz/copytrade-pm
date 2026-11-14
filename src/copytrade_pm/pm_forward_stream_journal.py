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
CREATE TABLE IF NOT EXISTS observer_source_locator_coverage (
    stream_id TEXT PRIMARY KEY,
    verified_through INTEGER NOT NULL CHECK (verified_through >= 0)
);
CREATE TABLE IF NOT EXISTS observer_source_health (
    stream_id TEXT PRIMARY KEY,
    epoch TEXT NOT NULL,
    account_sha TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    source_event_at TEXT,
    dex_clocks TEXT NOT NULL,
    position_sha TEXT NOT NULL,
    transport TEXT NOT NULL,
    freshness_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observer_source_locators (
    source_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    receipt_sha TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    event_seq INTEGER NOT NULL,
    PRIMARY KEY(source_id, receipt_id, receipt_sha),
    UNIQUE(stream_id, event_seq, source_id, receipt_id),
    FOREIGN KEY(stream_id, event_seq)
        REFERENCES observer_stream_events(stream_id, seq)
);
"""
# This scans historical payloads. Build ONLY during an operator-quiesced
# additive migration, never during PaperJournal startup on a live multi-GB DB.
INTERRUPTION_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS observer_stream_interruptions_idx
ON observer_stream_events(stream_id, seq)
WHERE json_extract(payload, '$.kind') IN ('GAP','BASELINE','SCOPE');
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
    compact_v2: bool = False,
) -> dict:
    result = {
        "schema": "paper_observer_stream_event_v2"
        if compact_v2
        else "paper_observer_stream_event_v1",
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
        or event.get("schema")
        not in ("paper_observer_stream_event_v1", "paper_observer_stream_event_v2")
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
    if event["schema"] == "paper_observer_stream_event_v2":
        details = event["details"]
        if event["kind"] in ("BASELINE", "OBSERVATION"):
            if (
                details.get("native_wire_ref") != event.get("raw_sha")
                or not isinstance(details.get("native_frame_sha"), str)
                or re.fullmatch(r"[0-9a-f]{64}", details["native_frame_sha"]) is None
                or details.get("native_wire") is not None
                or details.get("native_frame") is not None
            ):
                raise ValueError("STREAM_V2_EVIDENCE_REFERENCE_INVALID")
        elif (
            event["kind"] not in ("GAP", "SCOPE", "TRANSPORT", "STOP")
            or event.get("raw_sha") is not None
            or details.get("native_wire_ref") is not None
            or details.get("native_frame") is not None
        ):
            raise ValueError("STREAM_V2_NON_ECONOMIC_INVALID")
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
    if sid.startswith("account:"):
        checkpoint = event["checkpoint"]
        db.execute(
            "INSERT INTO observer_source_health VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(stream_id) DO UPDATE SET epoch=excluded.epoch,"
            "account_sha=excluded.account_sha,validated_at=excluded.validated_at,"
            "source_event_at=excluded.source_event_at,dex_clocks=excluded.dex_clocks,"
            "position_sha=excluded.position_sha,transport=excluded.transport,"
            "freshness_status=excluded.freshness_status",
            (
                sid,
                event["epoch"],
                checkpoint.get("account_sha", ""),
                event["first_known_at"],
                checkpoint.get("source_event_at"),
                _json(checkpoint.get("dex_clocks", {})),
                checkpoint.get("economic_sha", ""),
                checkpoint.get("transport", "UNKNOWN"),
                "VALID" if checkpoint.get("baseline_valid") else "BASELINE_REQUIRED",
            ),
        )
    for ref in refs:
        if ref["kind"] == "source":
            db.execute(
                "INSERT INTO observer_source_locators VALUES (?,?,?,?,?)",
                (ref["key"][0], ref["key"][1], ref["sha"], sid, seq),
            )
    # A legacy stream has no coverage marker until a separately verified
    # migration. Never declare its old receipts indexed from one new append.
    if head["cursor"] == 0:
        db.execute("INSERT OR IGNORE INTO observer_source_locator_coverage VALUES (?,0)", (sid,))
    db.execute(
        "UPDATE observer_source_locator_coverage SET verified_through=? "
        "WHERE stream_id=? AND verified_through=?",
        (seq, sid, head["cursor"]),
    )
    return {"cursor": seq, "chain_sha": chain, "status": "STREAM_COMMITTED"}


def backfill_verified_source_locators(path: Path, *, quiescence_verified: bool = False) -> dict:
    """Offline, additive v1 index migration; preserves every original hash.

    Requires operator-verified quiescence and a restored, independently verified
    backup. Never call on an active source journal. A full-chain audit precedes
    and follows the transaction; a failed row check rolls back all locators.
    """
    if not quiescence_verified:
        raise ValueError("STREAM_LOCATOR_BACKFILL_REQUIRES_QUIESCENCE")
    before = verify_streams(path)
    written = 0
    with closing(sqlite3.connect(path, timeout=1.0)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        # Upgrade previously created v1 journals without rewriting any old
        # source/stream evidence. Metadata DDL is safe to retry after failure.
        db.executescript(SCHEMA)
        db.executescript(INTERRUPTION_INDEX_SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        try:
            # This migration is additive on previously initialized journals.
            for sid, stream in sorted(before["streams"].items()):
                for seq, raw_refs in db.execute(
                    "SELECT seq,receipt_refs FROM observer_stream_events "
                    "WHERE stream_id=? ORDER BY seq",
                    (sid,),
                ):
                    refs = json.loads(raw_refs)
                    for ref in refs:
                        if ref["kind"] != "source":
                            continue
                        _receipt(db, ref)
                        values = (ref["key"][0], ref["key"][1], ref["sha"], sid, seq)
                        existing = db.execute(
                            "SELECT source_id,receipt_id,receipt_sha,stream_id,event_seq "
                            "FROM observer_source_locators "
                            "WHERE source_id=? AND receipt_id=? AND receipt_sha=?",
                            values[:3],
                        ).fetchone()
                        if existing is not None and tuple(existing) != values:
                            raise ValueError("STREAM_LOCATOR_BACKFILL_CONFLICT")
                        if existing is None:
                            db.execute(
                                "INSERT INTO observer_source_locators VALUES (?,?,?,?,?)", values
                            )
                            written += 1
                db.execute(
                    "INSERT INTO observer_source_locator_coverage VALUES (?,?) "
                    "ON CONFLICT(stream_id) DO UPDATE SET verified_through=excluded.verified_through",
                    (sid, stream["cursor"]),
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
    after = verify_streams(path)
    if before["head_sha"] != after["head_sha"]:
        raise ValueError("STREAM_LOCATOR_BACKFILL_CHANGED_EVIDENCE")
    return {
        "status": "VERIFIED_ADDITIVE_ONLY",
        "indexed_receipts": written,
        "original_stream_head_sha": before["head_sha"],
    }


def read_stream_head(path: Path, stream_id: str) -> dict:
    with closing(sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        return _head(db, stream_id)


def _verified_frame_sha(db: sqlite3.Connection, event: dict) -> str:
    """Resolve raw original proof without trusting an index or hash-only claim."""
    if event.get("schema") != "paper_observer_stream_event_v2":
        return digest(event.get("details", {}).get("native_frame"))
    from .pm_wire_evidence import read_wire

    db_file = db.execute("PRAGMA database_list").fetchone()[2]
    if not db_file:
        raise ValueError("V4_EVIDENCE_DATABASE_PATH_MISSING")
    if event.get("kind") not in ("BASELINE", "OBSERVATION"):
        return ""
    raw_sha = event.get("raw_sha")
    details = event["details"]
    raw = read_wire(Path(db_file), raw_sha)

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("V4_EVIDENCE_DUPLICATE_JSON_FIELD")
            result[key] = value
        return result

    parsed = json.loads(raw, object_pairs_hook=reject_duplicates)
    verified = digest(parsed)
    if verified != details.get("native_frame_sha"):
        raise ValueError("V4_EVIDENCE_NATIVE_FRAME_HASH_MISMATCH")
    return verified


def verify_official_position_transition(
    db: sqlite3.Connection,
    *,
    alias: str,
    receipt_id: str,
    receipt_sha: str,
    receipt: dict,
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
        # A missing active baseline, disconnected source or changed epoch
        # invalidates an old pending T+300 attempt regardless of its original
        # historical receipt. Check indexed current head BEFORE attempting the
        # potentially unbounded legacy v1 json_each locator fallback. This is
        # a negative admission fence, not proof that a surviving receipt is
        # authentic; all original proof checks below still run when eligible.
        current_head = db.execute(
            "SELECT cursor,checkpoint FROM observer_stream_heads WHERE stream_id=?",
            (sid,),
        ).fetchone()
        if current_head is None:
            return False
        current_state = json.loads(current_head[1])
        if (
            current_state.get("baseline_valid") is not True
            or current_state.get("transport") != "CONNECTED"
            or (
                require_current_positions
                and current_state.get("positions")
                != receipt.get("source_book", {}).get("positions")
            )
        ):
            return False
        epoch = db.execute(
            "SELECT json_extract(payload, '$.epoch') FROM observer_stream_events "
            "WHERE stream_id=? AND seq=?",
            (sid, current_head[0]),
        ).fetchone()
        if epoch is None or epoch[0] != receipt["stream_epoch"]:
            return False
        # Native BASELINE after a GAP may reuse the same source epoch in a
        # process. A more recently first-known completed source state fences
        # all earlier pending intents even when the resulting positions match.
        # Without this O(1) negative guard an old v1 receipt may force an
        # unbounded json_each scan over 400k+ original stream rows at each
        # V4 paper tick. Missing legacy clocks keep the existing proof path.
        last_state = current_state.get("last_state_at")
        if isinstance(last_state, str) and clock(last_state) > clock(receipt["first_known_at"]):
            return False
        indexed = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observer_source_locators'"
        ).fetchone()
        coverage = (
            db.execute(
                "SELECT verified_through FROM observer_source_locator_coverage WHERE stream_id=?",
                (sid,),
            ).fetchone()
            if indexed
            and db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='observer_source_locator_coverage'"
            ).fetchone()
            else None
        )
        indexed_matches = (
            db.execute(
                "SELECT e.seq,e.event_sha,e.payload,e.receipt_refs,e.prior_sha,"
                "e.chain_sha,e.committed_at FROM observer_source_locators l "
                "JOIN observer_stream_events e "
                "ON e.stream_id=l.stream_id AND e.seq=l.event_seq "
                "WHERE l.stream_id=? AND l.source_id=? AND l.receipt_id=? "
                "AND l.receipt_sha=?",
                (sid, alias, receipt_id, receipt_sha),
            ).fetchall()
            if indexed
            else []
        )
        if indexed_matches:
            # New receipts use indexed proof immediately even on a legacy
            # stream whose old rows have not been backfilled. The actual
            # referenced original event and chain are still independently
            # validated below; the locator alone never grants eligibility.
            matches = indexed_matches
        else:
            head_cursor = db.execute(
                "SELECT cursor FROM observer_stream_heads WHERE stream_id=?", (sid,)
            ).fetchone()
            if coverage is not None and head_cursor is not None and coverage[0] == head_cursor[0]:
                return False
            # Old v1 receipts remain readable until verified offline backfill.
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
        if not any(
            ref.get("kind") == "source"
            and ref.get("key") == [alias, receipt_id]
            and ref.get("sha") == receipt_sha
            for ref in receipt_refs
        ):
            return False
        if (
            digest(event) != event_sha
            or chain != digest([sid, seq, event_sha, prior, committed_at, receipt_refs])
            or event.get("kind") != "OBSERVATION"
            or event.get("epoch") != receipt["stream_epoch"]
            or event.get("first_known_at") != receipt.get("first_known_at")
            or event.get("source_event_at") != receipt.get("source_event_at")
            or _verified_frame_sha(db, event) != receipt.get("source_sha")
            or (
                event.get("schema") == "paper_observer_stream_event_v1"
                and event.get("details", {}).get("native_wire") is None
                and event.get("raw_sha") != receipt.get("source_sha")
            )
            or event.get("details", {}).get("classification") != "OBSERVED_STATE_CHANGE"
            or not event.get("details", {}).get("position_changes")
            or event.get("checkpoint", {}).get("positions")
            != receipt.get("source_book", {}).get("positions")
            or event.get("checkpoint", {}).get("last_receipt_sha") != digest(receipt)
        ):
            return False
        # Even a same-epoch GAP followed by a new BASELINE invalidates the
        # earlier new-risk intent. Do not rely on epoch comparison alone.
        interruption = db.execute(
            "SELECT 1 FROM observer_stream_events WHERE stream_id=? AND seq>? "
            "AND json_extract(payload, '$.kind') IN ('GAP','BASELINE','SCOPE') LIMIT 1",
            (sid, seq),
        ).fetchone()
        if interruption is not None:
            return False
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
    except sqlite3.Error, ValueError, KeyError, TypeError:
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
        compact_v2: bool = False,
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
            compact_v2=compact_v2,
        )

    def commit(self, event: dict, append=None) -> dict:
        result = self.journal.append_stream_event(event) if append is None else append(event)
        self.head = read_stream_head(self.journal.path, self.stream_id)
        return result


def verify_stream_heads_fast(path: Path) -> dict:
    """Bounded startup verification of current immutable proof heads only.

    This does NOT certify the complete historical journal. Full
    :func:`verify_streams` remains the separate operator/auditor step, and
    the producer MUST start a new GAP/BASELINE epoch before risk admission.
    Runtime restart must not deserialize 200k-400k historical native frames.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("STREAM_JOURNAL_FILE_INVALID")
    heads: list[tuple[str, int, str]] = []
    with closing(sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for sid, cursor, chain in db.execute(
            "SELECT stream_id,cursor,chain_sha FROM observer_stream_heads ORDER BY stream_id"
        ):
            if type(cursor) is not int or cursor < 1:
                raise ValueError("STREAM_HEAD_CURSOR_INVALID")
            head = _head(db, sid)
            if head["cursor"] != cursor or head["chain_sha"] != chain:
                raise ValueError("STREAM_HEAD_DIVERGENCE")
            row = db.execute(
                "SELECT event_sha,payload,receipt_refs,prior_sha,chain_sha,committed_at "
                "FROM observer_stream_events WHERE stream_id=? AND seq=?",
                (sid, cursor),
            ).fetchone()
            if row is None:
                raise ValueError("STREAM_HEAD_DIVERGENCE")
            event_sha, raw, refs_raw, prior, saved_chain, committed_at = row
            event, refs = json.loads(raw), json.loads(refs_raw)
            validate_event(event)
            if (
                event["expected_cursor"] != cursor - 1
                or event["stream_id"] != sid
                or digest(event) != event_sha
                or saved_chain != chain
                or clock(event["first_known_at"]) > clock(committed_at)
            ):
                raise ValueError("STREAM_TAIL_DIVERGENCE")
            if cursor == 1:
                if prior != ZERO:
                    raise ValueError("STREAM_TAIL_PREDECESSOR_DIVERGENCE")
            else:
                predecessor = db.execute(
                    "SELECT chain_sha FROM observer_stream_events WHERE stream_id=? AND seq=?",
                    (sid, cursor - 1),
                ).fetchone()
                if predecessor is None or prior != predecessor[0]:
                    raise ValueError("STREAM_TAIL_PREDECESSOR_DIVERGENCE")
            if event.get("schema") == "paper_observer_stream_event_v2" and event["kind"] in (
                "BASELINE",
                "OBSERVATION",
            ):
                _verified_frame_sha(db, event)
            for ref in refs:
                _receipt(db, ref)
            if sid.startswith("account:"):
                alias = sid.removeprefix("account:")
                latest = db.execute(
                    "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
                    "FROM source_receipts WHERE source_id=? ORDER BY seq DESC LIMIT 1",
                    (alias,),
                ).fetchone()
                if latest is not None:
                    seq, rid, payload, receipt_sha, receipt_prior, receipt_chain = latest
                    original = json.loads(payload)
                    if (
                        original.get("source_id") != alias
                        or digest(original) != receipt_sha
                        or receipt_chain != digest([alias, seq, rid, receipt_prior, receipt_sha])
                    ):
                        raise ValueError("STREAM_SOURCE_TAIL_DIVERGENCE")
                    if seq == 1:
                        if receipt_prior != ZERO:
                            raise ValueError("STREAM_SOURCE_PREDECESSOR_DIVERGENCE")
                    else:
                        prior_receipt = db.execute(
                            "SELECT chain_sha FROM source_receipts WHERE source_id=? AND seq=?",
                            (alias, seq - 1),
                        ).fetchone()
                        if prior_receipt is None or receipt_prior != prior_receipt[0]:
                            raise ValueError("STREAM_SOURCE_PREDECESSOR_DIVERGENCE")
                    expected_receipt_sha = head["checkpoint"].get("last_receipt_sha")
                    if expected_receipt_sha is not None and expected_receipt_sha != receipt_sha:
                        raise ValueError("STREAM_SOURCE_CHECKPOINT_DIVERGENCE")
            heads.append((sid, cursor, chain))
        db.execute("ROLLBACK")
    return {
        "schema": "paper_observer_stream_head_preflight_v1",
        "status": "TAILS_VERIFIED_HISTORICAL_AUDIT_PENDING",
        "stream_count": len(heads),
        "stream_head_sha": digest(heads),
        "complete_historical_integrity_verified": False,
        "paper_admitted": False,
        "order_route": "NONE",
    }


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
                if event["schema"] == "paper_observer_stream_event_v2" and event["kind"] in (
                    "BASELINE",
                    "OBSERVATION",
                ):
                    _verified_frame_sha(db, event)
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
