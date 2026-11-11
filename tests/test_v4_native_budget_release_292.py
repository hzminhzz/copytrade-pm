"""Reversible 0911 SHADOW user-systemd pin planning with no actual service writes."""

from __future__ import annotations

from hashlib import sha256

import pytest

import scripts.v4_native_budget_release_292 as deploy


SHA = "a" * 40
BASE = "/home/quant/.local/share/copytrade/releases/v4-sqlite-292-dea28357/.venv/bin/python"


def _fixtures(tmp_path, monkeypatch):
    units = tmp_path / "user-unit"
    units.mkdir(mode=0o700)
    root = tmp_path / "releases"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(deploy, "UNIT_ROOT", units)
    monkeypatch.setattr(deploy, "ROOT", root)
    release = deploy._release(SHA)
    release.mkdir(mode=0o700)
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("fake-python")
    (release / "source.sha").write_text(SHA + "\n")
    monkeypatch.setattr(deploy, "_verify_release", lambda *_: None)
    for unit in deploy.UNITS:
        folder = units / (unit + ".d")
        folder.mkdir(mode=0o700)
        module = deploy.SOURCE_MODULE if unit == deploy.SOURCE else deploy.PAPER_MODULE
        old = folder / deploy.OLD_OVERRIDE
        old.write_text(
            deploy.DEPLOYED_SOURCE_MARKER
            + "\n[Service]\nExecStart=\nExecStart="
            + BASE
            + " "
            + module
            + " --registry-db /owner/registry.sqlite"
            + "\nWorkingDirectory=/owner/old-release\n"
        )
    states = {u: {"ActiveState": "failed", "MainPID": "0"} for u in deploy.UNITS}
    states["copytrade-v4-selected-positions-0811.service"] = {
        "ActiveState": "active",
        "MainPID": "3001",
    }
    monkeypatch.setattr(deploy, "_status", lambda unit: states[unit])
    calls = []
    monkeypatch.setattr(deploy, "_run", lambda argv, **kwargs: calls.append(argv) or None)
    return units, release, states, calls


def test_release_plan_requires_existing_sha_and_adds_0911_only(tmp_path, monkeypatch):
    units, release, states, calls = _fixtures(tmp_path, monkeypatch)
    plan = deploy.planned_units(SHA)
    assert len(plan) == 3
    assert set(plan) == set(deploy.UNITS)
    assert not any("0811" in path.name for path in units.rglob(deploy.NEW_OVERRIDE))
    for unit, item in plan.items():
        data = item["content"].decode()
        assert data.startswith(deploy.MARKER + SHA)
        assert "broker" not in data.lower()
        assert "--compact-evidence" not in data
        assert str(release / ".venv/bin/python") in data
        assert item["additive_sha256"] == sha256(item["content"]).hexdigest()
        if unit == deploy.SOURCE:
            assert "--native-user-budget 7 --native-rotation-seconds 420" in data
        else:
            assert "--native-user-budget" not in data
    with pytest.raises(ValueError, match="PIN_INVALID"):
        deploy._release("unknown")


def test_apply_then_rollback_preserves_90_and_original_finance(tmp_path, monkeypatch):
    units, release, states, calls = _fixtures(tmp_path, monkeypatch)
    original = {
        unit: (units / (unit + ".d") / deploy.OLD_OVERRIDE).read_bytes() for unit in deploy.UNITS
    }
    applied = deploy.apply(SHA)
    assert applied["phase"] == "PINNED_NO_START"
    assert applied["trading_authorized"] is False
    assert applied["no_service_started"] is True
    assert len(calls) == 1 and calls[0] == ["systemctl", "--user", "daemon-reload"]
    for unit in deploy.UNITS:
        dest = units / (unit + ".d") / deploy.NEW_OVERRIDE
        assert dest.is_file()
        assert dest.stat().st_mode & 0o777 == 0o600
        assert (units / (unit + ".d") / deploy.OLD_OVERRIDE).read_bytes() == original[unit]
    with pytest.raises(FileExistsError, match="ALREADY_PRESENT"):
        deploy.apply(SHA)

    rolled = deploy.rollback(SHA)
    assert rolled["removed_units"] == 3
    assert rolled["source_and_finance_journals_unchanged"] is True
    for unit in deploy.UNITS:
        assert not (units / (unit + ".d") / deploy.NEW_OVERRIDE).exists()
        assert (units / (unit + ".d") / deploy.OLD_OVERRIDE).read_bytes() == original[unit]


def test_unsafe_active_source_or_0811_down_refuses_unit_mutation(tmp_path, monkeypatch):
    units, release, states, calls = _fixtures(tmp_path, monkeypatch)
    states[deploy.SOURCE] = {"ActiveState": "active", "MainPID": "5002"}
    with pytest.raises(ValueError, match="REQUIRES_STOPPED"):
        deploy.apply(SHA)
    assert not list(units.rglob(deploy.NEW_OVERRIDE))
    states[deploy.SOURCE] = {"ActiveState": "inactive", "MainPID": "0"}
    states["copytrade-v4-selected-positions-0811.service"] = {
        "ActiveState": "failed",
        "MainPID": "0",
    }
    with pytest.raises(ValueError, match="UPSTREAM_NOT_HEALTHY"):
        deploy.apply(SHA)
    assert not list(units.rglob(deploy.NEW_OVERRIDE))


def test_unowned_additive_override_cannot_be_removed(tmp_path, monkeypatch):
    units, release, states, calls = _fixtures(tmp_path, monkeypatch)
    source_dir = units / (deploy.SOURCE + ".d")
    dest = source_dir / deploy.NEW_OVERRIDE
    dest.write_text("unowned override")
    with pytest.raises(ValueError, match="UNOWNED_OVERRIDE"):
        deploy.rollback(SHA)
    assert dest.read_text() == "unowned override"
