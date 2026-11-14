"""Bounded, read-only inspections of independent release/OS/observer authorities.

Never infer paper-worker health from active units, a registry selection, a
repository checkout, or a public observer. No service mutation or broker I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


@dataclass(frozen=True)
class _UnitContract:
    expected_module: str
    runtime_scopes: frozenset[str]
    legacy_module: str | None = None
    role: str | None = None
    portfolio: str | None = None
    requires_release_revision: bool = False
    required_option: tuple[str, str] | None = None
    option_mismatch_code: str | None = None


_V4_MODULE = "copytrade_pm.pm_forward_protected_ops"
# Only known paper/source services may be inspected. Chapter 2 is user-managed;
# V4 protected units have separate user (legacy) and system manager identities.
_UNIT_CONTRACTS: dict[str, _UnitContract] = {
    "copytrade-cwsa-5m-source-chapter2.service": _UnitContract(
        expected_module="copytrade_pm.pm_cwsa_source_observer",
        runtime_scopes=frozenset({"user"}),
        legacy_module="copytrade_pm.pm_v4_selected_positions",
        required_option=("--source-mode", "CHECKPOINT_REST_V3"),
        option_mismatch_code="UNIT_SOURCE_POLICY_MISMATCH",
    ),
    "copytrade-cwsa-5m-paper-chapter2.service": _UnitContract(
        expected_module="copytrade_pm.pm_cwsa_six_paper",
        runtime_scopes=frozenset({"user"}),
    ),
    "copytrade-paper-p1.service": _UnitContract(
        expected_module=_V4_MODULE,
        runtime_scopes=frozenset({"system", "user"}),
        role="worker",
        portfolio="P1",
        requires_release_revision=True,
    ),
    "copytrade-paper-p14.service": _UnitContract(
        expected_module=_V4_MODULE,
        runtime_scopes=frozenset({"system", "user"}),
        role="worker",
        portfolio="P14",
        requires_release_revision=True,
    ),
    "copytrade-paper-watchdog.service": _UnitContract(
        expected_module=_V4_MODULE,
        runtime_scopes=frozenset({"system", "user"}),
        role="watchdog",
        requires_release_revision=True,
    ),
}
UNITS = tuple(name for name, c in _UNIT_CONTRACTS.items() if c.requires_release_revision)
_CHAPTER2_MODULES = {
    name: c.expected_module
    for name, c in _UNIT_CONTRACTS.items()
    if not c.requires_release_revision
}
_RUNTIME_SCOPES = {name: c.runtime_scopes for name, c in _UNIT_CONTRACTS.items()}
SHA = re.compile(r"^[a-f0-9]{40}$")
_LAUNCH_PATTERN = re.compile(r"^\{\s*path=(/[^;\s{}]+)\s*;\s*argv\[\]=([^;{}]+?)\s*;[^{}]*\}$")
_RUNTIME_LIMIT = (
    "This independently binds the launch, but loaded application bytes, "
    "dependencies and post-start module changes are not fully attested"
)
GIT_LOCAL_ENV_VARS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


def clean_git_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment stripped of repository-local GIT_* overrides."""
    env = dict(os.environ if base is None else base)
    for key in GIT_LOCAL_ENV_VARS:
        env.pop(key, None)
    return env


def _readonly_command(runner, args: list[str], *, timeout: int = 8):
    kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": timeout,
    }
    # Real git subprocesses must inspect the target release dir, not an inherited hook env.
    if runner is subprocess.run and args and args[0] == "git":
        kwargs["env"] = clean_git_env()
    return runner(args, **kwargs)


def _unit_properties(runner, unit: str, manager: str) -> dict[str, str]:
    args = ["systemctl"]
    if manager == "user":
        args.append("--user")
    args += ["show", unit]
    for field in (
        "Id",
        "LoadState",
        "ActiveState",
        "MainPID",
        "ExecMainStartTimestampMonotonic",
        "InvocationID",
        "ControlGroup",
        "WorkingDirectory",
        "FragmentPath",
        "ExecStart",
    ):
        args.extend(("-p", field))
    args.append("--no-pager")
    output = _readonly_command(runner, args)
    if output.returncode != 0:
        raise OSError("SYSTEMD_QUERY_UNAVAILABLE")
    data = dict(line.split("=", 1) for line in output.stdout.splitlines() if "=" in line)
    if data.get("Id") != unit:
        raise ValueError("SYSTEMD_UNIT_IDENTITY_UNAVAILABLE")
    return data


