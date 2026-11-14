"""The focused feedback command rejects ambiguous/unsafe selections."""

from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci_focused.sh"


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["-k", "example"],
        ["tests/test_not_present.py"],
        ["src/copytrade_pm/pm_ci_receipt.py"],
        ["tests/../src/copytrade_pm/pm_ci_receipt.py"],
    ],
)
def test_focused_gate_rejects_missing_or_unreviewed_targets(args):
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=SCRIPT.parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "CI_FOCUSED_REJECTED_TARGET" in result.stderr or "Usage:" in result.stderr
