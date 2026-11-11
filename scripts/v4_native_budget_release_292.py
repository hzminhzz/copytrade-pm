"""Operator-gated, reversible 0911 native-WS-budget SHADOW release (#292).

One explicit immutable source SHA is copied from tracked Git blobs into a new
owner-private release directory, dependencies are pinned to uv.lock, and three
stopped 0911 unit overrides are additively installed. Never touches original
SQLite, 0811 services, finance state, broker or Guardian. No implicit startup.

Phases: audit -> stage -> apply -> daemon-reload (inside apply) -> operator
starts source -> independent evidence gate -> operator starts consumers.
Rollback requires ALL 0911 units stopped and removes only owned 95 dropins.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path("/home/quant/.local/share/copytrade/releases")
UNIT_ROOT = Path.home() / ".config/systemd/user"
DEPLOYED_SOURCE_MARKER = "# V4_SQLITE_292_PINNED_RELEASE dea283570ce6558c07d516b0342983992e75f856"
MARKER = "# V4_NATIVE_WS_BUDGET_292_PINNED_RELEASE "
OLD_OVERRIDE = "90-v4-sqlite-292.conf"
NEW_OVERRIDE = "95-v4-native-budget-292.conf"
SOURCE = "copytrade-v4-sixteen-source-0911.service"
PAPER = "copytrade-v4-sixteen-paper-0911.service"
PYDNATIVE = "copytrade-pydnative-v4-sixteen-paper-0911.service"
UNITS = (SOURCE, PAPER, PYDNATIVE)
USER_BUDGET = 7
ROTATION_SECONDS = 420
SHAFULL = re.compile(r"[0-9a-f]{40}")
SOURCE_MODULE = "-m copytrade_pm.pm_v4_selected_positions"
PAPER_MODULE = "-m copytrade_pm.pm_v4_sixteen_paper"


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, text=True, timeout=120, **kwargs)


def _release(expected_sha: str) -> Path:
    if not SHAFULL.fullmatch(expected_sha):
        raise ValueError("V4_BUDGET_RELEASE_PIN_INVALID")
    return ROOT / ("v4-native-budget-" + expected_sha[:12])


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _status(unit: str) -> dict:
    out = _run(
        ["systemctl", "--user", "show", unit, "-p", "ActiveState", "-p", "MainPID"],
        capture_output=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def _quiescence(*, require_0811: bool = True) -> dict:
    units = {unit: _status(unit) for unit in UNITS}
    if any(
        row["ActiveState"] not in ("inactive", "failed") or row["MainPID"] != "0"
        for row in units.values()
    ):
        raise ValueError("V4_BUDGET_0911_REQUIRES_STOPPED_SOURCE_AND_CONSUMERS")
    if require_0811:
        upstream = _status("copytrade-v4-selected-positions-0811.service")
        if upstream["ActiveState"] != "active" or int(upstream["MainPID"]) <= 0:
            raise ValueError("V4_BUDGET_0811_UPSTREAM_NOT_HEALTHY")
    return units


def _verify_release(path: Path, expected_sha: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("V4_BUDGET_RELEASE_ROOT_INVALID")
    pin = path / "source.sha"
    if pin.is_symlink() or not pin.is_file() or pin.read_text().strip() != expected_sha:
        raise ValueError("V4_BUDGET_RELEASE_PIN_MISMATCH")
    python = path / ".venv/bin/python"
    # uv creates a symlink to its pinned Python interpreter in virtualenvs.
    # The containing release is owner-only and the executable is verified by
    # importing both source/paper modules before any systemd activation.
    if not python.is_file():
        raise ValueError("V4_BUDGET_RELEASE_VENV_MISSING")
    _run(
        [
            str(python),
            "-c",
            "import copytrade_pm.pm_v4_selected_positions;"
            "import copytrade_pm.pm_v4_sixteen_paper;"
            "import websockets",
        ],
        capture_output=True,
    )


def _source_git_sha() -> str:
    sha = _run(["git", "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if _run(["git", "status", "--porcelain"], capture_output=True).stdout.strip():
        raise ValueError("V4_BUDGET_GIT_TREE_DIRTY")
    return sha


def stage(expected_sha: str) -> dict:
    path = _release(expected_sha)
    if _source_git_sha() != expected_sha:
        raise ValueError("V4_BUDGET_GIT_SHA_MISMATCH")
    if path.exists() or path.is_symlink() or not ROOT.is_dir():
        raise FileExistsError("V4_BUDGET_RELEASE_NOT_NEW")
    entries = _run(["git", "ls-files", "-z"], capture_output=True).stdout.split("\0")
    path.mkdir(mode=0o700)
    for entry in entries:
        if not entry:
            continue
        relative = Path(entry)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("V4_BUDGET_UNSAFE_TRACKED_PATH")
        source = Path.cwd() / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError("V4_BUDGET_UNSAFE_TRACKED_FILE")
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Install locked dependencies in the staged, source-SHA-pinned copy,
    # never in running source/paper release or user-configured Python.
    subprocess.run(
        ["uv", "sync", "--frozen", "--no-dev", "--extra", "source", "--extra", "market"],
        check=True,
        cwd=path,
        timeout=240,
        capture_output=True,
    )
    pin = path / "source.sha"
    fd = os.open(pin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write((expected_sha + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    _verify_release(path, expected_sha)
    return {
        "release_sha": expected_sha,
        "path": str(path),
        "phase": "STAGED_ONLY",
        "service_mutation": False,
        "trading_authorized": False,
    }


def _old_command(unit: str) -> tuple[str, str]:
    source = UNIT_ROOT / (unit + ".d") / OLD_OVERRIDE
    if source.is_symlink() or not source.is_file():
        raise ValueError("V4_BUDGET_EXISTING_292_OVERRIDE_REQUIRED")
    raw = source.read_text()
    if not raw.startswith(DEPLOYED_SOURCE_MARKER + "\n"):
        raise ValueError("V4_BUDGET_BASELINE_RELEASE_PIN_MISMATCH")
    starts = [
        line[len("ExecStart=") :] for line in raw.splitlines() if line.startswith("ExecStart=")
    ]
    starts = [x for x in starts if x]
    if len(starts) != 1:
        raise ValueError("V4_BUDGET_EXACT_OLD_COMMAND_REQUIRED")
    command = starts[0]
    module = SOURCE_MODULE if unit == SOURCE else PAPER_MODULE
    if (
        command.count(module) != 1
        or " --compact-evidence" in command
        or "broker" in command.lower()
    ):
        raise ValueError("V4_BUDGET_OLD_UNIT_NOT_READONLY_RESEARCH")
    return command, _sha(raw.encode())


def planned_units(expected_sha: str) -> dict:
    path = _release(expected_sha)
    _verify_release(path, expected_sha)
    plans = {}
    for unit in UNITS:
        command, old_sha = _old_command(unit)
        module = SOURCE_MODULE if unit == SOURCE else PAPER_MODULE
        suffix = command.split(module, 1)[1]
        new = str(path / ".venv/bin/python") + " " + module + suffix
        if unit == SOURCE:
            new += (
                f" --native-user-budget {USER_BUDGET} --native-rotation-seconds {ROTATION_SECONDS}"
            )
        if " --compact-evidence" in new or "broker" in new.lower():
            raise ValueError("V4_BUDGET_BROKER_AND_V2_PROHIBITED")
        destination = UNIT_ROOT / (unit + ".d") / NEW_OVERRIDE
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("V4_BUDGET_ADDITIVE_OVERRIDE_ALREADY_PRESENT")
        raw = (
            MARKER + expected_sha + "\n"
            "[Service]\nExecStart=\nExecStart=" + new + "\nWorkingDirectory=" + str(path) + "\n"
        ).encode()
        plans[unit] = {
            "destination": destination,
            "content": raw,
            "baseline_sha256": old_sha,
            "additive_sha256": _sha(raw),
        }
    return plans


def _publish_exclusive(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ValueError("V4_BUDGET_SYMLINK_DESTINATION")
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("V4_BUDGET_OVERRIDE_DIRECTORY_INVALID")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(content)
        out.flush()
        os.fsync(out.fileno())


def apply(expected_sha: str) -> dict:
    status = _quiescence()
    plans = planned_units(expected_sha)
    written = []
    try:
        for unit in UNITS:
            record = plans[unit]
            _publish_exclusive(record["destination"], record["content"])
            written.append(record["destination"])
        _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        raise
    return {
        "phase": "PINNED_NO_START",
        "release_sha": expected_sha,
        "unit_count": 3,
        "prechange_state": status,
        "additive_override_sha256": {unit: plans[unit]["additive_sha256"] for unit in UNITS},
        "broker_route": "NONE",
        "trading_authorized": False,
        "no_service_started": True,
    }


def rollback(expected_sha: str) -> dict:
    _quiescence(require_0811=False)
    removed = []
    for unit in UNITS:
        path = UNIT_ROOT / (unit + ".d") / NEW_OVERRIDE
        if not path.exists():
            continue
        raw = path.read_bytes()
        if not raw.startswith((MARKER + expected_sha + "\n").encode()):
            raise ValueError("V4_BUDGET_UNOWNED_OVERRIDE_CANNOT_REMOVE")
        removed.append(path)
    for path in removed:
        path.unlink()
    _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return {
        "phase": "ROLLBACK_OVERRIDES_ONLY",
        "removed_units": len(removed),
        "source_and_finance_journals_unchanged": True,
    }


PAPER_OVERRIDE = "96-v4-paper-cursor-292.conf"
PAPER_MARKER = "# V4_PAPER_CURSOR_292_PINNED_RELEASE "
SOURCE_PARENT_SHA = "2598b25f55b7d542e351ed6fbcd4b5c233657a30"


def _running_cmdline(pid: int) -> bytes:
    return Path(f"/proc/{pid}/cmdline").read_bytes()


def _paper_quiescence(*, check_source: bool) -> dict:
    states = {unit: _status(unit) for unit in (PAPER, PYDNATIVE)}
    if any(
        row["ActiveState"] not in ("inactive", "failed") or row["MainPID"] != "0"
        for row in states.values()
    ):
        raise ValueError("V4_PAPER_CURSOR_REQUIRES_STOPPED_PAPER_READERS")
    if check_source:
        source = _status(SOURCE)
        old = UNIT_ROOT / (SOURCE + ".d") / NEW_OVERRIDE
        if (
            source["ActiveState"] != "active"
            or int(source["MainPID"]) <= 0
            or not old.is_file()
            or old.is_symlink()
            or not old.read_text().startswith(MARKER + SOURCE_PARENT_SHA + "\n")
        ):
            raise ValueError("V4_PAPER_CURSOR_PINNED_SOURCE_NOT_RUNNING")
        pid = int(source["MainPID"])
        cmdline = _running_cmdline(pid)
        expected = str(_release(SOURCE_PARENT_SHA) / ".venv/bin/python").encode()
        if expected not in cmdline or b"copytrade_pm.pm_v4_selected_positions" not in cmdline:
            raise ValueError("V4_PAPER_CURSOR_SOURCE_PROCESS_PIN_MISMATCH")
        upstream = _status("copytrade-v4-selected-positions-0811.service")
        if upstream["ActiveState"] != "active" or int(upstream["MainPID"]) <= 0:
            raise ValueError("V4_PAPER_CURSOR_0811_SOURCE_UNAVAILABLE")
    return states


def _paper_plans(expected_sha: str) -> dict:
    release = _release(expected_sha)
    _verify_release(release, expected_sha)
    planned = {}
    for unit in (PAPER, PYDNATIVE):
        old = UNIT_ROOT / (unit + ".d") / NEW_OVERRIDE
        if not old.is_file() or old.is_symlink():
            raise ValueError("V4_PAPER_CURSOR_REQUIRES_PREVIOUS_95_OVERRIDE")
        source_raw = old.read_text()
        if not source_raw.startswith(MARKER + SOURCE_PARENT_SHA + "\n"):
            raise ValueError("V4_PAPER_CURSOR_PREVIOUS_95_SHA_MISMATCH")
        starts = [
            row.removeprefix("ExecStart=")
            for row in source_raw.splitlines()
            if row.startswith("ExecStart=") and row != "ExecStart="
        ]
        if len(starts) != 1 or starts[0].count(PAPER_MODULE) != 1:
            raise ValueError("V4_PAPER_CURSOR_OLD_READER_COMMAND_INVALID")
        new_command = (
            str(release / ".venv/bin/python")
            + " "
            + PAPER_MODULE
            + starts[0].split(PAPER_MODULE, 1)[1]
        )
        if "broker" in new_command.lower() or "--compact-evidence" in new_command:
            raise ValueError("V4_PAPER_CURSOR_BROKER_OR_COMPACT_DISABLED")
        dest = UNIT_ROOT / (unit + ".d") / PAPER_OVERRIDE
        if dest.exists() or dest.is_symlink():
            raise FileExistsError("V4_PAPER_CURSOR_OVERRIDE_EXISTS")
        body = (
            PAPER_MARKER + expected_sha + "\n"
            "[Service]\nExecStart=\nExecStart="
            + new_command
            + "\nWorkingDirectory="
            + str(release)
            + "\n"
        ).encode()
        planned[unit] = {"destination": dest, "content": body, "sha256": _sha(body)}
    return planned


def paper_apply(expected_sha: str) -> dict:
    """Install paper readers from the new pinned SHA, leave live source alone."""
    old_states = _paper_quiescence(check_source=True)
    planned = _paper_plans(expected_sha)
    written = []
    try:
        for unit in (PAPER, PYDNATIVE):
            row = planned[unit]
            _publish_exclusive(row["destination"], row["content"])
            written.append(row["destination"])
        _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    except BaseException:
        for dest in reversed(written):
            dest.unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        raise
    return {
        "phase": "PAPER_PINNED_NO_START",
        "new_paper_release_sha": expected_sha,
        "source_release_sha": SOURCE_PARENT_SHA,
        "source_kept_running": True,
        "paper_units": list(planned),
        "prior_states": old_states,
        "paper_override_sha256": {unit: planned[unit]["sha256"] for unit in planned},
        "broker_route": "NONE",
        "trading_authorized": False,
    }


def paper_rollback(expected_sha: str) -> dict:
    """Remove only owned paper overrides while the paper readers are stopped."""
    _paper_quiescence(check_source=False)
    removed = []
    for unit in (PAPER, PYDNATIVE):
        dest = UNIT_ROOT / (unit + ".d") / PAPER_OVERRIDE
        if not dest.exists():
            continue
        raw = dest.read_bytes()
        if not raw.startswith((PAPER_MARKER + expected_sha + "\n").encode()):
            raise ValueError("V4_PAPER_CURSOR_UNOWNED_OVERRIDE")
        removed.append(dest)
    for dest in removed:
        dest.unlink()
    _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return {
        "phase": "PAPER_PIN_ROLLED_BACK",
        "removed": len(removed),
        "source_unchanged": True,
        "journals_unchanged": True,
    }


STABLE_SOURCE_OVERRIDE = "96-v4-stable-source-292.conf"
STABLE_SOURCE_MARKER = "# V4_STABLE_SOURCE_292_PINNED_RELEASE "
STABLE_SOURCE_ALIASES = ("S035", "S051", "S053", "S064", "Whale_0x5f94", "ACT04", "ACT08")


def _stable_source_plan(expected_sha: str) -> dict:
    release = _release(expected_sha)
    _verify_release(release, expected_sha)
    prior = UNIT_ROOT / (SOURCE + ".d") / NEW_OVERRIDE
    if prior.is_symlink() or not prior.is_file():
        raise ValueError("V4_STABLE_SOURCE_PRIOR_95_MISSING")
    original = prior.read_text()
    if not original.startswith(MARKER + SOURCE_PARENT_SHA + "\n"):
        raise ValueError("V4_STABLE_SOURCE_PRIOR_95_SHA_MISMATCH")
    starts = [
        line.removeprefix("ExecStart=")
        for line in original.splitlines()
        if line.startswith("ExecStart=") and line != "ExecStart="
    ]
    if len(starts) != 1 or starts[0].count(SOURCE_MODULE) != 1:
        raise ValueError("V4_STABLE_SOURCE_PREVIOUS_UNIT_INVALID")
    suffix = starts[0].split(SOURCE_MODULE, 1)[1]
    if "--native-stable-aliases" in suffix or "--compact-evidence" in suffix:
        raise ValueError("V4_STABLE_SOURCE_PREVIOUS_MODE_INVALID")
    new_command = (
        str(release / ".venv/bin/python")
        + " "
        + SOURCE_MODULE
        + suffix
        + " --native-stable-aliases "
        + ",".join(STABLE_SOURCE_ALIASES)
    )
    if "broker" in new_command.lower() or "--compact-evidence" in new_command:
        raise ValueError("V4_STABLE_SOURCE_FORBIDDEN_ORDER_ROUTE")
    dest = UNIT_ROOT / (SOURCE + ".d") / STABLE_SOURCE_OVERRIDE
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("V4_STABLE_SOURCE_OVERRIDE_EXISTS")
    content = (
        STABLE_SOURCE_MARKER + expected_sha + "\n"
        "[Service]\nExecStart=\nExecStart="
        + new_command
        + "\nWorkingDirectory="
        + str(release)
        + "\n"
    ).encode()
    return {"destination": dest, "content": content, "sha256": _sha(content)}


def stable_apply(expected_sha: str) -> dict:
    """Pin original 0911 source+paper to a seven-user fixed SHADOW cohort."""
    states = _quiescence()
    source_plan = _stable_source_plan(expected_sha)
    planned = {SOURCE: source_plan, **_paper_plans(expected_sha)}
    written = []
    try:
        for unit in UNITS:
            row = planned[unit]
            _publish_exclusive(row["destination"], row["content"])
            written.append(row["destination"])
        _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    except BaseException:
        for dest in reversed(written):
            dest.unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        raise
    return {
        "phase": "STABLE_SEVEN_SOURCE_AND_PAPER_PINNED_NO_START",
        "source_and_paper_release_sha": expected_sha,
        "original_14_parent_campaign_preserved": True,
        "official_active_user_budget": len(STABLE_SOURCE_ALIASES),
        "permanently_unsubscribed_parents": 7,
        "source_mode": "DEGRADED_PARTIAL_OFFICIAL_SOURCE",
        "prior_states": states,
        "overrides_sha256": {k: v["sha256"] for k, v in planned.items()},
        "no_services_started": True,
        "trading_authorized": False,
        "broker_route": "NONE",
    }


def stable_rollback(expected_sha: str) -> dict:
    _quiescence(require_0811=False)
    targets = [
        (SOURCE, STABLE_SOURCE_OVERRIDE, STABLE_SOURCE_MARKER),
        (PAPER, PAPER_OVERRIDE, PAPER_MARKER),
        (PYDNATIVE, PAPER_OVERRIDE, PAPER_MARKER),
    ]
    owned = []
    for unit, name, marker in targets:
        path = UNIT_ROOT / (unit + ".d") / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.read_bytes().startswith(
            (marker + expected_sha + "\n").encode()
        ):
            raise ValueError("V4_STABLE_SOURCE_UNOWNED_OVERRIDE")
        owned.append(path)
    for path in owned:
        path.unlink()
    _run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return {
        "phase": "STABLE_SHADOW_OVERRIDES_ROLLED_BACK",
        "removed": len(owned),
        "previous_95_and_90_preserved": True,
        "original_source_and_finance_journals_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=(
            "audit",
            "stage",
            "apply",
            "rollback",
            "paper-apply",
            "paper-rollback",
            "stable-apply",
            "stable-rollback",
        ),
        required=True,
    )
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not SHAFULL.fullmatch(args.expected_sha):
        raise ValueError("V4_BUDGET_SHA_INVALID")
    if args.phase == "audit":
        result = {
            "phase": "AUDIT_ONLY",
            "unit_states": {u: _status(u) for u in UNITS},
            "release_path": str(_release(args.expected_sha)),
            "release_exists": _release(args.expected_sha).exists(),
        }
    else:
        if not args.apply:
            raise ValueError("V4_BUDGET_OPERATOR_APPLY_REQUIRED")
        if args.phase == "stage":
            result = stage(args.expected_sha)
        elif args.phase == "apply":
            result = apply(args.expected_sha)
        elif args.phase == "paper-apply":
            result = paper_apply(args.expected_sha)
        elif args.phase == "paper-rollback":
            result = paper_rollback(args.expected_sha)
        elif args.phase == "stable-apply":
            result = stable_apply(args.expected_sha)
        elif args.phase == "stable-rollback":
            result = stable_rollback(args.expected_sha)
        else:
            result = rollback(args.expected_sha)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