def _configured_launch(props: dict[str, str]) -> tuple[Path, list[str]]:
    match = _LAUNCH_PATTERN.fullmatch(props.get("ExecStart", "").strip())
    if match is None:
        raise ValueError("SYSTEMD_EXECSTART_NOT_ATTESTABLE")
    executable = Path(match.group(1))
    args = shlex.split(match.group(2))
    if (
        not args
        or args[0] != str(executable)
        or executable.parts[-3:]
        != (
            ".venv",
            "bin",
            "python",
        )
    ):
        raise ValueError("SYSTEMD_LAUNCH_NOT_PINNED_PYTHON")
    return executable, args


def _trusted_release(release: Path, roots: tuple[Path, ...]) -> bool:
    # The release must be a direct physical child of an approved release store.
    return release.is_absolute() and any(
        release.parent == root and not root.is_symlink() for root in roots
    )


def _process_snapshot(proc_root: Path, pid: int) -> dict:
    directory = proc_root / str(pid)
    raw = (directory / "stat").read_text()
    fields = raw.rsplit(") ", 1)
    if len(fields) != 2 or not fields[0].startswith(str(pid) + " ("):
        raise ValueError("PROCESS_STAT_UNRECOGNIZED")
    tail = fields[1].split()
    if len(tail) <= 19:
        raise ValueError("PROCESS_STAT_INCOMPLETE")
    argv_bytes = (directory / "cmdline").read_bytes()
    if not argv_bytes.endswith(b"\0"):
        raise ValueError("PROCESS_ARGV_INCOMPLETE")
    argv = [os.fsdecode(item) for item in argv_bytes.rstrip(b"\0").split(b"\0")]
    if not argv or not argv[0]:
        raise ValueError("PROCESS_ARGV_EMPTY")
    cg_lines = (directory / "cgroup").read_text().splitlines()
    cg_paths = [line.split(":", 2)[2] for line in cg_lines if line.count(":") >= 2]
    uid_field = next(
        line for line in (directory / "status").read_text().splitlines() if line.startswith("Uid:")
    )
    uids = uid_field.split()[1:]
    if len(uids) != 4:
        raise ValueError("PROCESS_UID_UNAVAILABLE")
    env = (directory / "environ").read_bytes().split(b"\0")
    unsafe_env = any(
        e.startswith((b"PYTHONPATH=", b"PYTHONHOME=", b"LD_PRELOAD=")) and e.partition(b"=")[2]
        for e in env
    )
    return {
        "pid": pid,
        "state": tail[0],
        "process_start_ticks": int(tail[19]),
        "argv": argv,
        "argv_sha256": hashlib.sha256(argv_bytes).hexdigest(),
        "cgroup_paths": cg_paths,
        "uid": int(uids[1]),
        "cwd": str((directory / "cwd").resolve(strict=True)),
        "exe": str((directory / "exe").resolve(strict=True)),
        "unsafe_python_environment": unsafe_env,
    }


def _git_release(runner, release: Path) -> tuple[str, bool]:
    branch = _readonly_command(runner, ["git", "-C", str(release), "symbolic-ref", "-q", "HEAD"])
    if branch.returncode not in (0, 1):
        raise OSError("RELEASE_GIT_HEAD_UNAVAILABLE")
    if branch.returncode == 0:
        return "", False
    commit = _readonly_command(runner, ["git", "-C", str(release), "rev-parse", "--verify", "HEAD"])
    dirty = _readonly_command(
        runner,
        ["git", "-C", str(release), "status", "--porcelain", "--untracked-files=normal"],
        timeout=15,
    )
    if commit.returncode != 0 or dirty.returncode != 0:
        raise OSError("RELEASE_GIT_INSPECTION_UNAVAILABLE")
    return commit.stdout.strip(), not dirty.stdout.strip()


def _non_writable_to_process(path: Path, euid: int) -> bool:
    metadata = path.stat()
    # Fail closed for a process owning the release, or a group/other-writable
    # tree. These POSIX mode checks do not establish a mount/ACL-wide proof.
    return metadata.st_uid != euid and not metadata.st_mode & 0o022


