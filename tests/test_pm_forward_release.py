"""Protected paper release preflight must never silently authorize cutover."""

import os
from pathlib import Path

from copytrade_pm.pm_forward_release import (
    protected_paper_preflight,
    read_only_user_service_inventory,
)


def test_coding_identity_cannot_assert_release_permissions(tmp_path: Path) -> None:
    release = tmp_path / "release"
    state = tmp_path / "state"
    release.mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    result = protected_paper_preflight(
        release_root=release,
        state_root=state,
        deployment_uid=os.geteuid(),
        state_uid=os.geteuid(),
    )
    assert result["status"] == "BLOCKED"
    assert result["order_route"] == "NONE"
    assert result["cutover_performed"] is False
    assert result["systemd_units_mutated"] is False
    assert "RELEASE_CODING_IDENTITY_CAN_MUTATE" in result["reasons"]
    assert "STATE_CODING_IDENTITY_CAN_MUTATE" in result["reasons"]
    assert "RELEASE_AND_FINANCIAL_STATE_SAME_OS_IDENTITY" in result["reasons"]
    assert "SUDO_DOCKER_PRIVILEGE_SEPARATION_UNVERIFIED" in result["reasons"]
    assert list(release.iterdir()) == list(state.iterdir()) == []


def test_service_inventory_uses_show_only_and_no_systemd_mutation() -> None:
    calls = []

    def fake_runner(args, **kwargs):
        calls.append(args)
        assert args[:3] == ["systemctl", "--user", "show"]
        assert kwargs["check"] is False
        assert kwargs["timeout"] <= 8
        assert not any(x in args for x in ("restart", "stop", "start", "daemon-reload"))

        class Result:
            returncode = 0
            stdout = (
                "Id=" + args[3] + "\n"
                "LoadState=loaded\nActiveState=active\nMainPID=100\nFragmentPath=/test/unit\n"
            )

        return Result()

    inventory = read_only_user_service_inventory(runner=fake_runner)
    assert inventory["status"] == "READ_ONLY_SNAPSHOT"
    assert inventory["service_mutations"] == 0
    assert inventory["protected_system_services_verified"] is False
    assert len(inventory["units"]) == len(calls) == 6
    assert inventory["units"][0]["unit"] == "copytrade-tracker.service"


def test_preflight_rejects_worktree_nested_and_symlink_paths(tmp_path: Path) -> None:
    releases = tmp_path / ".devspace" / "release"
    releases.mkdir(parents=True)
    state = releases / "state"
    state.mkdir()
    result = protected_paper_preflight(
        release_root=releases,
        state_root=state,
        deployment_uid=os.geteuid(),
        state_uid=os.geteuid(),
        allow_cutover=True,
    )
    assert result["status"] == "BLOCKED"
    assert "RELEASE_PATH_INSIDE_WRITABLE_WORKTREE" in result["reasons"]
    assert "STATE_PATH_INSIDE_WRITABLE_WORKTREE" in result["reasons"]
    assert "FINANCIAL_STATE_NESTED_UNDER_RELEASE" in result["reasons"]
    assert "EXTERNAL_SIGNED_CUTOVER_APPROVAL_NOT_VERIFIED" in result["reasons"]
    linked = tmp_path / "link"
    linked.symlink_to(releases, target_is_directory=True)
    symlinked = protected_paper_preflight(
        release_root=linked,
        state_root=state,
        deployment_uid=os.geteuid(),
        state_uid=os.geteuid(),
    )
    assert "RELEASE_PATH_SYMLINK" in symlinked["reasons"]
