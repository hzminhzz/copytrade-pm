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


_CONTINUOUS_HEARTBEAT = "continuous-observer.heartbeat.json"


def _atomic_private_json(root: Path, name: str, body: dict) -> dict:
    _private_dir(root)
    envelope = {**body, "payload_sha": digest(body)}
    path = root / name
    if path.is_symlink() or (
        path.exists()
        and (
            not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.geteuid()
        )
    ):
        raise ValueError("OBSERVER_HEARTBEAT_DESTINATION_INVALID")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix=".observer-", delete=False
        ) as target:
            temporary = target.name
            os.fchmod(target.fileno(), 0o600)
            target.write(
                (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode()
            )
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        temporary = None
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return envelope


def publish_continuous_heartbeat(
    root: Path, *, revision: str, manifest_sha: str, started_at: str, now: str, metrics: dict
) -> dict:
    """Cheap producer heartbeat; the separate watchdog verifies the actual chains."""
    clock(now)
    root = Path(root)
    uri = "file:" + str((root / "paper-events.sqlite3").resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        heads = {
            sid: [cursor, sha]
            for sid, cursor, sha in db.execute(
                "SELECT stream_id,cursor,chain_sha FROM observer_stream_heads ORDER BY stream_id"
            )
        }
    return _atomic_private_json(
        root,
        _CONTINUOUS_HEARTBEAT,
        {
            "schema": "paper_continuous_observer_heartbeat_v1",
            "observed_at": now,
            "started_at": started_at,
            "revision": revision,
            "manifest_sha": manifest_sha,
            "process_identity": _process_identity(os.getpid()),
            "stream_prefixes": heads,
            "metrics": metrics,
            "source_nav_attested": False,
            "protected_worker_attested": False,
            "paper_observed": False,
            "order_route": "NONE",
        },
    )


def _private_json(path: Path, *, max_bytes=2_000_000) -> dict:
    info = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_mode & 0o077
        or info.st_uid != os.geteuid()
        or info.st_size > max_bytes
    ):
        raise ValueError("OBSERVER_STATUS_PERMISSION_OR_SIZE")
    payload = json.loads(path.read_bytes())
    body = {key: value for key, value in payload.items() if key != "payload_sha"}
    if digest(body) != payload.get("payload_sha"):
        raise ValueError("OBSERVER_STATUS_TAMPERED")
    return body


def inspect_continuous_observer(
    root: Path,
    *,
    as_of: str,
    expected_revision: str | None = None,
    max_heartbeat_age_seconds=45,
    max_transport_age_seconds=45,
    max_quote_age_seconds=30,
    require_watchdog=False,
) -> dict:
    """Independent read-only OS, legacy-receipt and stream-checkpoint verification."""
    from .pm_forward_stream_journal import verify_streams

    common = {
        "schema": "paper_continuous_observer_health_v1",
        "financial_admission": "BLOCKED_NO_TRADE",
        "source_nav_attested": False,
        "protected_worker_attested": False,
        "paper_observed": False,
        "order_route": "NONE",
    }
    try:
        now = clock(as_of)
        root = Path(root)
        _private_dir(root)
        body = _private_json(root / _CONTINUOUS_HEARTBEAT)
        if (
            body.get("schema") != "paper_continuous_observer_heartbeat_v1"
            or body.get("source_nav_attested") is not False
            or body.get("protected_worker_attested") is not False
            or body.get("paper_observed") is not False
            or body.get("order_route") != "NONE"
        ):
            raise ValueError("OBSERVER_HEARTBEAT_FINANCIAL_PROMOTION")
        if expected_revision is not None and body["revision"] != expected_revision:
            raise ValueError("OBSERVER_RELEASE_REVISION_MISMATCH")
        identity = body["process_identity"]
        if _process_identity(identity["pid"]) != identity:
            raise ValueError("OBSERVER_PROCESS_IDENTITY_CHANGED")
        age = (now - clock(body["observed_at"])).total_seconds()
        if not 0 <= age <= max_heartbeat_age_seconds:
            raise ValueError("OBSERVER_HEARTBEAT_STALE_OR_FUTURE")
        path = root / "paper-events.sqlite3"
        audit = verify_streams(path)
        with closing(sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            for sid, (cursor, sha) in body["stream_prefixes"].items():
                row = db.execute(
                    "SELECT chain_sha FROM observer_stream_events WHERE stream_id=? AND seq=?",
                    (sid, cursor),
                ).fetchone()
                if row != (sha,):
                    raise ValueError("OBSERVER_HEARTBEAT_STREAM_PREFIX_DIVERGENCE")
        control = audit["streams"]["observer:control"]
        manifest = control["checkpoint"]["manifest"]
        if (
            manifest["manifest_sha"]
            != digest({k: v for k, v in manifest.items() if k != "manifest_sha"})
            or manifest["manifest_sha"] != body["manifest_sha"]
            or manifest["revision"] != body["revision"]
        ):
            raise ValueError("OBSERVER_MANIFEST_REVISION_DIVERGENCE")
        scope = control["checkpoint"].get("scope")
        if scope is None:
            raise ValueError("OBSERVER_REQUIRED_SCOPE_NOT_YET_ENUMERATED")
        metrics = body["metrics"]
        reasons = []
        if metrics["queue_depth"] >= metrics["queue_capacity"]:
            reasons.append("WRITER_QUEUE_SATURATED")
        if metrics["disk_free_bytes"] < metrics["min_free_bytes"]:
            reasons.append("LOW_DISK")
        if metrics["journal_bytes"] > metrics["max_journal_bytes"]:
            reasons.append("JOURNAL_STORAGE_LIMIT")
        if control["event"]["kind"] == "STOP":
            reasons.append("OBSERVER_STOPPED")
        if control["checkpoint"].get("census_status") != "CURRENT_PUBLIC_CENSUS":
            reasons.append("ACCOUNT_CENSUS_UNKNOWN")
        if scope.get("budget_failure"):
            reasons.append(scope["budget_failure"])
        if scope.get("missing_accounts"):
            reasons.append("REQUIRED_ACCOUNT_STATE_MISSING")
        watchdog = "NOT_REQUIRED_FOR_BOUNDED_CANARY"
        if require_watchdog:
            witness = _private_json(root / "continuous-watchdog.status.json")
            if (
                witness["process_identity"]["pid"] == identity["pid"]
                or _process_identity(witness["process_identity"]["pid"])
                != witness["process_identity"]
                or not 0 <= (now - clock(witness["observed_at"])).total_seconds() <= 90
            ):
                raise ValueError("INDEPENDENT_WATCHDOG_MISSING_OR_STALE")
            watchdog = "SEPARATE_PROCESS_OBSERVED"
        required = ["account:" + alias for alias in scope["expected_accounts"]]
        required += [
            prefix + market
            for market in scope["required_markets"]
            for prefix in ("ccxt_l2:", "ccxt_trades:", "public:")
        ]
        feeds = {}
        for sid in required:
            row = audit["streams"].get(sid)
            failed = []
            if row is None:
                feeds[sid] = {
                    "status": "MISSING",
                    "reasons": ["REQUIRED_SUBSCRIPTION_NOT_OBSERVED"],
                }
                continue
            checkpoint = row["checkpoint"]
            transport = checkpoint.get("last_transport_at")
            transport_age = None if transport is None else (now - clock(transport)).total_seconds()
            if checkpoint.get("transport") != "CONNECTED":
                failed.append("TRANSPORT_" + checkpoint.get("transport", "UNKNOWN"))
            if transport_age is None or not 0 <= transport_age <= max_transport_age_seconds:
                failed.append("TRANSPORT_STALE_OR_MISSING")
            if not checkpoint.get("baseline_valid", False):
                failed.append("BASELINE_NOT_VALID")
            if sid.startswith(("account:", "public:")) and not checkpoint.get(
                "subscription_acknowledged"
            ):
                failed.append("NATIVE_SUBSCRIPTION_ACK_NOT_OBSERVED")
            quote_age = None
            if sid.startswith("ccxt_l2:"):
                quote = checkpoint.get("last_quote_at")
                quote_age = None if quote is None else (now - clock(quote)).total_seconds()
                if quote_age is None or not 0 <= quote_age <= max_quote_age_seconds:
                    failed.append("QUOTE_STALE_OR_MISSING")
            feeds[sid] = {
                "status": "DEGRADED" if failed else "CONNECTED_QUIET_OR_ACTIVE",
                "reasons": failed,
                "cursor": row["cursor"],
                "head_sha": row["chain_sha"],
                "epoch": row["event"]["epoch"],
                "baseline_valid": checkpoint.get("baseline_valid", False),
                "last_receipt_at": row["event"]["first_known_at"],
                "subscription_acknowledged": checkpoint.get(
                    "subscription_acknowledged", "UNKNOWN_CCXT_ACK"
                ),
                "transport_age_seconds": transport_age,
                "quote_age_seconds": quote_age,
                "state_age_seconds": None
                if checkpoint.get("last_state_at") is None
                else (now - clock(checkpoint["last_state_at"])).total_seconds(),
                "market_trade_age_seconds": None
                if checkpoint.get("last_market_trade_at", checkpoint.get("last_cache_at")) is None
                else (
                    now
                    - clock(checkpoint.get("last_market_trade_at", checkpoint.get("last_cache_at")))
                ).total_seconds(),
                "historical_gap_count": row["gap_count"],
                "historical_coverage": "GAP_UNRESOLVED" if row["gap_count"] else "NO_RECORDED_GAP",
                "last_gap_reason": checkpoint.get("gap_reason"),
                "trade_inactivity_is_failure": False,
            }
        degraded = bool(reasons) or any(
            row["status"] != "CONNECTED_QUIET_OR_ACTIVE" for row in feeds.values()
        )
        return {
            **common,
            "health": "DEGRADED_OBSERVER_ONLY",
            "feed_health": "DEGRADED" if degraded else "CURRENT_FEEDS_OBSERVED",
            "reason_codes": reasons,
            "observer_process_verified": True,
            "revision": body["revision"],
            "manifest_sha": body["manifest_sha"],
            "heartbeat_age_seconds": age,
            "journal_integrity": audit["integrity"],
            "required_feed_count": len(required),
            "feeds": feeds,
            "metrics": metrics,
            "native_acknowledged_count": sum(
                row.get("subscription_acknowledged") is True for row in feeds.values()
            ),
            "historical_gap_count": sum(row["gap_count"] for row in audit["streams"].values()),
            "historical_coverage": "GAP_UNRESOLVED",
            "independent_watchdog": watchdog,
            "release_independently_attested": False,
        }
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        code = str(exc)
        if len(code) > 150 or "0x" in code:
            code = type(exc).__name__
        return {**common, "health": "UNKNOWN", "feed_health": "UNKNOWN", "reason_codes": [code]}


def verify_watchdog_samples(root: Path) -> dict:
    """Read-only verification of the independent watchdog's bounded audit log."""
    path = Path(root) / "continuous-watchdog.samples.jsonl"
    if not path.exists():
        return {
            "samples": 0,
            "head_sha": "0" * 64,
            "first_at": None,
            "last_at": None,
            "max_interval_seconds": None,
            "degraded_samples": 0,
            "maxima": {},
        }
    if path.is_symlink() or path.stat().st_mode & 0o077 or path.stat().st_nlink != 1:
        raise ValueError("OBSERVER_WATCHDOG_LOG_PERMISSION_INVALID")
    if path.stat().st_size > 100_000_000:
        raise ValueError("OBSERVER_WATCHDOG_LOG_BOUND_EXCEEDED")
    result = {
        "samples": 0,
        "head_sha": "0" * 64,
        "first_at": None,
        "last_at": None,
        "max_interval_seconds": 0,
        "degraded_samples": 0,
        "maxima": {},
    }
    with path.open() as source:
        for line in source:
            row = json.loads(line)
            body = {k: v for k, v in row.items() if k != "sample_sha"}
            if row["sample_sha"] != digest(body) or row["prior_sha"] != result["head_sha"]:
                raise ValueError("OBSERVER_WATCHDOG_LOG_CHAIN_DIVERGENCE")
            if row["sequence"] != result["samples"] + 1 or row.get("order_route") != "NONE":
                raise ValueError("OBSERVER_WATCHDOG_LOG_SEQUENCE_DIVERGENCE")
            at = clock(row["observed_at"])
            if result["last_at"] is not None:
                interval = (at - clock(result["last_at"])).total_seconds()
                if interval < 0:
                    raise ValueError("OBSERVER_WATCHDOG_CLOCK_REGRESSION")
                result["max_interval_seconds"] = max(result["max_interval_seconds"], interval)
            result["samples"] += 1
            result["degraded_samples"] += row["feed_health"] != "CURRENT_FEEDS_OBSERVED"
            result["first_at"] = result["first_at"] or row["observed_at"]
            result["last_at"], result["head_sha"] = row["observed_at"], row["sample_sha"]
            for key, value in row["metrics"].items():
                if type(value) in (int, float):
                    result["maxima"][key] = max(result["maxima"].get(key, value), value)
    return result


def _append_watchdog_sample(
    root: Path, result: dict, *, observed_at: str, sequence: int, prior_sha: str
) -> str:
    import stat

    body = {
        "schema": "paper_continuous_watchdog_sample_v1",
        "sequence": sequence,
        "prior_sha": prior_sha,
        "observed_at": observed_at,
        "process_identity": _process_identity(os.getpid()),
        "feed_health": result["feed_health"],
        "reasons": result.get("reason_codes", []),
        "revision": result.get("revision"),
        "manifest_sha": result.get("manifest_sha"),
        "required_feed_count": result.get("required_feed_count"),
        "feeds_sha": digest(result.get("feeds", {})),
        "metrics": result.get("metrics", {}),
        "historical_gap_count": result.get("historical_gap_count"),
        "order_route": "NONE",
    }
    sha = digest(body)
    raw = (
        json.dumps({**body, "sample_sha": sha}, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    fd = os.open(
        Path(root) / "continuous-watchdog.samples.jsonl",
        os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_uid != os.geteuid()
            or info.st_size + len(raw) > 100_000_000
        ):
            raise ValueError("OBSERVER_WATCHDOG_LOG_PERMISSION_OR_SIZE_INVALID")
        with os.fdopen(os.dup(fd), "ab") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
    finally:
        os.close(fd)
    return sha


def audit_continuous_shadow(root: Path, *, as_of: str) -> dict:
    """Measure real evidence; elapsed time never automatically qualifies a run."""
    from .pm_forward_stream_journal import verify_streams

    # Bounded legacy observers share the SQLite filename but do not contain
    # continuous stream tables. Distinguish that unsupported scope from a
    # verified stream (or a fabricated zero-event financial result).
    try:
        audit = verify_streams(Path(root) / "paper-events.sqlite3")
    except sqlite3.OperationalError as exc:
        if not str(exc).startswith("no such table: observer_stream_"):
            raise
        return {
            "schema": "paper_continuous_shadow_audit_v1",
            "status": "BLOCKED_INCOMPATIBLE_JOURNAL",
            "as_of": as_of,
            "gate_reasons": ["CONTINUOUS_STREAM_SCHEMA_NOT_PRESENT"],
            "actual_witness_window_seconds": None,
            "watchdog": None,
            "latency": {},
            "matched_wallet_receipts": None,
            "reconciliation": {},
            "journal_integrity": "UNVERIFIED",
            "stream_head_sha": None,
            "streams": {},
            "financial_rows": None,
            "source_nav_attested": False,
            "scientifically_qualified": False,
            "operator_cutover_authorized": False,
            "paper_observed": False,
            "order_route": "NONE",
        }
    samples = verify_watchdog_samples(root)
    elapsed = (
        0
        if samples["first_at"] is None
        else (clock(samples["last_at"]) - clock(samples["first_at"])).total_seconds()
    )
    if samples["last_at"] and clock(samples["last_at"]) > clock(as_of):
        raise ValueError("OBSERVER_SHADOW_FUTURE_WITNESS")
    latency, reconciliation = {}, {}
    with closing(
        sqlite3.connect(
            "file:" + str((Path(root) / "paper-events.sqlite3").resolve()) + "?mode=ro", uri=True
        )
    ) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for prefix in ("account:", "ccxt_l2:", "public:"):
            base = (
                "SELECT (julianday(json_extract(payload,'$.first_known_at'))-"
                "julianday(json_extract(payload,'$.source_event_at')))*86400000 AS latency_ms "
                "FROM observer_stream_events WHERE stream_id LIKE ? "
                "AND json_extract(payload,'$.kind')='OBSERVATION' "
                "AND json_extract(payload,'$.source_event_at') IS NOT NULL"
            )
            count = db.execute("SELECT COUNT(*) FROM (" + base + ")", (prefix + "%",)).fetchone()[0]
            values = {"samples": count, "unit": "ms", "scope": "PERSISTED_POST_BASELINE_FRAMES"}
            for label, quantile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
                values[label] = (
                    None
                    if not count
                    else db.execute(
                        base + " ORDER BY latency_ms LIMIT 1 OFFSET ?",
                        (prefix + "%", min(count - 1, int((count - 1) * quantile))),
                    ).fetchone()[0]
                )
            latency[prefix] = values
        matched = db.execute("SELECT COUNT(*) FROM public_wallet_trade_receipts").fetchone()[0]
        finance = {
            table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("runs", "events")
        }
        for sid, row in audit["streams"].items():
            if sid.startswith("reconcile:"):
                reconciliation[sid] = row["checkpoint"]
    gates = []
    if elapsed < 72 * 3600:
        gates.append("ACTUAL_72_HOUR_WATCHDOG_WINDOW_NOT_COMPLETE")
    if samples["samples"] == 0 or samples["max_interval_seconds"] > 90:
        gates.append("INDEPENDENT_WATCHDOG_COVERAGE_INCOMPLETE")
    if samples["degraded_samples"]:
        gates.append("DEGRADED_INTERVALS_REQUIRE_INCIDENT_REVIEW")
    if not reconciliation:
        gates.append("INDEPENDENT_WALLET_FILL_COMPARISON_UNKNOWN")
    if any(finance.values()):
        gates.append("UNEXPECTED_FINANCIAL_STATE")
    return {
        "schema": "paper_continuous_shadow_audit_v1",
        "status": "BLOCKED_BY_GATE" if gates else "OPERATOR_ACCEPTANCE_REQUIRED",
        "as_of": as_of,
        "gate_reasons": gates,
        "actual_witness_window_seconds": elapsed,
        "watchdog": samples,
        "latency": latency,
        "matched_wallet_receipts": matched,
        "reconciliation": reconciliation,
        "journal_integrity": audit["integrity"],
        "stream_head_sha": audit["head_sha"],
        "streams": {
            sid: {
                key: row[key]
                for key in (
                    "cursor",
                    "gap_count",
                    "baseline_count",
                    "observation_count",
                    "epoch_count",
                )
            }
            for sid, row in audit["streams"].items()
        },
        "financial_rows": finance,
        "source_nav_attested": False,
        "scientifically_qualified": False,
        "operator_cutover_authorized": False,
        "paper_observed": False,
        "order_route": "NONE",
    }


def continuous_watchdog(root: Path, *, interval_seconds: float = 15, expected_revision=None):
    """Unattended independent status/alert file; no external message or service mutation."""
    import time

    if not 1 <= interval_seconds <= 60:
        raise ValueError("OBSERVER_WATCHDOG_INTERVAL_INVALID")
    import fcntl

    root = Path(root)
    _private_dir(root)
    lease = os.open(
        root / "continuous-watchdog.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    log = verify_watchdog_samples(root)
    sequence, previous = log["samples"], log["head_sha"]
    while True:
        now = datetime.now(UTC).isoformat()
        result = inspect_continuous_observer(root, as_of=now, expected_revision=expected_revision)
        sequence += 1
        previous = _append_watchdog_sample(
            root, result, observed_at=now, sequence=sequence, prior_sha=previous
        )
        _atomic_private_json(
            Path(root),
            "continuous-watchdog.status.json",
            {
                "schema": "paper_continuous_watchdog_status_v1",
                "observed_at": now,
                "process_identity": _process_identity(os.getpid()),
                "result": result,
                "alert": result["feed_health"] != "CURRENT_FEEDS_OBSERVED",
                "order_route": "NONE",
            },
        )
        print(
            json.dumps(
                {
                    "observed_at": now,
                    "feed_health": result["feed_health"],
                    "reasons": result.get("reason_codes", []),
                    "order_route": "NONE",
                }
            ),
            flush=True,
        )
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent read-only public observer watchdog")
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--as-of", default=datetime.now(UTC).isoformat())
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--expected-revision")
    parser.add_argument("--require-watchdog", action="store_true")
    parser.add_argument("--shadow-report", action="store_true")
    args = parser.parse_args()
    if args.shadow_report:
        print(
            json.dumps(
                audit_continuous_shadow(args.state_root, as_of=args.as_of), sort_keys=True, indent=2
            )
        )
        return
    if args.watch and not args.continuous:
        parser.error("--watch requires --continuous")
    if args.continuous:
        if args.watch:
            continuous_watchdog(args.state_root, expected_revision=args.expected_revision)
            return
        print(
            json.dumps(
                inspect_continuous_observer(
                    args.state_root,
                    as_of=args.as_of,
                    expected_revision=args.expected_revision,
                    require_watchdog=args.require_watchdog,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    result = inspect_public_observer_heartbeat(
        args.state_root,
        journal_db=args.state_root / "paper-events.sqlite3",
        as_of=args.as_of,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
