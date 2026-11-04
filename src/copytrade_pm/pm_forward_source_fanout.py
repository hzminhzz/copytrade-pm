"""Read-only shared-source receipt fanout into isolated P1/P14 SQLite journals.

The public source observer records each wallet exactly once. Financial
account journals are independent OS/state authorities; verified *copies* of
source receipts are imported as evidence only. A future PM04/PM03 effect must
still call the destination journal's atomic consume_source_effect() and pass
every separate source/market admission gate.

Never subscribe twice, import historical fills, synthesize equity, create a
paper fill or make an inter-DB atomicity claim.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .pm03_account import clock, digest
from .pm_forward_journal import PaperJournal
from .pm_forward_portfolios import P1, P14


def _verified_source_rows(db: sqlite3.Connection, source_id: str) -> list[tuple]:
    """Verify every source SHA/clock/sequence; no writable connection needed."""
    rows = db.execute(
        "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
        "FROM source_receipts WHERE source_id=? ORDER BY seq",
        (source_id,),
    ).fetchall()
    previous = "0" * 64
    previous_known = None
    verified = []
    for expected, (seq, receipt_id, raw, sha, prior, head) in enumerate(rows, 1):
        receipt = json.loads(raw)
        if (
            seq != expected
            or receipt.get("schema") != "paper_first_known_source_v1"
            or receipt.get("source_id") != source_id
            or digest(receipt) != sha
            or prior != previous
            or head != digest([source_id, seq, receipt_id, previous, sha])
        ):
            raise ValueError("PAPER_SOURCE_FANOUT_ORIGIN_CHAIN_INVALID")
        try:
            event = clock(receipt["source_event_at"])
            known = clock(receipt["first_known_at"])
            captured = clock(receipt["captured_at"])
            if (
                event > known
                or known > captured
                or (previous_known is not None and known < previous_known)
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("PAPER_SOURCE_FANOUT_CAUSAL_CLOCK_INVALID") from exc
        book = receipt.get("source_book")
        if book is not None:
            if (
                not isinstance(book, dict)
                or book.get("snapshot_sha")
                != digest({key: value for key, value in book.items() if key != "snapshot_sha"})
                or book.get("snapshot_sha") != receipt.get("payload_sha")
                or book.get("wallet_id") != source_id
            ):
                raise ValueError("PAPER_SOURCE_FANOUT_BOOK_HASH_INVALID")
        verified.append((seq, receipt_id, receipt, sha, head))
        previous = head
        previous_known = known
    return verified


def _readonly_source_rows(path: Path, aliases: tuple[str, ...]) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("PAPER_SOURCE_FANOUT_ORIGIN_FILE_INVALID")
    uri = "file:" + str(path.resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        try:
            snapshot = {alias: _verified_source_rows(db, alias) for alias in aliases}
        finally:
            db.execute("ROLLBACK")
    return snapshot


def _verified_local_prefix(destination: PaperJournal, alias: str, canonical: list[tuple]) -> int:
    """Reject a changed source prefix even when receipt IDs were reused."""
    existing = _readonly_source_rows(destination.path, (alias,))[alias]
    if len(existing) > len(canonical):
        raise ValueError("PAPER_SOURCE_FANOUT_LOCAL_CURSOR_AHEAD")
    for index, row in enumerate(existing):
        original = canonical[index]
        if (row[0], row[1], row[3], row[4]) != (
            original[0],
            original[1],
            original[3],
            original[4],
        ):
            raise ValueError("PAPER_SOURCE_FANOUT_PREFIX_CONFLICT")
    return len(existing)


def fanout_frozen_source_receipts(
    *,
    source_db: Path,
    p1_journal: PaperJournal,
    p14_journal: PaperJournal,
    max_source_receipts: int = 1000,
) -> dict:
    """Copy a single source snapshot into two financially isolated journals.

    Progress is per destination. A process crash after one portfolio copies a
    receipt but before the other does is safe: exact-prefix validation allows
    idempotent retry, and no PM03 account effect occurs here.
    """
    if not 1 <= max_source_receipts <= 10_000:
        raise ValueError("PAPER_SOURCE_FANOUT_BUDGET_INVALID")
    canonical_path = Path(source_db).resolve()
    roots = [p1_journal.root.resolve(), p14_journal.root.resolve()]
    if len({canonical_path, *roots}) != 3:
        raise ValueError("PAPER_SOURCE_FANOUT_FINANCIAL_SOURCE_ISOLATION_REQUIRED")
    if p1_journal.path.resolve() == p14_journal.path.resolve():
        raise ValueError("PAPER_SOURCE_FANOUT_JOURNALS_NOT_ISOLATED")

    unique_aliases = tuple(P14.members)
    canonical = _readonly_source_rows(source_db, unique_aliases)
    total_receipts = sum(len(rows) for rows in canonical.values())
    if total_receipts > max_source_receipts:
        raise ValueError("PAPER_SOURCE_FANOUT_BOUNDED_SOURCE_VOLUME_EXCEEDED")
    outputs = {}
    for portfolio, members, journal in (
        ("P1", P1.members, p1_journal),
        ("P14", P14.members, p14_journal),
    ):
        counts = {}
        current = None
        try:
            for member in members:
                alias = member
                current = alias
                rows = canonical[alias]
                prefix = _verified_local_prefix(journal, alias, rows)
                for seq, receipt_id, receipt, _, _ in rows[prefix:]:
                    journal.append_source_receipt(alias, seq, receipt_id, receipt)
                verified_after = _verified_local_prefix(journal, alias, rows)
                if verified_after != len(rows):
                    raise ValueError("PAPER_SOURCE_FANOUT_RESULT_NOT_CONTIGUOUS")
                counts[alias] = {
                    "source_receipts": len(rows),
                    "previous_import_cursor": prefix,
                    "imported_new": len(rows) - prefix,
                    "local_source_cursor": verified_after,
                    "source_head_sha": rows[-1][4] if rows else "0" * 64,
                }
            outputs[portfolio] = {
                "status": "COPIED_EVIDENCE_ONLY",
                "source_cursors": counts,
                "all_source_aliases_observed": all(
                    row["source_receipts"] > 0 for row in counts.values()
                ),
                "paper_admitted": False,
                "paper_financial_events_committed": 0,
            }
        except (ValueError, OSError, sqlite3.Error) as exc:
            outputs[portfolio] = {
                "status": "BLOCKED_SOURCE_FANOUT",
                "blocked_source_alias": current,
                "reason": type(exc).__name__ + ":" + str(exc)[:100],
                "source_cursors_imported_before_failure": counts,
                "paper_admitted": False,
                "paper_financial_events_committed": 0,
            }
    return {
        "schema": "paper_shared_source_isolated_account_fanout_v1",
        "canonical_source_tape_head_sha": digest(
            {alias: rows[-1][4] if rows else "0" * 64 for alias, rows in canonical.items()}
        ),
        "unique_sources": len(unique_aliases),
        "canonical_source_receipts": total_receipts,
        "canonical_all_required_sources_observed": all(bool(rows) for rows in canonical.values()),
        "portfolios": outputs,
        "all_destinations_reconciled": all(
            item["status"] == "COPIED_EVIDENCE_ONLY" for item in outputs.values()
        ),
        "source_subscriptions_created": 0,
        "broker_orders": 0,
        "paper_financial_events_committed": 0,
        "paper_observed": False,
        "order_route": "NONE",
    }