def _tracked_release_files_readonly(runner, release: Path, euid: int) -> bool:
    # A read-only directory is insufficient if an already-present module is
    # owned/writable by the worker. Check the tracked tree, not only Git status.
    files = _readonly_command(runner, ["git", "-C", str(release), "ls-files", "-z"], timeout=15)
    if files.returncode or not files.stdout:
        return False
    for relative in files.stdout.strip("\0").split("\0"):
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            return False
        target = release / path
        if target.is_symlink() or not target.is_file():
            return False
        if not _non_writable_to_process(target, euid):
            return False
    return True


def verify_unit_release(
    unit: str,
    *,
    expected_sha: str | None,
    manager: str = "user",
    release_roots: tuple[Path, ...] | None = None,
    proc_root: Path = Path("/proc"),
    runner=None,
) -> dict:
    """Independent, read-only binding of systemd, immutable Git and /proc.

    State is VERIFIED only for an allowlisted running launch in a physically
    pinned release location, with a matching service invocation and process
    birth. Hidden metadata, a mutable tree and races are UNKNOWN; an observed
    different process/revision is MISMATCH; a reliably inactive unit is
    NOT_RUNNING. This is *launch identity*, not loaded-byte or finance proof.
    """
    if unit not in _RUNTIME_SCOPES or manager not in _RUNTIME_SCOPES[unit]:
        raise ValueError("RUNTIME_UNIT_MANAGER_SCOPE_INVALID")
    runner = subprocess.run if runner is None else runner
    if release_roots is None:
        release_roots = (
            Path("/opt/copytrade-paper/releases"),
            Path.home() / ".local/share/copytrade/releases",
        )
    started = datetime.now(UTC).isoformat()
    report: dict = {
        "state": "UNKNOWN",
        "reason": "NOT_INSPECTED",
        "configured": {"unit": unit, "manager": manager},
        "installed": {"expected_revision": expected_sha},
        "observed": {},
        "clock": {"inspection_started_utc": started},
        "scope": "INDEPENDENT_OS_RELEASE_LAUNCH_ONLY_NOT_FINANCIAL_OR_TRADING",
        "limitations": [_RUNTIME_LIMIT, "Process metadata may be hidden by OS permissions"],
        "service_mutations": 0,
        "trading_authorized": False,
    }

    def done(state: str, reason: str) -> dict:
        report["state"], report["reason"] = state, reason
        report["clock"]["inspection_completed_utc"] = datetime.now(UTC).isoformat()
        return report

    try:
        first = _unit_properties(runner, unit, manager)
    except OSError, ValueError, subprocess.SubprocessError:
        return done("UNKNOWN", "SYSTEMD_IDENTITY_UNAVAILABLE")
    configured = report["configured"]
    configured.update(
        {
            "load_state": first.get("LoadState"),
            "active_state": first.get("ActiveState"),
            "main_pid": first.get("MainPID"),
            "invocation_id": first.get("InvocationID"),
            "control_group": first.get("ControlGroup"),
            "working_directory": first.get("WorkingDirectory"),
            "fragment_path": first.get("FragmentPath"),
            # Never emit raw unit arguments: private runtime paths and
            # configuration values may be present in ExecStart.
            "exec_argv_sha256": hashlib.sha256(first.get("ExecStart", "").encode()).hexdigest(),
        }
    )
    if first.get("ActiveState") in ("inactive", "failed") and first.get("MainPID") == "0":
        return done("NOT_RUNNING", "SYSTEMD_UNIT_STOPPED")
    if first.get("LoadState") != "loaded" or first.get("ActiveState") != "active":
        return done("UNKNOWN", "SYSTEMD_UNIT_NOT_STABLE")
    try:
        pid = int(first["MainPID"])
        configured["main_pid"] = pid
        system_start = int(first["ExecMainStartTimestampMonotonic"])
        if (
            pid <= 0
            or system_start <= 0
            or not first.get("ControlGroup")
            or not first.get("InvocationID")
        ):
            return done("UNKNOWN", "SYSTEMD_START_IDENTITY_INCOMPLETE")
        executable, configured_argv = _configured_launch(first)
        configured["exec_path"] = str(executable)
        configured["module"] = configured_argv[2] if len(configured_argv) > 2 else None
        release = executable.parent.parent.parent
        if first.get("WorkingDirectory") != str(release):
            return done("UNKNOWN", "SYSTEMD_RELEASE_WORKDIR_UNATTESTED")
        report["clock"]["systemd_start_monotonic_us"] = system_start
        report["installed"]["release_path"] = str(release)
        if not _trusted_release(release, release_roots):
            return done("UNKNOWN", "UNTRUSTED_RELEASE_LOCATION")
        if any(path.is_symlink() for path in (release, release / ".venv", release / ".venv/bin")):
            return done("UNKNOWN", "MUTABLE_RELEASE_NOT_ATTESTABLE")
        if not executable.is_file():
            return done("UNKNOWN", "PINNED_EXECUTABLE_INACCESSIBLE")
        executable_identity = (
            str(executable.resolve(strict=True)),
            executable.stat().st_dev,
            executable.stat().st_ino,
        )
        contract = _UNIT_CONTRACTS[unit]
        expected_module = contract.expected_module
        configured_module = configured_argv[2] if len(configured_argv) > 2 else ""
        # A pinned, already-running CWSA REST process may still carry the
        # historical module name until its separately verified release cutover.
        # This exception must not admit V4 WS timing or a new legacy launcher.
        old_cwsa_module = (
            contract.legacy_module is not None and configured_module == contract.legacy_module
        )
        if configured_argv[1:3] != ["-m", expected_module] and not old_cwsa_module:
            return done("MISMATCH", "UNIT_APPLICATION_MODULE_MISMATCH")
        if contract.role is not None:
            if len(configured_argv) < 4 or configured_argv[3] != contract.role:
                return done("MISMATCH", "UNIT_APPLICATION_ROLE_MISMATCH")
            if contract.portfolio is not None and (
                "--portfolio" not in configured_argv
                or configured_argv[configured_argv.index("--portfolio") + 1 :][:1]
                != [contract.portfolio]
            ):
                return done("MISMATCH", "UNIT_PORTFOLIO_MISMATCH")
        if contract.requires_release_revision and (
            "--release" not in configured_argv
            or configured_argv[configured_argv.index("--release") + 1 :][:1] != [str(release)]
            or "--revision" not in configured_argv
        ):
            return done("MISMATCH", "UNIT_RELEASE_ARGUMENT_MISMATCH")
        if contract.required_option is not None:
            flag, expected_val = contract.required_option
            if flag not in configured_argv or configured_argv[configured_argv.index(flag) + 1 :][
                :1
            ] != [expected_val]:
                return done("MISMATCH", contract.option_mismatch_code or "UNIT_OPTION_MISMATCH")
        revision, clean = _git_release(runner, release)
        report["installed"].update(revision=revision, detached=bool(revision), clean=clean)
        if not revision or not clean or not SHA.fullmatch(revision):
            return done("UNKNOWN", "MUTABLE_RELEASE_NOT_ATTESTABLE")
        if contract.requires_release_revision and (
            configured_argv[configured_argv.index("--revision") + 1 :][:1] != [revision]
        ):
            return done("MISMATCH", "UNIT_RELEASE_ARGUMENT_MISMATCH")
        if expected_sha is None or not SHA.fullmatch(expected_sha):
            return done("UNKNOWN", "EXPECTED_RELEASE_SHA_REQUIRED")
        if revision != expected_sha:
            return done("MISMATCH", "INSTALLED_RELEASE_SHA_DRIFT")
        # First observed PID identity MUST be read from OS, not systemd or a
        # self-reported health file. Missing /proc is evidence unavailable.
        process = _process_snapshot(proc_root, pid)
        report["observed"] = {
            key: value
            for key, value in process.items()
            if key not in {"argv", "cgroup_paths", "unsafe_python_environment"}
        }
        report["clock"]["process_start_ticks"] = process["process_start_ticks"]
        report["clock"]["ticks_per_second"] = os.sysconf("SC_CLK_TCK")
        report["clock"]["boot_id"] = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
        if process["state"] in ("Z", "X", "x"):
            return done("MISMATCH", "OBSERVED_PROCESS_NOT_RUNNING")
        if process["argv"] != configured_argv:
            return done("MISMATCH", "PROCESS_ARGV_MISMATCH")
        if process["cwd"] != str(release) or process["exe"] != str(executable.resolve()):
            return done("MISMATCH", "PROCESS_RELEASE_PATH_MISMATCH")
        cgroup = first["ControlGroup"]
        if not any(
            path == cgroup or path.startswith(cgroup + "/") for path in process["cgroup_paths"]
        ):
            return done("MISMATCH", "PROCESS_CGROUP_MISMATCH")
        if process["unsafe_python_environment"]:
            return done("UNKNOWN", "PYTHON_IMPORT_PATH_UNATTESTED")
        ticks = report["clock"]["ticks_per_second"]
        if abs(process["process_start_ticks"] * 1_000_000 / ticks - system_start) > 2_000_000:
            return done("MISMATCH", "PROCESS_START_TIME_MISMATCH")
        # The application code root and interpreter environment must not be
        # writable by the observed worker. A mutable development checkout
        # cannot qualify even when Git happens to be clean.
        if not all(
            _non_writable_to_process(path, process["uid"])
            for path in (
                release.parent,
                release,
                release / ".venv",
                release / ".venv/bin",
                executable.resolve(strict=True),
                release / "src",
                release / "src/copytrade_pm",
            )
        ) or not _tracked_release_files_readonly(runner, release, process["uid"]):
            return done("UNKNOWN", "MUTABLE_RELEASE_NOT_ATTESTABLE")
        directory_identity = (release.stat().st_dev, release.stat().st_ino)
        second = _unit_properties(runner, unit, manager)
        if second != first:
            return done("UNKNOWN", "SYSTEMD_IDENTITY_RACED")
        # Catch PID reuse, in-place execve and path swaps during inspection.
        after = _process_snapshot(proc_root, pid)
        if after != process or directory_identity != (
            release.stat().st_dev,
            release.stat().st_ino,
        ):
            return done("UNKNOWN", "PROCESS_IDENTITY_RACED")
        final_revision, final_clean = _git_release(runner, release)
        if (final_revision, final_clean) != (revision, clean) or any(
            path.is_symlink() for path in (release, release / ".venv", release / ".venv/bin")
        ):
            return done("UNKNOWN", "INSTALLED_RELEASE_RACED")
        if executable_identity != (
            str(executable.resolve(strict=True)),
            executable.stat().st_dev,
            executable.stat().st_ino,
        ):
            return done("UNKNOWN", "INSTALLED_EXECUTABLE_SYMLINK_RACED")
        report["installed"]["worker_nonwritable_tracked_tree"] = True
        return done("VERIFIED", "RUNNING_RELEASE_LAUNCH_BOUND")
    except OSError, ValueError, TypeError, KeyError, StopIteration, subprocess.SubprocessError:
        return done("UNKNOWN", "PROCESS_METADATA_UNAVAILABLE")


