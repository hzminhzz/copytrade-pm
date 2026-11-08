"""Verify V4 official selected-account events and export source-signed SHADOW evidence.

The producer owns the immutable stream journal and the *external* source signing
key. It never signs a baseline as a new position transition, never guesses a
mark, and never writes the original SQLite journal. Private wallet identities
and signatures must stay outside public logs and Git.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .pm03_account import digest as source_digest
from .pm_forward_stream_journal import verify_streams
from .production_manifest import canonical, digest, sign


ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
ZERO_SHA = "0" * 64


def _millis(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("V4_UTC_REQUIRED")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _source_marks(native: dict[str, Any], expected: dict[str, str]) -> dict[str, str]:
    """Use only native positionValue / abs(szi), never an invented OHLC spread."""
    data = native.get("data", {})
    states = data.get("clearinghouseStates")
    if not isinstance(states, list):
        raise ValueError("V4_NATIVE_STATES_MISSING")
    quantities: dict[str, str] = {}
    marks: dict[str, str] = {}
    for pair in states:
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[1], dict):
            raise ValueError("V4_NATIVE_STATE_INVALID")
        dex, state = pair
        dex_name = dex or "default"
        for item in state.get("assetPositions", []):
            position = item.get("position") if isinstance(item, dict) else None
            if not isinstance(position, dict):
                raise ValueError("V4_NATIVE_POSITION_INVALID")
            coin = position.get("coin")
            if not isinstance(coin, str) or not coin:
                raise ValueError("V4_NATIVE_COIN_MISSING")
            if ":" in coin and (dex_name == "default" or coin.split(":", 1)[0] != dex_name):
                raise ValueError("V4_NATIVE_DEX_COIN_MISMATCH")
            market = f"hyperliquid/mainnet:perp:{dex_name}/{coin.split(':')[-1]}"
            if market in quantities:
                raise ValueError("V4_NATIVE_MARKET_DUPLICATE")
            try:
                quantity = Decimal(str(position["szi"]))
            except (InvalidOperation, KeyError) as exc:
                raise ValueError("V4_NATIVE_QUANTITY_INVALID") from exc
            if not quantity.is_finite():
                raise ValueError("V4_NATIVE_QUANTITY_INVALID")
            if quantity == 0:
                continue
            quantities[market] = str(quantity)
            # Some genuine official frames omit positionValue. Missing source marks
            # make *that* book unavailable, never an excuse for a synthetic price.
            if position.get("positionValue") is None:
                continue
            try:
                value = Decimal(str(position["positionValue"]))
            except InvalidOperation as exc:
                raise ValueError("V4_NATIVE_POSITION_VALUE_INVALID") from exc
            if not value.is_finite() or value <= 0:
                raise ValueError("V4_NATIVE_POSITION_VALUE_INVALID")
            price = value / abs(quantity)
            if not price.is_finite() or price <= 0:
                raise ValueError("V4_NATIVE_SOURCE_MARK_INVALID")
            marks[market] = str(price)
    if {market: Decimal(value) for market, value in expected.items()} != {
        market: Decimal(value) for market, value in quantities.items()
    }:
        raise ValueError("V4_POSITION_CHECKPOINT_MISMATCH")
    return marks


def _record(
    db: sqlite3.Connection,
    *,
    alias: str,
    identity: str,
    row: tuple,
    signer: Ed25519PrivateKey,
) -> dict[str, Any]:
    cursor, event_sha, raw_event, raw_refs, prior_sha, chain_sha, committed_at = row
    event = json.loads(raw_event)
    refs = json.loads(raw_refs)
    sid = "account:" + alias
    checkpoint = event["checkpoint"]
    account_sha = sha256(identity.encode()).hexdigest()
    if (
        event["stream_id"] != sid
        or checkpoint.get("account_sha") != account_sha
        or checkpoint.get("parent_alias") != alias
        or source_digest(event) != event_sha
        or chain_sha != source_digest([sid, cursor, event_sha, prior_sha, committed_at, refs])
    ):
        raise ValueError("V4_SOURCE_IDENTITY_OR_CHAIN")
    kind = event["kind"]
    if (
        kind == "OBSERVATION"
        and event.get("details", {}).get("classification") != "OBSERVED_STATE_CHANGE"
    ):
        raise ValueError("V4_NOT_GENUINE_CHANGE")
    receipt, book = None, None
    if kind in {"BASELINE", "OBSERVATION", "UNCHANGED"}:
        linked = [ref for ref in refs if ref.get("kind") == "source"]
        if len(linked) != 1:
            raise ValueError("V4_SOURCE_REF_MISSING")
        ref = linked[0]
        if ref["key"][0] != alias:
            raise ValueError("V4_SOURCE_REF_ACCOUNT")
        source_row = db.execute(
            "SELECT seq,payload,receipt_sha,chain_sha FROM source_receipts "
            "WHERE source_id=? AND receipt_id=?",
            (alias, ref["key"][1]),
        ).fetchone()
        if source_row is None or source_row[2] != ref["sha"]:
            raise ValueError("V4_SOURCE_REF_DIVERGENCE")
        source_seq, raw_source, receipt_sha, _ = source_row
        receipt = json.loads(raw_source)
        if source_digest(receipt) != receipt_sha:
            raise ValueError("V4_SOURCE_RECEIPT_HASH_INVALID")
        original = receipt["source_book"]
        if (
            receipt["source_id"] != alias
            or receipt["first_known_at"] != event["first_known_at"]
            or receipt["source_event_at"] != event["source_event_at"]
            or original["account_id"] != account_sha
            or original.get("positions") != checkpoint.get("positions")
            or sorted(original["dex_census"]) != sorted(original["observed_dexes"])
            or receipt["payload_sha"] != original["snapshot_sha"]
            or original["snapshot_sha"]
            != source_digest(
                {field: value for field, value in original.items() if field != "snapshot_sha"}
            )
        ):
            raise ValueError("V4_OFFICIAL_BOOK_PROVENANCE")
        frame = event.get("details", {}).get("native_frame")
        if not isinstance(frame, dict) or receipt["source_sha"] != source_digest(frame):
            raise ValueError("V4_NATIVE_FRAME_PROVENANCE")
        marks = _source_marks(frame, original["positions"])
        known_at_ms = _millis(receipt["first_known_at"])
        event_ms = _millis(receipt["source_event_at"])
        if (
            len(marks) == len(original["positions"])
            and checkpoint.get("baseline_valid") is True
            and checkpoint.get("transport") == "CONNECTED"
        ):
            book = {
                "schema": "source_book_v1",
                "source_identity": identity,
                "source_event_ms": event_ms,
                "known_at_ms": known_at_ms,
                "sequence": source_seq,
                "scope": [identity],
                "scope_complete": True,
                "book_complete": True,
                "nav": None,
                "positions": [
                    {
                        "market": name,
                        "quantity": str(qty),
                        "mark": marks[name],
                        "mark_known_at_ms": known_at_ms,
                    }
                    for name, qty in sorted(original["positions"].items())
                ],
                "source_mode": "PROSPECTIVE",
            }
    else:
        if kind not in {"GAP", "SCOPE", "STOP", "START", "TRANSPORT", "DIAGNOSTIC"}:
            raise ValueError("V4_UNKNOWN_STREAM_EVENT")
        if refs:
            raise ValueError("V4_CONTROL_EVENT_UNEXPECTED_REF")
    known_ms = _millis(event["first_known_at"])
    proof = {
        "schema": "v4_official_event_proof_v1",
        "source_identity": identity,
        "account_sha": account_sha,
        "stream_id": sid,
        "stream_cursor": cursor,
        "stream_chain_sha": chain_sha,
        "observer_event_sha": event_sha,
        "stream_epoch": event["epoch"],
        "kind": kind,
        "classification": event.get("details", {}).get("classification"),
        "first_known_ms": known_ms,
        "source_event_ms": _millis(event["source_event_at"]) if event["source_event_at"] else None,
        "raw_sha": event.get("raw_sha"),
        "source_receipt_sha": receipt_sha if receipt is not None else None,
        "source_book_sha": digest(book) if book is not None else None,
        "continuity": bool(
            checkpoint.get("baseline_valid") is True and checkpoint.get("transport") == "CONNECTED"
        ),
        "full_selected_scope": book is not None,
        "trading_authorized": False,
    }
    return {
        "proof": sign(proof, signer, "source-observer-v4"),
        "book": sign(book, signer, "source-observer") if book is not None else None,
    }


def export_signed_events(
    journal_db: Path,
    *,
    selected: dict[str, str],
    signer: Ed25519PrivateKey,
    after: dict[str, int] | None = None,
    limit_per_account: int = 256,
) -> dict[str, Any]:
    """Export bounded prospective evidence from one verified read-only journal.

    The consumer persists its own high-water cursors. It must start at the
    current heads on first deployment; past transitions may not be replayed
    as fresh opportunities. No pointer to a private key crosses into Planner.
    """
    if journal_db.is_symlink() or not journal_db.is_file():
        raise ValueError("V4_JOURNAL_INVALID")
    if not selected or len(set(selected.values())) != len(selected):
        raise ValueError("V4_SELECTION_INVALID")
    if not 1 <= limit_per_account <= 256:
        raise ValueError("V4_EXPORT_LIMIT")
    verified = verify_streams(journal_db)
    after = after or {}
    records: dict[str, list[dict[str, Any]]] = {}
    heads: dict[str, int] = {}
    with closing(sqlite3.connect(f"file:{journal_db.resolve()}?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for alias, value in sorted(selected.items()):
            if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,70}", alias):
                raise ValueError("V4_ALIAS_INVALID")
            if not isinstance(value, str):
                raise ValueError("V4_IDENTITY_INVALID")
            identity = value.lower()
            if ADDRESS.fullmatch(identity) is None:
                raise ValueError("V4_IDENTITY_INVALID")
            sid = "account:" + alias
            if sid not in verified["streams"]:
                raise ValueError("V4_STREAM_ABSENT")
            head = verified["streams"][sid]["cursor"]
            cursor = after.get(alias, head)
            if type(cursor) is not int or not 0 <= cursor <= head:
                raise ValueError("V4_CURSOR_INVALID")
            rows = db.execute(
                "SELECT seq,event_sha,payload,receipt_refs,prior_sha,chain_sha,committed_at "
                "FROM observer_stream_events WHERE stream_id=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?",
                (sid, cursor, head, limit_per_account),
            ).fetchall()
            records[alias] = [
                _record(db, alias=alias, identity=identity, row=row, signer=signer) for row in rows
            ]
            heads[alias] = head
    result = {
        "schema": "v4_signed_source_export_v1",
        "head_cursors": heads,
        "events": records,
        "trading_authorized": False,
    }
    result["batch_envelope"] = sign(
        {
            "schema": "v4_source_batch_binding_v1",
            "selected": {alias: address.lower() for alias, address in selected.items()},
            "head_cursors": heads,
            "events_sha": digest(records),
            "trading_authorized": False,
        },
        signer,
        "source-observer-v4-batch",
    )
    return result


def _private_input(path: Path) -> bytes:
    """External evidence and signer must be operator provisioned and 0600."""
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("V4_PRIVATE_INPUT_REQUIRED")
    return path.read_bytes()


def _atomic_private_output(path: Path, payload: bytes, *, replace: bool = False) -> None:
    import os

    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise ValueError("V4_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    if path.is_symlink() or (path.exists() and not replace):
        raise ValueError("V4_PRIVATE_OUTPUT_EXISTS")
    if replace:
        temporary = path.with_name(path.name + ".new")
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("V4_OUTPUT_STAGING_EXISTS")
        path = temporary
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(path, path.with_name(path.name.removesuffix(".new")))
            dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    """Offline/bounded source-signed export. Never generate keys or approvals."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-db", type=Path, required=True)
    parser.add_argument("--selected-json", type=Path, required=True)
    parser.add_argument("--source-signing-key", type=Path, required=True)
    parser.add_argument("--source-public-key", type=Path, required=True)
    parser.add_argument("--cursor-state", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        selected = json.loads(_private_input(args.selected_json))
        if not isinstance(selected, dict):
            raise ValueError("V4_SELECTED_SCHEMA")
        raw_private = _private_input(args.source_signing_key)
        signer = Ed25519PrivateKey.from_private_bytes(raw_private)
        public = Ed25519PublicKey.from_public_bytes(_private_input(args.source_public_key))
        if signer.public_key().public_bytes_raw() != public.public_bytes_raw():
            raise ValueError("V4_SOURCE_PIN_MISMATCH")
        # First run only pins the present head (never imports historical
        # transitions as fresh opportunities).
        if args.cursor_state.exists():
            cursors = json.loads(_private_input(args.cursor_state))
            if not isinstance(cursors, dict):
                raise ValueError("V4_CURSOR_STATE_SCHEMA")
        else:
            cursors = None
        result = export_signed_events(
            args.journal_db, selected=selected, signer=signer, after=cursors
        )
        # Never replace an existing evidence packet. A crash after publication
        # but before cursor advance is at-least-once; consumer deduplicates
        # by the signed observer stream cursor.
        _atomic_private_output(args.private_output, canonical(result))
        next_cursor = {
            alias: events[-1]["proof"]["payload"]["stream_cursor"]
            if events
            else (cursors[alias] if cursors is not None else result["head_cursors"][alias])
            for alias, events in result["events"].items()
        }
        _atomic_private_output(
            args.cursor_state, canonical(next_cursor), replace=args.cursor_state.exists()
        )
        print(
            json.dumps(
                {
                    "state": "SIGNED_READ_ONLY_EXPORT",
                    "source_count": len(selected),
                    "events": sum(len(v) for v in result["events"].values()),
                    "trading_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(
            json.dumps(
                {
                    "state": "BLOCKED",
                    "reason": type(exc).__name__,
                    "trading_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
