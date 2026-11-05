"""Independent read-only integrity watcher for the unprotected public observer.

The producer's JSON heartbeat binds Linux PID/start epoch to current verified
source, collateral and market quote SQLite chain heads. It is *not* signed by
an independent operator or written under a protected service identity. Even
a fully consistent heartbeat is DEGRADED_OBSERVER_ONLY, never PAPER_RUNNING.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from .pm03_account import clock, digest
from .pm_forward_heartbeat import _private_dir, _process_identity
from .pm_forward_readiness import _collateral, _market, _source
from .pm_forward_registry_identity import P14
from .pm_forward_source_campaign import _ALIAS

_HEARTBEAT = "p1p14-public-observer.heartbeat.json"


def _readonly_tape_snapshot(db_path: Path) -> dict:
    db_path = Path(db_path)
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("OBSERVER_JOURNAL_NOT_REGULAR")
    uri = "file:" + str(db_path.resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
        db.execute("PRAGMA query_only=ON")
        # SQLite's implicit read transactions are statement-scoped. Pin a
        # single snapshot across source/quote/collateral chains while the
        # observer is appending new receipts in another connection.
        db.execute("BEGIN")
        sources = {}
        for member in P14:
            alias = _ALIAS[member]
            tape = _source(db, alias)
            sources[alias] = {
                "cursor": tape["cursor"],
                "head_sha": tape["head_sha"],
                "latest_first_known_at": (
                    tape["receipt"]["first_known_at"] if tape["receipt"] else None
                ),
                "distinct_accounts": len(tape["account_receipts"]),
            }
        market_keys = [
            item[0]
            for item in db.execute("SELECT instrument FROM market_quote_heads ORDER BY instrument")
        ]
        quotes = {}
        for market in market_keys:
            tape = _market(db, market)
            quotes[market] = {
                "cursor": tape["cursor"],
                "head_sha": tape["head_sha"],
                "latest_first_known_at": (
                    tape["quote"]["first_known_at"] if tape["quote"] else None
                ),
            }
        collateral_keys = [
            row[0]
            for row in db.execute(
                "SELECT DISTINCT account_sha FROM source_scope_receipts ORDER BY account_sha"
            )
        ]
        collateral = {
            key: {
                "cursor": result["cursor"],
                "head_sha": result["head_sha"],
            }
            for key in collateral_keys
            for result in [_collateral(db, key)]
        }
    return {
        "schema": "paper_observer_verified_tape_heads_v1",
        "source": sources,
        "quotes": quotes,
        "collateral": collateral,
    }


def _sealed_prefix_heads(snapshot: dict) -> dict:
    """Compact, heartbeat-sealed historical heads for in-progress epochs."""
    return {
        scope: {key: [entry["cursor"], entry["head_sha"]] for key, entry in snapshot[scope].items()}
        for scope in ("source", "quotes", "collateral")
    }


def _verified_append_only_advance(db_path: Path, older: object, current: dict) -> bool:
    """Accept only independently verified additions after a heartbeat.

    The current complete chains were checked by _readonly_tape_snapshot. Each
    earlier sealed head must still appear at its ORIGINAL sequence number;
    a rewritten head, truncated chain or old heartbeat format is UNKNOWN.
    A verified extension still does not attest the new receipts or financial
    operation: the observer remains DEGRADED_OBSERVER_ONLY.
    """
    tables = {
        "source": ("source_receipts", "source_id"),
        "quotes": ("market_quote_receipts", "instrument"),
        "collateral": ("source_scope_receipts", "account_sha"),
    }
    if not isinstance(older, dict) or set(older) != set(tables):
        return False
    uri = "file:" + str(Path(db_path).resolve()) + "?mode=ro"
    changed = False
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for scope, (table, key_field) in tables.items():
            previous = older[scope]
            latest = current[scope]
            if not isinstance(previous, dict) or not set(previous).issubset(latest):
                return False
            if set(previous) != set(latest):
                changed = True
            for key, pair in previous.items():
                if (
                    not isinstance(key, str)
                    or not isinstance(pair, list)
                    or len(pair) != 2
                    or type(pair[0]) is not int
                    or pair[0] < 0
                    or not isinstance(pair[1], str)
                    or len(pair[1]) != 64
                    or any(char not in "0123456789abcdef" for char in pair[1])
                ):
                    return False
                cursor, head = pair
                if cursor > latest[key]["cursor"]:
                    return False
                if cursor == latest[key]["cursor"]:
                    if head != latest[key]["head_sha"]:
                        return False
                    continue
                changed = True
                if cursor == 0:
                    if head != "0" * 64:
                        return False
                    continue
                row = db.execute(
                    f"SELECT chain_sha FROM {table} WHERE {key_field}=? AND seq=?",
                    (key, cursor),
                ).fetchone()
                if row != (head,):
                    return False
    return changed


def publish_public_observer_heartbeat(
    root: Path,
    *,
    journal_db: Path,
    epoch_report: dict,
    observed_at: str | None = None,
    idle_refresh: bool = False,
) -> dict:
    """Atomic fsynced local observer heartbeat. Never claim protected health."""
    root = Path(root)
    _private_dir(root)
    now = observed_at or datetime.now(UTC).isoformat()
    clock(now)
    if type(idle_refresh) is not bool:
        raise ValueError("OBSERVER_HEARTBEAT_REFRESH_KIND_INVALID")
    if (
        not isinstance(epoch_report, dict)
        or epoch_report.get("schema") != "paper_readonly_observer_service_epoch_v1"
        or epoch_report.get("paper_observed") is not False
        or epoch_report.get("financial_events_committed") != 0
        or epoch_report.get("protected_worker_attested") is not False
        or epoch_report.get("source_nav_attested") is not False
        or epoch_report.get("trade_volume_complete") is not False
        or epoch_report.get("order_route") != "NONE"
        or epoch_report.get("status")
        not in (
            "BLOCKED_NO_TRADE",
            "DEGRADED_OBSERVER_EVIDENCE",
            "DEGRADED_OBSERVER_FAILURE",
            "DEGRADED_OBSERVER_STOPPED",
        )
    ):
        raise ValueError("OBSERVER_HEARTBEAT_UNTRUSTED_EPOCH_REPORT")
    snapshot = _readonly_tape_snapshot(journal_db)
    envelope_body = {
        "schema": "paper_public_observer_heartbeat_v1",
        "observed_at": now,
        "process_identity": _process_identity(os.getpid()),
        "tape_heads_sha": digest(snapshot),
        "sealed_prefix_heads": _sealed_prefix_heads(snapshot),
        "source_count": len(snapshot["source"]),
        "quote_count": len(snapshot["quotes"]),
        "epoch_report_sha": digest(epoch_report),
        "last_epoch_status": epoch_report["status"],
        "heartbeat_kind": "IDLE_LIVENESS_ONLY" if idle_refresh else "COMPLETED_EPOCH",
        "protected_worker_attested": False,
        "independently_signed": False,
        "paper_observed": False,
        "order_route": "NONE",
    }
    envelope = {**envelope_body, "payload_sha": digest(envelope_body)}
    path = root / _HEARTBEAT
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("OBSERVER_HEARTBEAT_DESTINATION_INVALID")
    if path.exists() and (path.stat().st_mode & 0o077 or path.stat().st_uid != os.geteuid()):
        raise ValueError("OBSERVER_HEARTBEAT_DESTINATION_PERMISSION_INVALID")
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix=".p1p14-observer-", delete=False
        ) as tmp:
            tmp_name = tmp.name
            os.fchmod(tmp.fileno(), 0o600)
            tmp.write((json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode())
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if tmp_name is not None:
            os.unlink(tmp_name)
    return {
        "schema": "paper_observer_heartbeat_publish_v1",
        "status": "OBSERVER_ONLY_HEARTBEAT_PERSISTED",
        "payload_sha": envelope["payload_sha"],
        "protected_worker_attested": False,
    }


def inspect_public_observer_heartbeat(
    root: Path,
    *,
    journal_db: Path,
    as_of: str,
    max_heartbeat_age_seconds: int = 90,
    max_source_age_seconds: int = 180,
    max_market_age_seconds: int = 90,
) -> dict:
    """Read-only OS/SQLite inspection; no protected or economic status granted."""
    now = clock(as_of)
    if not 1 <= max_heartbeat_age_seconds <= 3600:
        raise ValueError("OBSERVER_WATCHDOG_HEARTBEAT_POLICY_INVALID")
    try:
        root = Path(root)
        _private_dir(root)
        path = root / _HEARTBEAT
        if path.is_symlink() or not path.is_file():
            raise ValueError("OBSERVER_HEARTBEAT_NOT_PRESENT")
        info = path.stat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.geteuid()
            or info.st_size > 16_384
        ):
            raise ValueError("OBSERVER_HEARTBEAT_FILE_PERMISSION_OR_SIZE")
        payload = json.loads(path.read_bytes())
        body = {key: value for key, value in payload.items() if key != "payload_sha"}
        if digest(body) != payload.get("payload_sha"):
            raise ValueError("OBSERVER_HEARTBEAT_PAYLOAD_TAMPERED")
        if (
            body.get("schema") != "paper_public_observer_heartbeat_v1"
            or body.get("protected_worker_attested") is not False
            or body.get("independently_signed") is not False
            or body.get("paper_observed") is not False
            or body.get("order_route") != "NONE"
            or body.get("heartbeat_kind", "COMPLETED_EPOCH")
            not in ("COMPLETED_EPOCH", "IDLE_LIVENESS_ONLY")
        ):
            raise ValueError("OBSERVER_HEARTBEAT_POSITIVE_MODE_UNTRUSTED")
        pid = body["process_identity"]["pid"]
        if _process_identity(pid) != body["process_identity"]:
            raise ValueError("OBSERVER_HEARTBEAT_PROCESS_IDENTITY_CHANGED")
        snapshot = _readonly_tape_snapshot(journal_db)
        in_progress = False
        if digest(snapshot) != body["tape_heads_sha"]:
            in_progress = _verified_append_only_advance(
                journal_db, body.get("sealed_prefix_heads"), snapshot
            )
            if not in_progress:
                raise ValueError("OBSERVER_HEARTBEAT_TAPE_HEAD_DIVERGENCE")
        heartbeat_age = (now - clock(body["observed_at"])).total_seconds()
        if heartbeat_age < 0 or heartbeat_age > max_heartbeat_age_seconds:
            raise ValueError("OBSERVER_HEARTBEAT_STALE_OR_FUTURE")
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        return {
            "schema": "paper_public_observer_health_v1",
            "health": "UNKNOWN",
            "reason_codes": [str(exc)[:140] or type(exc).__name__],
            "protected_worker_attested": False,
            "paper_observed": False,
            "order_route": "NONE",
        }
    reasons = ["UNPROTECTED_PUBLIC_OBSERVER_ONLY", "SOURCE_NAV_AND_VOLUME_UNATTESTED"]
    if in_progress:
        reasons.append("UNATTESTED_TAPE_ADVANCE_AFTER_HEARTBEAT")
    if body.get("heartbeat_kind") == "IDLE_LIVENESS_ONLY":
        reasons.append("IDLE_HEARTBEAT_NO_NEW_SOURCE_EVIDENCE")
    for alias, tape in snapshot["source"].items():
        when = tape["latest_first_known_at"]
        if when is None or not 0 <= (now - clock(when)).total_seconds() <= max_source_age_seconds:
            reasons.append("SOURCE_RECEIPT_STALE_OR_MISSING:" + alias)
    if not snapshot["quotes"]:
        reasons.append("NO_NATIVE_MARKET_QUOTE_RECEIPTS")
    for instrument, tape in snapshot["quotes"].items():
        when = tape["latest_first_known_at"]
        if when is None or not 0 <= (now - clock(when)).total_seconds() <= max_market_age_seconds:
            reasons.append("MARKET_QUOTE_STALE_OR_MISSING:" + instrument)
    if body["last_epoch_status"] != "BLOCKED_NO_TRADE":
        reasons.append("LATEST_OBSERVER_EPOCH_DEGRADED")
    return {
        "schema": "paper_public_observer_health_v1",
        "health": "DEGRADED_OBSERVER_ONLY",
        "reason_codes": reasons,
        "observer_process_verified": True,
        "heartbeat_age_seconds": heartbeat_age,
        "source_aliases_checked": len(snapshot["source"]),
        "source_aliases_with_receipts": sum(
            entry["cursor"] > 0 for entry in snapshot["source"].values()
        ),
        "market_quote_tapes_verified": len(snapshot["quotes"]),
        "collateral_diagnostic_tapes_verified": len(snapshot["collateral"]),
        "protected_worker_attested": False,
        "paper_observed": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent read-only public observer watchdog")
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--as-of", default=datetime.now(UTC).isoformat())
    args = parser.parse_args()
    result = inspect_public_observer_heartbeat(
        args.state_root,
        journal_db=args.state_root / "paper-events.sqlite3",
        as_of=args.as_of,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
