#!/usr/bin/env python3
"""Atomic, reversible deployment of the NO_TRADE Ops Control Center sidecar.

Only a committed, SHA-pinned release may become the user-level service. No
production SQLite writes, broker transport, Git main checkout or root unit.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[1]
RELEASES = Path.home() / ".local/share/copytrade/releases"
BACKUPS = Path.home() / ".local/share/copytrade/ops-center/unit-backups"
UNIT = Path.home() / ".config/systemd/user/copytrade-ops-center.service"
SERVICE = "copytrade-ops-center.service"


def run(*command: str, cwd: Path | None = None, timeout: int = 120) -> str:
    process = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    if process.returncode:
        raise RuntimeError(f"{command[0]} returned {process.returncode}: {process.stderr[-900:]}")
    return process.stdout.strip()


def full_sha(ref: str) -> str:
    sha = run("git", "rev-parse", "--verify", f"{ref}^{{commit}}", cwd=REPO)
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected an exact, local Git commit")
    return sha


def release_owner_python(release: Path) -> Path:
    """The owner CLI must use dependencies installed inside this exact release."""
    return release / ".venv/bin/python"


def assert_clean_release(release: Path) -> None:
    """Never promote local modifications in a reused pinned worktree."""
    if run("git", "status", "--porcelain", "--untracked-files=all", cwd=release):
        raise RuntimeError("Pinned Ops release has modified or untracked source files")


def prepare_owner_runtime(release: Path) -> Path:
    """Build and smoke-test the locked read-only owner CLI before any unit change."""
    run(
        "uv",
        "sync",
        "--locked",
        "--no-dev",
        "--no-editable",
        "--no-progress",
        cwd=release,
        timeout=240,
    )
    python = release_owner_python(release)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("Release-bound owner interpreter is unavailable")
    run(
        str(python),
        "-c",
        "import sys, pydantic, copytrade_pm.pm_operations; "
        f"assert sys.prefix == {str(release / '.venv')!r}; "
        "assert pydantic.__version__ == '2.14.3'",
        cwd=release,
        timeout=30,
    )
    run(
        str(python),
        "-m",
        "copytrade_pm.pm_operations",
        "cwsa",
        "chapter2",
        "site-view",
        "--help",
        cwd=release,
        timeout=30,
    )
    return python


def service_unit(release: Path, sha: str) -> str:
    return f"""[Unit]
Description=Copytrade Ops Control Center (NO_TRADE pinned {sha[:12]})
After=network.target

[Service]
Type=simple
WorkingDirectory={release}
Environment=COPYTRADE_OPS_RELEASE_SHA={sha}
Environment=COPYTRADE_OPS_OWNER_PYTHON={release_owner_python(release)}
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 {release}/scripts/dashboard_server.py --port 8888 --bind 127.0.0.1
Restart=always
RestartSec=3
NoNewPrivileges=yes
UMask=0077
LimitNOFILE=65535

