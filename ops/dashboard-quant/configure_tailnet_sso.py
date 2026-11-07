"""Switch the quant dashboard's private auth config to one Tailscale owner.

This changes only the 0600 viewer environment file. It preserves the original
password configuration in a 0600 rollback copy; no secret/login is printed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile

DIRECTORY = Path("/home/quant/.config/copytrade-dashboard")
CURRENT = DIRECTORY / "private.env"
BACKUP = DIRECTORY / "private.env.before-tailnet-sso"
KEY = "DASHBOARD_TAILSCALE_USER_LOGIN="


def _publish(raw: bytes) -> None:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=DIRECTORY, prefix=".private-env-", delete=False) as f:
            temp_path = Path(f.name)
            os.fchmod(f.fileno(), 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CURRENT)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _owner_identity() -> str:
    state = json.loads(
        subprocess.run(
            ["tailscale", "status", "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    )
    if state.get("BackendState") != "Running":
        raise RuntimeError("TAILSCALE_NOT_RUNNING")
    login = state["User"][str(state["Self"]["UserID"])]["LoginName"]
    if not isinstance(login, str) or re.fullmatch(r"[A-Za-z0-9._+@-]{2,254}", login) is None:
        raise RuntimeError("TAILSCALE_OWNER_IDENTITY_INVALID")
    return login


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("enable", "rollback"))
    args = parser.parse_args()

    if os.geteuid() != pwd.getpwnam("quant").pw_uid or CURRENT.stat().st_uid != os.geteuid():
        raise RuntimeError("QUANT_OWNED_CONFIG_REQUIRED")
    if CURRENT.stat().st_mode & 0o077:
        raise RuntimeError("DASHBOARD_PRIVATE_CONFIG_NOT_0600")

    if args.action == "rollback":
        if not BACKUP.is_file() or BACKUP.stat().st_uid != os.geteuid():
            raise RuntimeError("PRIVATE_SSO_BACKUP_MISSING")
        if BACKUP.stat().st_mode & 0o077:
            raise RuntimeError("PRIVATE_SSO_BACKUP_NOT_0600")
        _publish(BACKUP.read_bytes())
        print("PRE_SSO_CONFIG_RESTORED")
        return

    original = CURRENT.read_bytes()
    if original.count(KEY.encode()) != 0 or BACKUP.exists():
        raise RuntimeError("TAILNET_SSO_ALREADY_CONFIGURED_OR_BACKUP_PRESENT")
    if b"DASHBOARD_ACCESS_SECRET=" not in original:
        raise RuntimeError("ROLLBACK_VIEWER_SECRET_MISSING")
    login = _owner_identity()
    if not original.endswith(b"\n"):
        original += b"\n"
    added = original + (KEY + login + "\n").encode("ascii")

    descriptor = os.open(BACKUP, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as out:
            out.write(original)
            out.flush()
            os.fsync(out.fileno())
    except Exception:
        BACKUP.unlink(missing_ok=True)
        raise
    _publish(added)
    print("TAILNET_SSO_OWNER_CONFIGURED_NO_PASSWORD_DISPLAYED")


if __name__ == "__main__":
    main()
