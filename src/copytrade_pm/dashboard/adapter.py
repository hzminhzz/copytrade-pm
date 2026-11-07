"""Bounded, provenance-preserving readers for a strictly non-trading dashboard.

The native registry reader is the authority for wallet identity. Protected
Guardian data is read ONLY from independently published, restricted snapshots;
this module never opens the financial journal, imports Guardian, or invokes a
provider. No browser input can select a filesystem path or command.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from threading import BoundedSemaphore, Lock
import time
from typing import Any, Callable, Mapping

from copytrade_pm import pm_operations as operations
from copytrade_pm import pm_runtime_readonly as runtime
from copytrade_pm import wallet_registry as registry

READ_SCHEMA = "dashboard_read_result_v1"
PROJECTION_SCHEMA = "dashboard_guardian_capture_v1"
GUARDIAN_COMMANDS = frozenset({"status", "risk", "broker", "portfolio", "intent", "history"})
PRIVATE_ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}\b")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SHA40 = re.compile(r"^[a-f0-9]{40}$")
SERVICES = (
    "prop-production-guardian.service",
    "prop-production-watchdog.service",
    "prop-production-observer.service",
    "prop-production-planner.service",
    "prop-production-broker.service",
    "prop-production-bybit-observer.service",
)
STATUS = frozenset(
    {
        "VERIFIED",
        "DEGRADED",
        "STALE",
        "UNKNOWN",
        "BLOCKED",
        "UNAVAILABLE",
        "NOT_RUNNING",
        "NOT_REGISTERED_AT_ASOF",
        "SCHEMA_UPGRADE_REQUIRED",
    }
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def parse_utc(raw: object) -> datetime | None:
    if not isinstance(raw, str) or len(raw) > 45:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        return None
    return value.astimezone(UTC)


def safe_text(raw: object, maximum: int = 128) -> str | None:
    if not isinstance(raw, str) or len(raw) > maximum:
        return None
    if any(ord(c) < 32 for c in raw):
        return None
    return PRIVATE_ADDRESS.sub("[PRIVATE_WALLET]", raw)


def safe_decimal(raw: object) -> str | None:
    """Preserve Decimal strings exactly; do not convert finance through float."""
    if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
        return None
    value = str(raw)
    if not value or len(value) > 42:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or abs(number.as_tuple().exponent) > 18:
        return None
    return value


def sanitized(value: object) -> object:
    """Defense in depth over the already redacted native wallet projection."""
    if isinstance(value, str):
        return PRIVATE_ADDRESS.sub("[PRIVATE_WALLET]", value)
    if isinstance(value, dict):
        return {
            str(key): sanitized(item)
            for key, item in value.items()
            if str(key).lower()
            not in {
                "address",
                "account_id",
                "private_key",
                "secret",
                "exclusion_reason",
                "wallet_address",
            }
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    return value


def envelope(
    capability: str,
    status: str,
    *,
    authority: str,
    now: datetime,
    data: object = None,
    source_schema: str | None = None,
    source_observed_at: str | None = None,
    captured_at: str | None = None,
    revision: str | None = None,
    inventory_sha256: str | None = None,
    journal_sequence: int | None = None,
    account_binding_sha: str | None = None,
    limitations: list[str] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    if status not in STATUS:
        raise ValueError("INVALID_DASHBOARD_STATUS")
    return {
        "schema": READ_SCHEMA,
        "capability": capability,
        "status": status,
        "authority": authority,
        "source_schema": source_schema,
        "source_observed_at": source_observed_at,
        "captured_at": captured_at,
        "retrieved_at": utc_text(now),
        "revision": revision,
        "inventory_sha256": inventory_sha256,
        "journal_sequence": journal_sequence,
        "account_binding_sha": account_binding_sha,
        "data": data,
        "limitations": limitations or [],
        "error_code": error_code,
        "trading_authorized": False,
        "scientifically_qualified": False,
    }


class GuardianCaptureDirectory:
    """Read only producer-owned, bounded JSON, never production journals.

    The capture directory/files must be owned by a different OS identity than
    the dashboard; they must be neither group nor world writable. Its writer is
    a separate *future* authorized integration, not a dashboard responsibility.
    """

    def __init__(self, directory: Path | None):
        self.directory = directory

    def __call__(self, command: str) -> dict[str, Any]:
        if command not in GUARDIAN_COMMANDS:
            raise ValueError("UNAPPROVED_GUARDIAN_CAPABILITY")
        if self.directory is None:
            raise FileNotFoundError("NO_PROTECTED_SNAPSHOT_AUTHORITY")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        root_fd = os.open(self.directory, flags | os.O_DIRECTORY)
        try:
            owner = os.fstat(root_fd)
            if owner.st_uid == os.geteuid() or owner.st_mode & 0o022:
                raise PermissionError("UNTRUSTED_GUARDIAN_CAPTURE_DIRECTORY")
            fd = os.open(f"{command}.json", flags, dir_fd=root_fd)
            try:
                metadata = os.fstat(fd)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid == os.geteuid()
                    or metadata.st_mode & 0o022
                    or not 0 < metadata.st_size <= 131_072
                ):
                    raise PermissionError("UNTRUSTED_GUARDIAN_CAPTURE_FILE")
                with os.fdopen(fd, "rb", closefd=False) as reader:
                    raw = reader.read(131_073)
                if len(raw) != metadata.st_size or len(raw) > 131_072:
                    raise ValueError("GUARDIAN_CAPTURE_CHANGED_DURING_READ")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("GUARDIAN_CAPTURE_SCHEMA")
                return value
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)


def _guardian_public_data(command: str, native: Mapping[str, Any]) -> dict[str, Any]:
    if command == "status":
        health = native.get("health")
        health = health if isinstance(health, dict) else {}
        ages = health.get("ages_ms")
        ages = ages if isinstance(ages, dict) else {}
        return {
            "state": safe_text(native.get("state")),
            "mode": safe_text(native.get("mode")),
            "order_route": safe_text(native.get("order_route")),
            "account_readiness": safe_text(native.get("account_readiness")),
            "halts": [safe_text(x) for x in native.get("halts", [])[:40] if safe_text(x)]
            if isinstance(native.get("halts"), list)
            else None,
            "health": {
                "status": safe_text(health.get("status")),
                "reasons": [safe_text(x) for x in health.get("reasons", [])[:40] if safe_text(x)]
                if isinstance(health.get("reasons"), list)
                else None,
                "source_state": safe_text(health.get("source_state")),
                "ages_ms": {
                    key: value if type(value) is int and value >= 0 else None
                    for key, value in ages.items()
                    if key
                    in {
                        "financial_progress",
                        "account",
                        "market",
                        "watchdog",
                        "source_heartbeat",
                        "source_book",
                    }
                },
            },
        }
    if command == "risk":
        finance = native.get("finance")
        finance = finance if isinstance(finance, dict) else {}
        raw_used = native.get("pod_loss_used")
        used = raw_used if isinstance(raw_used, dict) else {}
        pods = [
            {"pod_id": safe_text(name, 96), "loss_used": safe_decimal(amount), "loss_budget": None}
            for name, amount in sorted(used.items(), key=lambda pair: str(pair[0]))[:64]
            if safe_text(name, 96) is not None
        ]
        return {
            "finance": {
                key: safe_decimal(finance.get(key))
                for key in (
                    "equity",
                    "cash",
                    "unrealized",
                    "initial_margin",
                    "maintenance_margin",
                    "headroom",
                    "daily_headroom",
                    "trailing_headroom",
                    "daily_baseline",
                    "daily_floor",
                    "internal_floor",
                    "trailing_floor",
                    "risk_floor",
                    "high_water",
                    "day_high_water",
                    "realized_made",
                )
            },
            "finance_observed_at_ms": finance.get("observed_at_ms")
            if type(finance.get("observed_at_ms")) is int
            else None,
            "reservation_count": len(native["reservations"])
            if isinstance(native.get("reservations"), dict)
            else None,
            "pod_loss_used": pods,
            "pod_entries_truncated": len(used) > 64,
            "pod_budget_authority": "UNAVAILABLE_IN_NATIVE_OPERATOR_RISK_V1",
            "exposure": (
                {
                    "status": "VERIFIED_OWNER_MARK_SNAPSHOT",
                    "gross": safe_decimal(native["exposure"].get("gross")),
                    "net": safe_decimal(native["exposure"].get("net")),
                    "observed_at_ms": native["exposure"].get("observed_at_ms"),
                }
                if isinstance(native.get("exposure"), dict)
                and native["exposure"].get("status") == "VERIFIED_OWNER_MARK_SNAPSHOT"
                and safe_decimal(native["exposure"].get("gross")) is not None
                and safe_decimal(native["exposure"].get("net")) is not None
                else {"status": "UNKNOWN", "gross": None, "net": None, "observed_at_ms": None}
            ),
        }
    if command == "broker":
        return {
            "certainty": safe_text(native.get("certainty")),
            "broker_epoch": native.get("broker_epoch")
            if type(native.get("broker_epoch")) is int
            else None,
            "last_snapshot_ms": native.get("last_snapshot_ms")
            if type(native.get("last_snapshot_ms")) is int
            else None,
            "flat_confirmed": native.get("flat_confirmed")
            if type(native.get("flat_confirmed")) is bool
            else None,
            "provider_cutoff_sha": native.get("provider_cutoff_sha")
            if isinstance(native.get("provider_cutoff_sha"), str)
            and SHA256.fullmatch(native["provider_cutoff_sha"])
            else None,
            "fills": [
                {
                    "execution_id_sha": f.get("execution_id_sha")
                    if isinstance(f.get("execution_id_sha"), str)
                    and SHA256.fullmatch(f["execution_id_sha"])
                    else None,
                    "intent_id": safe_text(f.get("intent_id"), 96),
                    "market": safe_text(f.get("market"), 96),
                    "quantity": safe_decimal(f.get("quantity")),
                    "price": safe_decimal(f.get("price")),
                    "fee": safe_decimal(f.get("fee")),
                    "known_at_ms": f.get("known_at_ms")
                    if type(f.get("known_at_ms")) is int and f["known_at_ms"] >= 0
                    else None,
                }
                for f in native.get("fills", [])[:120]
                if isinstance(f, dict)
            ]
            if isinstance(native.get("fills"), list)
            else [],
            "total_fills": native.get("total_fills")
            if type(native.get("total_fills")) is int and native["total_fills"] >= 0
            else None,
            "fills_truncated": native.get("fills_truncated") is True,
        }
    if command == "portfolio":
        decisions = native.get("decisions")
        if not isinstance(decisions, list):
            return {"decision_count": None, "decision_statuses": None, "decisions": []}
        visible = []
        for item in decisions[:64]:
            if not isinstance(item, dict):
                continue
            pods = item.get("pods")
            visible.append(
                {
                    "decision_id": safe_text(item.get("decision_id"), 96),
                    "release_sha": safe_text(item.get("release_sha"), 96),
                    "status": safe_text(item.get("status")),
                    "reasons": [safe_text(r) for r in item.get("reasons", [])[:8] if safe_text(r)]
                    if isinstance(item.get("reasons"), list)
                    else [],
                    "pod_count": len(pods) if isinstance(pods, list) else None,
                    "proposal_id": safe_text(item.get("proposal_id"), 96),
                    "first_known_ms": item.get("first_known_ms")
                    if type(item.get("first_known_ms")) is int
                    else None,
                    "due_ms": item.get("due_ms") if type(item.get("due_ms")) is int else None,
                    "batch_decision_ms": item.get("batch_decision_ms")
                    if type(item.get("batch_decision_ms")) is int
                    else None,
                    "guardian_decision_at_ms": item.get("guardian_decision_at_ms")
                    if type(item.get("guardian_decision_at_ms")) is int
                    else None,
                    "source_receipts": [
                        {
                            "receipt_sha": r.get("receipt_sha")
                            if isinstance(r.get("receipt_sha"), str)
                            and SHA256.fullmatch(r["receipt_sha"])
                            else None,
                            "source_event_ms": r.get("source_event_ms")
                            if type(r.get("source_event_ms")) is int
                            else None,
                            "source_known_ms": r.get("source_known_ms")
                            if type(r.get("source_known_ms")) is int
                            else None,
                            "local_known_ms": r.get("local_known_ms")
                            if type(r.get("local_known_ms")) is int
                            else None,
                            "source_sequence": r.get("source_sequence")
                            if type(r.get("source_sequence")) is int
                            else None,
                        }
                        for r in item.get("source_receipts", [])[:12]
                        if isinstance(r, dict)
                    ]
                    if isinstance(item.get("source_receipts"), list)
                    else [],
                    "source_receipts_truncated": item.get("source_receipts_truncated") is True,
                }
            )
        return {
            "decision_count": native.get("total_decisions")
            if type(native.get("total_decisions")) is int
            else len(decisions),
            "decision_statuses": dict(
                Counter(
                    safe_text(d.get("status")) or "UNKNOWN"
                    for d in decisions[:1000]
                    if isinstance(d, dict)
                )
            ),
            "decisions": visible,
            "truncated": len(decisions) > 64 or native.get("truncated") is True,
        }
    if command == "history":
        rows = native.get("rows")
        if not isinstance(rows, list) or len(rows) > 256:
            return {"rows": [], "status": "BLOCKED", "error_code": "HISTORY_ROW_BUDGET"}
        allowed = (
            "equity",
            "cash",
            "unrealized",
            "risk_floor",
            "daily_floor",
            "internal_floor",
            "trailing_floor",
            "headroom",
            "realized_made",
        )
        visible = []
        previous_sequence = 0
        maximum_sequence = native.get("journal_sequence")
        for item in rows:
            if not isinstance(item, dict):
                return {"rows": [], "status": "BLOCKED", "error_code": "HISTORY_ROW_SCHEMA_INVALID"}
            observed = item.get("observed_at_ms")
            sequence = item.get("journal_sequence")
            release = item.get("release_sha")
            day = item.get("day")
            reconciled = item.get("reconciled_at_ms")
            if (
                type(observed) is not int
                or observed < 0
                or type(sequence) is not int
                or sequence <= previous_sequence
                or type(maximum_sequence) is not int
                or sequence > maximum_sequence
                or not isinstance(release, str)
                or SHA256.fullmatch(release) is None
                or day is not None
                and type(day) is not int
                or reconciled is not None
                and (type(reconciled) is not int or reconciled < 0)
                or any(
                    item.get(key) is not None and safe_decimal(item.get(key)) is None
                    for key in allowed
                )
            ):
                return {"rows": [], "status": "BLOCKED", "error_code": "HISTORY_ROW_SCHEMA_INVALID"}
            previous_sequence = sequence
            visible.append(
                {
                    "journal_sequence": item.get("journal_sequence")
                    if type(item.get("journal_sequence")) is int
                    else None,
                    "observed_at_ms": observed,
                    "reconciled_at_ms": item.get("reconciled_at_ms")
                    if type(item.get("reconciled_at_ms")) is int
                    else None,
                    "day": item.get("day") if type(item.get("day")) is int else None,
                    "release_sha": item.get("release_sha")
                    if isinstance(item.get("release_sha"), str)
                    and SHA256.fullmatch(item["release_sha"])
                    else None,
                    **{key: safe_decimal(item.get(key)) for key in allowed},
                }
            )
        return {
            "rows": visible,
            "status": "RECENT_BOUNDED_TAIL",
            "evidence_class": "PAPER_SHADOW"
            if native.get("evidence_class") == "PAPER_SHADOW"
            else "UNKNOWN",
            "source_coverage": safe_text(native.get("source_coverage")),
            "truncated_to": native.get("rows_truncated_to"),
        }
    intents = native.get("intents")
    if not isinstance(intents, list):
        return {"intent_count": None, "intent_statuses": None, "intents": []}
    visible = []
    for item in intents[:100]:
        if not isinstance(item, dict):
            continue
        visible.append(
            {
                "intent_id": safe_text(item.get("intent_id"), 96),
                "decision_id": safe_text(item.get("decision_id"), 96),
                "release_sha": safe_text(item.get("release_sha"), 96),
                "market": safe_text(item.get("market"), 96),
                "quantity": safe_decimal(item.get("quantity")),
                "filled": safe_decimal(item.get("filled")),
                "status": safe_text(item.get("status")),
                "broker_epoch": item.get("broker_epoch")
                if type(item.get("broker_epoch")) is int
                else None,
                "boot_epoch": item.get("boot_epoch")
                if type(item.get("boot_epoch")) is int
                else None,
                "created_at_ms": item.get("created_at_ms")
                if type(item.get("created_at_ms")) is int
                else None,
                "expires_at_ms": item.get("expires_at_ms")
                if type(item.get("expires_at_ms")) is int
                else None,
                "sent_at_ms": item.get("sent_at_ms")
                if type(item.get("sent_at_ms")) is int
                else None,
                "reduce_only": item.get("reduce_only")
                if type(item.get("reduce_only")) is bool
                else None,
            }
        )
    return {
        "intent_count": native.get("total_intents")
        if type(native.get("total_intents")) is int
        else len(intents),
        "intent_statuses": dict(
            Counter(
                safe_text(item.get("status")) or "UNKNOWN"
                for item in intents[:1000]
                if isinstance(item, dict)
            )
        ),
        "intents": visible,
        "truncated": len(intents) > 100,
    }


class SmallTTLCache:
    """One bounded OS/native inspection per TTL across concurrent UI sessions."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.entries: dict[str, tuple[float, object]] = {}
        self.fill_locks: dict[str, Any] = {}

    def get(self, key: str, ttl: float, fn: Callable[[], object]) -> object:
        with self.lock:
            cached = self.entries.get(key)
            if cached is not None and time.monotonic() - cached[0] < ttl:
                return cached[1]
            if key not in self.fill_locks:
                if len(self.fill_locks) >= 64:
                    raise RuntimeError("DASHBOARD_CACHE_KEY_BUDGET_EXCEEDED")
                self.fill_locks[key] = Lock()
            fill_lock = self.fill_locks[key]
        # A slow OS/registry query cannot hold the lock for unrelated evidence.
        if not fill_lock.acquire(timeout=0.2):
            raise RuntimeError("DASHBOARD_CACHE_READ_BUSY")
        try:
            with self.lock:
                cached = self.entries.get(key)
                if cached is not None and time.monotonic() - cached[0] < ttl:
                    return cached[1]
            result = fn()
            with self.lock:
                self.entries[key] = (time.monotonic(), result)
            return result
        finally:
            fill_lock.release()


