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
from threading import Lock
import time
from typing import Any, Callable, Mapping

from copytrade_pm import pm_operations as operations
from copytrade_pm import pm_runtime_readonly as runtime
from copytrade_pm import wallet_registry as registry

READ_SCHEMA = "dashboard_read_result_v1"
PROJECTION_SCHEMA = "dashboard_guardian_capture_v1"
GUARDIAN_COMMANDS = frozenset({"status", "risk", "broker", "portfolio", "intent"})
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
    {"VERIFIED", "DEGRADED", "STALE", "UNKNOWN", "BLOCKED", "UNAVAILABLE",
     "NOT_RUNNING", "NOT_REGISTERED_AT_ASOF", "SCHEMA_UPGRADE_REQUIRED"}
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
            if str(key).lower() not in {"address", "account_id", "private_key", "secret",
                                        "exclusion_reason", "wallet_address"}
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
            "halts": [
                safe_text(x) for x in native.get("halts", [])[:40] if safe_text(x)
            ] if isinstance(native.get("halts"), list) else None,
            "health": {
                "status": safe_text(health.get("status")),
                "reasons": [
                    safe_text(x) for x in health.get("reasons", [])[:40] if safe_text(x)
                ] if isinstance(health.get("reasons"), list) else None,
                "source_state": safe_text(health.get("source_state")),
                "ages_ms": {
                    key: value if type(value) is int and value >= 0 else None
                    for key, value in ages.items()
                    if key in {"financial_progress", "account", "market", "watchdog",
                               "source_heartbeat", "source_book"}
                },
            },
        }
    if command == "risk":
        finance = native.get("finance")
        finance = finance if isinstance(finance, dict) else {}
        return {
            "finance": {
                key: safe_decimal(finance.get(key))
                for key in ("equity", "headroom", "daily_headroom", "trailing_headroom",
                            "realized_made")
            },
            "reservation_count": len(native["reservations"])
            if isinstance(native.get("reservations"), dict) else None,
        }
    if command == "broker":
        return {
            "certainty": safe_text(native.get("certainty")),
            "broker_epoch": native.get("broker_epoch")
            if type(native.get("broker_epoch")) is int else None,
            "last_snapshot_ms": native.get("last_snapshot_ms")
            if type(native.get("last_snapshot_ms")) is int else None,
            "flat_confirmed": native.get("flat_confirmed")
            if type(native.get("flat_confirmed")) is bool else None,
            "provider_cutoff_sha": native.get("provider_cutoff_sha")
            if isinstance(native.get("provider_cutoff_sha"), str)
            and SHA256.fullmatch(native["provider_cutoff_sha"]) else None,
        }
    if command == "portfolio":
        decisions = native.get("decisions")
        if not isinstance(decisions, list):
            return {"decision_count": None, "decision_statuses": None}
        return {
            "decision_count": len(decisions),
            "decision_statuses": dict(Counter(
                safe_text(d.get("status")) or "UNKNOWN"
                for d in decisions[:1000] if isinstance(d, dict)
            )),
        }
    intents = native.get("intents")
    if not isinstance(intents, list):
        return {"intent_count": None, "intent_statuses": None}
    return {
        "intent_count": len(intents),
        "intent_statuses": dict(Counter(
            safe_text(item.get("status")) or "UNKNOWN"
            for item in intents[:1000] if isinstance(item, dict)
        )),
    }