[Install]
WantedBy=default.target
"""


def health(expected_sha: str | None) -> dict:
    last: Exception | None = None
    for _ in range(45):
        try:
            with urlopen("http://127.0.0.1:8888/api/health", timeout=2) as res:
                state = json.load(res)
            if (
                state.get("status") == "ok"
                and state.get("mode") == "NO_TRADE"
                and state.get("revision") == expected_sha
            ):
                with urlopen("http://127.0.0.1:8888/api/state", timeout=5) as res:
                    data = json.load(res)
                if not data.get("wallets") or data["registrySync"]["latestAccepted"] is not None:
                    raise RuntimeError("Registry projection invalid or promoted")
                return {
                    "service": "active",
                    "revision": expected_sha,
                    "wallets": len(data["wallets"]),
                    "portfolios": len(data["portfolios"]),
                }
        except Exception as exc:
            last = exc
        time.sleep(0.2)
    raise RuntimeError(f"Release health probe failed: {type(last).__name__}: {last}")


def atomic_write_unit(content: str) -> None:
    UNIT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    candidate = UNIT.with_name(f".{UNIT.name}.candidate-{os.getpid()}")
    with open(candidate, "x", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    candidate.replace(UNIT)


def activate(content: str, expected_sha: str) -> dict:
    previous = UNIT.read_text(encoding="utf-8") if UNIT.exists() else None
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = None
    if previous is not None:
        digest = hashlib.sha256(previous.encode("utf-8")).hexdigest()[:12]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / f"{stamp}-{digest}.service"
        with open(backup, "x", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(previous)
            f.flush()
            os.fsync(f.fileno())
    try:
        atomic_write_unit(content)
        run("systemctl", "--user", "daemon-reload")
        run("systemctl", "--user", "restart", SERVICE)
        run("systemctl", "--user", "is-active", SERVICE)
        return {**health(expected_sha), "rollbackUnit": str(backup) if backup else None}
    except Exception:
        if previous is not None:
            atomic_write_unit(previous)
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", SERVICE)
        raise


def deploy(sha: str, apply: bool) -> None:
    target = RELEASES / f"ops-control-center-{sha[:12]}"
    if not apply:
        print(
            json.dumps(
                {
                    "action": "preview",
                    "commit": sha,
                    "release": str(target),
                    "unit": str(UNIT),
                    "mode": "NO_TRADE",
                }
            )
        )
        return
    RELEASES.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists():
        if full_sha_from(target) != sha:
            raise RuntimeError("Release path exists at a different Git commit")
    else:
        run("git", "worktree", "add", "--detach", str(target), sha, cwd=REPO, timeout=120)
    assert_clean_release(target)
    prepare_owner_runtime(target)
    pkg = target / "ops/control-center"
    run("npm", "ci", "--no-audit", "--no-fund", cwd=pkg, timeout=240)
    run("npm", "run", "build", cwd=pkg, timeout=180)
    if not (pkg / "dist/index.html").is_file():
        raise RuntimeError("Missing built index")
    run("node", "ops/control-center/tests/browser.cjs", cwd=target, timeout=180)
    assert_clean_release(target)
    receipt = activate(service_unit(target, sha), sha)
    print(json.dumps({"action": "deployed", **receipt}))


def full_sha_from(target: Path) -> str:
    return run("git", "rev-parse", "HEAD", cwd=target)


def rollback(filename: str, apply: bool) -> None:
    candidate = BACKUPS / filename
    if candidate.resolve().parent != BACKUPS.resolve() or not candidate.is_file():
        raise ValueError("Rollback must name an existing pinned unit backup in unit-backups")
    content = candidate.read_text(encoding="utf-8")
    if "ExecStart=/usr/bin/python3 " not in content:
        raise ValueError("Backup is not a compatible dashboard user unit")
    if not apply:
        print(json.dumps({"action": "rollback-preview", "backup": str(candidate)}))
        return
    previous = UNIT.read_text(encoding="utf-8") if UNIT.exists() else None
    try:
        atomic_write_unit(content)
        run("systemctl", "--user", "daemon-reload")
        run("systemctl", "--user", "restart", SERVICE)
        run("systemctl", "--user", "is-active", SERVICE)
        with urlopen("http://127.0.0.1:8888/", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("Rollback HTTP health failed")
        print(
            json.dumps(
                {
                    "action": "rolled_back",
                    "backup": str(candidate),
                    "service": "active",
                    "http": 200,
                }
            )
        )
    except Exception:
        if previous is not None:
            atomic_write_unit(previous)
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "restart", SERVICE)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback-unit", help="Saved basename in the private backup directory")
    args = parser.parse_args()
    if args.rollback_unit:
        rollback(args.rollback_unit, args.apply)
    else:
        deploy(full_sha(args.revision), args.apply)


if __name__ == "__main__":
    main()