def observe_unit_liveness(
    unit: str,
    *,
    manager: str = "user",
    proc_root: Path = Path("/proc"),
    runner=None,
) -> dict:
    """Independently observe a stable systemd process, without claiming release proof.

    A configured active unit or merely existing PID is insufficient. Check the
    actual process launch, cgroup and birth twice; missing OS evidence is UNKNOWN,
    not a stopped worker. This does not inspect finance or change any service.
    """
    if unit not in _RUNTIME_SCOPES or manager not in _RUNTIME_SCOPES[unit]:
        raise ValueError("RUNTIME_UNIT_MANAGER_SCOPE_INVALID")
    runner = subprocess.run if runner is None else runner
    report = {
        "state": "UNKNOWN",
        "reason": "NOT_INSPECTED",
        "unit": unit,
        "manager": manager,
        "pid": None,
        "process_start_ticks": None,
        "inspection_at_utc": datetime.now(UTC).isoformat(),
        "scope": "INDEPENDENT_OS_PROCESS_LIVENESS_ONLY_NOT_RELEASE_OR_FINANCE",
    }

    def done(state: str, reason: str) -> dict:
        report["state"], report["reason"] = state, reason
        return report

    try:
        first = _unit_properties(runner, unit, manager)
        if first.get("ActiveState") in ("inactive", "failed") and first.get("MainPID") == "0":
            if _unit_properties(runner, unit, manager) == first:
                return done("NOT_RUNNING", "SYSTEMD_UNIT_STOPPED")
            return done("UNKNOWN", "SYSTEMD_IDENTITY_RACED")
        if first.get("LoadState") != "loaded" or first.get("ActiveState") != "active":
            return done("UNKNOWN", "SYSTEMD_UNIT_NOT_STABLE")
        pid = int(first["MainPID"])
        start_us = int(first["ExecMainStartTimestampMonotonic"])
        if pid <= 0 or start_us <= 0 or not first.get("ControlGroup"):
            return done("UNKNOWN", "SYSTEMD_START_IDENTITY_INCOMPLETE")
        report["pid"] = pid
        before = _process_snapshot(proc_root, pid)
        report["process_start_ticks"] = before["process_start_ticks"]
        if before["state"] in ("Z", "X", "x"):
            return done("MISMATCH", "OBSERVED_PROCESS_NOT_RUNNING")
        executable, configured_argv = _configured_launch(first)
        if before["argv"] != configured_argv or before["exe"] != str(
            executable.resolve(strict=True)
        ):
            return done("MISMATCH", "PROCESS_LAUNCH_MISMATCH")
        cgroup = first["ControlGroup"]
        if not any(
            path == cgroup or path.startswith(cgroup + "/") for path in before["cgroup_paths"]
        ):
            return done("MISMATCH", "PROCESS_CGROUP_MISMATCH")
        if (
            abs(before["process_start_ticks"] * 1_000_000 / os.sysconf("SC_CLK_TCK") - start_us)
            > 2_000_000
        ):
            return done("MISMATCH", "PROCESS_START_TIME_MISMATCH")
        second = _unit_properties(runner, unit, manager)
        after = _process_snapshot(proc_root, pid)
        if first != second or before != after:
            return done("UNKNOWN", "PROCESS_OR_SYSTEMD_IDENTITY_RACED")
        return done("RUNNING", "PROCESS_BOUND_TO_RUNNING_SYSTEMD_UNIT")
    except OSError, ValueError, TypeError, KeyError, StopIteration, subprocess.SubprocessError:
        return done("UNKNOWN", "PROCESS_LIVENESS_UNAVAILABLE")


