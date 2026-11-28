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
import time
from typing import Any, Iterator

from .pm_appliance_config import ApplianceConfig, load_config, verify_config

ROOT = Path(__file__).resolve().parents[2]
TARGET = "copytrade-pm.target"
ROLES = ("source", "paper", "quotes")
SERVICES = tuple(f"copytrade-pm-{role}.service" for role in ROLES)
SOURCE_ALIAS = "copytrade-cwsa-5m-source-chapter2.service"


def _command(argv: list[str], *, cwd: Path | None = None, timeout: int = 30) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
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
    working = _unit_path(checkout)
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
        alias = directory / SOURCE_ALIAS
        source_unit = directory / "copytrade-pm-source.service"
        if (alias.exists() or alias.is_symlink()) and (
            not alias.is_symlink() or alias.resolve() != source_unit
        ):
            raise ValueError("APPLIANCE_LEGACY_SOURCE_UNIT_NOT_RETIRED")
        if any((directory / name).is_symlink() for name in changes):
            raise ValueError("APPLIANCE_UNIT_SYMLINK_CONFLICT")
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
        ]
    )
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def status(config: ApplianceConfig, *, checkout: Path = ROOT) -> dict[str, Any]:
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
                receipt = json.loads((config.root / "runtime" / f"{role}.json").read_text())
                if (
                    receipt["pid"] != pid
                    or receipt["revision"] != sha
                    or receipt["config_sha256"] != config.sha256
                    or receipt.get("phase") != "READY"
                ):
                    blockers.append("WORKER_RECEIPT_DRIFT:" + role)
            except OSError, ValueError, KeyError:
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
                    "SELECT h.stream,o.checkpoint_ms,o.outcome FROM cwsa_heads h "
                    "LEFT JOIN cwsa_outcomes o ON o.stream=h.stream AND o.checkpoint_ms="
                    "(SELECT MAX(x.checkpoint_ms) FROM cwsa_outcomes x WHERE x.stream=h.stream)"
                ).fetchall()
            oldest = min((r[1] or 0 for r in rows), default=0)
            kinds: dict[str, int] = {}
            for _, _, outcome in rows:
                kind = json.loads(outcome)["kind"] if outcome else "UNKNOWN"
                kinds[kind] = kinds.get(kind, 0) + 1
            expected = len(json.loads(config.path(item["checkpoint_config"]).read_text())["scopes"])
            sources[name] = {
                "scopes": len(rows),
                "expected_scopes": expected,
                "latest_kinds": kinds,
                "oldest_scope_checkpoint_ms": oldest,
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
                    "SELECT known_at FROM market_quote_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1",
                    (instrument,),
                ).fetchone()
                age = (
                    now_ms - int(datetime.fromisoformat(row[0]).timestamp() * 1000) if row else None
                )
                quotes[instrument] = {"age_ms": age}
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
                    row = db.execute(
                        "SELECT cursor,manifest FROM runs WHERE run_id=?", (portfolio["folder"],)
                    ).fetchone()
                if row is None:
                    raise ValueError("RUN_MISSING")
                owners[pid] = {
                    "financial_cursor": row[0],
                    "account_id": json.loads(row[1])["account_id"],
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
            "import sys; from pathlib import Path; "
            "from copytrade_pm.pm_appliance import reconcile; "
            "from copytrade_pm.pm_appliance_config import load_config; "
            "reconcile(load_config(Path(sys.argv[1])), checkout=Path(sys.argv[2]), apply=True)",
            str(config.root),
            str(checkout),
        ],
        cwd=checkout,
        timeout=120,
    )
    _command(["systemctl", "--user", "restart", TARGET], timeout=2800)
    if any(_unit_state(unit).get("ActiveState") != "active" for unit in SERVICES):
        raise RuntimeError("APPLIANCE_WORKER_START_FAILED")
    result: dict[str, Any] = json.loads(
        _command(
            [
                str(checkout / ".venv/bin/python"),
                "-I",
                "-m",
                "copytrade_pm.pm_operations",
                "appliance",
                "status",
                "--state-root",
                str(config.root),
            ],
            cwd=checkout,
        )
    )
    return result


def update(
    config: ApplianceConfig, candidate: Path, receipt: Path, *, checkout: Path = ROOT, apply: bool
) -> dict[str, Any]:
    from .pm_ci_receipt import validate_receipt

    candidate = candidate.expanduser().resolve()
    _clean(checkout)
    _clean(candidate)
    target = revision(candidate)
    errors = validate_receipt(receipt, candidate, target)
    if errors:
        raise ValueError("APPLIANCE_CANDIDATE_UNVERIFIED:" + ",".join(errors))
    _command(["git", "merge-base", "--is-ancestor", target, "origin/main"], cwd=checkout)
    before = revision(checkout)
    _command(["git", "merge-base", "--is-ancestor", before, target], cwd=checkout)
    verify_config(config)
    if not apply:
        return {"state": "DRY_RUN", "from": before, "to": target}
    _command(["systemctl", "--user", "stop", TARGET], timeout=1000)
    try:
        _command(["git", "merge", "--ff-only", target], cwd=checkout)
        _command(
            [
                "uv",
                "sync",
                "--frozen",
                "--no-dev",
                "--extra",
                "market",
                "--extra",
                "market-stream",
            ],
            cwd=checkout,
            timeout=240,
        )
        after = _start(config, checkout=checkout)
    except Exception as exc:
        # Roll back software only. Owner journals and their monotonically
        # committed effects are never restored from a pre-update snapshot.
        _command(["systemctl", "--user", "stop", TARGET], timeout=1000)
        _command(["git", "switch", "--detach", before], cwd=checkout)
        _command(
            [
                "uv",
                "sync",
                "--frozen",
                "--no-dev",
                "--extra",
                "market",
                "--extra",
                "market-stream",
            ],
            cwd=checkout,
            timeout=240,
        )
        _start(config, checkout=checkout)
        _private_json(
            config.root / "runtime" / "update.json",
            {
                "state": "ROLLED_BACK",
                "from": before,
                "candidate": target,
                "reason": type(exc).__name__,
            },
        )
        raise RuntimeError("APPLIANCE_UPDATE_ROLLED_BACK") from exc
    result = {"state": "UPDATED", "from": before, "to": target, "runtime": after}
    _private_json(config.root / "runtime" / "update.json", result)
    return result


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
                        payload = _start(config, checkout=ROOT) if args.apply else reconcile(config)
                    elif args.verb == "update":
                        payload = update(config, args.candidate, args.receipt, apply=args.apply)
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
