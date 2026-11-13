"""Regression tests proving pre-push and CI isolate git subprocess environments."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from copytrade_pm import pm_runtime_readonly as runtime


REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"
CI_SCRIPT = REPO_ROOT / "scripts" / "ci.sh"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=cwd,
        text=True,
        env=runtime.clean_git_env(),
    ).strip()


def _install_hook_and_stub_ci(repo: Path, capture_file: Path) -> None:
    hooks_dir = repo / ".githooks"
    scripts_dir = repo / "scripts"
    hooks_dir.mkdir(exist_ok=True)
    scripts_dir.mkdir(exist_ok=True)

    hook_dst = hooks_dir / "pre-push"
    shutil.copy2(PRE_PUSH_HOOK, hook_dst)
    hook_dst.chmod(hook_dst.stat().st_mode | stat.S_IXUSR)

    stub = scripts_dir / "ci.sh"
    stub.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import json, os, sys",
                "from pathlib import Path",
                f"keys = {sorted(runtime.GIT_LOCAL_ENV_VARS)!r}",
                "payload = {",
                '    "args": sys.argv[1:],',
                '    "cwd": os.getcwd(),',
                '    "git_env": {k: os.environ.get(k) for k in keys if k in os.environ},',
                "}",
                f"Path({str(capture_file)!r}).write_text(json.dumps(payload), encoding='utf-8')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)


def _init_repo_with_commit(repo: Path, canary: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "init",
    )
    canary.mkdir(parents=True, exist_ok=True)
    _git(canary, "init", "-q", "-b", "main")


def test_prepush_hook_scrubs_inherited_git_env_vars(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    canary = tmp_path / "canary"
    capture = tmp_path / "ci-env.json"
    _init_repo_with_commit(repo, canary)
    _install_hook_and_stub_ci(repo, capture)

    polluted_env = {
        **runtime.clean_git_env(),
        "GIT_DIR": str(canary / ".git"),
        "GIT_WORK_TREE": str(canary),
        "GIT_INDEX_FILE": str(canary / ".git" / "index"),
        "GIT_OBJECT_DIRECTORY": str(canary / ".git" / "objects"),
        "GIT_COMMON_DIR": str(canary / ".git"),
        "GIT_PREFIX": "nested/",
        "GIT_CONFIG_PARAMETERS": "'user.name=Spoof'",
        "GIT_CONFIG_COUNT": "1",
    }
    proc = subprocess.run(
        [str(repo / ".githooks" / "pre-push"), "origin", "https://example.invalid/repo.git"],
        cwd=repo,
        env=polluted_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    recorded = json.loads(capture.read_text(encoding="utf-8"))
    assert recorded["args"] == ["all"]
    assert Path(recorded["cwd"]).resolve() == repo.resolve()
    assert recorded["git_env"] == {}


def test_real_git_push_from_worktree_invokes_prepush_without_git_env(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream.git"
    upstream.mkdir()
    _git(upstream, "init", "-q", "--bare")

    main_repo = tmp_path / "main-repo"
    canary = tmp_path / "canary"
    capture = tmp_path / "worktree-ci-env.json"
    _init_repo_with_commit(main_repo, canary)
    _install_hook_and_stub_ci(main_repo, capture)
    _git(main_repo, "add", ".githooks", "scripts")
    _git(
        main_repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "add hook and ci stub",
    )
    _git(main_repo, "remote", "add", "origin", str(upstream))
    _git(main_repo, "push", "-q", "-u", "origin", "main")

    worktree = tmp_path / "linked-wt"
    _git(main_repo, "worktree", "add", "-q", "-b", "feat/hook-test", str(worktree), "main")
    (worktree / "tracked.txt").write_text("updated\n", encoding="utf-8")
    _git(worktree, "add", "tracked.txt")
    _git(
        worktree,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "worktree change",
    )
    _git(worktree, "config", "core.hooksPath", ".githooks")

    pushed = subprocess.run(
        ["git", "-C", str(worktree), "push", "-q", "-u", "origin", "feat/hook-test"],
        env=runtime.clean_git_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert pushed.returncode == 0, pushed.stderr
    recorded = json.loads(capture.read_text(encoding="utf-8"))
    assert recorded["args"] == ["all"]
    assert Path(recorded["cwd"]).resolve() == worktree.resolve()
    assert recorded["git_env"] == {}


def test_ci_script_scrubs_git_local_vars_and_avoids_git_dir_shadowing() -> None:
    for script in (PRE_PUSH_HOOK, CI_SCRIPT):
        checked = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False, timeout=10
        )
        assert checked.returncode == 0, checked.stderr
    text = CI_SCRIPT.read_text(encoding="utf-8")
    assert "git rev-parse --local-env-vars" in text
    assert "unset GIT_DIR" in text
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("GIT_DIR="), f"GIT_DIR variable shadows Git env: {line}"
