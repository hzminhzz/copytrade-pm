"""Guarded paper operations: liveness, HALT persistence and no financial effects."""

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from copytrade_pm.pm_forward_protected_ops import (
    StandbyBlocked,
    inspect_worker,
    watchdog_cycle,
    worker_cycle,
)
from copytrade_pm.pm_forward_protected_units import (
    UNIT_NAMES,
    render_system_units,
    stage_uninstalled_bundle,
    verify_uninstalled_bundle,
)

REV = "a" * 40


def roots(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    all_roots = {key: tmp_path / key.lower() for key in ("P1", "P14")}
    guard = tmp_path / "watchdog"
    for item in (*all_roots.values(), guard):
        item.mkdir(mode=0o700)
    return guard, all_roots


def standby_two(tmp_path):
    guard, all_roots = roots(tmp_path)
    now = datetime.now(UTC).isoformat()
    for portfolio, root in all_roots.items():
        worker_cycle(
            portfolio=portfolio, root=root, revision=REV, release=tmp_path, strict=False, as_of=now
        )
    return guard, all_roots, now


def test_guarded_standby_does_not_create_financial_journals(tmp_path):
    guard, all_roots, now = standby_two(tmp_path)
    for name, root in all_roots.items():
        health = inspect_worker(
            root,
            portfolio=name,
            revision=REV,
            as_of=now,
            require_independent_uid=False,
        )
        assert health["status"] == "ALIVE_STANDBY_ONLY"
        raw = json.loads((root / "standby-heartbeat.json").read_text())
        assert raw["paper_running"] is False
        assert raw["protected_worker_attested"] is False
        assert raw["financial_events_created_by_this_process"] == 0
        assert raw["order_route"] == "NONE"
        assert raw["protection_mode"] == "UNPROTECTED_CANARY"
        assert not list(root.glob("*.sqlite*"))
    result = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=now,
    )
    assert result["status"] == "STANDBY_MONITORED"
    assert result["paper_running"] is False
    assert not (guard / "halt-latch.json").exists()


def test_watchdog_detects_stale_and_persists_halt_after_worker_recovery(tmp_path):
    guard, all_roots, now = standby_two(tmp_path)
    stale = (datetime.fromisoformat(now) + timedelta(seconds=91)).isoformat()
    failed = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=stale,
    )
    assert failed["status"] == "HALT_LATCHED"
    assert all(x["status"] == "HALT" for x in failed["workers"].values())
    assert (guard / "halt-latch.json").exists()
    for portfolio, root in all_roots.items():
        worker_cycle(
            portfolio=portfolio,
            root=root,
            revision=REV,
            release=tmp_path,
            strict=False,
            as_of=stale,
        )
    retried = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=stale,
    )
    assert all(x["status"] == "ALIVE_STANDBY_ONLY" for x in retried["workers"].values())
    assert retried["status"] == "HALT_LATCHED"
    assert retried["manual_reset_required"] is True


def test_watchdog_fails_closed_on_missing_and_modified_receipts(tmp_path):
    guard, all_roots, now = standby_two(tmp_path)
    file = all_roots["P1"] / "standby-heartbeat.json"
    envelope = json.loads(file.read_text())
    envelope["process_identity"]["start_ticks"] += 1
    file.write_text(json.dumps(envelope))
    bad = inspect_worker(
        all_roots["P1"], portfolio="P1", revision=REV, as_of=now, require_independent_uid=False
    )
    assert bad["status"] == "HALT"
    assert "HEARTBEAT_CORRUPT" in bad["reasons"]
    file.write_text("[]")
    array = inspect_worker(
        all_roots["P1"], portfolio="P1", revision=REV, as_of=now, require_independent_uid=False
    )
    assert array["status"] == "HALT"
    file.unlink()
    lost = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=now,
    )
    assert lost["status"] == "HALT_LATCHED"
    assert lost["workers"]["P1"]["status"] == "HALT"
    assert lost["workers"]["P14"]["status"] == "ALIVE_STANDBY_ONLY"


def test_separate_watchdog_identity_is_mandatory_for_strict_inspection(tmp_path):
    _, all_roots, now = standby_two(tmp_path)
    result = inspect_worker(
        all_roots["P1"], portfolio="P1", revision=REV, as_of=now, require_independent_uid=True
    )
    assert "WATCHDOG_SHARES_WORKER_UID" in result["reasons"]
    with pytest.raises(StandbyBlocked, match="RELEASE_NOT_EXACTLY_PINNED"):
        worker_cycle(
            portfolio="P1", root=all_roots["P1"], revision=REV, release=tmp_path, strict=True
        )
    with pytest.raises(StandbyBlocked, match="RELEASE_NOT_EXACTLY_PINNED"):
        watchdog_cycle(
            watchdog_root=tmp_path / "watchdog",
            worker_roots=all_roots,
            revision=REV,
            release=tmp_path,
            strict=True,
        )


