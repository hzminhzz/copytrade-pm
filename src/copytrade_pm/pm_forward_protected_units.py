"""Offline, unprivileged staging of ROOT-managed guarded paper service units.

The bundle is not installed, signed, immutable, or proof of financial
admission. Only an OS administrator can create users, pin a root-owned
release, install these units, test rollback, and verify independent identity.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

SHA40 = re.compile(r"[a-f0-9]{40}\Z")
UNIT_NAMES = (
    "copytrade-paper-p1.service",
    "copytrade-paper-p14.service",
    "copytrade-paper-watchdog.service",
)
RELEASE_ROOT = Path("/opt/copytrade-paper/releases")
MONITOR_ROOT = Path("/var/lib/copytrade-paper/monitor")
WATCHDOG_ROOT = Path("/var/lib/copytrade-paper/watchdog")


def render_system_units(revision: str) -> dict[str, str]:
    """Return pinned, network-isolated, no-trade standby system units."""
    if not isinstance(revision, str) or SHA40.fullmatch(revision) is None:
        raise ValueError("PROTECTED_UNITS_REVISION_INVALID")
    release = RELEASE_ROOT / revision
    python = release / ".venv/bin/python"
    common = (
        "Type=simple\n"
        "WorkingDirectory=" + str(release) + "\n"
        "NoNewPrivileges=yes\n"
        "ProtectSystem=strict\n"
        "ProtectHome=yes\n"
        "PrivateTmp=yes\n"
        "PrivateDevices=yes\n"
        "ProtectClock=yes\n"
        "ProtectControlGroups=yes\n"
        "ProtectKernelTunables=yes\n"
        "ProtectKernelModules=yes\n"
        "LockPersonality=yes\n"
        "RestrictSUIDSGID=yes\n"
        "RestrictNamespaces=yes\n"
        "CapabilityBoundingSet=\n"
        "AmbientCapabilities=\n"
        "IPAddressDeny=any\n"
        "RestrictAddressFamilies=AF_UNIX\n"
        "UMask=0027\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        "TimeoutStopSec=15\n"
        "KillMode=control-group\n"
        "MemoryMax=256M\n"
        "TasksMax=32\n"
    )
    units: dict[str, str] = {}
    for portfolio in ("P1", "P14"):
        name = portfolio.lower()
        unit = "copytrade-paper-" + name + ".service"
        root = MONITOR_ROOT / name
        units[unit] = (
            "[Unit]\n"
            "Description=Guarded "
            + portfolio
            + " financial-paper STANDBY (no orders, no paper admission)\n"
            "After=local-fs.target\n"
            "ConditionPathIsDirectory=" + str(release) + "\n"
            "[Service]\n"
            "User=copytrade-paper-" + name + "\n"
            "Group=copytrade-paper-monitor\n"
            + common
            + "ReadWritePaths="
            + str(root)
            + "\n"
            + "ExecStart="
            + str(python)
            + " -m copytrade_pm.pm_forward_protected_ops worker"
            + " --portfolio "
            + portfolio
            + " --revision "
            + revision
            + " --release "
            + str(release)
            + " --state-root "
            + str(root)
            + " --interval-seconds 15\n"
            + "[Install]\nWantedBy=multi-user.target\n"
        )
    units["copytrade-paper-watchdog.service"] = (
        "[Unit]\n"
        "Description=Independent guarded paper watchdog (HALT latch, no trade)\n"
        "After=copytrade-paper-p1.service copytrade-paper-p14.service\n"
        "ConditionPathIsDirectory=" + str(release) + "\n"
        "[Service]\n"
        "User=copytrade-paper-watchdog\n"
        "Group=copytrade-paper-monitor\n"
        + common
        + "ReadOnlyPaths="
        + str(MONITOR_ROOT)
        + "\n"
        + "ReadWritePaths="
        + str(WATCHDOG_ROOT)
        + "\n"
        + "ExecStart="
        + str(python)
        + " -m copytrade_pm.pm_forward_protected_ops watchdog"
        + " --revision "
        + revision
        + " --release "
        + str(release)
        + " --p1-root "
        + str(MONITOR_ROOT / "p1")
        + " --p14-root "
        + str(MONITOR_ROOT / "p14")
        + " --state-root "
        + str(WATCHDOG_ROOT)
        + " --interval-seconds 20\n"
        + "[Install]\nWantedBy=multi-user.target\n"
    )
    return units


def stage_uninstalled_bundle(root: Path, *, revision: str) -> dict:
    """Exclusive, SHA-pinned candidate bundle; never invoke systemctl/sudo."""
    parent = root.parent
    if (
        not root.is_absolute()
        or root.is_symlink()
        or not parent.is_dir()
        or parent.is_symlink()
        or parent.stat().st_uid != os.geteuid()
        or stat.S_IMODE(parent.stat().st_mode) & 0o077
    ):
        raise ValueError("PROTECTED_UNIT_STAGE_PARENT_NOT_PRIVATE")
    texts = render_system_units(revision)
    root.mkdir(mode=0o700, exist_ok=False)
    hashes = {}
    for name, content in texts.items():
        path = root / name
        with path.open("x", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        hashes[name] = sha256(content.encode()).hexdigest()
    manifest = {
        "schema": "paper_root_systemd_candidate_v1",
        "revision": revision,
        "unit_sha256": hashes,
        "source_build_provenance_verified": False,
        "protected_os_users_created": False,
        "release_immutable_verified": False,
        "root_units_installed": False,
        "services_started": False,
        "rollback_verified": False,
        "financial_paper_authorized": False,
        "order_route": "NONE",
    }
    data = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    dest = root / "manifest.json"
    with dest.open("x", encoding="utf-8") as file:
        os.fchmod(file.fileno(), 0o600)
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return manifest


def verify_uninstalled_bundle(root: Path) -> dict:
    """Reject modified or extra units and never claim privileged installation."""
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError("PROTECTED_UNIT_BUNDLE_UNSAFE")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("PROTECTED_UNIT_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "paper_root_systemd_candidate_v1":
        raise ValueError("PROTECTED_UNIT_MANIFEST_SCHEMA_INVALID")
    expected = render_system_units(manifest["revision"])
    if (
        set(root.iterdir()) != {root / "manifest.json"} | {root / key for key in expected}
        or any(
            manifest.get(name) is not False
            for name in (
                "source_build_provenance_verified",
                "protected_os_users_created",
                "release_immutable_verified",
                "root_units_installed",
                "services_started",
                "rollback_verified",
                "financial_paper_authorized",
            )
        )
        or manifest.get("order_route") != "NONE"
    ):
        raise ValueError("PROTECTED_UNIT_BUNDLE_CONTENT_DRIFT")
    if manifest.get("unit_sha256") != {
        name: sha256(content.encode()).hexdigest() for name, content in expected.items()
    }:
        raise ValueError("PROTECTED_UNIT_MANIFEST_HASH_DRIFT")
    for name, content in expected.items():
        path = root / name
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError("PROTECTED_UNIT_FILE_UNSAFE")
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("PROTECTED_UNIT_FILE_CHANGED")
    return {
        "status": "STAGED_ONLY_NOT_INSTALLED",
        "revision": manifest["revision"],
        "unit_count": len(expected),
        "unit_sha256": manifest["unit_sha256"],
        "protected_service_attested": False,
        "paper_running": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage or inspect uninstalled protected unit candidates"
    )
    parser.add_argument("--revision", help="Exact 40-character source Git SHA for staging")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        report = verify_uninstalled_bundle(args.out)
    elif args.revision:
        report = stage_uninstalled_bundle(args.out, revision=args.revision)
    else:
        parser.error("--revision is required without --verify")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
