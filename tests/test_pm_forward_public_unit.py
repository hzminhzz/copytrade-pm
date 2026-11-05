"""Public observer unit can be installed only from a verified pinned release.

These tests use a fake release verifier; no systemctl or broker is invoked.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import stat

import pytest

from copytrade_pm import pm_forward_public_unit as unit


@pytest.fixture
def env(tmp_path: Path) -> dict:
    revision = "a" * 40
    releases = tmp_path / "releases"
    releases.mkdir(mode=0o700)
    release = releases / revision
    release.mkdir(mode=0o700)
    (release / ".venv/bin").mkdir(parents=True)
    (release / "scripts").mkdir()
    (release / "scripts/registry_release.py").write_text("# synthetic verifier\n")
    (release / ".venv/bin/python").write_text("# synthetic executable\n")
    (release / ".venv/bin/python").chmod(0o700)
    current = tmp_path / "current"
    current.symlink_to(release, target_is_directory=True)
    registry = tmp_path / "registry.sqlite"
    registry.write_bytes(b"synthetic registry identity")
    registry.chmod(0o600)
    primary = tmp_path / "primary"
    primary.mkdir(mode=0o775)
    secondary = tmp_path / "secondary"
    secondary.mkdir(mode=0o775)
    state = tmp_path / "private-observer"
    state.mkdir(mode=0o700)
    units = tmp_path / "units"
    units.mkdir(mode=0o750)
    return {
        "revision": revision,
        "releases_root": releases,
        "current": current,
        "registry": registry,
        "primary": primary,
        "secondary": secondary,
        "state": state,
        "unit_dir": units,
    }


def _runner(args: list[str], **kwargs: object) -> SimpleNamespace:
    if args[-1] == "verify":
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "result": "ACTIVE_READ_ONLY_VERIFIED",
                    "revision": "a" * 40,
                    "registry_timer": "NOT_INSTALLED",
                    "source": {
                        "trading_authorized": False,
                        "source_manifest_sha256": "b" * 64,
                    },
                }
            ),
            stderr="",
        )
    assert args[1] == "-c" and "ccxt.pro" in args[2]
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _plan(env: dict) -> tuple[dict, str]:
    return unit.plan(**env, runner=_runner)


def test_render_exact_pinned_no_order_unit(env: dict) -> None:
    report, text = _plan(env)
    assert report["status"] == "READY_UNPROTECTED_PUBLIC_OBSERVER_ONLY"
    assert report["release_verified"] == "ACTIVE_READ_ONLY_VERIFIED"
    assert report["order_route"] == "NONE"
    assert report["protected_worker_attested"] is False
    assert report["financial_events_allowed"] is False
    assert report["systemd_mutated"] is False
    assert report["trading_authorized"] is False
    assert report["historical_locator_source_integrity_independent"] is False
    assert "copytrade_pm.pm_forward_observer" in text
    assert f"/releases/{'a' * 40}/.venv/bin/python" in text
    assert "current/.venv/bin/python" not in text
    assert "Restart=on-failure" in text
    assert "--epochs 0" in text
    assert "--market-shard-size 8" in text
    assert "PYTHONDONTWRITEBYTECODE=1" in text
    assert "broker" not in text.lower()
    assert "--apply" not in text


def test_install_only_observer_unit_and_reject_drift(env: dict) -> None:
    report, content = _plan(env)
    target = Path(report["unit_path"])
    other = env["unit_dir"] / "copytrade-tracker.service"
    other.write_bytes(b"protected existing service")
    assert unit.install(target, content) == "INSTALLED_NOT_STARTED"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text() == content
    assert unit.install(target, content) == "EXISTS_IDENTICAL"
    assert _plan(env)[0]["existing"] == "SAME_CONTENT"
    assert other.read_bytes() == b"protected existing service"
    with pytest.raises(unit.ObserverUnitBlocked, match="CONFLICTING_EXISTING_OBSERVER_UNIT"):
        unit.install(target, content + "\n")
    assert target.read_text() == content


def test_missing_release_or_wrong_pinned_pointer_fails_closed(env: dict) -> None:
    with pytest.raises(unit.ObserverUnitBlocked, match="INVALID_PINNED_REVISION"):
        unit.plan(**{**env, "revision": "a" * 39}, runner=_runner)
    with pytest.raises(unit.ObserverUnitBlocked, match="INVALID_PINNED_REVISION"):
        unit.plan(**{**env, "revision": "../" + "a" * 40}, runner=_runner)
    env["current"].unlink()
    env["current"].symlink_to(env["releases_root"], target_is_directory=True)
    with pytest.raises(unit.ObserverUnitBlocked, match="REGISTRY_RELEASE_POINTER_NOT_PINNED"):
        _plan(env)


def test_candidate_requires_verified_release_and_extras(env: dict) -> None:
    def failed_verify(argv: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="{}", stderr="")

    with pytest.raises(unit.ObserverUnitBlocked, match="INSTALLED_REGISTRY_RELEASE_NOT_VERIFIED"):
        unit.plan(**env, runner=failed_verify)

    def no_extras(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[-1] == "verify":
            return _runner(argv, **kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="ModuleNotFoundError")

    with pytest.raises(unit.ObserverUnitBlocked, match="PINNED_PUBLIC_OBSERVER_EXTRAS_MISSING"):
        unit.plan(**env, runner=no_extras)

    def unauthorized(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[-1] == "verify":
            result = json.loads(_runner(argv).stdout)
            result["source"]["trading_authorized"] = True
            return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="")
        return _runner(argv, **kwargs)

    with pytest.raises(unit.ObserverUnitBlocked, match="PINNED_RELEASE_AUTHORITY_MISMATCH"):
        unit.plan(**env, runner=unauthorized)

    def missing_manifest_sha(argv: list[str], **kwargs: object) -> SimpleNamespace:
        if argv[-1] == "verify":
            result = json.loads(_runner(argv).stdout)
            result["source"].pop("source_manifest_sha256")
            return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="")
        return _runner(argv, **kwargs)

    with pytest.raises(unit.ObserverUnitBlocked, match="PINNED_RELEASE_AUTHORITY_MISMATCH"):
        unit.plan(**env, runner=missing_manifest_sha)


def test_reject_unsafe_unit_dirs_state_and_registry(env: dict) -> None:
    env["state"].chmod(0o750)
    with pytest.raises(unit.ObserverUnitBlocked, match="PRIVATE_OBSERVER_ROOT_NOT_0700"):
        _plan(env)
    env["state"].chmod(0o700)
    env["registry"].unlink()
    env["registry"].symlink_to(env["unit_dir"], target_is_directory=True)
    with pytest.raises(unit.ObserverUnitBlocked, match="UNAVAILABLE_OR_LINKED_UNIT_INPUT"):
        _plan(env)


def test_source_can_be_group_writable_but_not_world_writable(env: dict) -> None:
    report, _ = _plan(env)
    assert not report["historical_locator_source_integrity_independent"]
    env["primary"].chmod(0o777)
    with pytest.raises(unit.ObserverUnitBlocked, match="UNIT_INPUT_GROUP_WORLD_WRITABLE"):
        _plan(env)


def test_reject_candidate_that_changes_an_existing_unit(env: dict) -> None:
    report, _content = _plan(env)
    target = Path(report["unit_path"])
    target.write_text("arbitrary old contents")
    with pytest.raises(unit.ObserverUnitBlocked, match="CONFLICTING_EXISTING_OBSERVER_UNIT"):
        _plan(env)
    target.unlink()
    target.symlink_to(env["registry"])
    with pytest.raises(unit.ObserverUnitBlocked, match="USER_OBSERVER_UNIT_SYMLINK"):
        _plan(env)


def test_unit_status_does_not_claim_protected_finance(env: dict) -> None:
    report, rendered = _plan(env)
    assert "NOT PAPER_RUNNING" in rendered
    assert report["service_started"] is False
    assert report["financial_events_allowed"] is False
    assert report["protected_worker_attested"] is False
    assert "copytrade-paper-p1.service" not in rendered
    assert "copytrade-paper-p14.service" not in rendered
    assert "copytrade-paper-watchdog.service" not in rendered


def test_atomic_install_failure_leaves_no_unit(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    report, rendered = _plan(env)
    destination = Path(report["unit_path"])

    def fail_link(*args: object, **kwargs: object) -> None:
        raise OSError("filesystem link failed")

    monkeypatch.setattr(unit.os, "link", fail_link)
    with pytest.raises(unit.ObserverUnitBlocked, match="PUBLIC_OBSERVER_UNIT_INSTALL_IO_FAILED"):
        unit.install(destination, rendered)
    assert not destination.exists()
    assert not list(env["unit_dir"].glob("*.pending"))


def test_installer_has_no_systemctl_api(env: dict) -> None:
    report, text = _plan(env)
    sentinel = "other data"
    other_file = env["unit_dir"] / "copytrade-ensemble.service"
    other_file.write_text(sentinel)
    unit.install(Path(report["unit_path"]), text)
    assert other_file.read_text() == sentinel
    assert not hasattr(unit, "start_unit")