def installed_release(source_root: Path) -> dict:
    """Call the existing release owner's verified action; do not reimplement it."""
    script = Path(source_root) / "scripts" / "registry_release.py"
    if script.is_symlink() or not script.is_file():
        return {"state": "UNKNOWN", "error_code": "PINNED_RELEASE_VERIFIER_UNAVAILABLE"}
    try:
        call = subprocess.run(
            [sys.executable, str(script), "verify"],
            cwd=source_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=75,
        )
        if call.returncode:
            return {"state": "UNKNOWN", "error_code": "INSTALLED_RELEASE_VERIFY_FAILED"}
        parsed = json.loads(call.stdout)
        if (
            parsed.get("result") != "ACTIVE_READ_ONLY_VERIFIED"
            or not isinstance(parsed.get("revision"), str)
            or not SHA.fullmatch(parsed["revision"])
            or parsed.get("registry_timer") != "NOT_INSTALLED"
            or parsed.get("source", {}).get("trading_authorized") is not False
        ):
            return {"state": "UNKNOWN", "error_code": "INSTALLED_RELEASE_NOT_VERIFIED"}
        return {
            "state": "VERIFIED",
            "release_revision": parsed["revision"],
            "source_manifest_sha256": parsed["source"]["source_manifest_sha256"],
            "registry_timer": "NOT_INSTALLED",
            "trading_authorized": False,
            "scope": "PINNED_REGISTRY_ONLY_NOT_TRADING_SERVICES",
        }
    except OSError, ValueError, TypeError, subprocess.TimeoutExpired:
        return {"state": "UNKNOWN", "error_code": "INSTALLED_RELEASE_QUERY_UNAVAILABLE"}


