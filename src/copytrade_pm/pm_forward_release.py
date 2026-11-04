"""Fail-closed release and OS-identity preflight for isolated paper workers.

No installer, service-manager mutation, sudo or broker transports. A coding
identity with unrestricted filesystem/privileged access is NOT isolation.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess


_PROTECTED_SYSTEM_UNITS = (
    "copytrade-paper-p1.service",
    "copytrade-paper-p14.service",
    "copytrade-paper-watchdog.service",
)

_SERVICE_ALLOWLIST = (
    "copytrade-tracker.service",
    "copytrade-source-abc.service",
    "copytrade-ensemble.service",
    "copytrade-paper-p1.service",
    "copytrade-paper-p14.service",
    "copytrade-paper-watchdog.service",
)


def read_only_user_service_inventory(*, runner=subprocess.run) -> dict:
    """Retrieve allowlisted systemd properties, NEVER invoke service changes."""
    records = []
    unavailable = []
    for unit in _SERVICE_ALLOWLIST:
        args = [
            "systemctl",
            "--user",
            "show",
            unit,
            "-p",
            "Id",
            "-p",
            "LoadState",
            "-p",
            "ActiveState",
            "-p",
            "MainPID",
            "-p",
            "FragmentPath",
            "--no-pager",
        ]
        try:
            completed = runner(
                args,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if completed.returncode != 0:
                raise ValueError("SYSTEMD_READONLY_QUERY_FAILED")
            properties = dict(
                line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
            )
            if properties.get("Id") != unit:
                raise ValueError("SYSTEMD_IDENTITY_MISMATCH")
            records.append(
                {
                    "unit": unit,
                    "load_state": properties.get("LoadState", "UNKNOWN"),
                    "active_state": properties.get("ActiveState", "UNKNOWN"),
                    "main_pid": properties.get("MainPID", "UNKNOWN"),
                    "fragment_path": properties.get("FragmentPath", ""),
                }
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            unavailable.append({"unit": unit, "reason": type(exc).__name__})
    return {
        "schema": "paper_service_readonly_inventory_v1",
        "status": "READ_ONLY_PARTIAL" if unavailable else "READ_ONLY_SNAPSHOT",
        "units": records,
        "unavailable": unavailable,
        "service_mutations": 0,
        "protected_system_services_verified": False,
    }


def read_only_protected_system_inventory(*, runner=subprocess.run) -> dict:
    """Inspect system-level unit metadata without claiming OS isolation.

    A loaded/active systemd unit does not by itself prove independent process
    identity, code immutability or authorized service control rights.
    """
    rows = []
    missing = []
    for unit in _PROTECTED_SYSTEM_UNITS:
        args = [
            "systemctl",
            "show",
            unit,
            "-p",
            "Id",
            "-p",
            "LoadState",
            "-p",
            "ActiveState",
            "-p",
            "MainPID",
            "-p",
            "User",
            "-p",
            "Group",
            "-p",
            "FragmentPath",
            "--no-pager",
        ]
        try:
            completed = runner(args, capture_output=True, text=True, timeout=8, check=False)
            if completed.returncode != 0:
                raise ValueError("PROTECTED_SYSTEMD_QUERY_FAILED")
            fields = dict(
                line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
            )
            if fields.get("Id") != unit:
                raise ValueError("PROTECTED_SYSTEMD_UNIT_IDENTITY_MISMATCH")
            rows.append(
                {
                    "unit": unit,
                    "load_state": fields.get("LoadState", "UNKNOWN"),
                    "active_state": fields.get("ActiveState", "UNKNOWN"),
                    "main_pid": fields.get("MainPID", "UNKNOWN"),
                    "configured_user": fields.get("User", ""),
                    "configured_group": fields.get("Group", ""),
                    "fragment_path": fields.get("FragmentPath", ""),
                }
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            missing.append({"unit": unit, "reason": type(exc).__name__})
    users = [r["configured_user"] for r in rows]
    return {
        "schema": "paper_protected_systemd_readonly_inventory_v1",
        "status": "READ_ONLY_PARTIAL" if missing else "READ_ONLY_SNAPSHOT",
        "units": rows,
        "unavailable": missing,
        "all_units_loaded": not missing and all(x["load_state"] == "loaded" for x in rows),
        "all_units_active": not missing and all(x["active_state"] == "active" for x in rows),
        "distinct_nonroot_configured_users": (
            not missing
            and len(users) == len(_PROTECTED_SYSTEM_UNITS)
            and len(set(users)) == len(users)
            and all(user not in ("", "root", "0") for user in users)
        ),
        "protected_process_identity_verified": False,
        "release_immutable_verified": False,
        "service_mutations": 0,
        "cutover_performed": False,
    }


def protected_paper_preflight(
    *,
    release_root: Path,
    state_root: Path,
    deployment_uid: int,
    state_uid: int,
    allow_cutover: bool = False,
    inspect_services: bool = False,
) -> dict:
    """Audit paths, ownership and coding identity without changing anything."""
    reasons: list[str] = []
    release_root = Path(release_root)
    state_root = Path(state_root)
    current_uid = os.geteuid()
    if allow_cutover:
        # An in-process boolean cannot substitute for external owner signoff.
        reasons.append("EXTERNAL_SIGNED_CUTOVER_APPROVAL_NOT_VERIFIED")
    else:
        reasons.append("EXTERNAL_CUTOVER_APPROVAL_REQUIRED")
    roots = (("RELEASE", release_root, deployment_uid), ("STATE", state_root, state_uid))
    fingerprints = {}
    for name, root, expected_uid in roots:
        if not root.is_absolute():
            reasons.append(f"{name}_PATH_NOT_ABSOLUTE")
            continue
        if root.is_symlink():
            reasons.append(f"{name}_PATH_SYMLINK")
            continue
        if not root.is_dir():
            reasons.append(f"{name}_DIRECTORY_MISSING")
            continue
        resolved = root.resolve()
        if any(p in {".devspace", ".git"} for p in resolved.parts):
            reasons.append(f"{name}_PATH_INSIDE_WRITABLE_WORKTREE")
        mode = root.stat().st_mode
        if not stat.S_ISDIR(mode):
            reasons.append(f"{name}_DIRECTORY_INVALID")
        if root.stat().st_uid != expected_uid:
            reasons.append(f"{name}_OWNER_MISMATCH")
        if current_uid == expected_uid or os.access(root, os.W_OK):
            reasons.append(f"{name}_CODING_IDENTITY_CAN_MUTATE")
        if mode & 0o007:
            reasons.append(f"{name}_WORLD_ACCESSIBLE")
        if mode & 0o022:
            reasons.append(f"{name}_GROUP_OR_WORLD_WRITABLE")
        fingerprints[name.lower()] = sha256(
            f"{resolved}:{root.stat().st_uid}:{stat.S_IMODE(mode)}".encode()
        ).hexdigest()
    if release_root.is_absolute() and state_root.is_absolute():
        if release_root.resolve() == state_root.resolve():
            reasons.append("RELEASE_AND_FINANCIAL_STATE_NOT_SEPARATED")
        if release_root.resolve() in state_root.resolve().parents:
            reasons.append("FINANCIAL_STATE_NESTED_UNDER_RELEASE")
        if state_root.resolve() in release_root.resolve().parents:
            reasons.append("RELEASE_NESTED_UNDER_FINANCIAL_STATE")
    if deployment_uid == state_uid:
        reasons.append("RELEASE_AND_FINANCIAL_STATE_SAME_OS_IDENTITY")
    if current_uid == 0:
        reasons.append("ROOT_CODING_IDENTITY_NOT_ISOLATED")
    # A read-only process check cannot prove whether sudo/docker privileges
    # permit bypassing these filesystem boundaries.
    reasons.append("SUDO_DOCKER_PRIVILEGE_SEPARATION_UNVERIFIED")
    reasons.append("PROTECTED_SERVICE_START_STOP_RIGHTS_UNVERIFIED")
    inventory = read_only_user_service_inventory() if inspect_services else None
    system_inventory = read_only_protected_system_inventory() if inspect_services else None
    if inventory is not None and inventory["unavailable"]:
        reasons.append("SERVICE_INVENTORY_INCOMPLETE")
    if system_inventory is not None:
        if system_inventory["unavailable"]:
            reasons.append("PROTECTED_SYSTEMD_INVENTORY_INCOMPLETE")
        if not system_inventory["all_units_loaded"]:
            reasons.append("PROTECTED_SYSTEMD_UNITS_NOT_INSTALLED")
        if not system_inventory["all_units_active"]:
            reasons.append("PROTECTED_SYSTEMD_UNITS_NOT_RUNNING")
        if not system_inventory["distinct_nonroot_configured_users"]:
            reasons.append("PROTECTED_SYSTEMD_IDENTITIES_NOT_SEPARATED")
    return {
        "schema": "paper_release_preflight_v1",
        "status": "BLOCKED",
        "reasons": sorted(set(reasons)),
        "release_identity_hashes": fingerprints,
        "financial_data_mutated": False,
        "systemd_units_mutated": False,
        "order_route": "NONE",
        "cutover_performed": False,
        "read_only_service_inventory": inventory,
        "read_only_protected_system_inventory": system_inventory,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only protected paper-release preflight")
    parser.add_argument("--release-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--deployment-uid", required=True, type=int)
    parser.add_argument("--state-uid", required=True, type=int)
    parser.add_argument("--inspect-services", action="store_true")
    args = parser.parse_args()
    result = protected_paper_preflight(
        release_root=args.release_root,
        state_root=args.state_root,
        deployment_uid=args.deployment_uid,
        state_uid=args.state_uid,
        inspect_services=args.inspect_services,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
