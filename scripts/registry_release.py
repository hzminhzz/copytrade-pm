"""Reversible owner-private, read-only wallet registry release controller.

The wallet registry remains independent of production tracker, source capture,
broker, paper finance, Telegram and PM03/04 services. This controller never
starts, stops or restarts their systemd units and never writes their databases.

Usage from the reviewed clean WR worktree:
    uv run --group dev python scripts/registry_release.py preview
    uv run --group dev python scripts/registry_release.py activate
    uv run --group dev python scripts/registry_release.py verify
    uv run --group dev python scripts/registry_release.py rollback

Activation stages an immutable-by-Git snapshot in an owner-private release
directory, verifies the *deployed* CLI/source hashes, backs up only the WR
database, checks restore integrity, then atomically switches a single pointer.
No timer is deployed: on-demand only until a separate review approves cadence.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile

from copytrade_pm import wallet_registry as registry

CONTROL = registry.DB.parent / "release-control"
RELEASES = CONTROL / "releases"
CURRENT = CONTROL / "current"
STATE = CONTROL / "release-state.json"
SERVICE_UNITS = (
    "copytrade-tracker.service",
    "copytrade-ensemble.service",
    "copytrade-source-abc.service",
)
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
VERIFY_FILES = (
    "src/copytrade_pm/wallet_registry.py",
    "src/copytrade_pm/wallet_registry_portfolios.py",
    "src/copytrade_pm/wallet_registry_fp_journal.py",
    "src/copytrade_pm/wallet_registry_runs.py",
    "src/copytrade_pm/wallet_registry_qualification.py",
    "docs/WALLET-REGISTRY-ACCEPTANCE-20261104.md",
    "docs/WALLET-STATUS.md",
    "pyproject.toml",
    "uv.lock",
)


def command(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(args), cwd=cwd, check=True, capture_output=True, text=True, timeout=90
    )
    return result.stdout.strip()


def _json(path: Path) -> dict:
    if not path.exists():
        return {}
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise PermissionError("untrusted release state")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release state must be a dictionary")
    return data


def _mode(path: Path, expected: int) -> None:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != expected:
        raise PermissionError("insecure private release path")


def _private_dirs(control: Path = CONTROL) -> None:
    control.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _mode(control.parent, 0o700)
    control.mkdir(mode=0o700, exist_ok=True)
    _mode(control, 0o700)
    (control / "releases").mkdir(mode=0o700, exist_ok=True)
    _mode(control / "releases", 0o700)


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def snapshot_state(repo: Path, *, enforce_clean: bool = True) -> dict:
    git_sha = command("git", "rev-parse", "HEAD", cwd=repo)
    if not GIT_SHA.fullmatch(git_sha):
        raise ValueError("missing clean source commit SHA")
    if enforce_clean and command("git", "status", "--porcelain", cwd=repo):
        raise ValueError("dirty source worktree: no release may be staged")
    tracked = set(
        part
        for part in command("git", "ls-files", "--cached", "--full-name", cwd=repo).splitlines()
        if part
    )
    missing = set(VERIFY_FILES) - tracked
    if missing:
        raise ValueError("release is missing required tracked source files")
    if any(Path(part).is_absolute() or ".." in Path(part).parts for part in tracked):
        raise ValueError("untrusted source file name")
    if any((repo / part).is_symlink() for part in tracked):
        raise ValueError("symlinks are forbidden in pinned registry release")
    return {
        "revision": git_sha,
        "files": {part: sha(repo / part) for part in sorted(tracked)},
    }


def readonly_source_health() -> dict:
    """Review currently committed inventory, without opening writable sources."""
    baseline = registry.db_status(registry.DB)
    live = registry.status(
        registry.collect(registry.ROOT, registry.ENV, Path(__file__).resolve().parents[1])
    )
    checks = (
        "research_unique",
        "owner_excluded",
        "research_owner_excluded_overlap",
        "desired",
        "subscribed",
        "research_desired_overlap",
        "research_subscribed_overlap",
    )
    if (
        any(baseline["counts"][key] != live[key] for key in checks)
        or baseline["source_shas"] != live["source_shas"]
        or baseline["freshness"] != "CURRENT"
        or baseline["counts"]["registered_paper_runs"] < 0
        or baseline["counts"]["trading_authorized"] != "NOT_ESTABLISHED"
        or baseline["counts"]["scientifically_qualified"] != "NOT_ESTABLISHED"
    ):
        raise ValueError("source drift, stale inventory, or unauthorized registry state")
    with closing(registry.connect(registry.DB, False)) as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("registry SQLite integrity failure")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("registry SQLite foreign key failure")
    return {
        "source_manifest_sha256": baseline["generation"]["manifest_sha256"],
        "research_unique": live["research_unique"],
        "owner_excluded": live["owner_excluded"],
        "desired": live["desired"],
        "subscribed": live["subscribed"],
        "sealed_portfolio_definitions": baseline["counts"]["sealed_portfolio_definitions"],
        "registered_paper_runs": baseline["counts"]["registered_paper_runs"],
        "runtime_admitted": "UNKNOWN",
        "receipt_health": "UNKNOWN",
        "scientifically_qualified": "NOT_ESTABLISHED",
        "trading_authorized": False,
    }


def services() -> dict[str, dict]:
    """Check PIDs and state before/after, not presumed worker receipt health."""
    observed = {}
    for unit in SERVICE_UNITS:
        raw = command(
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=ActiveState",
            "--property=MainPID",
        )
        lines = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        observed[unit] = {
            "active": lines.get("ActiveState", "unknown"),
            "pid": lines.get("MainPID", "0"),
        }
    return observed


def service_parity(before: dict, after: dict) -> None:
    if before != after:
        raise RuntimeError(
            "service PID/state changed during registry release; investigate separately"
        )


def staged_archive(repo: Path, dst: Path, fingerprint: dict) -> None:
    if dst.exists() or dst.is_symlink():
        check_release(dst, fingerprint)
        return
    data = subprocess.run(
        ["git", "archive", "--format=tar", fingerprint["revision"]],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=90,
    ).stdout
    if len(data) > 20_000_000:
        raise ValueError("unexpectedly large repository archive")
    dst.mkdir(mode=0o700)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for member in archive:
                name = Path(member.name)
                if (
                    name.is_absolute()
                    or ".." in name.parts
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError("unsafe Git archive entry")
                path = dst / name
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with closing(archive.extractfile(member)) as src:
                        if src is None:
                            raise ValueError("missing Git archive file")
                        path.write_bytes(src.read())
        # Verify the actual source and decision docs from Git, not the
        # mutating development checkout.
        check_release(dst, fingerprint)
    except BaseException:
        # A partial release is intentionally left fail-closed for inspection;
        # it is never pointed to by current.
        raise


def check_release(path: Path, fingerprint: dict) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ValueError("missing or linked pinned release")
    for relative, expected in fingerprint["files"].items():
        if sha(path / relative) != expected:
            raise ValueError("pinned release source SHA mismatch")
    # Running a release uses its own project docs; it cannot silently depend
    # on another worktree's copy of the portfolio documents.


def _write_json_atomic(path: Path, value: dict) -> None:
    payload = json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"
    temp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_current(target: str | None, *, control: Path = CONTROL) -> None:
    """Switch only our dedicated pointer, never a production service symlink."""
    current = control / "current"
    candidate = control / f".current.{os.getpid()}.tmp"
    if current.exists() and not current.is_symlink():
        raise ValueError("release pointer is not a symlink")
    if target is not None and not GIT_SHA.fullmatch(target):
        raise ValueError("invalid release commit")
    try:
        if target is None:
            current.unlink(missing_ok=True)
        else:
            os.symlink(f"releases/{target}", candidate)
            os.replace(candidate, current)
    finally:
        candidate.unlink(missing_ok=True)


def active_revision(control: Path = CONTROL) -> str | None:
    current = control / "current"
    if not current.is_symlink():
        return None
    destination = os.readlink(current)
    match = re.fullmatch(r"releases/([0-9a-f]{40})", destination)
    if not match:
        raise ValueError("unexpected release pointer target")
    return match.group(1)


def _installed_doctor(release: Path) -> None:
    # First create an isolated package environment from the exact pinned
    # release. No network, broker, source or tracker writes allowed.
    raw = command(
        "uv",
        "run",
        "--offline",
        "--frozen",
        "--no-dev",
        "--directory",
        str(release),
        "copytrade-wallet-registry",
        "doctor",
    )
    data = json.loads(raw)
    if not data.get("counts_match") or data.get("freshness") != "CURRENT":
        raise ValueError("pinned-release doctor did not prove source parity")
    raw = command(
        "uv",
        "run",
        "--offline",
        "--frozen",
        "--no-dev",
        "--directory",
        str(release),
        "copytrade-wallet-registry",
        "paper",
    )
    status = json.loads(raw)
    if status.get("global_running_count") != "UNKNOWN":
        raise ValueError("paper status was promoted from research metadata")


def activate(repo: Path) -> dict:
    before_services = services()
    baseline = readonly_source_health()
    pin = snapshot_state(repo)
    _private_dirs()
    prior = active_revision()
    if prior == pin["revision"]:
        check_release(RELEASES / pin["revision"], pin)
        _installed_doctor(RELEASES / pin["revision"])
        service_parity(before_services, services())
        return {"result": "ALREADY_ACTIVE", "revision": prior, "source": baseline}
    stage = RELEASES / pin["revision"]
    staged_archive(repo, stage, pin)
    _installed_doctor(stage)

    # Immutable snapshot backup of ONLY our registry; positive source hash
    # and restored SQLite integrity are a hard prerequisite for pointer change.
    backup = CONTROL / (
        f"preactivation-{pin['revision']}-{baseline['source_manifest_sha256'][:16]}.sqlite"
    )
    if not backup.exists():
        registry.backup(registry.DB, backup)
    with closing(registry.connect(backup, False)) as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("preactivation backup failed restore audit")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("preactivation backup has invalid foreign keys")
    service_parity(before_services, services())
    try:
        atomic_current(pin["revision"])
        _installed_doctor(stage)
        service_parity(before_services, services())
        _write_json_atomic(
            STATE,
            {
                "current": pin["revision"],
                "previous": prior,
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "source_manifest_sha256": baseline["source_manifest_sha256"],
                "files": pin["files"],
                "mode": "ON_DEMAND_READ_ONLY_NO_TIMER",
            },
        )
    except BaseException:
        # Restore only the pointer owned by the new read-only registry.
        # Never restart, stop or modify any external service or source DB.
        atomic_current(prior)
        raise
    return {
        "result": "READ_ONLY_RELEASE_ACTIVE",
        "revision": pin["revision"],
        "previous": prior,
        "source": baseline,
        "legacy_services_unchanged": True,
        "registry_timer": "NOT_INSTALLED",
    }


def verify() -> dict:
    rev = active_revision()
    if rev is None:
        return {"result": "NO_RELEASE_POINTER"}
    state = _json(STATE)
    if state.get("current") != rev:
        raise ValueError("active release state/pointer mismatch")
    check_release(RELEASES / rev, {"files": state["files"]})
    _installed_doctor(RELEASES / rev)
    return {
        "result": "ACTIVE_READ_ONLY_VERIFIED",
        "revision": rev,
        "source": readonly_source_health(),
        "registry_timer": "NOT_INSTALLED",
    }


def rollback() -> dict:
    _private_dirs()
    before_services = services()
    state = _json(STATE)
    current = active_revision()
    if not current or state.get("current") != current:
        raise ValueError("no matching active release to roll back")
    prior = state.get("previous")
    if prior is not None:
        if not GIT_SHA.fullmatch(prior):
            raise ValueError("invalid rollback target")
        earlier = _json(STATE)  # existing control metadata
        if not (RELEASES / prior).is_dir():
            raise ValueError("previous release missing")
        # The earlier pinned release may be stale; rollback is still a
        # metadata pointer operation. Do not alter any source or registry DB.
        del earlier
    atomic_current(prior)
    _write_json_atomic(
        STATE,
        {
            "current": prior,
            "previous": None,
            "rolled_back_from": current,
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "mode": "ON_DEMAND_READ_ONLY_NO_TIMER",
        },
    )
    service_parity(before_services, services())
    return {
        "result": "POINTER_ROLLED_BACK",
        "previous_active": current,
        "now_active": prior,
        "registry_db_untouched": True,
        "legacy_services_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "activate", "verify", "rollback"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.action == "preview":
        result = {
            "result": "PREVIEW",
            "revision": snapshot_state(repo, enforce_clean=False)["revision"],
            "worktree_clean": not bool(command("git", "status", "--porcelain", cwd=repo)),
            "source": readonly_source_health(),
            "active_revision": active_revision(),
            "services": services(),
        }
    elif args.action == "activate":
        result = activate(repo)
    elif args.action == "verify":
        result = verify()
    else:
        result = rollback()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