def paper_unit_inventory() -> dict:
    """OS unit status is independent evidence, but insufficient for paper admission."""
    try:
        output = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                *UNITS,
                "--property=Id",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=MainPID",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if output.returncode:
            raise ValueError("SYSTEMD_USER_QUERY_FAILED")
        records: dict[str, dict] = {}
        for section in output.stdout.split("\n\n"):
            values = dict(line.split("=", 1) for line in section.splitlines() if "=" in line)
            name = values.get("Id")
            if name not in UNITS or name in records:
                raise ValueError("SYSTEMD_UNIT_INVENTORY_MISMATCH")
            if values.get("LoadState") not in ("loaded", "not-found", "masked", "error"):
                raise ValueError("SYSTEMD_UNIT_LOAD_UNKNOWN")
            if values.get("ActiveState") not in (
                "active",
                "inactive",
                "failed",
                "activating",
                "deactivating",
            ):
                raise ValueError("SYSTEMD_UNIT_ACTIVE_UNKNOWN")
            if not str(values.get("MainPID", "")).isdigit():
                raise ValueError("SYSTEMD_UNIT_PID_INVALID")
            records[name] = {
                "load_state": values["LoadState"],
                "active_state": values["ActiveState"],
                "pid_observed": int(values["MainPID"]) > 0,
            }
        if set(records) != set(UNITS):
            raise ValueError("SYSTEMD_UNIT_INVENTORY_INCOMPLETE")
        any_active = any(x["active_state"] == "active" for x in records.values())
        any_unknown = any(
            x["active_state"] in ("failed", "activating", "deactivating")
            or x["load_state"] == "error"
            for x in records.values()
        )
        # Actual protected candidates are SYSTEM services, not user units.
        # Never conclude NOT_RUNNING from the user manager alone.
        from .pm_forward_release import read_only_protected_system_inventory

        system = read_only_protected_system_inventory(runner=subprocess.run)
        system_active = any(x["active_state"] == "active" for x in system["units"])
        system_unavailable = bool(system["unavailable"])
        system_unknown = any(
            x["active_state"] in ("failed", "activating", "deactivating")
            or x["load_state"] == "error"
            for x in system["units"]
        )
        state = (
            "UNKNOWN"
            if system_unavailable
            else "DEGRADED"
            if any_active or any_unknown or system_active or system_unknown
            else "NOT_RUNNING"
        )
        return {
            "state": state,
            "units": records,
            "system_units": system["units"],
            "system_unit_inventory": system["status"],
            "scope": "USER_AND_SYSTEM_KNOWN_PROTECTED_UNIT_NAMES",
            "protected_worker_attested": False,
            "reason": "SYSTEM_PROTECTED_UNIT_INVENTORY_INCOMPLETE"
            if system_unavailable
            else "ACTIVE_UNIT_REQUIRES_INDEPENDENT_JOURNAL_AND_HEARTBEAT"
            if any_active or system_active
            else "SYSTEMD_SERVICE_STATE_REQUIRES_ATTENTION"
            if any_unknown or system_unknown
            else "NO_ACTIVE_KNOWN_PROTECTED_PAPER_UNITS",
        }
    except ValueError, OSError, subprocess.TimeoutExpired:
        return {"state": "UNKNOWN", "error_code": "PAPER_SYSTEMD_QUERY_UNAVAILABLE"}


