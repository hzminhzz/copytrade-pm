"""Durable, nonfinancial CWSA wave receipts for isolated Chapter 2 paper journals.

A canonical source writes one wallet result at a time. A portfolio may only
record a checkpoint when all expected results are published, or when the
source's original publication window has expired. Once recorded, a checkpoint
never changes because of a late-arriving source result.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import json
import sqlite3
from typing import Any

from .pm03_account import digest
from .pm_checkpoint_journal import CheckpointOutcome, CwsaPolicy

SCHEMA = """
CREATE TABLE IF NOT EXISTS chapter2_wave_receipts (
    checkpoint_ms INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,
    receipt_sha TEXT NOT NULL
);
"""
COMPLETE_KINDS = frozenset({"BASELINE", "UNCHANGED", "CHANGED", "RECOVERY_BASELINE"})


def publication_grace_ms(source_db, *, override: int | None = None) -> int:
    """Use the source's immutable policy, not a second strategy threshold."""
    if override is not None:
        if type(override) is not int or override <= 0:
            raise ValueError("CHAPTER2_PUBLICATION_GRACE")
        return override
    if not source_db.is_file():
        raise ValueError("CHAPTER2_SOURCE_NOT_AVAILABLE")
    with closing(sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)) as db:
        policies = db.execute("SELECT DISTINCT policy FROM cwsa_heads").fetchall()
    if not policies:
        raise ValueError("CHAPTER2_SOURCE_POLICY_NOT_REGISTERED")
    values = {
        CwsaPolicy.model_validate_json(row[0]).limits.publication_grace_ms for row in policies
    }
    if len(values) != 1 or min(values) <= 0:
        raise ValueError("CHAPTER2_SOURCE_POLICY_MISMATCH")
    return values.pop()


def parse_outcome(stream: str, checkpoint_ms: int, raw: str, candidate_sha: str) -> dict:
    """Check source-row identity and published candidate bytes before observation."""
    outcome = CheckpointOutcome.model_validate_json(raw)
    if (
        outcome.checkpoint_ms != checkpoint_ms
        or outcome.outcome_id != digest(["cwsa_outcome_v3", stream, checkpoint_ms])
        or (outcome.kind == "CHANGED") != (outcome.signal_id is not None)
        or (
            outcome.sample is not None
            and digest(outcome.sample.model_dump(mode="json")) != candidate_sha
        )
    ):
        raise ValueError("CHAPTER2_SOURCE_OUTCOME_CONFLICT")
    return {
        "source_id": outcome.source_id,
        "stream": stream,
        "outcome_id": outcome.outcome_id,
        "outcome_sha": digest(outcome.model_dump(mode="json")),
        "kind": outcome.kind,
        "published_ms": outcome.published_ms,
        "policy_epoch": outcome.policy_epoch,
        "scope_generation": outcome.scope_generation,
    }


class WaveReceipts:
    """Immutable observation ledger; never claims a financial or execution effect."""

    def __init__(self, journal) -> None:
        self.journal = journal
        with journal._writer() as db:
            db.execute(SCHEMA)
        self.last_checkpoint_ms = 0
        self.last_receipt_sha = "0" * 64
        with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as db:
            rows = db.execute(
                "SELECT checkpoint_ms,payload,receipt_sha FROM chapter2_wave_receipts "
                "ORDER BY checkpoint_ms"
            ).fetchall()
        for checkpoint_ms, raw, sha in rows:
            payload = json.loads(raw)
            if (
                digest(payload) != sha
                or payload.get("schema") != "chapter2_wave_receipt_v1"
                or payload.get("checkpoint_ms") != checkpoint_ms
                or payload.get("prior_sha") != self.last_receipt_sha
                or checkpoint_ms <= self.last_checkpoint_ms
            ):
                raise ValueError("CHAPTER2_WAVE_RECEIPT_TAMPERED")
            self.last_checkpoint_ms = checkpoint_ms
            self.last_receipt_sha = sha

    def latest(self) -> dict | None:
        """Return the most recent journal-verified wave after restart."""
        if not self.last_checkpoint_ms:
            return None
        with closing(sqlite3.connect(f"file:{self.journal.path}?mode=ro", uri=True)) as db:
            row = db.execute(
                "SELECT payload,receipt_sha FROM chapter2_wave_receipts WHERE checkpoint_ms=?",
                (self.last_checkpoint_ms,),
            ).fetchone()
        if row is None:
            raise ValueError("CHAPTER2_WAVE_RECEIPT_MISSING")
        payload = json.loads(row[0])
        if digest(payload) != row[1] or row[1] != self.last_receipt_sha:
            raise ValueError("CHAPTER2_WAVE_RECEIPT_TAMPERED")
        return payload

    def record(
        self,
        checkpoint_ms: int,
        member_ids: tuple[str, ...],
        available: dict[str, dict],
        *,
        recorded_ms: int,
    ) -> dict[str, Any]:
        if checkpoint_ms <= self.last_checkpoint_ms:
            with closing(sqlite3.connect(f"file:{self.journal.path}?mode=ro", uri=True)) as db:
                row = db.execute(
                    "SELECT payload,receipt_sha FROM chapter2_wave_receipts WHERE checkpoint_ms=?",
                    (checkpoint_ms,),
                ).fetchone()
            if row is None or digest(json.loads(row[0])) != row[1]:
                raise ValueError("CHAPTER2_WAVE_RECEIPT_CONFLICT")
            return json.loads(row[0])

        if not member_ids or set(available) - set(member_ids):
            raise ValueError("CHAPTER2_WAVE_UNEXPECTED_SOURCE")
        missing = sorted(set(member_ids) - set(available))
        evidence = {member: available[member] for member in sorted(available)}
        complete = not missing and all(item["kind"] in COMPLETE_KINDS for item in evidence.values())
        payload = {
            "schema": "chapter2_wave_receipt_v1",
            "prior_sha": self.last_receipt_sha,
            "checkpoint_ms": checkpoint_ms,
            "recorded_ms": recorded_ms,
            "recorded_at": datetime.fromtimestamp(recorded_ms / 1000, UTC).isoformat(),
            "members": list(member_ids),
            "outcomes": evidence,
            "missing_sources": missing,
            "coverage_complete": complete,
        }
        with self.journal._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT checkpoint_ms FROM chapter2_wave_receipts ORDER BY checkpoint_ms DESC LIMIT 1"
                ).fetchone()
                if row and checkpoint_ms <= row[0]:
                    raise ValueError("CHAPTER2_WAVE_RECEIPT_REORDERED")
                db.execute(
                    "INSERT INTO chapter2_wave_receipts VALUES (?,?,?)",
                    (
                        checkpoint_ms,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        digest(payload),
                    ),
                )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        self.last_checkpoint_ms = checkpoint_ms
        self.last_receipt_sha = digest(payload)
        return payload
