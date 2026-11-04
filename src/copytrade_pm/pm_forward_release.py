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


def protected_paper_preflight(
    *,
    release_root: Path,
    state_root: Path,
    deployment_uid: int,
    state_uid: int,
    allow_cutover: bool = False,
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
    return {
        "schema": "paper_release_preflight_v1",
        "status": "BLOCKED",
        "reasons": sorted(set(reasons)),
        "release_identity_hashes": fingerprints,
        "financial_data_mutated": False,
        "systemd_units_mutated": False,
        "order_route": "NONE",
        "cutover_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only protected paper-release preflight")
    parser.add_argument("--release-root", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--deployment-uid", required=True, type=int)
    parser.add_argument("--state-uid", required=True, type=int)
    args = parser.parse_args()
    result = protected_paper_preflight(
        release_root=args.release_root,
        state_root=args.state_root,
        deployment_uid=args.deployment_uid,
        state_uid=args.state_uid,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
