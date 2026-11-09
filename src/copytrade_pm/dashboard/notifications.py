"""Independent, read-only incident-to-notification dry-run pipeline (TD-11).

No broker, Guardian mutation, network-delivery implementation, or browser dependency.
The source is the already validated owner status capture, not a second risk detector.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Iterator, Protocol

SCHEMA = "dashboard_notification_state_v1"
MAX_BYTES = 65536
MAX_INCIDENTS = 128
MAX_ATTEMPTS = 3
RETRY_SECONDS = (5, 30, 120)
REASON = re.compile(r"[A-Z][A-Z0-9_:-]{0,63}\Z")
EMPTY: dict[str, Any] = {
    "schema": SCHEMA,
    "updated_at": None,
    "source_status": "UNKNOWN",
    "external_delivery": "NOT_CONFIGURED",
    "incidents": [],
    "last_error": None,
    "last_source_observed_at": None,
    "last_source_binding": None,
    "incident_sequence": 0,
}


class NotificationStateError(ValueError):
    """A corrupt/unsafe state is never replaced with an empty delivery history."""


class Delivery(Protocol):
    def send(self, record: dict[str, Any]) -> None: ...


class DryRunDelivery:
    """An explicitly non-network delivery backend for source and staging tests."""

    def send(self, record: dict[str, Any]) -> None:
        # All real external destinations remain unconfigured.
        return None


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise NotificationStateError("UTC_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise NotificationStateError("INVALID_UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise NotificationStateError("INVALID_UTC") from exc


def _file_bytes(path: Path) -> bytes | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise NotificationStateError("STATE_ACCESS_DENIED") from exc
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_BYTES:
            raise NotificationStateError("STATE_NOT_BOUNDED_REGULAR_FILE")
        data = os.read(fd, MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise NotificationStateError("STATE_TOO_LARGE")
        return data
    finally:
        os.close(fd)


def _validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise NotificationStateError("STATE_SCHEMA_INVALID")
    records = data.get("incidents")
    if (
        not isinstance(records, list)
        or len(records) > MAX_INCIDENTS
        or data.get("external_delivery") != "NOT_CONFIGURED"
    ):
        raise NotificationStateError("STATE_CONTRACT_INVALID")
    sequence = data.get("incident_sequence", 0)
    if type(sequence) is not int or not 0 <= sequence < 2**63:
        raise NotificationStateError("STATE_INCIDENT_SEQUENCE_INVALID")
    ids: set[str] = set()
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise NotificationStateError("STATE_RECORD_INVALID")
        if item["id"] in ids or not re.fullmatch(r"[a-f0-9]{64}", item["id"]):
            raise NotificationStateError("STATE_RECORD_DUPLICATE_OR_INVALID")
        ids.add(item["id"])
        if (
            item.get("status")
            not in {"PENDING", "RETRY", "DRY_RUN_DELIVERED", "FAILED", "ACKNOWLEDGED"}
            or type(item.get("attempts")) is not int
            or not 0 <= item["attempts"] <= MAX_ATTEMPTS
            or type(item.get("active")) is not bool
            or not isinstance(item.get("reason"), str)
            or not REASON.fullmatch(item["reason"])
        ):
            raise NotificationStateError("STATE_RECORD_INVALID")
        if (
            "acknowledged" in item
            and type(item["acknowledged"]) is not bool
            or item.get("delivery_status", "UNKNOWN")
            not in {"UNKNOWN", "PENDING", "RETRY", "DRY_RUN_DELIVERED", "FAILED"}
        ):
            raise NotificationStateError("STATE_DELIVERY_OR_ACK_INVALID")
        _parse_utc(item.get("source_observed_at"))
    return data


def read_state(path: Path) -> dict[str, Any]:
    """Fail closed; the dashboard gets a bounded status, not a write handle."""
    raw = _file_bytes(path)
    if raw is None:
        return {**EMPTY, "incidents": []}
    try:
        return _validate(json.loads(raw))
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise NotificationStateError("STATE_CORRUPT_OR_UNTRUSTED") from exc


def dashboard_status(path: Path | None, *, now: datetime | None = None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "NOT_CONFIGURED",
            "external_delivery": "NOT_CONFIGURED",
            "source_status": "UNKNOWN",
            "incidents": [],
            "error_code": None,
        }
    try:
        data = read_state(path)
        records = data["incidents"][-20:]
        now = now or datetime.now(UTC)
        updated = data.get("updated_at")
        age = (now - _parse_utc(updated)).total_seconds() if updated else None
        stale = age is None or not 0 <= age <= 120
        return {
            "status": ("STALE" if stale else "DRY_RUN_ONLY" if records else "NO_DELIVERY_ATTEMPTS"),
            "external_delivery": "NOT_CONFIGURED",
            "source_status": "STALE" if stale else data.get("source_status", "UNKNOWN"),
            "last_source_status": data.get("source_status", "UNKNOWN"),
            "state_age_seconds": age,
            "updated_at": data.get("updated_at"),
            "incidents": [
                {
                    key: item.get(key)
                    for key in (
                        "id",
                        "reason",
                        "severity",
                        "source_observed_at",
                        "active",
                        "status",
                        "attempts",
                        "next_attempt_at",
                        "last_error",
                    )
                }
                | {
                    "acknowledged": item.get("acknowledged", item["status"] == "ACKNOWLEDGED"),
                    "delivery_status": item.get(
                        "delivery_status",
                        item["status"] if item["status"] != "ACKNOWLEDGED" else "UNKNOWN",
                    ),
                }
                for item in records
            ],
            "error_code": None,
        }
    except NotificationStateError, PermissionError, OSError:
        return {
            "status": "BLOCKED",
            "external_delivery": "NOT_CONFIGURED",
            "source_status": "UNKNOWN",
            "incidents": [],
            "error_code": "STATE_UNAVAILABLE",
        }


def _secure_directory(path: Path) -> None:
    meta = path.stat()
    if not stat.S_ISDIR(meta.st_mode) or meta.st_mode & 0o022:
        raise NotificationStateError("STATE_DIRECTORY_UNSAFE")


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    _secure_directory(path.parent)
    lock_path = path.with_name(path.name + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _save(path: Path, state: dict[str, Any]) -> None:
    _validate(state)
    data = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise NotificationStateError("STATE_TOO_LARGE")
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def _reasons(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        raise NotificationStateError("OWNER_INCIDENT_SOURCE_INVALID")
    health = payload.get("health")
    if health is not None and not isinstance(health, dict):
        raise NotificationStateError("OWNER_INCIDENT_SOURCE_INVALID")
    items = [payload.get("halts"), (health or {}).get("reasons")]
    causes: set[str] = set()
    for field in items:
        if field is None:
            continue
        if not isinstance(field, list) or len(field) > 128:
            raise NotificationStateError("OWNER_INCIDENT_SOURCE_INVALID")
        for item in field:
            if not isinstance(item, str) or not REASON.fullmatch(item):
                raise NotificationStateError("OWNER_INCIDENT_CAUSE_INVALID")
            causes.add(item)
    return sorted(causes)


def _incident_key(binding: str, reason: str) -> str:
    return sha256(f"{binding}:{reason}".encode()).hexdigest()


def process_once(
    state_path: Path,
    owner_status: dict[str, Any],
    *,
    delivery: Delivery | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read one owner observation, dedup/retry atomically; never touch Guardian."""
    now = now or datetime.now(UTC)
    clock = _utc(now)
    delivery = delivery or DryRunDelivery()
    with _exclusive(state_path):
        state = read_state(state_path)
        state["updated_at"] = clock
        state["external_delivery"] = "NOT_CONFIGURED"
        source_status = owner_status.get("status", "UNKNOWN")
        state["source_status"] = source_status
        if source_status == "VERIFIED":
            binding = owner_status.get("account_binding_sha")
            observed = owner_status.get("source_observed_at")
            if not isinstance(binding, str) or re.fullmatch("[a-fA-F0-9]{64}", binding) is None:
                raise NotificationStateError("OWNER_BINDING_INVALID")
            source_time = _parse_utc(observed)
            if source_time > now:
                raise NotificationStateError("OWNER_FUTURE_INCIDENT_CLOCK")
            previous = state.get("last_source_observed_at")
            if previous is not None and source_time < _parse_utc(previous):
                raise NotificationStateError("OWNER_INCIDENT_CLOCK_REGRESSION")
            causes = _reasons(owner_status.get("data"))
            state["last_source_observed_at"] = _utc(source_time)
            state["last_source_binding"] = binding
            active_keys = {_incident_key(binding, item) for item in causes}
            for record in state["incidents"]:
                same_account = record.get("key") == _incident_key(binding, record["reason"])
                if same_account and record.get("active") and record.get("key") not in active_keys:
                    record["active"] = False
                    record["resolved_at"] = clock
            for reason in causes:
                key = _incident_key(binding, reason)
                if any(item.get("key") == key and item["active"] for item in state["incidents"]):
                    continue
                # Retention must never reset identity after the 128th occurrence.
                sequence = state.get("incident_sequence", 0) + 1
                state["incident_sequence"] = sequence
                record_id = sha256(f"incident-v2:{key}:{sequence}".encode()).hexdigest()
                state["incidents"].append(
                    {
                        "id": record_id,
                        "key": key,
                        "reason": reason,
                        "severity": "UNSPECIFIED",
                        "source_observed_at": _utc(source_time),
                        "active": True,
                        "status": "PENDING",
                        "delivery_status": "PENDING",
                        "acknowledged": False,
                        "attempts": 0,
                        "next_attempt_at": clock,
                        "last_error": None,
                    }
                )
            if len(state["incidents"]) > MAX_INCIDENTS:
                inactive = [i for i in state["incidents"] if not i["active"]]
                active = [i for i in state["incidents"] if i["active"]]
                if len(active) > MAX_INCIDENTS:
                    raise NotificationStateError("TOO_MANY_ACTIVE_INCIDENTS")
                state["incidents"] = (
                    inactive[-(MAX_INCIDENTS - len(active)) :]
                    if len(active) < MAX_INCIDENTS
                    else []
                ) + active
        # No invented event is generated while owner capture is stale or unavailable.
        for record in state["incidents"]:
            if not record["active"] or record["status"] not in {"PENDING", "RETRY"}:
                continue
            if _parse_utc(record["next_attempt_at"]) > now:
                continue
            try:
                delivery.send(record.copy())
            except Exception as exc:
                record["attempts"] += 1
                record["last_error"] = type(exc).__name__[:64]
                if record["attempts"] >= MAX_ATTEMPTS:
                    record["status"] = "FAILED"
                    record["next_attempt_at"] = None
                else:
                    record["status"] = "RETRY"
                    record["next_attempt_at"] = _utc(
                        now + timedelta(seconds=RETRY_SECONDS[record["attempts"] - 1])
                    )
            else:
                record["attempts"] += 1
                record["status"] = "DRY_RUN_DELIVERED"
                record["next_attempt_at"] = None
            record["delivery_status"] = record["status"]
        _save(state_path, state)
        return dashboard_status(state_path, now=now)


def acknowledge(state_path: Path, incident_id: str) -> bool:
    """Acknowledge a notification only; never touch owner HALT or incident source."""
    if not re.fullmatch(r"[a-f0-9]{64}", incident_id):
        return False
    with _exclusive(state_path):
        state = read_state(state_path)
        for record in state["incidents"]:
            if record["id"] == incident_id:
                record.setdefault(
                    "delivery_status",
                    record["status"] if record["status"] != "ACKNOWLEDGED" else "UNKNOWN",
                )
                record["acknowledged"] = True
                record["status"] = "ACKNOWLEDGED"
                _save(state_path, state)
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent dry-run owner-incident notifier")
    parser.add_argument(
        "--state-file",
        type=Path,
        required=True,
        help="Private standalone state file; precreate its secured parent directory",
    )
    parser.add_argument("--once", action="store_true", help="One observation, no daemon")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args(argv)
    if args.interval < 10 or args.interval > 3600:
        parser.error("--interval must be 10..3600 seconds")
    from .adapter import DashboardReader

    while True:
        source = DashboardReader().guardian("status")
        summary = process_once(args.state_file, source)
        print(
            json.dumps(
                {
                    key: summary.get(key)
                    for key in ("status", "source_status", "external_delivery", "error_code")
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
