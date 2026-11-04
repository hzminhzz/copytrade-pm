"""Owner-private, reversible registry release gate tests.

No production service operations, source DB mutations or network calls.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import importlib.util
from pathlib import Path
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


def test_preview_does_not_require_clean_worktree() -> None:
    repo = Path(__file__).resolve().parents[1]
    state = release.snapshot_state(repo, enforce_clean=False)
    assert len(state["revision"]) == 40
    assert state["files"]["src/copytrade_pm/wallet_registry.py"] == registry.digest(
        repo / "src/copytrade_pm/wallet_registry.py"
    )