def test_private_state_rejects_world_or_group_writable_directories(tmp_path):
    state = tmp_path / "public"
    state.mkdir(mode=0o777)
    os.chmod(state, 0o777)
    with pytest.raises(StandbyBlocked, match="UNSAFE_PERMISSIONS"):
        worker_cycle(portfolio="P1", root=state, revision=REV, release=tmp_path, strict=False)


def test_worker_cli_one_shot_no_network_or_financial_effects(tmp_path):
    root = tmp_path / "p1"
    root.mkdir(mode=0o700)
    execution = subprocess.run(
        [
            sys.executable,
            "-m",
            "copytrade_pm.pm_forward_protected_ops",
            "worker",
            "--portfolio",
            "P1",
            "--release",
            str(tmp_path),
            "--state-root",
            str(root),
            "--revision",
            REV,
            "--unprotected-canary",
            "--once",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=12,
    )
    report = json.loads(execution.stdout)
    assert report["paper_running"] is False
    assert report["order_route"] == "NONE"
    assert (root / "standby-heartbeat.json").is_file()


def test_actual_sigkill_then_restart_never_auto_resets_halt(tmp_path):
    guard, all_roots, _ = standby_two(tmp_path)
    command = [
        sys.executable,
        "-m",
        "copytrade_pm.pm_forward_protected_ops",
        "worker",
        "--portfolio",
        "P1",
        "--release",
        str(tmp_path),
        "--state-root",
        str(all_roots["P1"]),
        "--revision",
        REV,
        "--interval-seconds",
        "2",
        "--unprotected-canary",
    ]
    child = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        expected = None
        for _ in range(100):
            report = inspect_worker(
                all_roots["P1"], portfolio="P1", revision=REV, require_independent_uid=False
            )
            recorded = json.loads((all_roots["P1"] / "standby-heartbeat.json").read_text())
            if (
                report["status"] == "ALIVE_STANDBY_ONLY"
                and recorded["process_identity"]["pid"] == child.pid
            ):
                expected = report
                break
            time.sleep(0.03)
        assert expected is not None
        child.kill()
        child.wait(timeout=5)
        check = inspect_worker(
            all_roots["P1"], portfolio="P1", revision=REV, require_independent_uid=False
        )
        assert check["status"] == "HALT"
        latched = watchdog_cycle(
            watchdog_root=guard,
            worker_roots=all_roots,
            revision=REV,
            release=tmp_path,
            strict=False,
        )
        assert latched["status"] == "HALT_LATCHED"
        replacement = subprocess.run(
            [*command, "--once"], capture_output=True, text=True, timeout=10, check=True
        )
        assert json.loads(replacement.stdout)["paper_running"] is False
        result = watchdog_cycle(
            watchdog_root=guard,
            worker_roots=all_roots,
            revision=REV,
            release=tmp_path,
            strict=False,
        )
        assert result["status"] == "HALT_LATCHED"
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_same_watchdog_process_can_refresh_without_false_restart_latch(tmp_path):
    guard, all_roots, _ = standby_two(tmp_path)
    first = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
    )
    second = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
    )
    assert first["status"] == second["status"] == "STANDBY_MONITORED"
    assert second["watchdog_recovery_reasons"] == []
    assert second["alert_required"] is False
    assert second["feed_evidence_status"] == "UNATTESTED_NO_INDEPENDENT_SOURCE_OR_MARKET"
    assert second["paper_running"] is False


def test_actual_watchdog_process_restart_latches_manual_halt(tmp_path):
    guard, all_roots, _ = standby_two(tmp_path)
    args = [
        sys.executable,
        "-m",
        "copytrade_pm.pm_forward_protected_ops",
        "watchdog",
        "--release",
        str(tmp_path),
        "--state-root",
        str(guard),
        "--p1-root",
        str(all_roots["P1"]),
        "--p14-root",
        str(all_roots["P14"]),
        "--revision",
        REV,
        "--unprotected-canary",
        "--once",
    ]
    initial = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(initial.stdout)["status"] == "STANDBY_MONITORED"
    restarted = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    report = json.loads(restarted.stdout)
    assert report["status"] == "HALT_LATCHED"
    assert report["alert_required"] is True
    assert report["watchdog_recovery_reasons"] == ["WATCHDOG_PROCESS_EPOCH_CHANGED"]
    latch = json.loads((guard / "halt-latch.json").read_text())
    assert latch["manual_reset_required"] is True
    assert latch["reasons"]["watchdog"] == ["WATCHDOG_PROCESS_EPOCH_CHANGED"]
    # A third process can never silently treat restored child PIDs as admission.
    third = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(third.stdout)["status"] == "HALT_LATCHED"
    assert not list(tmp_path.rglob("*.sqlite*"))


