"""Install an explicitly *unprotected*, no-order public observer user unit.

This is NOT the protected financial P1/P14 paper worker or watchdog.
Only the registry release owner's independently verified, exact Git revision
may be pinned. The installer never invokes systemctl, starts a process,
creates a paper account, or modifies any broker service.

The one supported --apply writes a new, unique user-unit configuration.
Installing or activating a protected financial worker is out of scope.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

SCHEMA = "paper_public_observer_user_unit_v1"
UNIT = "copytrade-public-observer-p1p14.service"
RELEASES = Path.home() / ".local/share/copytrade/registry/release-control/releases"
CURRENT = RELEASES.parent / "current"
UNIT_DIR = Path.home() / ".config/systemd/user"
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]+\Z")


class ObserverUnitBlocked(ValueError):
    pass


def _require_path(
    path: Path, *, directory: bool, private: bool, historical_locator: bool = False
) -> Path:
    """Reject path injection/symlinks and unowned or incorrectly permissioned roots."""
    raw = str(path)
    if not path.is_absolute() or not SAFE_PATH.fullmatch(raw):
        raise ObserverUnitBlocked("UNSAFE_OR_NON_ABSOLUTE_UNIT_PATH")
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise ObserverUnitBlocked("UNAVAILABLE_OR_LINKED_UNIT_INPUT")
    info = path.stat()
    if info.st_uid != os.geteuid():
        raise ObserverUnitBlocked("UNIT_INPUT_WRONG_OWNER")
    if private and info.st_mode & 0o077:
        raise ObserverUnitBlocked("PRIVATE_OBSERVER_ROOT_NOT_0700")
    if not private and info.st_mode & (0o002 if historical_locator else 0o022):
        raise ObserverUnitBlocked("UNIT_INPUT_GROUP_WORLD_WRITABLE")
    return path.resolve(strict=True)


def _verify_release(
    revision: str,
    releases_root: Path,
    current: Path,
    *,
    runner=subprocess.run,
) -> tuple[Path, dict]:
    if type(revision) is not str or not SHA40.fullmatch(revision):
        raise ObserverUnitBlocked("INVALID_PINNED_REVISION")
    releases_root = _require_path(releases_root, directory=True, private=True)
    path = releases_root / revision
    _require_path(path, directory=True, private=False)
    if not current.is_symlink() or current.resolve(strict=True) != path:
        raise ObserverUnitBlocked("REGISTRY_RELEASE_POINTER_NOT_PINNED")
    verifier = path / "scripts/registry_release.py"
    if verifier.is_symlink() or not verifier.is_file():
        raise ObserverUnitBlocked("CANONICAL_RELEASE_VERIFIER_MISSING")
    try:
        outcome = runner(
            [sys.executable, str(verifier), "verify"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=80,
            check=False,
        )
        if outcome.returncode:
            raise ObserverUnitBlocked("INSTALLED_REGISTRY_RELEASE_NOT_VERIFIED")
        verified = json.loads(outcome.stdout)
    except (OSError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ObserverUnitBlocked("INSTALLED_REGISTRY_RELEASE_NOT_VERIFIED") from exc
    source = verified.get("source") if isinstance(verified, dict) else None
    if (
        not isinstance(verified, dict)
        or not isinstance(source, dict)
        or verified.get("result") != "ACTIVE_READ_ONLY_VERIFIED"
        or verified.get("revision") != revision
        or source.get("trading_authorized") is not False
        or not isinstance(source.get("source_manifest_sha256"), str)
        or not SHA64.fullmatch(source["source_manifest_sha256"])
        or verified.get("registry_timer") != "NOT_INSTALLED"
    ):
        raise ObserverUnitBlocked("PINNED_RELEASE_AUTHORITY_MISMATCH")
    executable = path / ".venv/bin/python"
    if not executable.exists() or not os.access(executable, os.X_OK):
        raise ObserverUnitBlocked("PINNED_OBSERVER_PYTHON_MISSING")
    try:
        imports = runner(
            [
                str(executable),
                "-c",
                "import copytrade_pm.pm_forward_observer; import ccxt.pro; import websockets",
            ],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if imports.returncode:
            raise ObserverUnitBlocked("PINNED_PUBLIC_OBSERVER_EXTRAS_MISSING")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ObserverUnitBlocked("PINNED_PUBLIC_OBSERVER_EXTRAS_MISSING") from exc
    return path, verified


def _unit_text(
    release: Path,
    registry: Path,
    primary: Path,
    secondary: Path,
    state: Path,
) -> str:
    # All paths were validated and must be absolute, non-whitespace ASCII.
    command = " ".join(
        (
            str(release / ".venv/bin/python"),
            "-m copytrade_pm.pm_forward_observer",
            "--registry",
            str(registry),
            "--primary-dir",
            str(primary),
            "--secondary-dir",
            str(secondary),
            "--state-root",
            str(state),
            "--epochs 0",
            "--service-cadence-seconds 120",
            "--service-cycle-timeout-seconds 360",
            "--seconds-per-account 2",
            "--max-source-frames 2",
            "--market-duration-seconds 2",
            "--max-market-updates 3",
            "--market-shard-size 8",
        )
    )
    return (
        "[Unit]\n"
        "Description=P1/P14 public observer only (NO TRADE, NOT PAPER_RUNNING)\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "StartLimitIntervalSec=600\n"
        "StartLimitBurst=5\n"
        "\n[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={release}\n"
        f"ExecStart={command}\n"
        "Restart=on-failure\n"
        "RestartSec=25s\n"
        "TimeoutStopSec=30s\n"
        "KillSignal=SIGTERM\n"
        "UMask=0077\n"
        "Environment=PYTHONDONTWRITEBYTECODE=1\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        "NoNewPrivileges=true\n"
        "ProtectSystem=full\n"
        "PrivateTmp=true\n"
        "RestrictSUIDSGID=true\n"
        "LockPersonality=true\n"
        "TasksMax=100\n"
        "MemoryMax=700M\n"
        "CPUQuota=60%\n"
        "\n[Install]\n"
        "WantedBy=default.target\n"
    )


def plan(
    *,
    revision: str,
    registry: Path,
    primary: Path,
    secondary: Path,
    state: Path,
    releases_root: Path = RELEASES,
    current: Path = CURRENT,
    unit_dir: Path = UNIT_DIR,
    runner=subprocess.run,
) -> tuple[dict, str]:
    release, verified = _verify_release(revision, releases_root, current, runner=runner)
    registry = _require_path(registry, directory=False, private=False)
    primary = _require_path(primary, directory=True, private=False, historical_locator=True)
    secondary = _require_path(secondary, directory=True, private=False, historical_locator=True)
    state = _require_path(state, directory=True, private=True)
    unit_dir = _require_path(unit_dir, directory=True, private=False)
    if state == registry.parent or state == release:
        raise ObserverUnitBlocked("PUBLIC_STATE_OVERLAPS_AUTHORITY")
    if (
        state in (primary, secondary)
        or state in primary.parents
        or state in secondary.parents
        or primary in state.parents
        or secondary in state.parents
    ):
        raise ObserverUnitBlocked("PUBLIC_STATE_OVERLAPS_SOURCE")
    # Mainline public observer writes to its own journal, *never* to the WR
    # registry, tracker subscriber DB, independent source dirs, or PM-03 state.
    content = _unit_text(release, registry, primary, secondary, state)
    destination = unit_dir / UNIT
    if destination.is_symlink():
        raise ObserverUnitBlocked("USER_OBSERVER_UNIT_SYMLINK")
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != content.encode():
            raise ObserverUnitBlocked("CONFLICTING_EXISTING_OBSERVER_UNIT")
        existing = "SAME_CONTENT"
    else:
        existing = "NOT_INSTALLED"
    return {
        "schema": SCHEMA,
        "status": "READY_UNPROTECTED_PUBLIC_OBSERVER_ONLY",
        "unit": UNIT,
        "unit_path": str(destination),
        "revision": revision,
        "release_verified": verified["result"],
        "source_manifest_sha256": verified["source"]["source_manifest_sha256"],
        "unit_sha256": sha256(content.encode()).hexdigest(),
        "existing": existing,
        "financial_events_allowed": False,
        "paper_observed": False,
        "protected_worker_attested": False,
        "trading_authorized": False,
        "order_route": "NONE",
        "systemd_mutated": False,
        "service_started": False,
        "protection_scope": "UNPRIVILEGED_PUBLIC_OBSERVER_ONLY",
        "historical_locator_source_integrity_independent": False,
    }, content


def install(path: Path, content: str) -> str:
    """Atomic no-overwrite unit installation; failed writes leave no active unit."""
    if path.is_symlink():
        raise ObserverUnitBlocked("USER_OBSERVER_UNIT_SYMLINK")
    if path.exists():
        if path.read_bytes() != content.encode():
            raise ObserverUnitBlocked("CONFLICTING_EXISTING_OBSERVER_UNIT")
        return "EXISTS_IDENTICAL"
    pending = path.with_name(f".{path.name}.{secrets.token_hex(8)}.pending")
    descriptor = None
    linked = False
    try:
        descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            descriptor = None
            target.write(content.encode())
            target.flush()
            os.fsync(target.fileno())
        # Linking is atomic and cannot replace an existing unit.
        os.link(pending, path, follow_symlinks=False)
        linked = True
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return "INSTALLED_NOT_STARTED"
    except FileExistsError as exc:
        raise ObserverUnitBlocked("CONCURRENT_OBSERVER_UNIT_INSTALL") from exc
    except OSError as exc:
        if linked:
            os.unlink(path)
        raise ObserverUnitBlocked("PUBLIC_OBSERVER_UNIT_INSTALL_IO_FAILED") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if pending.exists():
            os.unlink(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--secondary-dir", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report, unit = plan(
            revision=args.revision,
            registry=args.registry,
            primary=args.primary_dir,
            secondary=args.secondary_dir,
            state=args.state_root,
        )
        if args.apply:
            installation = install(Path(report["unit_path"]), unit)
            report.update(
                status=installation,
                systemd_unit_file_mutated=(installation == "INSTALLED_NOT_STARTED"),
                systemd_mutated=False,
                service_started=False,
            )
    except ObserverUnitBlocked as exc:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "BLOCKED",
                    "reason": str(exc),
                    "order_route": "NONE",
                    "protected_worker_attested": False,
                    "paper_observed": False,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(2) from None
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
