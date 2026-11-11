"""Durable, original-backed Vike candidate SourceBook; never a paper authority.

This is deliberately co-located with the original observation SQLite DB so a
projected checkpoint and its referenced wire row share one WAL transaction.
A candidate is NOT an OBSERVED_STATE_CHANGE and cannot satisfy the V4 official
source verifier. Each start/reconnect requires a new, nonactionable epoch and
fresh independently verified official REST archive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from .pm03_account import clock, digest
from .pm_vike_official_parity import verify_archived_official_census
from .pm_vike_position_observations import checkpoint as transport_checkpoint
from .pm_vike_reconciled_positions import (
    CandidatePositionBook,
    candidate_from_vike_event,
    mark_gap,
    reconcile_candidate_with_official,
    start_nonactionable_baseline,
)
from .pm_vike_stream_canary import allowed_wallet

SCHEMA = """
CREATE TABLE IF NOT EXISTS selected_position_candidate_heads (
 account_sha256 TEXT PRIMARY KEY,
 revision INTEGER NOT NULL,
 state_json TEXT NOT NULL,
 state_sha256 TEXT NOT NULL,
 chain_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selected_position_candidate_history (
 account_sha256 TEXT NOT NULL,
 revision INTEGER NOT NULL,
 kind TEXT NOT NULL,
 source_event_id TEXT,
 source_cursor TEXT,
 original_wire_sha256 TEXT,
 original_manifest_sha256 TEXT,
 first_known_at TEXT NOT NULL,
 committed_at TEXT NOT NULL,
 state_json TEXT NOT NULL,
 state_sha256 TEXT NOT NULL,
 prior_chain_sha256 TEXT NOT NULL,
 chain_sha256 TEXT NOT NULL,
 PRIMARY KEY(account_sha256,revision),
 UNIQUE(account_sha256,source_event_id)
);
"""
ZERO = "0" * 64
HEX = re.compile(r"[0-9a-f]{64}\Z")
KINDS = {"BASELINE", "POSITION_EVENT", "OFFICIAL_RECONCILIATION", "GAP"}


def initialize(db: sqlite3.Connection) -> None:
    """Create only bounded, indexed tables; never scan the original event tape."""
    db.executescript(SCHEMA)


def _wire_object(raw: str) -> dict:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("VIKE_CANDIDATE_DUPLICATE_ORIGINAL_KEY")
            result[key] = value
        return result

    parsed = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(parsed, dict):
        raise ValueError("VIKE_CANDIDATE_ORIGINAL_NOT_OBJECT")
    return parsed


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _head(
    db: sqlite3.Connection, account_sha: str
) -> tuple[int, CandidatePositionBook | None, str]:
    row = db.execute(
        "SELECT revision,state_json,state_sha256,chain_sha256 "
        "FROM selected_position_candidate_heads WHERE account_sha256=?",
        (account_sha,),
    ).fetchone()
    if row is None:
        return 0, None, ZERO
    revision, serialized, state_sha, chain_sha = row
    if sha256(serialized.encode()).hexdigest() != state_sha:
        raise ValueError("VIKE_CANDIDATE_HEAD_HASH_MISMATCH")
    state = CandidatePositionBook.model_validate_json(serialized, strict=True)
    if state.account_sha256 != account_sha:
        raise ValueError("VIKE_CANDIDATE_HEAD_ACCOUNT_MISMATCH")
    last = db.execute(
        "SELECT state_sha256,chain_sha256 FROM selected_position_candidate_history "
        "WHERE account_sha256=? AND revision=?",
        (account_sha, revision),
    ).fetchone()
    if last != (state_sha, chain_sha):
        raise ValueError("VIKE_CANDIDATE_HEAD_HISTORY_DIVERGENCE")
    return revision, state, chain_sha


def _append(
    db: sqlite3.Connection,
    *,
    account_sha: str,
    state: CandidatePositionBook,
    kind: str,
    known_at: str,
    source_event_id: str | None = None,
    source_cursor: str | None = None,
    wire_sha: str | None = None,
    manifest_sha: str | None = None,
) -> dict:
    if kind not in KINDS or state.account_sha256 != account_sha:
        raise ValueError("VIKE_CANDIDATE_KIND_OR_ACCOUNT_INVALID")
    revision, _, prior = _head(db, account_sha)
    committed_at = datetime.now(UTC).isoformat(timespec="microseconds")
    if clock(known_at) > clock(committed_at):
        raise ValueError("VIKE_CANDIDATE_KNOWN_AFTER_COMMIT")
    serialized = _canonical(state.model_dump(mode="json"))
    state_sha = sha256(serialized.encode()).hexdigest()
    chain_sha = digest(
        [
            account_sha,
            revision + 1,
            kind,
            source_event_id,
            source_cursor,
            wire_sha,
            manifest_sha,
            known_at,
            committed_at,
            state_sha,
            prior,
        ]
    )
    db.execute(
        "INSERT INTO selected_position_candidate_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            account_sha,
            revision + 1,
            kind,
            source_event_id,
            source_cursor,
            wire_sha,
            manifest_sha,
            known_at,
            committed_at,
            serialized,
            state_sha,
            prior,
            chain_sha,
        ),
    )
    db.execute(
        "INSERT INTO selected_position_candidate_heads VALUES(?,?,?,?,?) "
        "ON CONFLICT(account_sha256) DO UPDATE SET "
        "revision=excluded.revision,state_json=excluded.state_json,"
        "state_sha256=excluded.state_sha256,chain_sha256=excluded.chain_sha256",
        (account_sha, revision + 1, serialized, state_sha, chain_sha),
    )
    return {
        "status": state.status,
        "revision": revision + 1,
        "state_sha256": state_sha,
        "chain_sha256": chain_sha,
        "paper_new_risk_eligible": False,
        "order_route": "NONE",
    }


def begin_epoch(
    db: sqlite3.Connection,
    *,
    account: str,
    archive_dir: Path,
    manifest_sha256: str,
    subscription_ack_at: str,
    stream_cursor: str,
    epoch_id: str,
) -> dict:
    """Verified complete baseline after subscription ACK, never an entry.

    A prior GAP cannot be cleared retrospectively. New epochs may establish
    a fresh nonactionable baseline; old events never become new opportunities.
    """
    wallet = allowed_wallet(account)
    account_sha = sha256(wallet.encode()).hexdigest()
    if HEX.fullmatch(manifest_sha256) is None:
        raise ValueError("VIKE_CANDIDATE_ARCHIVE_HASH_INVALID")
    census = verify_archived_official_census(
        wallet, directory=archive_dir, manifest_sha256=manifest_sha256
    )
    with db:
        db.execute("BEGIN IMMEDIATE")
        subscribed = db.execute(
            "SELECT acknowledged_at FROM selected_position_subscription WHERE id=1"
        ).fetchone()
        checkpoint_cursor, transport_gap = transport_checkpoint(db)
        if (
            subscribed is None
            or clock(subscribed[0]) != clock(subscription_ack_at)
            or checkpoint_cursor != stream_cursor
        ):
            raise ValueError("VIKE_CANDIDATE_ORIGINAL_SUBSCRIPTION_NOT_BOUND")
        state = start_nonactionable_baseline(
            wallet,
            official_census=census,
            manifest_sha256=manifest_sha256,
            live_subscription_ack_at=subscription_ack_at,
            stream_cursor=stream_cursor,
            stream_epoch=epoch_id,
            had_gap=transport_gap,
        )
        old_revision, old, _ = _head(db, account_sha)
        if old_revision and old is not None and old.epoch_id == epoch_id:
            raise ValueError("VIKE_CANDIDATE_REUSED_STREAM_EPOCH")
        return _append(
            db,
            account_sha=account_sha,
            state=state,
            kind="BASELINE",
            known_at=census["completed_at"],
            manifest_sha=manifest_sha256,
            source_cursor=stream_cursor,
        )


def observe_committed_original(
    db: sqlite3.Connection, *, account: str, event_id: str, epoch_id: str
) -> dict:
    """Project exactly one original WAL-committed event atomically.

    The event is read from the immutable original table inside the *same*
    transaction as the derived checkpoint. No caller-supplied event payload,
    source timestamp, or eligibility flag can replace original evidence.
    """
    wallet = allowed_wallet(account)
    account_sha = sha256(wallet.encode()).hexdigest()
    with db:
        db.execute("BEGIN IMMEDIATE")
        revision, state, _ = _head(db, account_sha)
        if not revision or state is None:
            raise ValueError("VIKE_CANDIDATE_REQUIRES_BASELINE")
        existing = db.execute(
            "SELECT revision,original_wire_sha256 FROM selected_position_candidate_history "
            "WHERE account_sha256=? AND source_event_id=?",
            (account_sha, event_id),
        ).fetchone()
        row = db.execute(
            "SELECT cursor,account_sha256,event_at,first_known_at,"
            "raw_wire_sha256,raw_event_sha256,raw_wire,prospective "
            "FROM selected_position_events WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if row is None or row[1] != account_sha:
            raise ValueError("VIKE_CANDIDATE_ORIGINAL_EVENT_MISSING_OR_FOREIGN")
        cursor, _, event_at, known_at, wire_sha, event_sha, wire, prospective = row
        if not isinstance(wire, str) or sha256(wire.encode()).hexdigest() != wire_sha:
            raise ValueError("VIKE_CANDIDATE_ORIGINAL_WIRE_HASH_MISMATCH")
        frame = _wire_object(wire)
        if (
            frame.get("type") != "event"
            or frame.get("event", {}).get("event_id") != event_id
            or frame.get("cursor") != cursor
        ):
            raise ValueError("VIKE_CANDIDATE_ORIGINAL_FRAME_MISMATCH")
        event = frame["event"]
        if (
            sha256(_canonical(event).encode()).hexdigest() != event_sha
            or event.get("ts") != event_at
        ):
            raise ValueError("VIKE_CANDIDATE_ORIGINAL_EVENT_HASH_MISMATCH")
        if existing:
            if existing[1] != wire_sha:
                raise ValueError("VIKE_CANDIDATE_DUPLICATE_ORIGINAL_CONFLICT")
            return {
                "status": "DUPLICATE_NO_MUTATION",
                "revision": existing[0],
                "paper_new_risk_eligible": False,
                "order_route": "NONE",
            }
        _, gap = transport_checkpoint(db)
        new = candidate_from_vike_event(
            state,
            event=event,
            raw_event_sha256=event_sha,
            cursor=cursor,
            local_first_known_at=known_at,
            is_prospective=bool(prospective),
            has_stream_gap=gap,
            epoch_id=epoch_id,
        )
        return _append(
            db,
            account_sha=account_sha,
            state=new,
            kind="POSITION_EVENT",
            known_at=known_at,
            source_event_id=event_id,
            source_cursor=cursor,
            wire_sha=wire_sha,
        )


def reconcile_official_archive(
    db: sqlite3.Connection, *, account: str, archive_dir: Path, manifest_sha256: str
) -> dict:
    """Independently verify new original official bytes before comparing books."""
    wallet = allowed_wallet(account)
    account_sha = sha256(wallet.encode()).hexdigest()
    if HEX.fullmatch(manifest_sha256) is None:
        raise ValueError("VIKE_CANDIDATE_ARCHIVE_HASH_INVALID")
    census = verify_archived_official_census(
        wallet, directory=archive_dir, manifest_sha256=manifest_sha256
    )
    with db:
        db.execute("BEGIN IMMEDIATE")
        _, state, _ = _head(db, account_sha)
        if state is None:
            raise ValueError("VIKE_CANDIDATE_REQUIRES_BASELINE")
        _, gap = transport_checkpoint(db)
        if gap:
            new = mark_gap(state, reason="PROVIDER_POSITION_CHANNEL_GAP")
        else:
            new = reconcile_candidate_with_official(
                state, verified_census=census, manifest_sha256=manifest_sha256
            )
        return _append(
            db,
            account_sha=account_sha,
            state=new,
            kind="OFFICIAL_RECONCILIATION",
            known_at=census["completed_at"],
            manifest_sha=manifest_sha256,
        )


def gap(db: sqlite3.Connection, *, account: str, reason: str, known_at: str) -> dict:
    wallet = allowed_wallet(account)
    account_sha = sha256(wallet.encode()).hexdigest()
    with db:
        db.execute("BEGIN IMMEDIATE")
        _, state, _ = _head(db, account_sha)
        if state is None:
            raise ValueError("VIKE_CANDIDATE_REQUIRES_BASELINE")
        return _append(
            db,
            account_sha=account_sha,
            state=mark_gap(state, reason=reason),
            kind="GAP",
            known_at=known_at,
        )


def status(db: sqlite3.Connection, *, account: str) -> dict:
    wallet = allowed_wallet(account)
    account_sha = sha256(wallet.encode()).hexdigest()
    rev, state, chain = _head(db, account_sha)
    _, transport_gap = transport_checkpoint(db)
    return {
        "schema": "vike_original_backed_candidate_journal_v1",
        "revision": rev,
        "chain_sha256": chain,
        "state": state.model_dump(mode="json") if state is not None else None,
        "transport_gap": transport_gap,
        "source_authority": "NONE_CANDIDATE_ONLY",
        "paper_new_risk_eligible": False,
        "order_route": "NONE",
    }


def verify_history(db: sqlite3.Connection, *, account: str, max_rows: int = 5000) -> dict:
    """Bounded full candidate chain audit; fail instead of scanning forever."""
    wallet = allowed_wallet(account)
    account_sha = sha256(wallet.encode()).hexdigest()
    if not 1 <= max_rows <= 100000:
        raise ValueError("VIKE_CANDIDATE_AUDIT_BOUNDS_INVALID")
    total = db.execute(
        "SELECT COUNT(*) FROM selected_position_candidate_history WHERE account_sha256=?",
        (account_sha,),
    ).fetchone()[0]
    if total > max_rows:
        raise ValueError("VIKE_CANDIDATE_AUDIT_REQUIRES_BOUNDED_WINDOW")
    prior = ZERO
    for expected, row in enumerate(
        db.execute(
            "SELECT revision,kind,source_event_id,source_cursor,original_wire_sha256,"
            "original_manifest_sha256,first_known_at,committed_at,state_json,"
            "state_sha256,prior_chain_sha256,chain_sha256 "
            "FROM selected_position_candidate_history WHERE account_sha256=? "
            "ORDER BY revision",
            (account_sha,),
        ),
        start=1,
    ):
        (
            revision,
            kind,
            eid,
            cursor,
            wire_sha,
            manifest_sha,
            known_at,
            committed_at,
            payload,
            state_sha,
            previous,
            chain_sha,
        ) = row
        if (
            revision != expected
            or previous != prior
            or kind not in KINDS
            or sha256(payload.encode()).hexdigest() != state_sha
            or digest(
                [
                    account_sha,
                    revision,
                    kind,
                    eid,
                    cursor,
                    wire_sha,
                    manifest_sha,
                    known_at,
                    committed_at,
                    state_sha,
                    prior,
                ]
            )
            != chain_sha
        ):
            raise ValueError("VIKE_CANDIDATE_HISTORY_CHAIN_DIVERGENCE")
        state = CandidatePositionBook.model_validate_json(payload, strict=True)
        if state.account_sha256 != account_sha:
            raise ValueError("VIKE_CANDIDATE_HISTORY_ACCOUNT_DIVERGENCE")
        if eid is not None:
            source = db.execute(
                "SELECT cursor,account_sha256,event_at,first_known_at,"
                "raw_wire_sha256,raw_event_sha256,raw_wire "
                "FROM selected_position_events WHERE event_id=?",
                (eid,),
            ).fetchone()
            if source is None:
                raise ValueError("VIKE_CANDIDATE_HISTORY_ORIGINAL_MISSING")
            (
                original_cursor,
                original_account,
                original_at,
                original_known,
                original_wire_sha,
                original_event_sha,
                raw_wire,
            ) = source
            if (
                original_cursor != cursor
                or original_account != account_sha
                or original_known != known_at
                or original_wire_sha != wire_sha
                or sha256(raw_wire.encode()).hexdigest() != wire_sha
            ):
                raise ValueError("VIKE_CANDIDATE_HISTORY_ORIGINAL_DIVERGENCE")
            frame = _wire_object(raw_wire)
            original_event = frame.get("event")
            if (
                frame.get("type") != "event"
                or frame.get("cursor") != cursor
                or not isinstance(original_event, dict)
                or original_event.get("event_id") != eid
                or original_event.get("ts") != original_at
                or sha256(_canonical(original_event).encode()).hexdigest() != original_event_sha
            ):
                raise ValueError("VIKE_CANDIDATE_HISTORY_ORIGINAL_DIVERGENCE")
        prior = chain_sha
    revision, _, head_chain = _head(db, account_sha)
    if revision != total or head_chain != prior:
        raise ValueError("VIKE_CANDIDATE_HISTORY_HEAD_DIVERGENCE")
    return {
        "schema": "vike_candidate_chain_audit_v1",
        "events_verified": total,
        "head_sha256": prior,
        "paper_new_risk_eligible": False,
        "order_route": "NONE",
    }
