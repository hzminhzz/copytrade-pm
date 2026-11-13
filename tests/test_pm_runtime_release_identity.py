"""Independent systemd, OS and immutable-release evidence for ANOS-05.

Fake systemd responses are paired with real on-disk /proc and Git fixtures;
the configured unit alone is never sufficient to attest the running PID.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from copytrade_pm import pm_runtime_readonly as runtime
from copytrade_pm import pm_cwsa_chapter2_gate as chapter2


START_TICKS = 500_000
CGROUP = "/user.slice/user-1001.slice/user@1001.service/app.slice/copytrade-cwsa-5m-paper-chapter2.service"
PAPER = "copytrade-cwsa-5m-paper-chapter2.service"
SOURCE = "copytrade-cwsa-5m-source-chapter2.service"
V4 = "copytrade-paper-p1.service"


@dataclass
class Rig:
    release: Path
    proc: Path
    python: Path
    sha: str
    calls: list[list[str]]
    props: dict[str, str]
    pid: int = 12345
    alternate_props: dict[str, str] | None = None

    def runner(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append(argv)
        if argv[0] != "systemctl":
            return subprocess.run(argv, **kwargs)
        assert "show" in argv and "--no-pager" in argv
        assert all(token not in argv for token in ("start", "stop", "restart", "enable", "sudo"))
        values = (
            self.alternate_props
            if self.alternate_props and sum(x[0] == "systemctl" for x in self.calls) > 1
            else self.props
        )
        return SimpleNamespace(
            returncode=0, stdout="\n".join(f"{k}={v}" for k, v in values.items()) + "\n", stderr=""
        )

    def set_process(
        self,
        *,
        argv: list[str] | None = None,
        ticks: int = START_TICKS,
        cgroup: str = CGROUP,
        uid: int | None = None,
    ) -> None:
        process = self.proc / str(self.pid)
        process.mkdir(parents=True, exist_ok=True)
        proc_argv = argv or [
            str(self.python),
            "-m",
            "copytrade_pm.pm_cwsa_six_paper",
            "--poll-seconds",
            "5",
        ]
        (process / "cmdline").write_bytes(b"\0".join(x.encode() for x in proc_argv) + b"\0")
        (process / "stat").write_text(
            f"{self.pid} (python interpreter) S " + " ".join(["0"] * 18 + [str(ticks), "0"]) + "\n"
        )
        (process / "cgroup").write_text(f"0::{cgroup}\n")
        (process / "environ").write_bytes(b"PYTHONDONTWRITEBYTECODE=1\0")
        (process / "status").write_text(
            f"Name:\tpython\nUid:\t{uid or os.geteuid() + 1000}\t"
            f"{uid or os.geteuid() + 1000}\t{uid or os.geteuid() + 1000}\t"
            f"{uid or os.geteuid() + 1000}\n"
        )
        for name, target in [("cwd", self.release), ("exe", Path(sys.executable).resolve())]:
            link = process / name
            if link.is_symlink():
                link.unlink()
            link.symlink_to(target)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    release = tmp_path / "releases" / "candidate"
    release.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(release)], check=True)
    (release / ".gitignore").write_text(".venv/\n")
    (release / "src" / "copytrade_pm").mkdir(parents=True)
    (release / "src" / "copytrade_pm" / "__init__.py").write_text("# fixture application\n")
    (release / ".gitignore").chmod(0o644)
    (release / "src" / "copytrade_pm" / "__init__.py").chmod(0o644)
    subprocess.run(["git", "-C", str(release), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(release),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "sealed test fixture",
        ],
        check=True,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(release), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(["git", "-C", str(release), "checkout", "-q", "--detach"], check=True)
    python = release / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(Path(sys.executable).resolve())
    # Fixture release files are inaccessible for writes from the simulated
    # worker UID, regardless of the host test user's group-writable umask.
    for directory in (
        release.parent,
        release,
        release / "src",
        release / "src/copytrade_pm",
        release / ".venv",
        release / ".venv/bin",
    ):
        directory.chmod(0o755)
    proc = tmp_path / "proc"
    (proc / "sys" / "kernel" / "random").mkdir(parents=True)
    (proc / "sys" / "kernel" / "random" / "boot_id").write_text(
        "4203c011-2026-4000-9000-000000000339\n"
    )
    argv = f"{python} -m copytrade_pm.pm_cwsa_six_paper --poll-seconds 5"
    unit = {
        "Id": PAPER,
        "LoadState": "loaded",
        "ActiveState": "active",
        "MainPID": "12345",
        "ExecMainStartTimestampMonotonic": str(
            int(START_TICKS * 1_000_000 / os.sysconf("SC_CLK_TCK"))
        ),
        "InvocationID": "feedcafe001122334455667788990011",
        "ControlGroup": CGROUP,
        "WorkingDirectory": str(release),
        "FragmentPath": "/home/quant/.config/systemd/user/" + PAPER,
        "ExecStart": f"{{ path={python} ; argv[]={argv} ; ignore_errors=no }}",
    }
    item = Rig(release, proc, python, sha, [], unit)
    item.set_process()
    return item


def inspect(rig: Rig, *, unit: str = PAPER, manager: str = "user", sha: str | None = None) -> dict:
    return runtime.verify_unit_release(
        unit,
        expected_sha=rig.sha if sha is None else sha,
        manager=manager,
        release_roots=(rig.release.parent,),
        proc_root=rig.proc,
        runner=rig.runner,
    )


def test_independent_systemd_process_and_release_are_distinct(rig: Rig) -> None:
    result = inspect(rig)
    assert result["state"] == "VERIFIED", result
    assert result["configured"]["manager"] == "user"
    assert result["installed"]["revision"] == rig.sha
    assert result["observed"]["pid"] == rig.pid
    assert result["observed"]["process_start_ticks"] == START_TICKS
    assert result["observed"]["argv_sha256"]
    assert result["clock"]["boot_id"].endswith("0339")
    assert any("loaded application bytes" in x for x in result["limitations"])
    assert all(x[0] in {"systemctl", "git"} for x in rig.calls)


def test_counterfeit_configured_release_plus_unrelated_live_pid_is_mismatch(rig: Rig) -> None:
    rig.set_process(argv=[str(rig.python), "-m", "unrelated.worker"])
    result = inspect(rig)
    assert result["state"] == "MISMATCH"
    assert result["reason"] == "PROCESS_ARGV_MISMATCH"
    assert result["configured"]["main_pid"] == rig.pid
    assert result["installed"]["revision"] == rig.sha


def test_process_from_old_release_and_wrong_expected_sha_are_mismatches(rig: Rig) -> None:
    old = rig.release.parent / "old"
    old.mkdir()
    other_python = old / ".venv" / "bin" / "python"
    other_python.parent.mkdir(parents=True)
    other_python.symlink_to(Path(sys.executable).resolve())
    rig.set_process(
        argv=[str(other_python), "-m", "copytrade_pm.pm_cwsa_six_paper", "--poll-seconds", "5"]
    )
    assert inspect(rig)["state"] == "MISMATCH"
    rig.set_process()
    result = inspect(rig, sha="f" * 40)
    assert result["state"] == "MISMATCH"
    assert result["reason"] == "INSTALLED_RELEASE_SHA_DRIFT"


def test_inaccessible_proc_is_unknown_but_proven_stopped_is_not_running(rig: Rig) -> None:
    (rig.proc / str(rig.pid) / "cmdline").unlink()
    unknown = inspect(rig)
    assert unknown["state"] == "UNKNOWN"
    assert unknown["reason"] == "PROCESS_METADATA_UNAVAILABLE"
    assert unknown["limitations"]
    rig.props.update(ActiveState="inactive", MainPID="0")
    stopped = inspect(rig)
    assert stopped["state"] == "NOT_RUNNING"
    assert stopped["reason"] == "SYSTEMD_UNIT_STOPPED"


def test_mutable_branch_and_checkout_location_cannot_attest_release(rig: Rig) -> None:
    subprocess.run(["git", "-C", str(rig.release), "switch", "-q", "master"], check=True)
    assert inspect(rig)["state"] == "UNKNOWN"
    assert inspect(rig)["reason"] == "MUTABLE_RELEASE_NOT_ATTESTABLE"
    subprocess.run(["git", "-C", str(rig.release), "checkout", "-q", "--detach"], check=True)
    result = runtime.verify_unit_release(
        PAPER,
        expected_sha=rig.sha,
        manager="user",
        release_roots=(rig.release.parent / "unrelated",),
        proc_root=rig.proc,
        runner=rig.runner,
    )
    assert result["state"] == "UNKNOWN"
    assert result["reason"] == "UNTRUSTED_RELEASE_LOCATION"


def test_symlink_release_and_cgroup_drift_cannot_attest(rig: Rig) -> None:
    rig.set_process(cgroup=CGROUP + "-unrelated")
    assert inspect(rig)["state"] == "MISMATCH"
    rig.set_process()
    moved = rig.release.with_name("moved")
    rig.release.rename(moved)
    rig.release.symlink_to(moved, target_is_directory=True)
    assert inspect(rig)["state"] == "UNKNOWN"


def test_pid_reuse_and_restart_during_inspection_become_unknown(rig: Rig) -> None:
    original = rig.runner

    def reused_pid(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[0] == "systemctl" and sum(x[0] == "systemctl" for x in rig.calls) == 2:
            rig.set_process(ticks=START_TICKS + 100)
        return result

    reused = runtime.verify_unit_release(
        PAPER,
        expected_sha=rig.sha,
        manager="user",
        release_roots=(rig.release.parent,),
        proc_root=rig.proc,
        runner=reused_pid,
    )
    assert reused["state"] == "UNKNOWN"
    assert reused["reason"] == "PROCESS_IDENTITY_RACED"
    rig.set_process()
    rig.calls.clear()
    rig.alternate_props = {**rig.props, "InvocationID": "another-boot-session"}
    restarted = inspect(rig)
    assert restarted["state"] == "UNKNOWN"
    assert restarted["reason"] == "SYSTEMD_IDENTITY_RACED"


def test_interpreter_symlink_drift_during_inspection_cannot_attest(rig: Rig) -> None:
    original = rig.runner

    def changed_interpreter(argv, **kwargs):
        response = original(argv, **kwargs)
        if argv[0] == "systemctl" and sum(x[0] == "systemctl" for x in rig.calls) == 2:
            rig.python.unlink()
            rig.python.symlink_to("/bin/sh")
        return response

    checked = runtime.verify_unit_release(
        PAPER,
        expected_sha=rig.sha,
        manager="user",
        release_roots=(rig.release.parent,),
        proc_root=rig.proc,
        runner=changed_interpreter,
    )
    assert checked["state"] == "UNKNOWN"
    assert checked["reason"] == "INSTALLED_EXECUTABLE_SYMLINK_RACED"


def test_scoped_v4_system_and_chapter2_user_manager_only(rig: Rig) -> None:
    rig.props["Id"] = V4
    rig.props["ControlGroup"] = "/system.slice/" + V4
    rig.props["ExecStart"] = (
        f"{{ path={rig.python} ; argv[]={rig.python} -m "
        f"copytrade_pm.pm_forward_protected_ops worker --portfolio P1 "
        f"--revision {rig.sha} --release {rig.release} ; ignore_errors=no }}"
    )
    rig.set_process(
        argv=[
            str(rig.python),
            "-m",
            "copytrade_pm.pm_forward_protected_ops",
            "worker",
            "--portfolio",
            "P1",
            "--revision",
            rig.sha,
            "--release",
            str(rig.release),
        ],
        cgroup="/system.slice/" + V4,
    )
    v4 = inspect(rig, unit=V4, manager="system")
    assert v4["state"] == "VERIFIED", v4
    with pytest.raises(ValueError, match="SCOPE"):
        inspect(rig, unit=PAPER, manager="system")


def test_chapter2_source_has_independent_policy_and_release_scope(rig: Rig) -> None:
    rig.props.update(
        Id=SOURCE,
        ControlGroup=CGROUP.replace(PAPER, SOURCE),
        ExecStart=(
            f"{{ path={rig.python} ; argv[]={rig.python} -m "
            "copytrade_pm.pm_v4_selected_positions --source-mode CHECKPOINT_REST_V3"
            " ; ignore_errors=no }"
        ),
    )
    rig.set_process(
        argv=[
            str(rig.python),
            "-m",
            "copytrade_pm.pm_v4_selected_positions",
            "--source-mode",
            "CHECKPOINT_REST_V3",
        ],
        cgroup=rig.props["ControlGroup"],
    )
    assert inspect(rig, unit=SOURCE)["state"] == "VERIFIED"
    rig.props["ExecStart"] = rig.props["ExecStart"].replace("CHECKPOINT_REST_V3", "OTHER")
    assert inspect(rig, unit=SOURCE)["reason"] == "UNIT_SOURCE_POLICY_MISMATCH"


def test_v4_legacy_user_manager_is_explicit_not_inferred(rig: Rig) -> None:
    rig.props.update(
        Id=V4,
        ControlGroup=CGROUP.replace(PAPER, V4),
        ExecStart=(
            f"{{ path={rig.python} ; argv[]={rig.python} -m "
            f"copytrade_pm.pm_forward_protected_ops worker --portfolio P1 "
            f"--revision {rig.sha} --release {rig.release} ; ignore_errors=no }}"
        ),
    )
    rig.set_process(
        argv=[
            str(rig.python),
            "-m",
            "copytrade_pm.pm_forward_protected_ops",
            "worker",
            "--portfolio",
            "P1",
            "--revision",
            rig.sha,
            "--release",
            str(rig.release),
        ],
        cgroup=rig.props["ControlGroup"],
    )
    assert inspect(rig, unit=V4, manager="user")["state"] == "VERIFIED"
    rig.props["ExecStart"] = rig.props["ExecStart"].replace("worker --portfolio P1", "watchdog")
    assert inspect(rig, unit=V4, manager="user")["reason"] == "UNIT_APPLICATION_ROLE_MISMATCH"


def test_process_start_clock_or_tracked_file_writability_never_passes(rig: Rig) -> None:
    rig.set_process(ticks=START_TICKS + 3000)
    assert inspect(rig)["reason"] == "PROCESS_START_TIME_MISMATCH"
    rig.set_process()
    file = rig.release / "src/copytrade_pm/__init__.py"
    file.chmod(0o666)
    assert inspect(rig)["reason"] == "MUTABLE_RELEASE_NOT_ATTESTABLE"


def test_chapter2_gate_maps_liveness_unknown_and_mismatch_correctly(monkeypatch, rig: Rig) -> None:
    original = runtime.verify_unit_release
    monkeypatch.setattr(
        chapter2.runtime,
        "verify_unit_release",
        lambda *a, **k: original(
            PAPER,
            expected_sha=rig.sha,
            manager="user",
            release_roots=(rig.release.parent,),
            proc_root=rig.proc,
            runner=rig.runner,
        ),
    )
    good = chapter2._unit(PAPER, rig.sha)
    assert good.state == "PASS"
    rig.set_process(argv=[str(rig.python), "-m", "fake.worker"])
    mismatched = chapter2._unit(PAPER, rig.sha)
    assert mismatched.state == "FAIL"
    assert mismatched.detail == "PROCESS_ARGV_MISMATCH"
    (rig.proc / str(rig.pid) / "cmdline").unlink()
    unknown = chapter2._unit(PAPER, rig.sha)
    assert unknown.state == "BLOCKED_EVIDENCE"
    assert (
        chapter2.assess_financial_runtime(
            service_active=None,
            signed_portfolios={"A"},
            finance_scans={},
            source_changes={},
            journal_cursors={},
            latest_source_checkpoint_ms=0,
        ).state
        == "BLOCKED_EVIDENCE"
    )