def observer_market_health(state_root: Path | None) -> dict:
    """Only actual source/market receipt tape evidence, never venue-provider health."""
    if state_root is None:
        return {
            "state": "UNKNOWN",
            "error_code": "OBSERVER_STATE_ROOT_NOT_SUPPLIED",
            "scope": "NOT_A_LIVE_MARKET_PROVIDER_ATTESTATION",
        }
    from .pm_forward_observer_health import (
        inspect_public_observer_heartbeat,
        inspect_continuous_observer,
    )

    root = Path(state_root)
    try:
        if (root / "continuous-observer.heartbeat.json").exists():
            checked = inspect_continuous_observer(root, as_of=datetime.now(UTC).isoformat())
            return {
                "state": "DEGRADED"
                if checked.get("health") == "DEGRADED_OBSERVER_ONLY"
                else "UNKNOWN",
                "observer_health": checked.get("health", "UNKNOWN"),
                "feed_health": checked.get("feed_health", "UNKNOWN"),
                "required_feed_count": checked.get("required_feed_count", 0),
                "journal_integrity": checked.get("journal_integrity", "UNKNOWN"),
                "protected_worker_attested": False,
                "provider_health": "UNKNOWN",
                "scope": "PUBLIC_OBSERVER_ONLY_NOT_BROKER_OR_MARKET_PROVIDER",
            }
        checked = inspect_public_observer_heartbeat(
            root,
            journal_db=root / "paper-events.sqlite3",
            as_of=datetime.now(UTC).isoformat(),
        )
        return {
            "state": "DEGRADED" if checked.get("health") == "DEGRADED_OBSERVER_ONLY" else "UNKNOWN",
            "observer_health": checked.get("health", "UNKNOWN"),
            "market_quote_tapes_verified": checked.get("market_quote_tapes_verified", 0),
            "source_aliases_with_receipts": checked.get("source_aliases_with_receipts", 0),
            "protected_worker_attested": False,
            "provider_health": "UNKNOWN",
            "scope": "PUBLIC_OBSERVER_ONLY_NOT_BROKER_OR_MARKET_PROVIDER",
        }
    except OSError, ValueError, TypeError, KeyError:
        return {"state": "UNKNOWN", "error_code": "OBSERVER_MARKET_QUERY_UNAVAILABLE"}
