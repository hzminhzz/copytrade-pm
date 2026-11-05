"""Bounded, read-only inspections of independent release/OS/observer authorities.

Never infer paper-worker health from active units, a registry selection, a
repository checkout, or a public observer. No service mutation or broker I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import sys

UNITS = (
    "copytrade-paper-p1.service",
    "copytrade-paper-p14.service",
    "copytrade-paper-watchdog.service",
)
SHA = re.compile(r"^[a-f0-9]{40}$")


def installed_release(source_root: Path) -> dict:
    """Call the existing release owner's verified action; do not reimplement it."""
    script = Path(source_root) / "scripts" / "registry_release.py"
    if script.is_symlink() or not script.is_file():
        return {"state": "UNKNOWN", "error_code": "PINNED_RELEASE_VERIFIER_UNAVAILABLE"}
    try:
        call = subprocess.run(
            [sys.executable, str(script), "verify"],
            cwd=source_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=75,
        )
        if call.returncode:
            return {"state": "UNKNOWN", "error_code": "INSTALLED_RELEASE_VERIFY_FAILED"}
        parsed = json.loads(call.stdout)
        if (
            parsed.get("result") != "ACTIVE_READ_ONLY_VERIFIED"
            or not isinstance(parsed.get("revision"), str)
            or not SHA.fullmatch(parsed["revision"])
            or parsed.get("registry_timer") != "NOT_INSTALLED"
            or parsed.get("source", {}).get("trading_authorized") is not False
        ):
            return {"state": "UNKNOWN", "error_code": "INSTALLED_RELEASE_NOT_VERIFIED"}
        return {
            "state": "VERIFIED",
            "release_revision": parsed["revision"],
            "source_manifest_sha256": parsed["source"]["source_manifest_sha256"],
            "registry_timer": "NOT_INSTALLED",
            "trading_authorized": False,
            "scope": "PINNED_REGISTRY_ONLY_NOT_TRADING_SERVICES",
        }
    except OSError, ValueError, TypeError, subprocess.TimeoutExpired:
        return {"state": "UNKNOWN", "error_code": "INSTALLED_RELEASE_QUERY_UNAVAILABLE"}


def paper_unit_inventory() -> dict:
    """OS unit status is independent evidence, but insufficient for paper admission."""
    try:
        output = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                *UNITS,
                "--property=Id",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=MainPID",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if output.returncode:
            raise ValueError("SYSTEMD_USER_QUERY_FAILED")
        records: dict[str, dict] = {}
        for section in output.stdout.split("\n\n"):
            values = dict(line.split("=", 1) for line in section.splitlines() if "=" in line)
            name = values.get("Id")
            if name not in UNITS or name in records:
                raise ValueError("SYSTEMD_UNIT_INVENTORY_MISMATCH")
            if values.get("LoadState") not in ("loaded", "not-found", "masked", "error"):
                raise ValueError("SYSTEMD_UNIT_LOAD_UNKNOWN")
            if values.get("ActiveState") not in (
                "active",
                "inactive",
                "failed",
                "activating",
                "deactivating",
            ):
                raise ValueError("SYSTEMD_UNIT_ACTIVE_UNKNOWN")
            if not str(values.get("MainPID", "")).isdigit():
                raise ValueError("SYSTEMD_UNIT_PID_INVALID")
            records[name] = {
                "load_state": values["LoadState"],
                "active_state": values["ActiveState"],
                "pid_observed": int(values["MainPID"]) > 0,
            }
        if set(records) != set(UNITS):
            raise ValueError("SYSTEMD_UNIT_INVENTORY_INCOMPLETE")
        any_active = any(x["active_state"] == "active" for x in records.values())
        any_unknown = any(
            x["active_state"] in ("failed", "activating", "deactivating")
            or x["load_state"] == "error"
            for x in records.values()
        )
        # Actual protected candidates are SYSTEM services, not user units.
        # Never conclude NOT_RUNNING from the user manager alone.
        from .pm_forward_release import read_only_protected_system_inventory

        system = read_only_protected_system_inventory(runner=subprocess.run)
        system_active = any(x["active_state"] == "active" for x in system["units"])
        system_unavailable = bool(system["unavailable"])
        system_unknown = any(
            x["active_state"] in ("failed", "activating", "deactivating")
            or x["load_state"] == "error"
            for x in system["units"]
        )
        state = (
            "UNKNOWN"
            if system_unavailable
            else "DEGRADED"
            if any_active or any_unknown or system_active or system_unknown
            else "NOT_RUNNING"
        )
        return {
            "state": state,
            "units": records,
            "system_units": system["units"],
            "system_unit_inventory": system["status"],
            "scope": "USER_AND_SYSTEM_KNOWN_PROTECTED_UNIT_NAMES",
            "protected_worker_attested": False,
            "reason": "SYSTEM_PROTECTED_UNIT_INVENTORY_INCOMPLETE"
            if system_unavailable
            else "ACTIVE_UNIT_REQUIRES_INDEPENDENT_JOURNAL_AND_HEARTBEAT"
            if any_active or system_active
            else "SYSTEMD_SERVICE_STATE_REQUIRES_ATTENTION"
            if any_unknown or system_unknown
            else "NO_ACTIVE_KNOWN_PROTECTED_PAPER_UNITS",
        }
    except ValueError, OSError, subprocess.TimeoutExpired:
        return {"state": "UNKNOWN", "error_code": "PAPER_SYSTEMD_QUERY_UNAVAILABLE"}


def observer_market_health(state_root: Path | None) -> dict:
    """Only actual source/market receipt tape evidence, never venue-provider health."""
    if state_root is None:
        return {
            "state": "UNKNOWN",
            "error_code": "OBSERVER_STATE_ROOT_NOT_SUPPLIED",
            "scope": "NOT_A_LIVE_MARKET_PROVIDER_ATTESTATION",
        }
    from .pm_forward_observer_health import inspect_public_observer_heartbeat

    root = Path(state_root)
    try:
        checked = inspect_public_observer_heartbeat(
            root,
            journal_db=root / "paper-events.sqlite3",
            as_of=datetime.now(UTC).isoformat(),
        )
        return {
            "state": "DEGRADED" if checked.get("health") == "DEGRADED_OBSERVER_ONLY" else "UNKNOWN",
            "observer_health": checked.get("health", "UNKNOWN"),
            "market_quote_tapes_verified": checked.get("market_quote_tapes_verified", 0),
            "source_aliases_with_receipts": checked.get("source_aliases_with_receipts", 0),
            "protected_worker_attested": False,
            "provider_health": "UNKNOWN",
            "scope": "PUBLIC_OBSERVER_ONLY_NOT_BROKER_OR_MARKET_PROVIDER",
        }
    except OSError, ValueError, TypeError, KeyError:
        return {"state": "UNKNOWN", "error_code": "OBSERVER_MARKET_QUERY_UNAVAILABLE"}
