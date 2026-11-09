"""Commit-safe, read-only V4 source capture for an offline protected inbox.

Only trusted SQLite-sealed selected parents are eligible. Exactly one writer
owns the private spool. This process has NO broker/Guardian credentials.
An independently provisioned source-observer Ed25519 seed and separately pinned
public key are mandatory; no signing authority is generated here.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .pm_v4_selected_positions import selected_parents
from .production_manifest import canonical, digest
from .v4_source_export import (
    _atomic_private_output,
    _private_input,
    export_signed_events,
)


def _private_directory(root: Path) -> None:
    if (
        not root.is_dir()
        or root.is_symlink()
        or root.stat().st_mode & 0o077
        or root.parent.is_symlink()
    ):
        raise ValueError("V4_SPOOL_PRIVATE_DIRECTORY_REQUIRED")


def _expected_state(raw: bytes, selected: dict[str, str], pinned_public: bytes) -> dict[str, int]:
    state = json.loads(raw)
    if (
        not isinstance(state, dict)
        or set(state) != {"schema", "selected_sha", "public_sha", "cursors"}
        or state["schema"] != "v4_spool_cursor_state_v1"
        or state["selected_sha"] != digest(selected)
        or state["public_sha"] != sha256(pinned_public).hexdigest()
        or not isinstance(state["cursors"], dict)
        or set(state["cursors"]) != set(selected)
        or any(type(v) is not int or v < 0 for v in state["cursors"].values())
    ):
        raise ValueError("V4_SPOOL_CURSOR_DRIFT")
    return state["cursors"]


def _recover_bootstrap(outbox: Path, selected: dict[str, str], public: Ed25519PublicKey) -> dict:
    """Recover only the authenticated first empty publication.

    Later missing-cursor history is ambiguous and stays blocked. A first packet
    signed at an explicit cutoff contains no replayable historical opportunity.
    Unpublished private staging files never count as packets.
    """
    from .production_manifest import verify

    packets = []
    for path in outbox.iterdir():
        if path.name.startswith(".v4-stage-") and path.name.endswith(".tmp"):
            continue
        if not path.name.endswith(".json"):
            raise ValueError("V4_SPOOL_UNRECOGNIZED_HISTORY")
        packets.append(path)
    if not packets:
        return {}
    if len(packets) != 1:
        raise ValueError("V4_SPOOL_STATE_MISSING_WITH_HISTORY")
    packet_path = packets[0]
    raw = _private_input(packet_path)
    packet = json.loads(raw)
    if (
        not isinstance(packet, dict)
        or set(packet)
        != {"schema", "head_cursors", "events", "trading_authorized", "batch_envelope"}
        or packet["schema"] != "v4_signed_source_export_v1"
        or packet["trading_authorized"] is not False
        or packet["events"] != {alias: [] for alias in selected}
        or raw != canonical(packet)
        or not packet_path.name.endswith("-" + sha256(raw).hexdigest()[:16] + ".json")
    ):
        raise ValueError("V4_SPOOL_BOOTSTRAP_INVALID")
    bound = verify(packet["batch_envelope"], public, "source-observer-v4-batch")
    heads = packet["head_cursors"]
    if (
        bound
        != {
            "schema": "v4_source_batch_binding_v1",
            "selected": {a: address.lower() for a, address in selected.items()},
            "head_cursors": heads,
            "events_sha": digest(packet["events"]),
            "trading_authorized": False,
        }
        or not isinstance(heads, dict)
        or set(heads) != set(selected)
        or any(type(value) is not int or value < 0 for value in heads.values())
    ):
        raise ValueError("V4_SPOOL_BOOTSTRAP_PIN_OR_CURSOR_INVALID")
    directory = os.open(outbox, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return heads


def capture_once(
    *,
    registry_db: Path,
    journal_db: Path,
    root: Path,
    signing_key: Path,
    public_key: Path,
    portfolios: tuple[str, ...],
    now: datetime | None = None,
) -> dict[str, Any]:
    _private_directory(root)
    outbox = root / "outbox"
    if not outbox.exists():
        outbox.mkdir(mode=0o700)
    _private_directory(outbox)
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("V4_SPOOL_UTC_REQUIRED")
    chosen = selected_parents(registry_db, portfolios=portfolios, as_of=now.isoformat())
    if not chosen:
        raise ValueError("V4_SPOOL_EMPTY_SELECTION")
    key = Ed25519PrivateKey.from_private_bytes(_private_input(signing_key))
    raw_public = _private_input(public_key)
    public = Ed25519PublicKey.from_public_bytes(raw_public)
    if key.public_key().public_bytes_raw() != public.public_bytes_raw():
        raise ValueError("V4_SOURCE_PIN_MISMATCH")

    lock = os.open(root / "producer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cursor_path = root / "cursor.json"
        state_exists = cursor_path.exists()
        if state_exists:
            cursors = _expected_state(_private_input(cursor_path), chosen, raw_public)
        else:
            recovered = _recover_bootstrap(outbox, chosen, public)
            if recovered:
                state = {
                    "schema": "v4_spool_cursor_state_v1",
                    "selected_sha": digest(chosen),
                    "public_sha": sha256(raw_public).hexdigest(),
                    "cursors": recovered,
                }
                _atomic_private_output(cursor_path, canonical(state))
                state_exists, cursors = True, recovered
            else:
                cursors = None
        snapshot = export_signed_events(journal_db, selected=chosen, signer=key, after=cursors)
        count = sum(len(events) for events in snapshot["events"].values())
        if cursors is not None and count == 0:
            return {
                "state": "NO_NEW_VERIFIED_EVENTS",
                "events": 0,
                "selected_accounts": len(chosen),
                "trading_authorized": False,
            }
        payload = canonical(snapshot)
        packet_sha = sha256(payload).hexdigest()
        # UTC nanoseconds sort packets in publication order. Randomness and
        # order-route details must never appear in the payload or filename.
        path = outbox / f"{time.time_ns():020d}-{packet_sha[:16]}.json"
        _atomic_private_output(path, payload)
        new_cursors = {
            alias: events[-1]["proof"]["payload"]["stream_cursor"]
            if events
            else (cursors[alias] if cursors is not None else snapshot["head_cursors"][alias])
            for alias, events in snapshot["events"].items()
        }
        state = {
            "schema": "v4_spool_cursor_state_v1",
            "selected_sha": digest(chosen),
            "public_sha": sha256(raw_public).hexdigest(),
            "cursors": new_cursors,
        }
        _atomic_private_output(cursor_path, canonical(state), replace=state_exists)
        return {
            "state": "SIGNED_SOURCE_PACKET_PUBLISHED",
            "events": count,
            "selected_accounts": len(chosen),
            "packet_sha": packet_sha,
            "trading_authorized": False,
        }
    finally:
        os.close(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-db", type=Path, required=True)
    parser.add_argument("--journal-db", type=Path, required=True)
    parser.add_argument("--spool-root", type=Path, required=True)
    parser.add_argument("--source-signing-key", type=Path, required=True)
    parser.add_argument("--source-public-key", type=Path, required=True)
    parser.add_argument("--portfolios", default="P1,P14,P16")
    args = parser.parse_args(argv)
    try:
        result = capture_once(
            registry_db=args.registry_db,
            journal_db=args.journal_db,
            root=args.spool_root,
            signing_key=args.source_signing_key,
            public_key=args.source_public_key,
            portfolios=tuple(args.portfolios.split(",")),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, sqlite3.Error, KeyError) as exc:
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