def test_tampered_watchdog_previous_status_forces_halt(tmp_path):
    guard, all_roots, now = standby_two(tmp_path)
    watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=now,
    )
    previous = guard / "watchdog-status.json"
    payload = json.loads(previous.read_text())
    payload["paper_running"] = True
    previous.write_text(json.dumps(payload))
    result = watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=now,
    )
    assert result["status"] == "HALT_LATCHED"
    assert result["watchdog_recovery_reasons"] == ["WATCHDOG_PREVIOUS_STATUS_CORRUPT"]
    assert json.loads((guard / "halt-latch.json").read_text())["order_route"] == "NONE"


def test_corrupt_or_group_writable_halt_record_cannot_be_cleared(tmp_path):
    guard, all_roots, now = standby_two(tmp_path)
    stale = (datetime.fromisoformat(now) + timedelta(seconds=91)).isoformat()
    watchdog_cycle(
        watchdog_root=guard,
        worker_roots=all_roots,
        revision=REV,
        release=tmp_path,
        strict=False,
        as_of=stale,
    )
    latch = guard / "halt-latch.json"
    payload = json.loads(latch.read_text())
    payload["manual_reset_required"] = False
    latch.write_text(json.dumps(payload))
    with pytest.raises(StandbyBlocked, match="WATCHDOG_LATCH_INTEGRITY_FAILURE"):
        watchdog_cycle(
            watchdog_root=guard,
            worker_roots=all_roots,
            revision=REV,
            release=tmp_path,
            strict=False,
            as_of=stale,
        )
    assert json.loads((guard / "watchdog-status.json").read_text())["status"] == "HALT_LATCHED"
    os.chmod(latch, 0o660)
    with pytest.raises(StandbyBlocked, match="WATCHDOG_LATCH_FILE_UNSAFE"):
        watchdog_cycle(
            watchdog_root=guard,
            worker_roots=all_roots,
            revision=REV,
            release=tmp_path,
            strict=False,
            as_of=stale,
        )


def test_systemd_bundle_pin_sandbox_and_no_install(tmp_path):
    files = render_system_units(REV)
    assert set(files) == set(UNIT_NAMES)
    for name, unit in files.items():
        assert "/opt/copytrade-paper/releases/" + REV in unit
        assert "IPAddressDeny=any" in unit
        assert "ProtectSystem=strict" in unit
        assert "NoNewPrivileges=yes" in unit
        assert "Restart=on-failure" in unit
        assert "RootDirectory=" not in unit
        assert "--unprotected-canary" not in unit
        assert "copytrade_pm.pm_forward_protected_ops" in unit
        assert "User=copytrade-paper-" in unit
    assert "Group=copytrade-paper-monitor" in files[UNIT_NAMES[2]]
    parent = tmp_path / "stage"
    parent.mkdir(mode=0o700)
    staged = parent / "candidate"
    manifest = stage_uninstalled_bundle(staged, revision=REV)
    assert manifest["services_started"] is False
    verified = verify_uninstalled_bundle(staged)
    assert verified["status"] == "STAGED_ONLY_NOT_INSTALLED"
    assert verified["unit_count"] == 3
    with pytest.raises(FileExistsError):
        stage_uninstalled_bundle(staged, revision=REV)
    file = staged / UNIT_NAMES[0]
    os.chmod(file, 0o600)
    file.write_text(file.read_text() + "TAMPER\n")
    with pytest.raises(ValueError, match="CHANGED"):
        verify_uninstalled_bundle(staged)


def test_render_rejects_non_sha_and_bundle_requires_private_parent(tmp_path):
    with pytest.raises(ValueError, match="REVISION_INVALID"):
        render_system_units("main")
    parent = tmp_path / "staging"
    parent.mkdir(mode=0o700)
    os.chmod(parent, 0o755)
    with pytest.raises(ValueError, match="PARENT_NOT_PRIVATE"):
        stage_uninstalled_bundle(parent / "bundle", revision=REV)
