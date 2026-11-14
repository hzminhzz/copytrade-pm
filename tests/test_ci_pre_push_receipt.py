"""Pre-push receipt reuse must fall back to full CI on every unsafe case."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-push"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize(
    ("case", "reuses"),
    [
        ("matching", True),
        ("missing", False),
        ("stale_sha", False),
        ("invalid_receipt", False),
        ("dirty_tree", False),
        ("force_full", False),
        ("symlink_receipt", False),
    ],
)
def test_pre_push_receipt_reuse_fails_closed(tmp_path: Path, case: str, reuses: bool):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "CI fixture")
    _git(tmp_path, "config", "user.email", "ci@example.invalid")
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts" / "ci.sh"
    script.write_text("#!/bin/sh\nprintf 'FULL_CI_EXECUTED\\n'\n")
    script.chmod(0o755)
    (tmp_path / ".gitignore").write_text(".venv-ci-core/\n")
    _git(tmp_path, "add", "scripts/ci.sh", ".gitignore")
    _git(tmp_path, "commit", "-qm", "fixture")
    sha = _git(tmp_path, "rev-parse", "HEAD")

    # Stub only the verifier process. Real receipt semantics are tested
    # separately by the pm_ci_receipt validator.
    binary = tmp_path / ".venv-ci-core" / "bin" / "python"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit " + ("1" if case == "invalid_receipt" else "0") + "\n")
    binary.chmod(0o755)

    receipts = tmp_path / ".git" / "local-ci"
    receipts.mkdir()
    if case != "missing":
        name_sha = "0" * 40 if case == "stale_sha" else sha
        receipt = receipts / f"{name_sha}-fixture.json"
        if case == "symlink_receipt":
            receipt.symlink_to(tmp_path / "missing-target")
        else:
            receipt.write_text("{}")
    if case == "dirty_tree":
        script.write_text(script.read_text() + "# dirty\n")

    env = dict(os.environ)
    env.pop("SKIP_CI", None)
    env.pop("CI_FORCE_FULL", None)
    if case == "force_full":
        env["CI_FORCE_FULL"] = "1"
    proc = subprocess.run(
        ["bash", str(HOOK)], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert ("verified exact-commit CI receipt" in proc.stderr) == reuses
    assert ("FULL_CI_EXECUTED" in proc.stdout) != reuses
