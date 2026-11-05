"""No-order standby worker and independent fail-closed watchdog.

This component is deliberately not the financial paper engine. It cannot submit
broker orders or write PM-03/PM-04 account events. A process heartbeat must never
be interpreted as PAPER_RUNNING, scientific qualification or protected isolation.
System-level services require separately managed OS identities and release files.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import pwd
import re
import signal
import stat
import tempfile
import time
from typing import Any

from .pm03_account import clock, digest
from .pm_forward_heartbeat import _process_identity

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ROLES = {"P1": "copytrade-paper-p1", "P14": "copytrade-paper-p14"}
SCHEMA = "paper_guarded_standby_heartbeat_v1"
WATCHDOG_SCHEMA = "paper_guarded_watchdog_status_v1"


class StandbyBlocked(ValueError):
    """A failed prerequisite never grants protected runtime status."""


def _private_root(path: Path, *, allow_monitor_group: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise StandbyBlocked("PRIVATE_STATE_ROOT_MISSING_OR_LINKED")
    attrs = path.stat()
    allowed = 0o750 if allow_monitor_group else 0o700
    if not stat.S_ISDIR(attrs.st_mode) or attrs.st_uid != os.geteuid():
        raise StandbyBlocked("PRIVATE_STATE_WRONG_OWNER")
    if stat.S_IMODE(attrs.st_mode) & ~allowed:
        raise StandbyBlocked("PRIVATE_STATE_UNSAFE_PERMISSIONS")
    return path


def _strict_release(release: Path, revision: str, role: str) -> None:
    """Check only locally observable OS preconditions, not a signed cutover."""
    if not SHA40.fullmatch(revision) or role not in (*ROLES.values(), "copytrade-paper-watchdog"):
        raise StandbyBlocked("UNSAFE_RELEASE_OR_ROLE")
    release = Path(release)
    if not release.is_absolute() or release.is_symlink() or release.name != revision:
        raise StandbyBlocked("RELEASE_NOT_EXACTLY_PINNED")
    if not release.is_dir() or release.stat().st_uid != 0:
        raise StandbyBlocked("RELEASE_NOT_ROOT_OWNED")
    if stat.S_IMODE(release.stat().st_mode) & 0o022:
        raise StandbyBlocked("RELEASE_WRITABLE_BY_NONROOT")
    actual = pwd.getpwuid(os.geteuid()).pw_name
    if actual != role or os.geteuid() == 0:
        raise StandbyBlocked("INDEPENDENT_OS_ROLE_NOT_PRESENT")
    module = Path(__file__).resolve()
    if not module.is_relative_to(release.resolve(strict=True)):
        raise StandbyBlocked("EXECUTING_OUTSIDE_PINNED_RELEASE")


def _write_state(path: Path, payload: dict[str, Any], *, group_readable: bool = False) -> None:
    """Crash-atomic private publication with a content digest and fsync."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise StandbyBlocked("STATE_DESTINATION_UNSAFE")
    data = (
        json.dumps(
            {**payload, "payload_sha": digest(payload)}, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode()
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".state-", delete=False
        ) as file:
            temp_name = file.name
            os.fchmod(file.fileno(), 0o640 if group_readable else 0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
        temp_name = None
        fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temp_name is not None:
            os.unlink(temp_name)


def _read_bounded_state(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise StandbyBlocked("HEARTBEAT_MISSING_OR_UNSAFE")
    if stat.S_IMODE(path.stat().st_mode) & 0o007:
        raise StandbyBlocked("HEARTBEAT_WORLD_ACCESSIBLE")
    try:
        item = json.loads(path.read_bytes())
        if not isinstance(item, dict):
            raise StandbyBlocked("HEARTBEAT_INVALID_SCHEMA")
        payload = {key: value for key, value in item.items() if key != "payload_sha"}
        if item.get("payload_sha") != digest(payload):
            raise StandbyBlocked("HEARTBEAT_SHA_INVALID")
        return payload
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise StandbyBlocked("HEARTBEAT_CORRUPT") from exc


def worker_cycle(
    *,
    portfolio: str,
    root: Path,
    revision: str,
    release: Path,
    strict: bool = True,
    as_of: str | None = None,
) -> dict:
    """Emit self-attested *standby only* heartbeat; never create a paper run."""
    if portfolio not in ROLES or not SHA40.fullmatch(revision):
        raise StandbyBlocked("INVALID_PORTFOLIO_OR_REVISION")
    _private_root(root, allow_monitor_group=True)
    if strict:
        _strict_release(release, revision, ROLES[portfolio])
    observed = clock(as_of or datetime.now(UTC).isoformat()).isoformat()
    payload = {
        "schema": SCHEMA,
        "portfolio": portfolio,
        "revision": revision,
        "observed_at": observed,
        "process_identity": _process_identity(os.getpid()),
        "status": "BLOCKED_NO_FINANCIAL_ADMISSION",
        "reason": "SOURCE_NAV_MARKET_CAPACITY_AND_FINANCIAL_ADMISSION_NOT_ATTESTED",
        "execution_enabled": False,
        "financial_events_created_by_this_process": 0,
        "paper_running": False,
        "protected_worker_attested": False,
        "trading_authorized": False,
        "order_route": "NONE",
        "protection_mode": "ROOT_MANAGED_STANDBY_UNATTESTED" if strict else "UNPROTECTED_CANARY",
    }
    _write_state(Path(root) / "standby-heartbeat.json", payload, group_readable=strict)
    return payload


def inspect_worker(
    root: Path,
    *,
    portfolio: str,
    revision: str,
    as_of: str | None = None,
    max_age_seconds: int = 90,
    require_independent_uid: bool = True,
) -> dict:
    """Independent liveness proof is not financial admission."""
    reasons: list[str] = []
    try:
        observed = clock(as_of or datetime.now(UTC).isoformat())
        payload = _read_bounded_state(Path(root) / "standby-heartbeat.json")
        if (
            payload.get("schema") != SCHEMA
            or payload.get("portfolio") != portfolio
            or payload.get("revision") != revision
            or payload.get("status") != "BLOCKED_NO_FINANCIAL_ADMISSION"
            or payload.get("paper_running") is not False
            or payload.get("protected_worker_attested") is not False
            or payload.get("execution_enabled") is not False
            or payload.get("order_route") != "NONE"
        ):
            raise StandbyBlocked("UNTRUSTED_WORKER_STATUS")
        process = payload["process_identity"]
        if process != _process_identity(process["pid"]):
            raise StandbyBlocked("WORKER_PROCESS_IDENTITY_CHANGED")
        if (
            Path(root).stat().st_uid != process["uid"]
            or (Path(root) / "standby-heartbeat.json").stat().st_uid != process["uid"]
        ):
            raise StandbyBlocked("WORKER_STATE_OWNER_MISMATCH")
        if require_independent_uid:
            if process["uid"] == os.geteuid():
                raise StandbyBlocked("WATCHDOG_SHARES_WORKER_UID")
            if pwd.getpwuid(process["uid"]).pw_name != ROLES[portfolio]:
                raise StandbyBlocked("WORKER_OS_ROLE_MISMATCH")
        age = (observed - clock(payload["observed_at"])).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise StandbyBlocked("WORKER_HEARTBEAT_STALE_OR_FUTURE")
    except (StandbyBlocked, OSError, ValueError, KeyError, TypeError) as exc:
        reasons.append(str(exc)[:120])
    return {
        "portfolio": portfolio,
        "status": "ALIVE_STANDBY_ONLY" if not reasons else "HALT",
        "reasons": reasons,
        "protected_worker_attested": False,
        "paper_running": False,
        "order_route": "NONE",
    }


def watchdog_cycle(
    *,
    watchdog_root: Path,
    worker_roots: dict[str, Path],
    revision: str,
    release: Path,
    strict: bool = True,
    as_of: str | None = None,
) -> dict:
    """Latches a halt on missing/stale/tampered workers; never clears it."""
    _private_root(watchdog_root)
    if strict:
        _strict_release(release, revision, "copytrade-paper-watchdog")
    if set(worker_roots) != set(ROLES) or not SHA40.fullmatch(revision):
        raise StandbyBlocked("WATCHDOG_SCOPE_INVALID")
    assessments = {
        name: inspect_worker(
            path,
            portfolio=name,
            revision=revision,
            as_of=as_of,
            require_independent_uid=strict,
        )
        for name, path in sorted(worker_roots.items())
    }
    latch = Path(watchdog_root) / "halt-latch.json"
    if any(row["status"] != "ALIVE_STANDBY_ONLY" for row in assessments.values()):
        if not latch.exists():
            _write_state(
                latch,
                {
                    "schema": "paper_guarded_halt_latch_v1",
                    "at": clock(as_of or datetime.now(UTC).isoformat()).isoformat(),
                    "reasons": {k: v["reasons"] for k, v in assessments.items() if v["reasons"]},
                    "manual_reset_required": True,
                    "execution_enabled": False,
                    "order_route": "NONE",
                },
            )
    result = {
        "schema": WATCHDOG_SCHEMA,
        "observed_at": clock(as_of or datetime.now(UTC).isoformat()).isoformat(),
        "revision": revision,
        "workers": assessments,
        "status": "HALT_LATCHED" if latch.exists() else "STANDBY_MONITORED",
        "manual_reset_required": latch.exists(),
        "protected_watchdog_attested": False,
        "paper_running": False,
        "order_route": "NONE",
        "process_identity": _process_identity(os.getpid()),
    }
    _write_state(Path(watchdog_root) / "watchdog-status.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded no-order paper standby (not financial)")
    parser.add_argument("role", choices=("worker", "watchdog"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--portfolio", choices=("P1", "P14"))
    parser.add_argument("--p1-root", type=Path)
    parser.add_argument("--p14-root", type=Path)
    parser.add_argument("--interval-seconds", type=int, default=20)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--unprotected-canary", action="store_true")
    args = parser.parse_args()
    if args.interval_seconds < 2 or args.interval_seconds > 60:
        parser.error("interval must be 2..60 seconds")
    if args.role == "worker" and (args.portfolio is None or args.p1_root or args.p14_root):
        parser.error("worker requires portfolio only")
    if args.role == "watchdog" and (args.portfolio or not args.p1_root or not args.p14_root):
        parser.error("watchdog requires both worker roots")
    run = True

    def stop(_sig: int, _frame: object) -> None:
        nonlocal run
        run = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while run:
        if args.role == "worker":
            report = worker_cycle(
                portfolio=args.portfolio,
                root=args.state_root,
                release=args.release,
                revision=args.revision,
                strict=not args.unprotected_canary,
            )
        else:
            report = watchdog_cycle(
                watchdog_root=args.state_root,
                worker_roots={"P1": args.p1_root, "P14": args.p14_root},
                release=args.release,
                revision=args.revision,
                strict=not args.unprotected_canary,
            )
        print(json.dumps(report, sort_keys=True), flush=True)
        if args.once:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
