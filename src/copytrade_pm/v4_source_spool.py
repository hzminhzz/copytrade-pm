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


def _publish_checkpoint(packet: dict, outbox: Path) -> dict:
    raw = canonical(packet)
    packet_sha = sha256(raw).hexdigest()
    issued_ms = packet["payload"]["issued_ms"]
    path = outbox / f"{issued_ms * 1_000_000:020d}-{packet_sha[:16]}.json"
    if path.exists():
        if _private_input(path) != raw:
            raise ValueError("CWSA_PACKET_COLLISION")
    else:
        _atomic_private_output(path, raw)
    return {
        "schema": "cwsa_source_spool_v3",
        "packet_sha": packet_sha,
        "source_id": packet["payload"]["scope"]["source_id"],
        "cursor": packet["payload"]["transitions"][-1]["sequence"],
        "trading_authorized": False,
    }


def capture_checkpoint_batch(
    *,
    journal_db: Path,
    config,
    root: Path,
    signing_key: Path,
    public_key: Path,
    issued_ms: int,
) -> dict:
    """Resume solely from immutable signed packets; no mutable cursor can erase history."""
    from contextlib import closing
    from .pm_checkpoint_journal import SourceTransition, history
    from .production_manifest import verify
    from .v4_source_export import export_checkpoint_packet

    _private_directory(root)
    if (root / "cursor.json").exists():
        raise ValueError("CWSA_LEGACY_SPOOL_MIX")
    outbox = root / "outbox"
    outbox.mkdir(mode=0o700, exist_ok=True)
    _private_directory(outbox)
    signer = Ed25519PrivateKey.from_private_bytes(_private_input(signing_key))
    public_raw = _private_input(public_key)
    if signer.public_key().public_bytes_raw() != public_raw:
        raise ValueError("CWSA_SOURCE_PIN_MISMATCH")
    public = Ed25519PublicKey.from_public_bytes(public_raw)
    lock = os.open(root / "producer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        retained = {alias: {} for alias in config.scopes}
        for path in outbox.iterdir():
            if path.name.startswith(".v4-stage-") and path.name.endswith(".tmp"):
                continue
            raw = _private_input(path)
            envelope = json.loads(raw)
            body = verify(envelope, public, "cwsa-checkpoint-v3")
            alias = body["scope"]["source_id"]
            if (
                raw != canonical(envelope)
                or not path.name.endswith("-" + sha256(raw).hexdigest()[:16] + ".json")
                or alias not in retained
                or body["schema"] != "cwsa_checkpoint_packet_v3"
                or body["scope"] != config.scopes[alias].model_dump(mode="json")
                or body["policy"] != config.policy.model_dump(mode="json")
                or body["trading_authorized"] is not False
                or body["issued_ms"] > issued_ms
            ):
                raise ValueError("CWSA_SPOOL_HISTORY_PIN")
            for event in body["transitions"]:
                transition = SourceTransition.model_validate_json(canonical(event))
                prior = retained[alias].setdefault(transition.sequence, transition.sha)
                if prior != transition.sha:
                    raise ValueError("CWSA_SPOOL_EQUIVOCATION")
        heads, blocked, packets, events = {}, {}, [], 0
        with closing(sqlite3.connect(f"file:{journal_db.resolve()}?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            for alias, scope in sorted(config.scopes.items()):
                rows = history(db, scope, config.policy.epoch)
                published = retained[alias]
                cursor = max(published, default=0)
                if set(published) != set(range(1, cursor + 1)):
                    raise ValueError("CWSA_SPOOL_HISTORY_GAP")
                if cursor > len(rows) or any(published[t.sequence] != t.sha for t in rows[:cursor]):
                    raise ValueError("CWSA_SPOOL_JOURNAL_DIVERGENCE")
                heads[alias] = cursor
                if not rows:
                    blocked[alias] = "SOURCE_NOT_REGISTERED"
                    continue
                if cursor == rows[-1].sequence:
                    continue
                packet = export_checkpoint_packet(
                    journal_db,
                    scope,
                    config.policy,
                    signer=signer,
                    after_cursor=cursor,
                    issued_ms=issued_ms,
                )
                receipt = _publish_checkpoint(packet, outbox)
                packets.append(receipt["packet_sha"])
                events += receipt["cursor"] - cursor
                heads[alias] = receipt["cursor"]
        return {
            "schema": "cwsa_source_spool_batch_v3",
            "state": "SIGNED_SOURCE_PACKETS_PUBLISHED" if packets else "NO_NEW_VERIFIED_EVENTS",
            "packets": len(packets),
            "events": events,
            "packet_shas": packets,
            "head_cursors": heads,
            "blocked_sources": blocked,
            "trading_authorized": False,
        }
    finally:
        os.close(lock)


def capture_checkpoint_once(
    *,
    journal,
    scope,
    policy,
    root: Path,
    signing_key: Path,
    public_key: Path,
    after_cursor: int,
    issued_ms: int,
) -> dict:
    """Publish one immutable CWSA packet; the existing journal owns its source cursor."""
    from .v4_source_export import export_checkpoint_packet

    _private_directory(root)
    outbox = root / "outbox"
    outbox.mkdir(mode=0o700, exist_ok=True)
    _private_directory(outbox)
    signer = Ed25519PrivateKey.from_private_bytes(_private_input(signing_key))
    public = _private_input(public_key)
    if signer.public_key().public_bytes_raw() != public:
        raise ValueError("CWSA_SOURCE_PIN_MISMATCH")
    lock = os.open(root / "producer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        packet = export_checkpoint_packet(
            journal, scope, policy, signer=signer, after_cursor=after_cursor, issued_ms=issued_ms
        )
        return _publish_checkpoint(packet, outbox)
    finally:
        os.close(lock)


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
    parser.add_argument("--wire-version", type=int, choices=(1, 3), default=1)
    parser.add_argument("--checkpoint-config", type=Path)
    parser.add_argument("--checkpoint-config-sha256")
    parser.add_argument("--campaign-manifest", type=Path)
    parser.add_argument("--campaign-sha256")
    args = parser.parse_args(argv)
    if args.wire_version == 3:
        if args.checkpoint_config is None or args.checkpoint_config_sha256 is None:
            parser.error("wire v3 requires an explicit checkpoint config and SHA pin")
    elif any(
        (
            args.checkpoint_config,
            args.checkpoint_config_sha256,
            args.campaign_manifest,
            args.campaign_sha256,
        )
    ):
        parser.error("checkpoint and campaign options require wire v3")
    try:
        if args.wire_version == 3:
            from .pm_checkpoint_source import utc_milliseconds
            from .pm_v4_selected_positions import (
                load_checkpoint_configuration,
                selected_source_parents,
            )

            parents = selected_source_parents(
                args.registry_db,
                portfolios=tuple(args.portfolios.split(",")),
                as_of=datetime.now(UTC).isoformat(),
                campaign_manifest=args.campaign_manifest,
                campaign_sha256=args.campaign_sha256,
            )
            config = load_checkpoint_configuration(
                args.checkpoint_config,
                args.checkpoint_config_sha256,
                parents,
            )
            result = capture_checkpoint_batch(
                journal_db=args.journal_db,
                config=config,
                root=args.spool_root,
                signing_key=args.source_signing_key,
                public_key=args.source_public_key,
                issued_ms=utc_milliseconds(),
            )
        else:
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
