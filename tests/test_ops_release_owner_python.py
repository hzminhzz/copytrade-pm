"""Release-only Ops checks: locked owner CLI and dirty worktree refusal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import deploy_ops_control_center as ops


def test_unit_pins_owner_to_its_own_immutable_release(tmp_path: Path):
    release = tmp_path / "ops-control-center-aabbccddeeff"
    sha = "aabbccddeeff" + "0" * 28
    unit = ops.service_unit(release, sha)
    assert f"WorkingDirectory={release}" in unit
    assert f"Environment=COPYTRADE_OPS_RELEASE_SHA={sha}" in unit
    assert f"Environment=COPYTRADE_OPS_OWNER_PYTHON={release}/.venv/bin/python" in unit
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit
    assert (
        f"ExecStart=/usr/bin/python3 {release}/scripts/dashboard_server.py "
        "--port 8888 --bind 127.0.0.1"
    ) in unit
    assert "NO_TRADE" in unit
    assert "Guardian" not in unit


@pytest.mark.parametrize(
    "dirty_status",
    [" M scripts/dashboard_server.py", "?? scripts/unreviewed_owner.py"],
)
def test_reused_release_with_tracked_or_untracked_changes_rejected_before_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dirty_status: str
):
    sha = "a" * 40
    release = tmp_path / f"ops-control-center-{sha[:12]}"
    release.mkdir()
    monkeypatch.setattr(ops, "RELEASES", tmp_path)
    monkeypatch.setattr(ops, "full_sha_from", lambda _: sha)
    calls = []

    def fake_run(*command, cwd=None, timeout=120):
        calls.append(command)
        if command[:3] == ("git", "status", "--porcelain"):
            return dirty_status
        pytest.fail(f"Unexpected command after dirty-release refusal: {command!r}")

    monkeypatch.setattr(ops, "run", fake_run)
    with pytest.raises(RuntimeError, match="modified or untracked source files"):
        ops.deploy(sha, apply=True)
    assert calls == [("git", "status", "--porcelain", "--untracked-files=all")]


def test_owner_runtime_installs_only_locked_core_and_smoke_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    release = tmp_path / "pinned-release"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("fixture executable", encoding="utf-8")
    python.chmod(0o700)
    calls = []

    def fake_run(*command, cwd=None, timeout=120):
        calls.append((command, cwd, timeout))
        return ""

    monkeypatch.setattr(ops, "run", fake_run)
    assert ops.prepare_owner_runtime(release) == python
    assert calls[0] == (
        ("uv", "sync", "--locked", "--no-dev", "--no-editable", "--no-progress"),
        release,
        240,
    )
    assert calls[1][0][0] == str(python)
    assert "pydantic" in calls[1][0][2]
    assert str(release / ".venv") in calls[1][0][2]
    assert calls[2] == (
        (
            str(python),
            "-m",
            "copytrade_pm.pm_operations",
            "cwsa",
            "chapter2",
            "site-view",
            "--help",
        ),
        release,
        30,
    )


def test_owner_runtime_fails_closed_if_interpreter_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(ops, "run", lambda *args, **kwargs: "")
    with pytest.raises(RuntimeError, match="unavailable"):
        ops.prepare_owner_runtime(tmp_path)


def test_preview_has_no_release_side_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
):
    monkeypatch.setattr(ops, "RELEASES", tmp_path)
    monkeypatch.setattr(ops, "run", lambda *args, **kwargs: pytest.fail("preview executed command"))
    sha = "b" * 40
    ops.deploy(sha, apply=False)
    data = json.loads(capsys.readouterr().out)
    assert data["action"] == "preview"
    assert data["commit"] == sha
    assert data["mode"] == "NO_TRADE"