_SHARED_CACHE = SmallTTLCache()
_NATIVE_READ_SLOTS = BoundedSemaphore(2)


def _bounded_native_read(fn: Callable[[], Any]) -> Any:
    """At most two native metadata queries per Python reader process."""
    if not _NATIVE_READ_SLOTS.acquire(timeout=0.1):
        raise RuntimeError("DASHBOARD_NATIVE_READ_BUSY")
    try:
        return fn()
    finally:
        _NATIVE_READ_SLOTS.release()


class DashboardReader:
    """Single allowlisted read interface. All browser arguments are scalar filters."""

    def __init__(
        self,
        *,
        db: Path | None = None,
        observer_root: Path | None = None,
        guardian_provider: Callable[[str], Mapping[str, Any]] | None = None,
        capture_root: Path | None = None,
        research_root: Path | None = None,
        clock: Callable[[], datetime] = utc_now,
        native_read: Callable[[list[str]], Mapping[str, Any]] | None = None,
        cache: SmallTTLCache | None = None,
    ) -> None:
        self.db = db if db is not None else registry.DB
        self.observer_root = observer_root
        configured_capture = os.environ.get("DASHBOARD_GUARDIAN_CAPTURE_ROOT", "")
        self.guardian_provider = guardian_provider or GuardianCaptureDirectory(
            capture_root
            if capture_root is not None
            else Path(configured_capture)
            if configured_capture
            else None
        )
        configured_research = os.environ.get("DASHBOARD_RESEARCH_CACHE_ROOT", "")
        self.research_root = (
            research_root
            if research_root is not None
            else Path(configured_research)
            if configured_research
            else None
        )
        self.clock = clock
        self._native_override = native_read
        self.cache = cache or _SHARED_CACHE

    def _native(self, args: list[str]) -> dict[str, Any]:
        if self._native_override is not None:
            return dict(self._native_override(args))
        parsed = operations.parser().parse_args(["--db", str(self.db), *args])
        return _bounded_native_read(lambda: operations.dispatch(parsed))

    def _native_envelope(self, args: list[str], capability: str) -> dict[str, Any]:
        now = self.clock()
        try:
            source = self._native(args)
            # The native owner records its query clock during the call. Compare
            # against retrieval completion, not the earlier request-start clock.
            now = self.clock()
            state = source.get("status")
            metadata = source.get("source")
            if (
                source.get("schema") != "copytrade_read_result_v1"
                or source.get("trading_authorized") is not False
                or source.get("scientifically_qualified") is not False
                or not isinstance(metadata, dict)
                or state not in STATUS
                or not isinstance(metadata.get("authority"), str)
                or not metadata["authority"]
                or parse_utc(source.get("observed_at")) is None
                or parse_utc(source["observed_at"]) > now
            ):
                raise ValueError("NATIVE_READ_SCHEMA_INVALID")
            return envelope(
                capability,
                state,
                authority=metadata.get("authority") or "UNKNOWN",
                now=now,
                data=sanitized(source.get("data")),
                source_schema=source.get("schema"),
                source_observed_at=metadata.get("observed_at"),
                captured_at=source.get("observed_at"),
                revision=metadata.get("version"),
                inventory_sha256=metadata.get("sha256"),
                limitations=list(source.get("limitations") or []),
                error_code=source.get("error_code"),
            )
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            return envelope(
                capability,
                "UNKNOWN",
                authority="copytrade_pm.native_read",
                now=now,
                error_code="NATIVE_READ_UNAVAILABLE",
                limitations=[type(exc).__name__],
            )

    def guardian(self, command: str) -> dict[str, Any]:
        if command not in GUARDIAN_COMMANDS:
            raise ValueError("UNAPPROVED_GUARDIAN_CAPABILITY")
        now = self.clock()
        try:
            capture = self.guardian_provider(command)
            if not isinstance(capture, Mapping) or capture.get("schema") != PROJECTION_SCHEMA:
                raise ValueError("GUARDIAN_CAPTURE_WRAPPER_INVALID")
            if capture.get("command") != command:
                raise ValueError("GUARDIAN_CAPTURE_COMMAND_MISMATCH")
            native = capture.get("native")
            if not isinstance(native, Mapping) or native.get("schema") != f"operator_{command}_v1":
                raise ValueError("GUARDIAN_NATIVE_SCHEMA_INVALID")
            if native.get("trading_authorized") is not False or (
                command == "history" and native.get("scientifically_qualified") is not False
            ):
                raise ValueError("GUARDIAN_AUTHORITY_UNSAFE")
            sequence = native.get("journal_sequence")
            if type(sequence) is not int or sequence < 0:
                raise ValueError("GUARDIAN_JOURNAL_SEQUENCE_INVALID")
            account_hash = native.get("account_binding_sha")
            if not isinstance(account_hash, str) or SHA256.fullmatch(account_hash) is None:
                raise ValueError("GUARDIAN_ACCOUNT_IDENTITY_INVALID")
            release = native.get("release_sha")
            if release is not None and (
                not isinstance(release, str) or SHA256.fullmatch(release) is None
            ):
                raise ValueError("GUARDIAN_RELEASE_INVALID")
            observed = parse_utc(capture.get("source_observed_at"))
            captured = parse_utc(capture.get("captured_at"))
            if observed is None or captured is None:
                raise ValueError("GUARDIAN_SOURCE_CLOCK_INVALID")
            if observed > captured or captured > now:
                raise ValueError("GUARDIAN_CLOCK_REGRESSED_OR_FUTURE")
            if (now - captured).total_seconds() > 60:
                state = "STALE"
            elif (now - observed).total_seconds() > 15:
                state = "STALE"
            else:
                state = "VERIFIED"
            return envelope(
                f"guardian.{command}",
                state,
                authority="prop-production.operator",
                now=now,
                data=_guardian_public_data(command, native),
                source_schema=native["schema"],
                source_observed_at=utc_text(observed),
                captured_at=utc_text(captured),
                revision=release,
                journal_sequence=sequence,
                account_binding_sha=account_hash,
                limitations=[
                    "Producer-reported Guardian read only; no independent trading authorization",
                    "Native operator command reads are not an atomic multi-command broker snapshot",
                    "File capture does not prove current broker equity or service process identity",
                ],
            )
        except (FileNotFoundError, PermissionError) as exc:
            return envelope(
                f"guardian.{command}",
                "UNAVAILABLE",
                authority="prop-production.operator",
                now=now,
                error_code="PROTECTED_CAPTURE_UNAVAILABLE",
                limitations=[type(exc).__name__],
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return envelope(
                f"guardian.{command}",
                "BLOCKED",
                authority="prop-production.operator",
                now=now,
                error_code="PROTECTED_CAPTURE_INVALID",
                limitations=[type(exc).__name__],
            )

    def wallets(
        self,
        *,
        query: str | None = None,
        cohort: str | None = None,
        excluded: bool | None = None,
        subscribed: bool | None = None,
        asof: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        now = self.clock()
        for value in (query, cohort):
            if value is not None and (
                not isinstance(value, str)
                or not 1 <= len(value) <= 96
                or value.startswith("-")
                or any(ord(char) < 32 for char in value)
            ):
                return envelope(
                    "registry.wallets",
                    "BLOCKED",
                    authority="wallet_registry",
                    now=now,
                    error_code="INVALID_WALLET_FILTER",
                )
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 10000
            or excluded not in (None, True, False)
            or subscribed not in (None, True, False)
            or (asof is not None and parse_utc(asof) is None)
        ):
            return envelope(
                "registry.wallets",
                "BLOCKED",
                authority="wallet_registry",
                now=now,
                error_code="INVALID_WALLET_WINDOW_OR_ASOF",
            )
        command = ["wallets", "list", "--limit", str(limit), "--offset", str(offset)]
        if query:
            command.extend(["--query", query])
        if cohort:
            command.extend(["--cohort", cohort])
        if excluded is not None:
            command.append("--excluded" if excluded else "--no-excluded")
        if subscribed is not None:
            command.append("--subscribed" if subscribed else "--no-subscribed")
        if asof:
            command.extend(["--asof", asof])
        answer = self._native_envelope(command, "registry.wallets")
        if answer["status"] not in {"VERIFIED", "STALE"}:
            return answer
        rows = answer.get("data")
        if (
            not isinstance(rows, dict)
            or rows.get("schema") != "wallet_registry_private_inventory_v1"
        ):
            answer.update(status="BLOCKED", data=None, error_code="WALLET_NATIVE_SCHEMA_INVALID")
            return answer
        if (
            rows.get("addresses_redacted") is not True
            or not isinstance(rows.get("wallets"), list)
            or len(rows["wallets"]) > limit
        ):
            answer.update(status="BLOCKED", data=None, error_code="WALLET_PRIVACY_CONTRACT_INVALID")
            return answer
        # Independent SQLite physical integrity & inventory SHA must match.
        try:
            doctor = self.cache.get(
                "doctor:" + str(self.db),
                30.0,
                lambda: _bounded_native_read(lambda: operations._doctor(self.db)),
            )
        except RuntimeError:
            doctor = None
        if not isinstance(doctor, dict) or doctor.get("status") != "VERIFIED":
            answer.update(status="STALE", error_code="REGISTRY_PARITY_UNVERIFIED")
        elif doctor.get("data", {}).get("inventory_sha256") != answer["inventory_sha256"]:
            answer.update(status="STALE", error_code="REGISTRY_GENERATION_MISMATCH")
        return answer

    def research_selection(self) -> dict[str, Any]:
        try:
            return self.cache.get(
                "selection:" + str(self.db),
                60.0,
                lambda: self._native_envelope(
                    ["portfolios", "current"], "registry.research_selection"
                ),
            )
        except RuntimeError:
            return envelope(
                "registry.research_selection",
                "UNKNOWN",
                authority="wallet_registry",
                now=self.clock(),
                error_code="DASHBOARD_NATIVE_READ_BUSY",
            )

    def overview(self) -> dict[str, Any]:
        # Never call Guardian Journal.read in a polling path.
        sources = {name: self.guardian(name) for name in ("status", "risk", "broker", "portfolio")}
        valid = [src for src in sources.values() if src["status"] == "VERIFIED"]
        if len(valid) == len(sources):
            pairs = {
                (
                    src["revision"],
                    src["journal_sequence"],
                    src["account_binding_sha"],
                    src["captured_at"],
                )
                for src in valid
            }
            if len(pairs) != 1 or any(src["revision"] is None for src in valid):
                # Keep separately observed status diagnostics available, but never
                # label an unbound financial book as verified.
                sources["risk"]["status"] = "BLOCKED"
                sources["risk"]["error_code"] = "GUARDIAN_ACCOUNT_SEQUENCE_OR_RELEASE_MISMATCH"
        elif sources["risk"]["status"] == "VERIFIED":
            # A single risk capture is never a coherent broker/account book.
            sources["risk"]["status"] = "BLOCKED"
            sources["risk"]["error_code"] = "GUARDIAN_CROSS_CAPTURE_PARITY_UNAVAILABLE"
        finance = sources["risk"].get("data")
        finance = finance.get("finance") if isinstance(finance, dict) else None
        finance = finance if isinstance(finance, dict) else {}
        metrics = {
            key: {
                "value": finance.get(key) if sources["risk"]["status"] == "VERIFIED" else None,
                "status": (
                    sources["risk"]["status"]
                    if sources["risk"]["status"] != "VERIFIED"
                    else "VERIFIED"
                    if finance.get(key) is not None
                    else "UNKNOWN"
                ),
            }
            for key in ("equity", "headroom", "daily_headroom", "trailing_headroom")
        }
        reported = sources["status"].get("data") or {}
        health = reported.get("health") if isinstance(reported, dict) else {}
        health = health if isinstance(health, dict) else {}
        incidents = []
        for reason in (reported.get("halts") or []) + (health.get("reasons") or []):
            if isinstance(reason, str) and reason not in incidents:
                incidents.append(reason)
        return {
            "schema": "dashboard_overview_v1",
            "retrieved_at": utc_text(self.clock()),
            "metrics": metrics,
            "sources": sources,
            "incidents": incidents,
            "research_selection": self.research_selection(),
            "membership_authority": "UNKNOWN_UNTIL_VERIFIED_INSTALLED_AND_RUNTIME_RELEASE",
            "trading_authorized": False,
        }

    def risk_status(self) -> dict[str, Any]:
        """Current Guardian-only risk; never estimate a contractual floor in the UI."""
        report = self.overview()
        sources = report["sources"]
        risk = sources["risk"]
        raw = risk.get("data")
        raw = raw if isinstance(raw, dict) else {}
        finance = raw.get("finance") if risk["status"] == "VERIFIED" else {}
        finance = finance if isinstance(finance, dict) else {}
        names = (
            "equity",
            "headroom",
            "daily_headroom",
            "trailing_headroom",
            "daily_floor",
            "internal_floor",
            "trailing_floor",
            "risk_floor",
            "daily_baseline",
            "high_water",
            "realized_made",
            "unrealized",
            "initial_margin",
            "maintenance_margin",
        )
        metrics = {
            name: {
                "value": finance.get(name),
                "status": (
                    risk["status"]
                    if risk["status"] != "VERIFIED"
                    else "VERIFIED"
                    if finance.get(name) is not None
                    else "UNKNOWN"
                ),
                "unit": "account currency (operator native)",
            }
            for name in names
        }
        return {
            "schema": "dashboard_risk_v1",
            "retrieved_at": utc_text(self.clock()),
            "metrics": metrics,
            "pod_losses": raw.get("pod_loss_used", []) if risk["status"] == "VERIFIED" else [],
            "pod_budget_status": "UNAVAILABLE",
            "pod_budget_reason": "operator_risk_v1 exports use, not signed budget limits",
            "pod_entries_truncated": raw.get("pod_entries_truncated", False),
            "reservation_count": raw.get("reservation_count")
            if risk["status"] == "VERIFIED"
            else None,
            "exposure": (
                raw.get("exposure")
                if risk["status"] == "VERIFIED" and isinstance(raw.get("exposure"), dict)
                else {"gross": None, "net": None, "status": "UNAVAILABLE"}
            ),
            "guardian_halts": (sources["status"].get("data") or {}).get("halts")
            if sources["status"]["status"] in {"VERIFIED", "STALE"}
            else None,
            "reconciliation": (sources["broker"].get("data") or {}).get("certainty")
            if sources["broker"]["status"] == "VERIFIED"
            else "UNKNOWN",
            "sources": sources,
            "trading_authorized": False,
        }

    def execution_monitor(self) -> dict[str, Any]:
        """Stable-ID causal receipts and verified owner fills, never temporal guesses."""
        sources = {
            name: self.guardian(name) for name in ("status", "portfolio", "intent", "broker")
        }
        complete = all(
            s["status"] == "VERIFIED" and s["revision"] and s["account_binding_sha"]
            for s in sources.values()
        )
        bindings = {
            (s["account_binding_sha"], s["revision"], s["journal_sequence"], s["captured_at"])
            for s in sources.values()
        }
        coherent = bool(complete and len(bindings) == 1)
        portfolio = sources["portfolio"].get("data")
        intent = sources["intent"].get("data")
        broker = sources["broker"].get("data")
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        intent = intent if isinstance(intent, dict) else {}
        broker = broker if isinstance(broker, dict) else {}
        decisions = portfolio.get("decisions") or []
        decisions_by_id: dict[str, list[dict]] = {}
        for item in decisions:
            if isinstance(item, dict) and item.get("decision_id"):
                decisions_by_id.setdefault(item["decision_id"], []).append(item)
        fills = broker.get("fills") or []
        fills_by_intent: dict[str, list[dict]] = {}
        seen_fills: set[str] = set()
        duplicate_fills = False
        for item in fills:
            if not isinstance(item, dict) or not item.get("execution_id_sha"):
                continue
            identifier = item["execution_id_sha"]
            if identifier in seen_fills:
                duplicate_fills = True
                continue
            seen_fills.add(identifier)
            if item.get("intent_id"):
                fills_by_intent.setdefault(item["intent_id"], []).append(item)
        source_events = []
        if coherent:
            for decision in decisions:
                for receipt in decision.get("source_receipts") or []:
                    if not isinstance(receipt, dict):
                        continue
                    source, known, local = (
                        receipt.get("source_event_ms"),
                        receipt.get("source_known_ms"),
                        receipt.get("local_known_ms"),
                    )
                    batch, first, due = (
                        decision.get("batch_decision_ms"),
                        decision.get("first_known_ms"),
                        decision.get("due_ms"),
                    )
                    if (
                        not all(type(x) is int for x in (source, known, local, batch, first, due))
                        or not 0 <= source <= known <= local <= batch
                        or due != first + 300_000
                        or batch < due
                    ):
                        continue
                    source_events.append(
                        {
                            "decision_id": decision["decision_id"],
                            "receipt_sha": receipt.get("receipt_sha"),
                            "source_event_ms": source,
                            "source_known_ms": known,
                            "first_known_ms": local,
                            "batch_due_ms": due,
                            "batch_decision_ms": batch,
                            "guardian_decision_at_ms": decision.get("guardian_decision_at_ms"),
                        }
                    )
        rows = []
        for item in intent.get("intents") or []:
            if not isinstance(item, dict):
                continue
            matches = decisions_by_id.get(item.get("decision_id"), [])
            linked = (
                coherent
                and len(matches) == 1
                and matches[0].get("release_sha") == item.get("release_sha")
                and item.get("release_sha") == sources["intent"]["revision"]
            )
            decision = matches[0] if linked else {}
            observed_fills = fills_by_intent.get(item.get("intent_id"), []) if linked else []
            if duplicate_fills:
                observed_fills = []
            credible_fills = [
                f
                for f in observed_fills
                if (
                    f.get("market") == item.get("market")
                    and f.get("known_at_ms") is not None
                    and item.get("created_at_ms") is not None
                    and f["known_at_ms"] >= item["created_at_ms"]
                )
            ]
            rows.append(
                {
                    **item,
                    "decision_link": "VERIFIED_ID_MATCH" if linked else "UNKNOWN",
                    "decision_status": decision.get("status"),
                    "source_event_at": (
                        min(
                            (
                                r["source_event_ms"]
                                for r in source_events
                                if r["decision_id"] == item.get("decision_id")
                            ),
                            default=None,
                        )
                        if linked
                        else None
                    ),
                    "first_known_at": decision.get("first_known_ms") if linked else None,
                    "batch_due_ms": decision.get("due_ms") if linked else None,
                    "batch_decision_at": decision.get("batch_decision_ms") if linked else None,
                    "guardian_decision_at_ms": (
                        decision.get("guardian_decision_at_ms") if linked else None
                    ),
                    "guardian_intent_at_ms": item.get("created_at_ms"),
                    "broker_acceptance_at": None,
                    "broker_fill_at": max((f["known_at_ms"] for f in credible_fills), default=None),
                    "confirmed_fills": len(credible_fills),
                    "fill_trace_status": (
                        "VERIFIED_OWNER_FILL_ID" if credible_fills else "UNKNOWN"
                    ),
                    "reconciliation_at_ms": broker.get("last_snapshot_ms") if coherent else None,
                }
            )
        return {
            "schema": "dashboard_execution_v1",
            "retrieved_at": utc_text(self.clock()),
            "coherent_capture": coherent,
            "link_status": "VERIFIED_CAPTURE_BINDING" if coherent else "UNKNOWN",
            "decisions": decisions if sources["portfolio"]["status"] == "VERIFIED" else [],
            "intents": rows if sources["intent"]["status"] == "VERIFIED" else [],
            "decision_count": portfolio.get("decision_count"),
            "intent_count": intent.get("intent_count"),
            "truncated": bool(
                portfolio.get("truncated")
                or intent.get("truncated")
                or broker.get("fills_truncated")
            ),
            "source_events": source_events if coherent else [],
            "first_known_events": source_events if coherent else [],
            "batch_decisions": [
                {
                    "decision_id": d.get("decision_id"),
                    "batch_decision_ms": d.get("batch_decision_ms"),
                    "batch_due_ms": d.get("due_ms"),
                }
                for d in decisions
                if coherent and d.get("batch_decision_ms") is not None
            ],
            "confirmed_fill_records": len(seen_fills) if coherent else None,
            "duplicate_fill_identity": duplicate_fills,
            "target_vs_actual": None,
            "reconciliation": broker.get("certainty")
            if sources["broker"]["status"] == "VERIFIED"
            else "UNKNOWN",
            "sources": sources,
            "trading_authorized": False,
        }

    def performance_history(
        self, *, risk_report: dict[str, Any] | None = None, max_points: int = 1200
    ) -> dict[str, Any]:
        """Consume separately captured owner-verified recent SHADOW equity history.

        No dashboard journal access. Only matched account/release/sequence
        captures are admissible. Chart values are display-only approximations.
        """
        report = risk_report if risk_report is not None else self.risk_status()
        source = self.guardian("history")
        sources = report.get("sources") or {}
        financial_sources = [sources.get(k) for k in ("status", "risk", "broker", "portfolio")]
        matching = (
            source["status"] == "VERIFIED"
            and all(
                isinstance(s, dict) and s.get("status") == "VERIFIED" for s in financial_sources
            )
            and source.get("revision") is not None
            and len(
                {
                    (
                        s.get("account_binding_sha"),
                        s.get("revision"),
                        s.get("journal_sequence"),
                        s.get("captured_at"),
                    )
                    for s in [source, *financial_sources]
                }
            )
            == 1
        )
        payload = source.get("data")
        payload = payload if isinstance(payload, dict) else {}
        rows = payload.get("rows") or []
        if (
            not matching
            or payload.get("evidence_class") != "PAPER_SHADOW"
            or payload.get("status") == "BLOCKED"
        ):
            return {
                "schema": "dashboard_history_v1",
                "status": "UNAVAILABLE" if source["status"] == "UNAVAILABLE" else "BLOCKED",
                "error_code": "HISTORY_AND_ACCOUNT_CAPTURE_PARITY_UNVERIFIED",
                "points": [],
                "source": source,
                "limitations": [
                    "Owner-verified history and fresh coherent account captures required"
                ],
                "trading_authorized": False,
            }
        series = []
        last_key: dict[tuple[str, str], tuple[int, str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            release = row.get("release_sha")
            stamp = row.get("observed_at_ms")
            if (
                not isinstance(release, str)
                or SHA256.fullmatch(release) is None
                or type(stamp) is not int
                or stamp < 0
                or stamp > int(self.clock().timestamp() * 1000)
                or (
                    source.get("captured_at") is not None
                    and stamp > int(parse_utc(source["captured_at"]).timestamp() * 1000)
                )
            ):
                return {
                    "schema": "dashboard_history_v1",
                    "status": "BLOCKED",
                    "error_code": "INVALID_OWNER_FINANCE_ROW_CLOCK_OR_RELEASE",
                    "points": [],
                    "source": source,
                    "trading_authorized": False,
                }
            timestamp = utc_text(datetime.fromtimestamp(stamp / 1000, UTC))
            for metric in ("equity", "risk_floor", "headroom", "unrealized"):
                value = row.get(metric)
                if value is None:
                    continue
                name = f"Guardian SHADOW {metric} ({release[:12]})"
                identity = (name, metric)
                previous = last_key.get(identity)
                if previous is not None and stamp == previous[0]:
                    if value != previous[1]:
                        return {
                            "schema": "dashboard_history_v1",
                            "status": "BLOCKED",
                            "error_code": "CONFLICTING_OWNER_FINANCE_AT_SAME_TIMESTAMP",
                            "points": [],
                            "source": source,
                            "trading_authorized": False,
                        }
                    continue
                if previous is not None and stamp < previous[0]:
                    return {
                        "schema": "dashboard_history_v1",
                        "status": "BLOCKED",
                        "error_code": "REGRESSED_OWNER_FINANCE_CLOCK",
                        "points": [],
                        "source": source,
                        "trading_authorized": False,
                    }
                last_key[identity] = (stamp, value)
                series.append(
                    {
                        "timestamp": timestamp,
                        "value": value,
                        "series": name,
                        "metric": metric,
                        "source_id": release,
                        "evidence_class": "PAPER_SHADOW",
                        "reset_boundary": False,
                        # A snapshot tail is not a continuous trade tape. Never draw
                        # a line across unexplained observation gaps over five minutes.
                        "gap_before": previous is not None and stamp - previous[0] > 300_000,
                    }
                )
        # Preserve contractual UTC reset boundaries where the owner supplied
        # day identity. No interpolation or invented zero for missing fields.
        day_by_stamp = {
            (r.get("release_sha"), r["observed_at_ms"]): r.get("day")
            for r in rows
            if isinstance(r, dict) and type(r.get("observed_at_ms")) is int
        }
        prior_day: dict[str, int] = {}
        for point in series:
            stamp = int(datetime.fromisoformat(point["timestamp"]).timestamp() * 1000)
            current = day_by_stamp.get((point["source_id"], stamp))
            if current is not None:
                key = point["series"]
                point["reset_boundary"] = key in prior_day and prior_day[key] != current
                prior_day[key] = current
        try:
            from .chart_data import prepare_series

            visual = prepare_series(series, max_points=max_points)
        except (ValueError, TypeError, OverflowError) as exc:
            return {
                "schema": "dashboard_history_v1",
                "status": "BLOCKED",
                "error_code": "OWNER_HISTORY_CHART_REJECTED",
                "points": [],
                "source": source,
                "limitations": [type(exc).__name__],
                "trading_authorized": False,
            }
        return {
            "schema": "dashboard_history_v1",
            "status": "VERIFIED_OWNER_SHADOW_TAIL" if visual else "UNAVAILABLE",
            "points": visual,
            "source": source,
            "limitations": [
                "Recent bounded tail only, not full account history",
                "Owner SHADOW financial snapshots, not broker-executed performance",
                "Chart floats never determine contractual risk or follower alpha",
            ],
            "trading_authorized": False,
        }

    def portfolio_explorer(
        self, *, asof: str | None = None, query: str | None = None, limit: int = 25, offset: int = 0
    ) -> dict[str, Any]:
        """Canonical frozen SQLite definitions, separate from financial runtime."""
        now = self.clock()
        if (
            asof is not None
            and (parse_utc(asof) is None or parse_utc(asof) > now)
            or query is not None
            and (
                not isinstance(query, str)
                or not 1 <= len(query) <= 96
                or any(ord(char) < 32 for char in query)
            )
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 10000
        ):
            return envelope(
                "registry.portfolio_explorer",
                "BLOCKED",
                authority="wallet_registry",
                now=now,
                error_code="INVALID_PORTFOLIO_FILTER",
            )
        suffix = ["--asof", asof] if asof else []
        catalog = self._native_envelope(["portfolios", "list", *suffix], "portfolio.list")
        selection = (
            self._native_envelope(["portfolios", "current", *suffix], "portfolio.current")
            if asof
            else self.research_selection()
        )
        records = catalog.get("data")
        if catalog["status"] not in {"VERIFIED", "STALE"} or not isinstance(records, dict):
            return {
                "schema": "dashboard_portfolios_v1",
                "status": catalog["status"],
                "records": [],
                "catalog": catalog,
                "selection": selection,
                "error_code": catalog["error_code"] or "PORTFOLIO_CATALOG_UNAVAILABLE",
                "trading_authorized": False,
            }
        if len(records) > 250:
            return {
                "schema": "dashboard_portfolios_v1",
                "status": "BLOCKED",
                "records": [],
                "catalog": catalog,
                "selection": selection,
                "error_code": "PORTFOLIO_CATALOG_EXCEEDS_READ_BUDGET",
                "trading_authorized": False,
            }
        selected_data = selection.get("data")
        selected_data = selected_data if isinstance(selected_data, dict) else {}
        selection_valid = selection["status"] in {"VERIFIED", "STALE"} and str(
            selected_data.get("selection_state", "")
        ).startswith("SIGNATURE_CHECKED")
        selected = {
            (p.get("portfolio_id"), p.get("version"), p.get("definition_sha256"))
            for p in selected_data.get("portfolios", [])
            if selection_valid and isinstance(p, dict)
        }
        filtered = [
            (key, record)
            for key, record in sorted(records.items())
            if isinstance(key, str) and (query is None or query.casefold() in key.casefold())
        ]
        visible = []
        for key, record in filtered[offset : offset + limit]:
            if not isinstance(record, dict) or not isinstance(key, str):
                continue
            identity = safe_text(record.get("portfolio_id"), 96)
            if identity is None or identity != safe_text(key, 96):
                continue
            members = record.get("members")
            members = members if isinstance(members, list) else []
            chosen = (identity, record.get("version"), record.get("definition_sha256")) in selected
            visible.append(
                {
                    "portfolio_id": identity,
                    "version": record.get("version"),
                    "definition_sha256": safe_text(record.get("definition_sha256"), 96),
                    "selection_known_at": safe_text(record.get("selection_known_at")),
                    "members": [safe_text(m, 96) for m in members[:50] if safe_text(m, 96)],
                    "members_truncated": len(members) > 50,
                    "source_state": safe_text(record.get("state")),
                    "sizing_contract": safe_text(record.get("sizing_contract")),
                    "source_sealed": record.get("source_sealed") is True,
                    "account_scope": safe_text(record.get("account_scope")),
                    "market_scope": safe_text(record.get("market_scope")),
                    "exclusions": sanitized(record.get("exclusions"))
                    if isinstance(record.get("exclusions"), list)
                    else None,
                    "signed_fixed_k": sanitized(record.get("signed_fixed_k"))
                    if isinstance(record.get("signed_fixed_k"), dict)
                    else None,
                    "storage_state": "SAVED",
                    "research_state": "RESEARCH_SELECTED" if chosen else "SAVED",
                    "deployment_state": "UNKNOWN",
                    "runtime_state": "UNKNOWN",
                    "release_binding": "UNAVAILABLE_NO_VERIFIED_PORTFOLIO_RELEASE_MAPPING",
                }
            )
        return {
            "schema": "dashboard_portfolios_v1",
            "status": catalog["status"],
            "records": visible,
            "total": len(records),
            "total_matches": len(filtered),
            "offset": offset,
            "limit": limit,
            "truncated": offset + limit < len(filtered),
            "catalog": catalog,
            "selection": selection,
            "asof": asof,
            "query": query,
            "trading_authorized": False,
        }

    def research_reports(
        self,
        *,
        run_id: str | None = None,
        cache_key: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Fixed owner-configured cache scope; UI cannot supply paths or run jobs."""
        now = self.clock()
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 10000
            or (
                run_id is not None
                and (
                    not isinstance(run_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}", run_id)
                )
            )
            or (
                cache_key is not None
                and (not isinstance(cache_key, str) or SHA256.fullmatch(cache_key) is None)
            )
        ):
            return envelope(
                "research.reports",
                "BLOCKED",
                authority="immutable_offline_job_cache",
                now=now,
                error_code="INVALID_RESEARCH_FILTER",
            )
        if self.research_root is None:
            return envelope(
                "research.reports",
                "UNAVAILABLE",
                authority="immutable_offline_job_cache",
                now=now,
                error_code="RESEARCH_CACHE_ROOT_NOT_CONFIGURED",
                limitations=["Only explicitly configured immutable report caches are readable"],
            )
        cmd = ["research", "show" if run_id else "list"]
        if run_id:
            cmd.append(run_id)
        cmd.extend(
            [
                "--cache-root",
                str(self.research_root),
                "--limit",
                str(limit),
                "--offset",
                str(offset),
            ]
        )
        if cache_key:
            cmd.extend(["--cache-key", cache_key])
        result = self._native_envelope(cmd, "research.reports")
        payload = result.get("data")
        if result["status"] in {"VERIFIED", "STALE"} and (
            not isinstance(payload, dict)
            or payload.get("schema") != "pm_offline_verified_job_catalog_v1"
            or not isinstance(payload.get("reports"), list)
            or len(payload["reports"]) > limit
        ):
            result.update(status="BLOCKED", data=None, error_code="RESEARCH_CATALOG_SCHEMA_INVALID")
        return result

    def contract_rules(self) -> dict[str, Any]:
        """Show native unverified scenario archetypes; never simulate or read tapes."""
        now = self.clock()
        try:
            native = self._native(["contracts", "rules"])
            rows = native.get("contracts")
            if (
                native.get("schema") != "copytrade_contract_rule_catalog_v1"
                or native.get("trading_authorized") is not False
                or native.get("scientifically_qualified") is not False
                or not isinstance(rows, list)
                or len(rows) > 10
            ):
                raise ValueError("NATIVE_CONTRACT_RULE_SCHEMA_INVALID")
            return envelope(
                "research.contract_rules",
                "VERIFIED",
                authority="copytrade_pm.native_contract_selector",
                now=now,
                source_schema="copytrade_contract_rule_catalog_v1",
                data={
                    "rule_set_version": safe_text(native.get("rule_set_version")),
                    "rules_sha256": safe_text(native.get("rules_sha256")),
                    "status": "SCENARIO_ONLY",
                    "contracts": [
                        {
                            "id": safe_text(item.get("id")),
                            "rule_sha256": safe_text(item.get("rule_sha256")),
                            "rule_authority": safe_text(item.get("rule_authority")),
                            "missing_terms": [
                                safe_text(x)
                                for x in item.get("missing_terms", [])[:12]
                                if safe_text(x)
                            ]
                            if isinstance(item.get("missing_terms"), list)
                            else [],
                            "configuration": sanitized(item.get("configuration"))
                            if isinstance(item.get("configuration"), dict)
                            else None,
                            "scientifically_qualified": False,
                        }
                        for item in rows
                        if isinstance(item, dict)
                    ],
                },
                limitations=[
                    "Scenario rule archetypes are unverified and not executed EV results",
                    "No contract comparison or expensive research job runs in dashboard",
                ],
            )
        except OSError, ValueError, TypeError, KeyError, RuntimeError:
            return envelope(
                "research.contract_rules",
                "BLOCKED",
                authority="copytrade_pm.native_contract_selector",
                now=now,
                error_code="NATIVE_CONTRACT_RULE_CATALOG_UNAVAILABLE",
            )

    def _os_services(self) -> dict[str, Any]:
        records = {}
        for name in SERVICES:
            try:
                proc = subprocess.run(
                    [
                        "systemctl",
                        "show",
                        name,
                        "--property=LoadState",
                        "--property=ActiveState",
                        "--property=MainPID",
                        "--no-pager",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if proc.returncode:
                    raise ValueError("SYSTEMD_FAILED")
                fields = dict(
                    line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line
                )
                active = fields.get("ActiveState")
                if active not in {"active", "inactive", "failed", "activating", "deactivating"}:
                    raise ValueError("UNRECOGNIZED_SERVICE_STATE")
                records[name] = {
                    "state": "UNKNOWN",
                    "os_active_state": active,
                    "os_load_state": safe_text(fields.get("LoadState")),
                    "pid_observed": fields.get("MainPID", "0").isdigit()
                    and int(fields["MainPID"]) > 0,
                    "attests_financial_health": False,
                }
            except OSError, ValueError, subprocess.TimeoutExpired:
                records[name] = {
                    "state": "UNKNOWN",
                    "os_active_state": None,
                    "attests_financial_health": False,
                }
        return records

    def health(self) -> dict[str, Any]:
        now = self.clock()
        guardian = self.guardian("status")
        broker = self.guardian("broker")
        try:
            observer = self.cache.get(
                "observer:" + str(self.observer_root),
                30.0,
                lambda: runtime.observer_market_health(self.observer_root),
            )
        except RuntimeError:
            observer = {"state": "UNKNOWN", "error_code": "OBSERVER_READ_BUSY"}
        if not isinstance(observer, dict):
            observer = {"state": "UNKNOWN", "error_code": "OBSERVER_QUERY_INVALID"}
        try:
            services = self.cache.get("os_services", 30.0, self._os_services)
        except RuntimeError:
            services = {
                name: {
                    "state": "UNKNOWN",
                    "os_active_state": None,
                    "attests_financial_health": False,
                }
                for name in SERVICES
            }
        source = envelope(
            "public.observer",
            observer.get("state", "UNKNOWN"),
            authority="copytrade_pm.public_observer",
            now=now,
            data=sanitized(observer),
            source_schema="pm_runtime_readonly.observer_market_health",
            limitations=["Public market receipts are not authenticated broker health"],
            error_code=observer.get("error_code"),
        )
        return {
            "schema": "dashboard_health_v1",
            "retrieved_at": utc_text(now),
            "guardian": guardian,
            "broker": broker,
            "watchdog": {
                "status": "DEGRADED"
                if guardian["status"] == "VERIFIED"
                and isinstance(guardian.get("data"), dict)
                and isinstance(guardian["data"].get("health"), dict)
                and guardian["data"]["health"].get("ages_ms", {}).get("watchdog") is not None
                else "UNKNOWN",
                "source_observed_at": guardian["source_observed_at"],
                "limitation": "Guardian-reported watchdog age, not a separate incident detector",
            },
            "observer": source,
            "market": {
                "status": "UNKNOWN",
                "reason": "Public observer receipts cannot attest executable market health",
            },
            "services": services,
            "incidents": self.overview_incidents(guardian),
            "trading_authorized": False,
        }

    @staticmethod
    def overview_incidents(guardian: Mapping[str, Any]) -> list[str]:
        payload = guardian.get("data")
        if not isinstance(payload, dict):
            return []
        health = payload.get("health")
        health = health if isinstance(health, dict) else {}
        return list(
            dict.fromkeys(
                [
                    *[s for s in payload.get("halts") or [] if isinstance(s, str)],
                    *[s for s in health.get("reasons") or [] if isinstance(s, str)],
                ]
            )
        )