class SmallTTLCache:
    """One bounded OS/native inspection per TTL across concurrent UI sessions."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.entries: dict[str, tuple[float, object]] = {}

    def get(self, key: str, ttl: float, fn: Callable[[], object]) -> object:
        with self.lock:
            cached = self.entries.get(key)
            if cached is not None and time.monotonic() - cached[0] < ttl:
                return cached[1]
            result = fn()
            self.entries[key] = (time.monotonic(), result)
            return result


_SHARED_CACHE = SmallTTLCache()


class DashboardReader:
    """Single allowlisted read interface. All browser arguments are scalar filters."""

    def __init__(
        self,
        *,
        db: Path | None = None,
        observer_root: Path | None = None,
        guardian_provider: Callable[[str], Mapping[str, Any]] | None = None,
        capture_root: Path | None = None,
        clock: Callable[[], datetime] = utc_now,
        native_read: Callable[[list[str]], Mapping[str, Any]] | None = None,
        cache: SmallTTLCache | None = None,
    ) -> None:
        self.db = db if db is not None else registry.DB
        self.observer_root = observer_root
        self.guardian_provider = guardian_provider or GuardianCaptureDirectory(capture_root)
        self.clock = clock
        self._native_override = native_read
        self.cache = cache or _SHARED_CACHE

    def _native(self, args: list[str]) -> dict[str, Any]:
        if self._native_override is not None:
            return dict(self._native_override(args))
        parsed = operations.parser().parse_args(["--db", str(self.db), *args])
        return operations.dispatch(parsed)

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
                capability, state, authority=metadata.get("authority") or "UNKNOWN",
                now=now, data=sanitized(source.get("data")),
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
                capability, "UNKNOWN", authority="copytrade_pm.native_read",
                now=now, error_code="NATIVE_READ_UNAVAILABLE",
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
            if native.get("trading_authorized") is not False:
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
                f"guardian.{command}", state, authority="prop-production.operator",
                now=now, data=_guardian_public_data(command, native),
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
                f"guardian.{command}", "UNAVAILABLE", authority="prop-production.operator",
                now=now, error_code="PROTECTED_CAPTURE_UNAVAILABLE",
                limitations=[type(exc).__name__],
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return envelope(
                f"guardian.{command}", "BLOCKED", authority="prop-production.operator",
                now=now, error_code="PROTECTED_CAPTURE_INVALID",
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
                not isinstance(value, str) or not 1 <= len(value) <= 96
                or any(ord(char) < 32 for char in value)
            ):
                return envelope(
                    "registry.wallets", "BLOCKED", authority="wallet_registry",
                    now=now, error_code="INVALID_WALLET_FILTER",
                )
        if (
            type(limit) is not int or not 1 <= limit <= 100
            or type(offset) is not int or not 0 <= offset <= 10000
            or excluded not in (None, True, False)
            or subscribed not in (None, True, False)
            or (asof is not None and parse_utc(asof) is None)
        ):
            return envelope(
                "registry.wallets", "BLOCKED", authority="wallet_registry",
                now=now, error_code="INVALID_WALLET_WINDOW_OR_ASOF",
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
        if not isinstance(rows, dict) or rows.get("schema") != "wallet_registry_private_inventory_v1":
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
        doctor = self.cache.get(
            "doctor:" + str(self.db), 30.0, lambda: operations._doctor(self.db)
        )
        if not isinstance(doctor, dict) or doctor.get("status") != "VERIFIED":
            answer.update(status="STALE", error_code="REGISTRY_PARITY_UNVERIFIED")
        elif doctor.get("data", {}).get("inventory_sha256") != answer["inventory_sha256"]:
            answer.update(status="STALE", error_code="REGISTRY_GENERATION_MISMATCH")
        return answer

    def research_selection(self) -> dict[str, Any]:
        return self.cache.get(
            "selection:" + str(self.db),
            60.0,
            lambda: self._native_envelope(["portfolios", "current"], "registry.research_selection"),
        )

    def overview(self) -> dict[str, Any]:
        # Never call Guardian Journal.read in a polling path.
        sources = {name: self.guardian(name) for name in ("status", "risk", "broker", "portfolio")}
        valid = [src for src in sources.values() if src["status"] == "VERIFIED"]
        if len(valid) == len(sources):
            pairs = {
                (src["revision"], src["journal_sequence"], src["account_binding_sha"])
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
                    if sources["risk"]["status"] != "VERIFIED" else
                    "VERIFIED" if finance.get(key) is not None else "UNKNOWN"
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

    def _os_services(self) -> dict[str, Any]:
        records = {}
        for name in SERVICES:
            try:
                proc = subprocess.run(
                    ["systemctl", "show", name, "--property=LoadState",
                     "--property=ActiveState", "--property=MainPID", "--no-pager"],
                    check=False, capture_output=True, text=True, timeout=2,
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
                    "state": "DEGRADED" if active == "active" else "UNKNOWN",
                    "os_active_state": active,
                    "os_load_state": safe_text(fields.get("LoadState")),
                    "pid_observed": fields.get("MainPID", "0").isdigit()
                    and int(fields["MainPID"]) > 0,
                    "attests_financial_health": False,
                }
            except (OSError, ValueError, subprocess.TimeoutExpired):
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
        observer = self.cache.get(
            "observer:" + str(self.observer_root), 30.0,
            lambda: runtime.observer_market_health(self.observer_root),
        )
        if not isinstance(observer, dict):
            observer = {"state": "UNKNOWN", "error_code": "OBSERVER_QUERY_INVALID"}
        services = self.cache.get("os_services", 30.0, self._os_services)
        source = envelope(
            "public.observer", observer.get("state", "UNKNOWN"),
            authority="copytrade_pm.public_observer", now=now,
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
                if guardian["status"] == "VERIFIED" and
                isinstance(guardian.get("data"), dict) and
                isinstance(guardian["data"].get("health"), dict) and
                guardian["data"]["health"].get("ages_ms", {}).get("watchdog") is not None
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
        return list(dict.fromkeys([
            *[s for s in payload.get("halts") or [] if isinstance(s, str)],
            *[s for s in health.get("reasons") or [] if isinstance(s, str)],
        ]))
