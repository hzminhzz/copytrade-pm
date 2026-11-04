"""Owner-private, reversible registry release gate tests.

No production service operations, source DB mutations or network calls.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import sqlite3
import stat

import pytest

from copytrade_pm import wallet_registry as registry
from test_wallet_registry import fixture


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "registry_release.py"
SPEC = importlib.util.spec_from_file_location("wallet_registry_release_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_current_pointer_atomic_activation_and_rollback_without_service_mutation(
    tmp_path: Path,
) -> None:
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    a = "1" * 40
    b = "2" * 40
    for version in (a, b):
        (control / "releases" / version).mkdir(parents=True)
    release.atomic_current(a, control=control)
    assert release.active_revision(control) == a
    release.atomic_current(b, control=control)
    assert release.active_revision(control) == b
    assert (control / "current").is_symlink()
    release.atomic_current(a, control=control)
    assert release.active_revision(control) == a
    release.atomic_current(None, control=control)
    assert release.active_revision(control) is None
    with pytest.raises(ValueError, match="invalid release"):
        release.atomic_current("../../other", control=control)
    assert release.active_revision(control) is None


def test_release_rejects_pointer_tampering(tmp_path: Path) -> None:
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    (control / "current").symlink_to("../../external")
    with pytest.raises(ValueError, match="unexpected release pointer"):
        release.active_revision(control)
    (control / "current").unlink()
    (control / "current").write_text("not an owned symlink")
    with pytest.raises(ValueError, match="not a symlink"):
        release.atomic_current("a" * 40, control=control)


def test_rollback_to_prior_release_preserves_pinned_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "private" / "control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    releases = control / "releases"
    releases.mkdir(mode=0o700)
    a, b = "a" * 40, "b" * 40
    file_hashes = {}
    for revision in (a, b):
        package = releases / revision
        package.mkdir(mode=0o700)
        (package / "source.py").write_text(revision)
        file_hashes[revision] = {"source.py": sha256(revision.encode()).hexdigest()}
    release.atomic_current(b, control=control)
    state = control / "release-state.json"
    state.write_text(
        json.dumps(
            {
                "current": b,
                "previous": a,
                "files": file_hashes[b],
                "release_files": file_hashes,
            }
        )
    )
    state.chmod(0o600)
    original_pointer = release.active_revision
    original_atomic = release.atomic_current
    original_private_dirs = release._private_dirs
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "RELEASES", releases)
    monkeypatch.setattr(release, "STATE", state)
    monkeypatch.setattr(release, "active_revision", lambda: original_pointer(control))
    monkeypatch.setattr(
        release, "atomic_current", lambda rev: original_atomic(rev, control=control)
    )
    monkeypatch.setattr(release, "_private_dirs", lambda: original_private_dirs(control))
    monkeypatch.setattr(release, "services", lambda: {"tracker": {"pid": "100"}})
    monkeypatch.setattr(release, "_installed_doctor", lambda _: None)
    monkeypatch.setattr(release, "readonly_source_health", lambda: {"source": "unchanged"})

    result = release.rollback()
    assert result["result"] == "POINTER_ROLLED_BACK"
    assert result["now_active"] == a
    assert release.verify()["revision"] == a
    assert release.verify()["result"] == "ACTIVE_READ_ONLY_VERIFIED"
    assert (releases / b).is_dir()
    assert (releases / a).is_dir()


def test_service_parity_catches_legacy_service_restart() -> None:
    previous = {
        "copytrade-tracker.service": {"active": "active", "pid": "42"},
    }
    release.service_parity(previous, previous)
    with pytest.raises(RuntimeError, match="service PID/state changed"):
        release.service_parity(
            previous,
            {
                "copytrade-tracker.service": {"active": "active", "pid": "43"},
            },
        )


def test_verified_archive_file_hash_fails_closed_if_modified(tmp_path: Path) -> None:
    location = tmp_path / "release"
    location.mkdir()
    (location / "src").mkdir()
    file = location / "src" / "program.py"
    file.write_bytes(b"trusted")
    pin = {
        "files": {"src/program.py": sha256(b"trusted").hexdigest()},
    }
    release.check_release(location, pin)
    file.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source SHA mismatch"):
        release.check_release(location, pin)


def test_private_control_has_owner_only_perms_and_fails_on_symlinks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "owner"
    root.mkdir(mode=0o700)
    control = root / "control"
    release._private_dirs(control)
    assert stat.S_IMODE(control.stat().st_mode) == 0o700
    assert stat.S_IMODE((control / "releases").stat().st_mode) == 0o700
    (root / "bad").symlink_to(control, target_is_directory=True)
    with pytest.raises(PermissionError, match="insecure"):
        release._private_dirs(root / "bad")
    root.chmod(0o755)
    with pytest.raises(PermissionError, match="insecure"):
        release._private_dirs(control)


def test_recovering_verified_backup_does_not_edit_live_inventory(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    database = tmp_path / "registry" / "wallet-registry.sqlite"
    registry.apply(database, snapshot, "2026-11-04T00:00:00+00:00")
    generation = registry.db_status(database)
    backup = tmp_path / "registry" / "backup" / "on-disk.sqlite"
    registry.backup(database, backup)
    with closing(sqlite3.connect(backup)) as backup_connection:
        assert backup_connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup_connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert registry.db_status(database) == generation
    assert registry.db_status(backup) == generation
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_release_pointer_and_metadata_recover_after_failing_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (control / "releases").mkdir(mode=0o700)
    old, new = "a" * 40, "b" * 40
    release.atomic_current(old, control=control)
    metadata = control / "release-state.json"
    previous = {"current": old, "previous": None, "mode": "ON_DEMAND_READ_ONLY_NO_TIMER"}
    metadata.write_text(json.dumps(previous))
    metadata.chmod(0o600)
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "STATE", metadata)
    pointer = release.atomic_current
    active = release.active_revision
    monkeypatch.setattr(release, "atomic_current", lambda rev: pointer(rev, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: active(control))
    writer = release._write_json_atomic
    attempts = []

    def fail_first(path: Path, contents: dict) -> None:
        attempts.append(contents)
        if len(attempts) == 1:
            raise OSError("injected metadata disk write failure")
        writer(path, contents)

    monkeypatch.setattr(release, "_write_json_atomic", fail_first)
    with pytest.raises(OSError, match="injected"):
        release.commit_release(new, {"current": new})
    assert active(control) == old
    assert json.loads(metadata.read_text()) == previous
    assert len(attempts) == 2


def test_release_pointer_and_metadata_recover_after_post_switch_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (control / "releases").mkdir(mode=0o700)
    old, new = "c" * 40, "d" * 40
    release.atomic_current(old, control=control)
    metadata = control / "release-state.json"
    previous = {"current": old, "previous": None}
    metadata.write_text(json.dumps(previous))
    metadata.chmod(0o600)
    pointer = release.atomic_current
    active = release.active_revision
    monkeypatch.setattr(release, "STATE", metadata)
    monkeypatch.setattr(release, "atomic_current", lambda rev: pointer(rev, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: active(control))

    def fail_doctor() -> None:
        raise RuntimeError("injected installed doctor failure")

    with pytest.raises(RuntimeError, match="injected"):
        release.commit_release(new, {"current": new}, after_switch=fail_doctor)
    assert active(control) == old
    assert json.loads(metadata.read_text()) == previous


def test_release_rejects_diverged_pointer_and_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    pointer = release.atomic_current
    active = release.active_revision
    release.atomic_current("b" * 40, control=control)
    metadata = control / "release-state.json"
    metadata.write_text(json.dumps({"current": "a" * 40}))
    metadata.chmod(0o600)
    monkeypatch.setattr(release, "STATE", metadata)
    monkeypatch.setattr(release, "atomic_current", lambda rev: pointer(rev, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: active(control))
    with pytest.raises(ValueError, match="diverged"):
        release.commit_release("c" * 40, {"current": "c" * 40})
    assert active(control) == "b" * 40


def test_operator_release_lock_rejects_concurrent_mutator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    monkeypatch.setattr(release, "CONTROL", control)
    with release.release_lock():
        with pytest.raises(RuntimeError, match="already in progress"):
            with release.release_lock():
                pass


def test_release_lock_rejects_symlink_and_nonprivate_lock_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (control / "releases").mkdir(mode=0o700)
    monkeypatch.setattr(release, "CONTROL", control)
    lock = control / "operator.lock"
    lock.symlink_to(tmp_path / "out-of-scope")
    with pytest.raises(OSError):
        with release.release_lock():
            pass
    lock.unlink()
    lock.write_text("owner")
    lock.chmod(0o644)
    with pytest.raises(PermissionError, match="owner-private"):
        with release.release_lock():
            pass


def test_crash_after_pointer_swap_can_repair_to_last_committed_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (control / "releases").mkdir(mode=0o700)
    committed, uncommitted = "a" * 40, "b" * 40
    pinned = control / "releases" / committed
    pinned.mkdir(mode=0o700)
    (pinned / "registry.py").write_bytes(b"pinned source")
    fingerprint = {"registry.py": sha256(b"pinned source").hexdigest()}
    (control / "releases" / uncommitted).mkdir(mode=0o700)
    release.atomic_current(uncommitted, control=control)
    metadata = control / "release-state.json"
    metadata.write_text(
        json.dumps(
            {
                "current": committed,
                "files": fingerprint,
                "previous": None,
            }
        )
    )
    metadata.chmod(0o600)
    pointer = release.atomic_current
    active = release.active_revision
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "STATE", metadata)
    monkeypatch.setattr(release, "RELEASES", control / "releases")
    monkeypatch.setattr(release, "atomic_current", lambda rev: pointer(rev, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: active(control))
    monkeypatch.setattr(release, "_installed_doctor", lambda _: None)
    monkeypatch.setattr(release, "readonly_source_health", lambda: {"source": "unchanged"})
    monkeypatch.setattr(release, "services", lambda: {"tracker": {"pid": "100"}})

    with pytest.raises(ValueError, match="mismatch"):
        release.verify()
    assert release.repair()["result"] == "LAST_COMMITTED_POINTER_RESTORED"
    assert active(control) == committed
    assert release.verify()["result"] == "ACTIVE_READ_ONLY_VERIFIED"
    # This repairs only the release pointer, without deleting the next
    # staged revision or modifying the authoritative inventory.
    assert (control / "releases" / uncommitted).is_dir()


def test_process_crash_between_pointer_and_state_is_repairable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (control / "releases").mkdir(mode=0o700)
    old, uncommitted = "e" * 40, "f" * 40
    old_root = control / "releases" / old
    old_root.mkdir(mode=0o700)
    (old_root / "checked.py").write_bytes(b"original")
    fingerprint = {"checked.py": sha256(b"original").hexdigest()}
    release.atomic_current(old, control=control)
    state = control / "release-state.json"
    original_state = {"current": old, "files": fingerprint}
    state.write_text(json.dumps(original_state))
    state.chmod(0o600)
    script = """
