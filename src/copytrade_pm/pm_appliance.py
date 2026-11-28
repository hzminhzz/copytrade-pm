"""Thin operations over git, the frozen uv environment and existing systemd.

No broker client, signing key, worker-specific release or supervisory daemon
belongs here. Financial and source owners recover their own durable journals.
"""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import UTC, datetime
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
import time
from typing import Any, Iterator

from .pm_appliance_config import ApplianceConfig, load_config, verify_config

ROOT = Path(__file__).resolve().parents[2]
TARGET = "copytrade-pm.target"
ROLES = ("source", "paper", "quotes")
SERVICES = tuple(f"copytrade-pm-{role}.service" for role in ROLES)
SOURCE_ALIAS = "copytrade-cwsa-5m-source-chapter2.service"


def _command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    env_overrides: dict[str, str] | None = None,
) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(env_overrides or {})
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        # Commands use explicit public operations, never keys or broker arguments.
        raise RuntimeError(f"APPLIANCE_COMMAND_FAILED:{argv[0]}:{result.stderr[-800:]}")
    return result.stdout.strip()


def revision(root: Path = ROOT) -> str:
    return _command(["git", "rev-parse", "HEAD"], cwd=root)


def _clean(root: Path) -> None:
    if _command(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root):
        raise ValueError("APPLIANCE_CHECKOUT_DIRTY")


def _private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("APPLIANCE_RECEIPT_SYMLINK")
    with temporary.open("w") as out:
        os.chmod(temporary, 0o600)
        json.dump(value, out, sort_keys=True, indent=2)
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(path)


@contextmanager
def operation_lock(root: Path) -> Iterator[None]:
    directory = root / "runtime"
    directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory / "operation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("APPLIANCE_OPERATION_IN_PROGRESS") from exc
        yield
    finally:
        os.close(fd)


def _unit_path(path: Path) -> str:
    text = str(path)
    if any(c in text for c in ("\n", "\r", "%", '"', "\\")):
        raise ValueError("APPLIANCE_UNIT_PATH_UNSUPPORTED")
    return '"' + text + '"'