import importlib.util, os, pathlib, sys
spec=importlib.util.spec_from_file_location("reg_release_child",sys.argv[1])
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root=pathlib.Path(sys.argv[2])
module.CONTROL=root
module.STATE=root/"release-state.json"
orig_pointer=module.atomic_current
orig_revision=module.active_revision
module.atomic_current=lambda revision:orig_pointer(revision,control=root)
module.active_revision=lambda:orig_revision(root)
module.commit_release(sys.argv[3],{"current":sys.argv[3]},after_switch=lambda:os._exit(47))
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(SCRIPT), str(control), uncommitted],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert child.returncode == 47, child.stderr
    assert release.active_revision(control) == uncommitted
    assert json.loads(state.read_text()) == original_state

    pointer, revision = release.atomic_current, release.active_revision
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "RELEASES", control / "releases")
    monkeypatch.setattr(release, "STATE", state)
    monkeypatch.setattr(release, "atomic_current", lambda value: pointer(value, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: revision(control))
    monkeypatch.setattr(release, "services", lambda: {"tracker": {"pid": "100"}})
    with pytest.raises(ValueError, match="mismatch"):
        release.verify()
    assert release.repair()["result"] == "LAST_COMMITTED_POINTER_RESTORED"
    assert revision(control) == old
    assert json.loads(state.read_text()) == original_state


def test_pointer_repair_rejects_tampered_committed_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    (control / "releases").mkdir(mode=0o700)
    a, b = "a" * 40, "b" * 40
    pinned = control / "releases" / a
    pinned.mkdir(mode=0o700)
    (pinned / "registry.py").write_bytes(b"tampered")
    release.atomic_current(b, control=control)
    metadata = control / "release-state.json"
    metadata.write_text(
        json.dumps(
            {
                "current": a,
                "files": {"registry.py": sha256(b"trusted").hexdigest()},
            }
        )
    )
    metadata.chmod(0o600)
    pointer = release.atomic_current
    active = release.active_revision
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "STATE", metadata)
    monkeypatch.setattr(release, "RELEASES", control / "releases")
    monkeypatch.setattr(release, "atomic_current", lambda rev: pointer(rev, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: active(control))
    monkeypatch.setattr(release, "services", lambda: {"tracker": {"pid": "100"}})
    with pytest.raises(ValueError, match="source SHA mismatch"):
        release.repair()
    assert active(control) == b


def test_preview_does_not_require_clean_worktree() -> None:
    repo = Path(__file__).resolve().parents[1]
    state = release.snapshot_state(repo, enforce_clean=False)
    assert len(state["revision"]) == 40
    assert state["files"]["src/copytrade_pm/wallet_registry.py"] == registry.digest(
        repo / "src/copytrade_pm/wallet_registry.py"
    )