def render_units(config: ApplianceConfig, *, checkout: Path, sha: str) -> dict[str, str]:
    python = _unit_path(checkout / ".venv/bin/python")
    # WorkingDirectory takes a literal path, unlike the quoted ExecStart arguments.
    working = str(checkout)
    state = _unit_path(config.root)
    units = {}
    for role in (*ROLES, "health"):
        oneshot = role == "health"
        unit = f"copytrade-pm-{role}.service"
        after = "network-online.target"
        if role == "paper":
            after += " copytrade-pm-source.service copytrade-pm-quotes.service"
        units[unit] = (
            "[Unit]\nDescription=Copytrade appliance " + role + " (NO BROKER)\n"
            f"PartOf={TARGET}\nAfter={after}\n\n[Service]\n"
            f"Type={'oneshot' if oneshot else 'notify'}\nUMask=0077\n"
            f"WorkingDirectory={working}\n"
            f"Environment=COPYTRADE_RELEASE_SHA={sha}\n"
            "Environment=PYTHONDONTWRITEBYTECODE=1\n"
            f"ExecStart={python} -m copytrade_pm.pm_operations appliance run {role} --state-root {state} --apply\n"
            + (
                "TimeoutStartSec=3600\n"
                if oneshot
                else "NotifyAccess=main\nTimeoutStartSec=900\nRestart=on-failure\nRestartSec=10\n"
            )
            + f"TimeoutStopSec={900 if role == 'paper' else 90}\n"
            + "NoNewPrivileges=true\nPrivateTmp=true\n"
            "MemoryMax=2G\nTasksMax=128\n\n[Install]\n"
            + ("" if oneshot else f"WantedBy={TARGET}\n")
            + (f"Alias={SOURCE_ALIAS}\n" if role == "source" else "")
        )
    units["copytrade-pm-health.timer"] = (
        f"[Unit]\nDescription=Daily Copytrade wallet health\nPartOf={TARGET}\n\n"
        f"[Timer]\nOnCalendar={config.health['calendar']}\nPersistent=true\n"
        "RandomizedDelaySec=120\nUnit=copytrade-pm-health.service\n\n"
        f"[Install]\nWantedBy={TARGET}\n"
    )
    units[TARGET] = (
        "[Unit]\nDescription=Single-owner Copytrade appliance\n"
        "Wants=" + " ".join((*SERVICES, "copytrade-pm-health.timer")) + "\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    return units


def _check_unit_destinations(directory: Path, units: dict[str, str]) -> None:
    alias = directory / SOURCE_ALIAS
    source_unit = directory / "copytrade-pm-source.service"
    if (alias.exists() or alias.is_symlink()) and (
        not alias.is_symlink() or alias.resolve() != source_unit
    ):
        raise ValueError("APPLIANCE_LEGACY_SOURCE_UNIT_NOT_RETIRED")
    if any((directory / name).is_symlink() for name in units):
        raise ValueError("APPLIANCE_UNIT_SYMLINK_CONFLICT")


def _verify_units(
    units: dict[str, str], *, config: ApplianceConfig, checkout: Path, sha: str
) -> None:
    if set(units) != {
        *SERVICES,
        TARGET,
        "copytrade-pm-health.service",
        "copytrade-pm-health.timer",
    }:
        raise ValueError("APPLIANCE_UNIT_SET_MISMATCH")
    # Native parsing alone accepts a syntactically valid but wrong command.
    for role in (*ROLES, "health"):
        lines = units[f"copytrade-pm-{role}.service"].splitlines()
        expected = {
            f"WorkingDirectory={checkout}",
            f"Environment=COPYTRADE_RELEASE_SHA={sha}",
            f"PartOf={TARGET}",
            f"Type={'oneshot' if role == 'health' else 'notify'}",
            f"ExecStart={_unit_path(checkout / '.venv/bin/python')} -m copytrade_pm.pm_operations "
            f"appliance run {role} --state-root {_unit_path(config.root)} --apply",
        }
        critical = (
            "WorkingDirectory=",
            "Environment=",
            "EnvironmentFile=",
            "PartOf=",
            "Type=",
            "Exec",
        )
        actual = [line for line in lines if line.startswith(critical)]
        if sorted(actual) != sorted(expected | {"Environment=PYTHONDONTWRITEBYTECODE=1"}):
            raise ValueError("APPLIANCE_UNIT_BINDING:" + role)
    timer = units["copytrade-pm-health.timer"].splitlines()
    target = units[TARGET].splitlines()
    if (
        f"OnCalendar={config.health['calendar']}" not in timer
        or f"PartOf={TARGET}" not in timer
        or "Unit=copytrade-pm-health.service" not in timer
        or [line for line in target if line.startswith(("Wants=", "Requires="))]
        != ["Wants=" + " ".join((*SERVICES, "copytrade-pm-health.timer"))]
    ):
        raise ValueError("APPLIANCE_UNIT_LIFECYCLE_BINDING")
    _check_unit_destinations(Path.home() / ".config/systemd/user", units)
    with TemporaryDirectory(prefix="copytrade-unit-preflight-") as directory:
        paths = []
        for name, content in units.items():
            path = Path(directory) / name
            path.write_text(content)
            paths.append(str(path))
        _command(["systemd-analyze", "--user", "verify", *paths], timeout=60)


def reconcile(
    config: ApplianceConfig, *, checkout: Path = ROOT, apply: bool = False
) -> dict[str, Any]:
    verified = verify_config(config)
    sha = revision(checkout)
    units = render_units(config, checkout=checkout, sha=sha)
    directory = Path.home() / ".config/systemd/user"
    changes = [
        name
        for name, content in units.items()
        if not (directory / name).is_file() or (directory / name).read_text() != content
    ]
    if apply:
        _clean(checkout)
        _verify_units(units, config=config, checkout=checkout, sha=sha)
        directory.mkdir(parents=True, exist_ok=True)
        for name in changes:
            path = directory / name
            if path.is_symlink():
                raise ValueError("APPLIANCE_UNIT_SYMLINK_CONFLICT")
            if path.is_file():
                backup = (
                    config.root
                    / "backups"
                    / "appliance-units"
                    / sha256(path.read_bytes()).hexdigest()
                    / name
                )
                if not backup.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    backup.write_bytes(path.read_bytes())
                    backup.chmod(0o600)
            path.write_text(units[name])
            path.chmod(0o600)
        _command(["systemctl", "--user", "daemon-reload"])
        _command(["systemctl", "--user", "enable", TARGET, "copytrade-pm-source.service"])
    return {
        **verified,
        "state": "RECONCILED" if apply else "DRY_RUN",
        "revision": sha,
        "changed_units": changes,
    }


def _unit_state(name: str) -> dict[str, str]:
    raw = _command(
        [
            "systemctl",
            "--user",
            "show",
            name,
            "--no-pager",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "MainPID",
            "-p",
            "Result",
            "-p",
            "WorkingDirectory",
            "-p",
            "FragmentPath",
            "-p",
            "DropInPaths",
            "-p",
            "NeedDaemonReload",
        ]
    )
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def status(config: ApplianceConfig, *, checkout: Path = ROOT) -> dict[str, Any]:
    from .pm_cwsa_chapter2_release import FinanceScan
    from .roster.store import RosterStore

    sha = revision(checkout)
    blockers = []
    try:
        _clean(checkout)
    except ValueError:
        blockers.append("APPLIANCE_CHECKOUT_DIRTY")
    workers = {}
    for role, name in zip(ROLES, SERVICES, strict=True):
        state = _unit_state(name)
        pid = int(state.get("MainPID", "0"))
        state["running_revision"] = "UNKNOWN"
        if state.get("DropInPaths") or state.get("NeedDaemonReload") == "yes":
            blockers.append("WORKER_UNIT_DRIFT:" + role)
        if state.get("ActiveState") != "active" or pid < 1:
            blockers.append("WORKER_NOT_RUNNING:" + role)
        else:
            try:
                cwd = Path(f"/proc/{pid}/cwd").resolve(strict=True)
                env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
                pin = next(
                    (
                        v.split(b"=", 1)[1].decode()
                        for v in env
                        if v.startswith(b"COPYTRADE_RELEASE_SHA=")
                    ),
                    "",
                )
                state["running_revision"] = pin or "UNKNOWN"
                if cwd != checkout.resolve() or pin != sha:
                    blockers.append("WORKER_REVISION_DRIFT:" + role)
                executable = checkout / ".venv/bin/python"
                argv = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\x00").split(b"\x00")
                expected_argv = [
                    str(executable),
                    "-m",
                    "copytrade_pm.pm_operations",
                    "appliance",
                    "run",
                    role,
                    "--state-root",
                    str(config.root),
                    "--apply",
                ]
                if (
                    Path(f"/proc/{pid}/exe").resolve(strict=True) != executable.resolve(strict=True)
                    or argv != [os.fsencode(arg) for arg in expected_argv]
                    or state.get("WorkingDirectory") != str(checkout)
                ):
                    blockers.append("WORKER_EXECUTABLE_DRIFT:" + role)
                receipt = json.loads((config.root / "runtime" / f"{role}.json").read_text())
                if (
                    receipt["pid"] != pid
                    or receipt["revision"] != sha
                    or receipt["config_sha256"] != config.sha256
                    or receipt.get("phase") != "READY"
                    or not receipt.get("ready_at")
                ):
                    blockers.append("WORKER_RECEIPT_DRIFT:" + role)
                else:
                    state["ready_at"] = receipt["ready_at"]
            except OSError, ValueError, KeyError, TypeError:
                blockers.append("WORKER_IDENTITY_UNKNOWN:" + role)
        workers[role] = state
    sources = {}
    now_ms = time.time_ns() // 1_000_000
    for name, item in config.sources.items():
        path = config.path(item["state"]) / "paper-events.sqlite3"
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                # Independent scopes can fail while their neighbouring sources advance.
                rows = db.execute(
                    "SELECT h.stream,o.checkpoint_ms,o.outcome,h.state,h.head FROM cwsa_heads h "
                    "LEFT JOIN cwsa_outcomes o ON o.stream=h.stream AND o.checkpoint_ms="
                    "(SELECT MAX(x.checkpoint_ms) FROM cwsa_outcomes x WHERE x.stream=h.stream)"
                ).fetchall()
            oldest = min((r[1] or 0 for r in rows), default=0)
            kinds: dict[str, int] = {}
            scope_kinds = {}
            for stream, _, outcome, _, _ in rows:
                kind = json.loads(outcome)["kind"] if outcome else "UNKNOWN"
                scope_kinds[stream] = kind
                kinds[kind] = kinds.get(kind, 0) + 1
            expected = len(json.loads(config.path(item["checkpoint_config"]).read_text())["scopes"])
            sources[name] = {
                "scopes": len(rows),
                "expected_scopes": expected,
                "latest_kinds": kinds,
                "scope_kinds": scope_kinds,
                "oldest_scope_checkpoint_ms": oldest,
                "scope_checkpoints": {row[0]: row[1] or 0 for row in rows},
                "scope_heads": {row[0]: [json.loads(row[3])["sequence"], row[4]] for row in rows},
                "age_ms": now_ms - oldest,
            }
            if len(rows) != expected:
                blockers.append("SOURCE_SCOPE_MISMATCH:" + name)
            if not rows or not 0 <= now_ms - oldest <= 600_000:
                blockers.append("SOURCE_STALE:" + name)
            if set(kinds) - {"BASELINE", "RECOVERY_BASELINE", "CHANGED", "UNCHANGED"}:
                blockers.append("SOURCE_COVERAGE_GAP:" + name)
        except sqlite3.Error, ValueError, KeyError:
            sources[name] = {"state": "UNKNOWN"}
            blockers.append("SOURCE_UNAVAILABLE:" + name)
    quotes = {}
    quote_path = config.path(config.quotes["state"]) / "paper-events.sqlite3"
    try:
        with closing(sqlite3.connect(quote_path.as_uri() + "?mode=ro", uri=True)) as db:
            for instrument in config.quotes["instruments"]:
                row = db.execute(
                    "SELECT known_at,seq,chain_sha FROM market_quote_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1",
                    (instrument,),
                ).fetchone()
                age = (
                    now_ms - int(datetime.fromisoformat(row[0]).timestamp() * 1000) if row else None
                )
                quotes[instrument] = {
                    "age_ms": age,
                    "cursor": row[1] if row else 0,
                    "head_sha": row[2] if row else None,
                }
                if age is None or not 0 <= age <= 60_000:
                    blockers.append("QUOTE_STALE:" + instrument)
    except sqlite3.Error, ValueError:
        blockers.append("QUOTE_JOURNAL_UNAVAILABLE")
    papers = {}
    for name, item in config.papers.items():
        owners = {}
        for pid, portfolio in item["portfolios"].items():
            path = config.path(item["state"]) / portfolio["folder"] / "paper-events.sqlite3"
            try:
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                    db.execute("BEGIN")
                    row = db.execute(
                        "SELECT cursor,manifest,manifest_sha FROM runs WHERE run_id=?",
                        (portfolio["folder"],),
                    ).fetchone()
                    wave = db.execute(
                        "SELECT checkpoint_ms,receipt_sha FROM chapter2_wave_receipts ORDER BY checkpoint_ms DESC LIMIT 1"
                    ).fetchone()
                    head = db.execute(
                        "SELECT chain_sha FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1",
                        (portfolio["folder"],),
                    ).fetchone()
                    scans = {}
                    if item["approval"]:
                        scans = FinanceScan.read_heads(db)
                if row is None:
                    raise ValueError("RUN_MISSING")
                owners[pid] = {
                    "financial_cursor": row[0],
                    "account_id": json.loads(row[1])["account_id"],
                    "manifest_sha": row[2],
                    "observation_cursor": wave[0] if wave else 0,
                    "observation_head_sha": wave[1] if wave else None,
                    "financial_head_sha": head[0] if head else None,
                    "finance_scan_cursors": {key: value[0] for key, value in scans.items()},
                    "finance_scan_heads": {key: value[1] for key, value in scans.items()},
                    "configured_approval": bool(item["approval"]),
                    "order_route": "NONE",
                }
                projection = json.loads(path.with_name("status.json").read_text())
                owners[pid]["financial_admission"] = projection["financial_admission"]
                owners[pid]["admission_reason"] = projection["admission_reason"]
                if projection["admission_reason"].startswith(
                    ("PAPER_REVIEW_BLOCKED", "CWSA_SIGNED_SOURCE_STREAM_MISSING")
                ):
                    blockers.append("PAPER_REVIEW_REQUIRED:" + pid)
            except OSError, sqlite3.Error, ValueError, KeyError:
                owners[pid] = {"state": "UNKNOWN"}
                blockers.append("PAPER_JOURNAL_UNAVAILABLE:" + pid)
        papers[name] = owners
    with RosterStore(config.roster) as roster:
        health = roster.health()
        observed = len(roster.observation_portfolios())
    timer = _unit_state("copytrade-pm-health.timer")
    if timer.get("ActiveState") != "active":
        blockers.append("HEALTH_TIMER_NOT_RUNNING")
    health_job = _unit_state("copytrade-pm-health.service")
    if health_job.get("Result", "success") != "success":
        blockers.append("HEALTH_CAPTURE_FAILED")
    if health["database_integrity"] != "VERIFIED":
        blockers.append("ROSTER_INTEGRITY")
    return {
        "schema": "copytrade_appliance_status_v1",
        "state": "DEGRADED" if blockers else "HEALTHY",
        "observed_at": datetime.now(UTC).isoformat(),
        "revision": sha,
        "checkout": str(checkout),
        "environment": str(checkout / ".venv"),
        "dependency_lock_sha256": sha256((checkout / "uv.lock").read_bytes()).hexdigest(),
        "state_root": str(config.root),
        "config_sha256": config.sha256,
        "workers": workers,
        "sources": sources,
        "quotes": quotes,
        "papers": papers,
        "health_timer": timer,
        "health_job": health_job,
        "roster": {**health, "observation_portfolios": observed},
        "blockers": blockers,
        "trading_authorized": False,
        "scientifically_qualified": False,
        "order_route": "NONE",
    }


def _start(config: ApplianceConfig, *, checkout: Path) -> dict[str, Any]:
    # update() may have replaced the code loaded by this process. Generate
    # units with the installed interpreter while the parent holds the operation
    # lock; never render a new release with the old module still in memory.
    _command(
        [
            str(checkout / ".venv/bin/python"),
            "-I",
            "-c",
            "import sys; from pathlib import Path; import copytrade_pm; "
            "from copytrade_pm.pm_appliance import reconcile; "
            "from copytrade_pm.pm_appliance_config import load_config; "
            "root=Path(sys.argv[2]); "
            "assert Path(sys.prefix).resolve()==(root/'.venv').resolve(), 'ENVIRONMENT_BINDING'; "
            "assert Path(copytrade_pm.__file__).resolve().is_relative_to(root/'src'), 'IMPORT_BINDING'; "
            "reconcile(load_config(Path(sys.argv[1])), checkout=root, apply=True)",
            str(config.root),
            str(checkout),
        ],
        cwd=checkout,
        timeout=120,
    )
    _command(["systemctl", "--user", "restart", TARGET], timeout=2800)
    if any(_unit_state(unit).get("ActiveState") != "active" for unit in SERVICES):
        raise RuntimeError("APPLIANCE_WORKER_START_FAILED")
    # Inspect with this verifier even after a rollback to an older CLI schema.
    return status(config, checkout=checkout)


SYNC_ARGS = [
    "uv",
    "sync",
    "--frozen",
    "--offline",
    "--no-dev",
    "--extra",
    "market",
    "--extra",
    "market-stream",
]


def _sync_environment(checkout: Path, environment: Path, *, check: bool = False) -> None:
    _command(
        [*SYNC_ARGS, "--project", str(checkout)] + (["--check"] if check else []),
        cwd=checkout,
        timeout=240,
        env_overrides={"UV_PROJECT_ENVIRONMENT": str(environment)},
    )
    if not (environment / "bin/python").is_file():
        raise RuntimeError("APPLIANCE_ENVIRONMENT_MISSING:" + str(environment))


def _preflight(
    config: ApplianceConfig, checkout: Path, candidate: Path, before: str, target: str
) -> None:
    """Prepare both environments and validate candidate code before touching units."""
    if checkout.resolve() == candidate:
        raise ValueError("APPLIANCE_CANDIDATE_MUST_BE_ISOLATED")
    if (checkout / ".venv").is_symlink():
        raise ValueError("APPLIANCE_ENVIRONMENT_SYMLINK")
    # An isolated, frozen rollback build proves the old lock is actually
    # installable from the local cache, not just that the old commit exists.
    rollback_units: dict[str, str] = {}
    with TemporaryDirectory(prefix="copytrade-preflight-") as directory:
        for label, root, sha in (("rollback", checkout, before), ("candidate", candidate, target)):
            environment = Path(directory) / label
            _command(
                ["uv", "lock", "--check", "--offline", "--project", str(root)],
                cwd=root,
                timeout=120,
            )
            _sync_environment(root, environment)
            _sync_environment(root, environment, check=True)
            output = _command(
                [
                    str(environment / "bin/python"),
                    "-I",
                    "-c",
                    "import json,sys; from pathlib import Path; import copytrade_pm; "
                    "from copytrade_pm.pm_appliance import render_units,revision; "
                    "from copytrade_pm.pm_appliance_config import load_config,verify_config; "
                    "root=Path(sys.argv[1]); environment=Path(sys.argv[2]); "
                    "assert Path(sys.prefix).resolve()==environment.resolve(), 'ENVIRONMENT_BINDING'; "
                    "assert Path(copytrade_pm.__file__).resolve().is_relative_to(root/'src'), 'IMPORT_BINDING'; "
                    "assert revision(root)==sys.argv[3], 'REVISION_BINDING'; "
                    "config=load_config(Path(sys.argv[4])); verify_config(config); "
                    "assert config.sha256==sys.argv[5], 'CONFIG_DRIFT'; "
                    "print(json.dumps(render_units(config,checkout=Path(sys.argv[6]),sha=sys.argv[3])))",
                    str(root),
                    str(environment),
                    sha,
                    str(config.root),
                    config.sha256,
                    str(checkout),
                ],
                cwd=root,
                timeout=120,
            )
            units: dict[str, str] = json.loads(output)
            _verify_units(units, config=config, checkout=checkout, sha=sha)
            if label == "rollback":
                rollback_units = units
    directory = Path.home() / ".config/systemd/user"
    for name, content in rollback_units.items():
        installed = directory / name
        state = _unit_state(name)
        if (
            not installed.is_file()
            or installed.read_text() != content
            or state.get("FragmentPath") != str(installed)
            or state.get("DropInPaths")
            or state.get("NeedDaemonReload") == "yes"
        ):
            raise ValueError("APPLIANCE_ROLLBACK_UNIT_DRIFT:" + name)
    _sync_environment(checkout, checkout / ".venv", check=True)
    _command(
        [
            str(checkout / ".venv/bin/python"),
            "-I",
            "-c",
            "import sys,copytrade_pm; from pathlib import Path; root=Path(sys.argv[1]); "
            "assert Path(sys.prefix).resolve()==(root/'.venv').resolve(), 'ENVIRONMENT_BINDING'; "
            "assert Path(copytrade_pm.__file__).resolve().is_relative_to(root/'src'), 'IMPORT_BINDING'",
            str(checkout),
        ],
        cwd=checkout,
    )
    _clean(candidate)
    _clean(checkout)
    if (
        revision(candidate) != target
        or revision(checkout) != before
        or load_config(config.root).sha256 != config.sha256
    ):
        raise ValueError("APPLIANCE_PREFLIGHT_DRIFT")


def _existing_domain_blockers(baseline: dict[str, Any]) -> set[str]:
    return {
        blocker
        for blocker in baseline["blockers"]
        if blocker.startswith(("SOURCE_COVERAGE_GAP:", "PAPER_REVIEW_REQUIRED:"))
    }


def _activation_blockers(
    config: ApplianceConfig, before: dict[str, Any], after: dict[str, Any], expected_sha: str
) -> list[str]:
    """Allow existing domain gaps, never identity failures or cursor rewind."""
    tolerated = _existing_domain_blockers(before)
    persisted = tolerated & set(after["blockers"])
    problems = sorted(set(after["blockers"]) - tolerated)
    if after.get("order_route") != "NONE" or after.get("trading_authorized") is not False:
        problems.append("ACTIVATION_AUTHORITY_DRIFT")
    if after["revision"] != expected_sha or after["config_sha256"] != before["config_sha256"]:
        problems.append("ACTIVATION_REVISION_OR_CONFIG_DRIFT")
    for role in ROLES:
        worker = after["workers"][role]
        if (
            worker.get("running_revision") != expected_sha
            or worker.get("MainPID") == before["workers"][role].get("MainPID")
            or not worker.get("ready_at")
            or (before.get("observed_at") and worker["ready_at"] <= before["observed_at"])
        ):
            problems.append("ACTIVATION_WORKER_IDENTITY:" + role)
    for name, source in before["sources"].items():
        old = source.get("scope_checkpoints", {})
        new = after["sources"].get(name, {}).get("scope_checkpoints", {})
        if not old or set(old) != set(new) or any(new[key] < old[key] for key in old):
            problems.append("ACTIVATION_SOURCE_CONTINUITY:" + name)
        elif any(new[key] <= old[key] for key in old):
            problems.append("ACTIVATION_SOURCE_NOT_ADVANCING:" + name)
        good = {"BASELINE", "RECOVERY_BASELINE", "CHANGED", "UNCHANGED"}
        new_kinds = after["sources"].get(name, {}).get("scope_kinds", {})
        if any(
            kind in good and new_kinds.get(key) not in good
            for key, kind in source.get("scope_kinds", {}).items()
        ):
            problems.append("ACTIVATION_SOURCE_NEW_GAP:" + name)
    for instrument, quote in before["quotes"].items():
        old_cursor = quote.get("cursor", 0)
        new_cursor = after["quotes"].get(instrument, {}).get("cursor", 0)
        if new_cursor < old_cursor:
            problems.append("ACTIVATION_QUOTE_CONTINUITY:" + instrument)
        elif new_cursor <= old_cursor:
            problems.append("ACTIVATION_QUOTE_NOT_ADVANCING:" + instrument)
    for name, owners in before["papers"].items():
        for pid, owner in owners.items():
            new = after["papers"].get(name, {}).get(pid, {})
            if (
                not owner.get("manifest_sha")
                or new.get("manifest_sha") != owner["manifest_sha"]
                or new.get("account_id") != owner.get("account_id")
                or new.get("financial_cursor", -1) < owner["financial_cursor"]
                or new.get("observation_cursor", -1) < owner["observation_cursor"]
                or any(
                    new.get("finance_scan_cursors", {}).get(key, -1) < cursor
                    for key, cursor in owner["finance_scan_cursors"].items()
                )
                or any(
                    new.get("finance_scan_cursors", {}).get(key)
                    == owner["finance_scan_cursors"][key]
                    and new.get("finance_scan_heads", {}).get(key) != head
                    for key, head in owner.get("finance_scan_heads", {}).items()
                )
            ):
                problems.append("ACTIVATION_PAPER_CONTINUITY:" + pid)
            elif new["observation_cursor"] <= owner["observation_cursor"] and not (
                "SOURCE_COVERAGE_GAP:" + config.papers[name]["source"] in persisted
                or "PAPER_REVIEW_REQUIRED:" + pid in persisted
            ):
                problems.append("ACTIVATION_PAPER_NOT_ADVANCING:" + pid)
            if (
                new.get("configured_approval") != owner.get("configured_approval")
                or new.get("order_route") != "NONE"
                or (
                    owner.get("configured_approval") is False
                    and new.get("financial_cursor") != owner["financial_cursor"]
                )
            ):
                problems.append("ACTIVATION_PAPER_AUTHORITY_DRIFT:" + pid)
    return problems


def _verify_prefixes(config: ApplianceConfig, baseline: dict[str, Any]) -> None:
    """The prior committed head must still exist in each independent journal."""

    def require(path: Path, sql: str, params: tuple[Any, ...], expected: str) -> None:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute(sql, params).fetchone()
        if row != (expected,):
            raise RuntimeError("APPLIANCE_JOURNAL_PREFIX_CHANGED:" + path.parent.name)

    for name, source in baseline["sources"].items():
        path = config.path(config.sources[name]["state"]) / "paper-events.sqlite3"
        for stream, (sequence, head) in source["scope_heads"].items():
            require(
                path,
                "SELECT sha FROM cwsa_transitions WHERE stream=? AND seq=?",
                (stream, sequence),
                head,
            )
    path = config.path(config.quotes["state"]) / "paper-events.sqlite3"
    for instrument, quote in baseline["quotes"].items():
        if quote["cursor"]:
            require(
                path,
                "SELECT chain_sha FROM market_quote_receipts WHERE instrument=? AND seq=?",
                (instrument, quote["cursor"]),
                quote["head_sha"],
            )
    for name, owners in baseline["papers"].items():
        item = config.papers[name]
        for pid, owner in owners.items():
            folder = item["portfolios"][pid]["folder"]
            path = config.path(item["state"]) / folder / "paper-events.sqlite3"
            if owner["financial_cursor"]:
                require(
                    path,
                    "SELECT chain_sha FROM events WHERE run_id=? AND seq=?",
                    (folder, owner["financial_cursor"]),
                    owner["financial_head_sha"],
                )
            if owner["observation_cursor"]:
                require(
                    path,
                    "SELECT receipt_sha FROM chapter2_wave_receipts WHERE checkpoint_ms=?",
                    (owner["observation_cursor"],),
                    owner["observation_head_sha"],
                )


def _await_activation(
    config: ApplianceConfig,
    checkout: Path,
    baseline: dict[str, Any],
    expected_sha: str,
    observed: dict[str, Any],
    *,
    timeout: float = 660,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        if load_config(config.root).sha256 != config.sha256:
            raise RuntimeError("APPLIANCE_ACTIVATION_CONFIG_DRIFT")
        problems = _activation_blockers(config, baseline, observed, expected_sha)
        if not problems:
            _verify_prefixes(config, baseline)
            return observed
        # A broken identity or a rewind is not a transient wait for a 5m wave.
        if any("CONTINUITY:" in p or "IDENTITY:" in p or "DRIFT" in p for p in problems):
            raise RuntimeError("APPLIANCE_ACTIVATION_FAILED:" + ",".join(problems))
        if time.monotonic() >= deadline:
            raise RuntimeError("APPLIANCE_ACTIVATION_FAILED:" + ",".join(problems))
        time.sleep(5)
        observed = status(config, checkout=checkout)


def update(
    config: ApplianceConfig, candidate: Path, receipt: Path, *, checkout: Path = ROOT, apply: bool
) -> dict[str, Any]:
    from .pm_ci_receipt import validate_receipt

    candidate = candidate.expanduser().resolve()
    checkout = checkout.expanduser().resolve()
    _clean(checkout)
    _clean(candidate)
    target = revision(candidate)
    errors = validate_receipt(receipt, candidate, target)
    if errors:
        raise ValueError("APPLIANCE_CANDIDATE_UNVERIFIED:" + ",".join(errors))
    _command(["git", "merge-base", "--is-ancestor", target, "origin/main"], cwd=checkout)
    before = revision(checkout)
    _command(["git", "merge-base", "--is-ancestor", before, target], cwd=checkout)
    _preflight(config, checkout, candidate, before, target)
    baseline = status(config, checkout=checkout)
    blocked = sorted(set(baseline["blockers"]) - _existing_domain_blockers(baseline))
    if blocked:
        raise ValueError("APPLIANCE_ROLLBACK_BASELINE_UNVERIFIED:" + ",".join(blocked))
    _verify_prefixes(config, baseline)
    if not apply:
        return {
            "state": "DRY_RUN",
            "from": before,
            "to": target,
            "preflight": "VERIFIED",
            "pre_existing_blockers": baseline["blockers"],
        }
    operation = {
        "from": before,
        "candidate": target,
        "pre_existing_blockers": baseline["blockers"],
        "baseline": baseline,
    }
    operation_path = config.root / "runtime" / "update.json"
    _private_json(operation_path, {**operation, "state": "ACTIVATING"})
    try:
        _command(["systemctl", "--user", "stop", TARGET], timeout=1000)
        # A worker may have committed after the pre-stop status read. Capture
        # the quiescent owners before replacing any software.
        stopped = status(config, checkout=checkout)
        continuity = [
            problem
            for problem in _activation_blockers(config, baseline, stopped, before)
            if "CONTINUITY:" in problem
        ]
        if continuity:
            raise RuntimeError("APPLIANCE_QUIESCENT_CONTINUITY:" + ",".join(continuity))
        _verify_prefixes(config, baseline)
        baseline = {**baseline, **{key: stopped[key] for key in ("sources", "quotes", "papers")}}
        operation["baseline"] = baseline
        _private_json(operation_path, {**operation, "state": "ACTIVATING"})
        _command(["git", "merge", "--ff-only", target], cwd=checkout)
        _sync_environment(checkout, checkout / ".venv")
        after = _await_activation(
            config, checkout, baseline, target, _start(config, checkout=checkout)
        )
    except Exception as exc:
        # Roll back software only. Never restore any owner journal or cursor.
        _private_json(
            operation_path, {**operation, "state": "RECOVERING", "reason": str(exc)[:1000]}
        )
        try:
            _command(["systemctl", "--user", "stop", TARGET], timeout=1000)
            # Recovery must not rewind candidate-era commits either. If their
            # journal evidence is unreadable, still restore software, but do not
            # claim verified recovery.
            recovery_baseline = baseline
            recovery_evidence_error = ""
            try:
                latest = status(config, checkout=checkout)
                continuity = [
                    problem
                    for problem in _activation_blockers(
                        config, baseline, latest, revision(checkout)
                    )
                    if "CONTINUITY:" in problem
                ]
                if continuity:
                    raise RuntimeError(",".join(continuity))
                recovery_baseline = {
                    **baseline,
                    **{key: latest[key] for key in ("sources", "quotes", "papers")},
                }
            except Exception as evidence_error:
                recovery_evidence_error = str(evidence_error)[:1000]
            _command(["git", "switch", "--detach", before], cwd=checkout)
            _sync_environment(checkout, checkout / ".venv")
            restored = _await_activation(
                config, checkout, recovery_baseline, before, _start(config, checkout=checkout)
            )
            continuity = [
                problem
                for problem in _activation_blockers(config, baseline, restored, before)
                if "CONTINUITY:" in problem
            ]
            if continuity or recovery_evidence_error:
                raise RuntimeError(
                    "APPLIANCE_RECOVERY_CONTINUITY:"
                    + ",".join(continuity)
                    + recovery_evidence_error
                )
            _verify_prefixes(config, baseline)
        except Exception as recovery_error:
            _private_json(
                operation_path,
                {
                    **operation,
                    "state": "RECOVERY_FAILED",
                    "reason": str(exc)[:1000],
                    "recovery_error": str(recovery_error)[:1000],
                },
            )
            raise RuntimeError("APPLIANCE_UPDATE_RECOVERY_FAILED") from recovery_error
        _private_json(
            operation_path,
            {**operation, "state": "ROLLED_BACK", "reason": str(exc)[:1000], "runtime": restored},
        )
        raise RuntimeError("APPLIANCE_UPDATE_ROLLED_BACK") from exc
    result = {**operation, "state": "UPDATED", "to": target, "runtime": after}
    _private_json(operation_path, result)
    return {
        "state": "UPDATED",
        "from": before,
        "to": target,
        "pre_existing_blockers": operation["pre_existing_blockers"],
        "remaining_blockers": after["blockers"],
        "receipt": str(operation_path),
        "worker_pids": {role: worker["MainPID"] for role, worker in after["workers"].items()},
    }


def recover(config: ApplianceConfig, *, checkout: Path = ROOT) -> dict[str, Any]:
    baseline = status(config, checkout=checkout)
    receipt = config.root / "runtime" / "recover.json"
    try:
        observed = _await_activation(
            config, checkout, baseline, revision(checkout), _start(config, checkout=checkout)
        )
    except Exception as exc:
        _private_json(
            receipt, {"state": "RECOVERY_FAILED", "baseline": baseline, "reason": str(exc)[:1000]}
        )
        raise RuntimeError("APPLIANCE_RECOVERY_FAILED") from exc
    _private_json(receipt, {"state": "RECOVERED", "baseline": baseline, "runtime": observed})
    return {
        "state": "RECOVERED",
        "revision": observed["revision"],
        "remaining_blockers": observed["blockers"],
        "receipt": str(receipt),
    }


def run(args: argparse.Namespace) -> int:
    try:
        root = args.state_root.expanduser().absolute()
        if args.verb == "adopt":
            from .roster.observations import import_registry

            with operation_lock(root) if args.apply else _no_lock():
                payload = import_registry(
                    args.registry_snapshot,
                    args.sha256,
                    root / "roster.sqlite",
                    at_ms=time.time_ns() // 1_000_000,
                    apply=args.apply,
                )
        else:
            config = load_config(root)
            if args.verb == "status":
                payload = status(config)
            elif args.verb == "run":
                if not args.apply:
                    payload = {**verify_config(config), "state": "DRY_RUN", "role": args.role}
                else:
                    from .pm_appliance_workers import run_worker

                    verify_config(config)
                    _clean(ROOT)
                    sha = revision()
                    expected = os.environ.get("COPYTRADE_RELEASE_SHA", sha)
                    if expected != sha:
                        raise ValueError("APPLIANCE_WORKER_REVISION_MISMATCH")
                    _private_json(
                        root / "runtime" / f"{args.role}.json",
                        {
                            "pid": os.getpid(),
                            "revision": sha,
                            "config_sha256": config.sha256,
                            "started_at": datetime.now(UTC).isoformat(),
                            "phase": "STARTING",
                        },
                    )
                    return run_worker(config, args.role, once=args.once)
            else:
                with operation_lock(root) if args.apply else _no_lock():
                    if args.verb == "reconcile":
                        payload = reconcile(config, apply=args.apply)
                    elif args.verb == "recover":
                        payload = recover(config) if args.apply else reconcile(config)
                    elif args.verb == "update":
                        payload = update(
                            config,
                            args.candidate,
                            args.receipt,
                            checkout=args.checkout or ROOT,
                            apply=args.apply,
                        )
                    else:
                        raise ValueError("APPLIANCE_UNKNOWN_OPERATION")
        print(
            json.dumps(
                {**payload, "trading_authorized": False, "order_route": "NONE"},
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "state": "BLOCKED",
                    "error": str(exc)[:1000],
                    "error_type": type(exc).__name__,
                    "trading_authorized": False,
                    "order_route": "NONE",
                },
                sort_keys=True,
            )
        )
        return 2


@contextmanager
def _no_lock() -> Iterator[None]:
    yield
