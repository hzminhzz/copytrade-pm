"""ANOS-02 pinned baseline workload and engineering-only scoring checks."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess

from copytrade_pm import pm_agent_trace_eval as evaluator

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "1c4ac38e76dc7ed31e3421273269750b2f03e086"
BASE_BLOBS = {
    "src/copytrade_pm/pm_agent_trace_eval.py": "d77b740e90e30cab2d89f25980938e1df5ff42f8",
    "tests/test_pm_agent_trace_eval.py": "abd5c8eb749facb1c29950f66592783dd0afa1fc",
    "docs/AGENT-TRACE-EVAL-20261105.md": "3b2964112342ae1286b078f4faac57587dad525a",
    "src/copytrade_pm/pm_operations.py": "3111dac83467b2f22314e408e6cd0dbd91542861",
}
FIXED_TASK_IDS = (
    "current-selection",
    "wallet-w083",
    "wallet-inventory",
    "wallet-exclusions",
    "portfolio-e6",
    "portfolio-q3-b",
    "paper-running",
    "research-cache",
    "installed-release",
    "protected-paper-os",
    "market-evidence",
    "source-collection-authority",
    "pm03-authority",
)


def test_frozen_git_inputs_retain_exact_blobs() -> None:
    for path, expected in BASE_BLOBS.items():
        result = subprocess.run(
            ["git", "rev-parse", f"{BASE_SHA}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == expected


def test_fixed_public_tasks_and_eight_scenarios_documented() -> None:
    assert tuple(evaluator.TASK_MAP) == FIXED_TASK_IDS
    doc = (ROOT / "docs/ANOS-02-AGENT-EVAL-BASELINE-20261113.md").read_text()
    assert BASE_SHA in doc
    for task_id in FIXED_TASK_IDS:
        assert f"`{task_id}`" in doc
    for index in range(1, 9):
        assert f"| S{index} |" in doc
    assert "BLOCKED_EVIDENCE" in doc
    assert "10% reduction" in doc


def _event(sequence: int, argv: list[str], status: str) -> dict:
    return {
        "sequence": sequence,
        "argv": argv,
        "exit_code": 0,
        "result_status": status,
    }


def test_fixture_cost_and_unknown_observations_are_not_agent_evidence(
    tmp_path: Path,
) -> None:
    runs = []
    for task in evaluator.TASK_MAP.values():
        calls = [_event(1, ["copytrade-pm", "capabilities", "show", task["capability"]], "FOUND")]
        status = "VERIFIED"
        if not task["discovery_only"]:
            argv = list(task["query_prefix"])
            if argv[-1] == "--cache-root":
                argv.append("/private/owner-cache")
            if task["id"] == "paper-running":
                status = "UNKNOWN"
            elif task["id"] in {"installed-release", "protected-paper-os", "market-evidence"}:
                status = "DEGRADED"
            calls.append(_event(2, argv, status))
        runs.append(
            {
                "task_id": task["id"],
                "calls": calls,
                "final": {
                    "answered": True,
                    "status": status,
                    "scientifically_qualified": False,
                    "trading_authorized": False,
                },
            }
        )
    trace = tmp_path / "engineering-fixture.json"
    trace.write_text(
        json.dumps(
            {
                "schema": evaluator.SCHEMA,
                "run_id": "anos-02-synthetic",
                "observed_at": datetime.now(UTC).isoformat(),
                "capture_kind": "SYNTHETIC",
                "tool_events_source": "TEST_FIXTURE",
                "runs": runs,
            }
        )
    )
    trace.chmod(0o600)
    result = evaluator.evaluate(trace)
    assert result["status"] == "UNVERIFIED_TOOL_TRACE"
    assert result["independent_evidence"] is False
    assert result["tasks_passed"] == result["task_count"] == 13
    assert result["total_calls"] == 24
    assert result["discovery_hops"] == 13
    assert result["read_scope_calls"] == 11
    assert result["repeated_work_calls"] == 0
    assert result["invented_calls"] == 0
    assert result["off_target_calls"] == 0
    assert result["unsafe_calls"] == 0
    assert result["bytes_read"] is None
    assert result["wall_time_ms"] is None
    assert result["context_tokens"] is None


def test_wrong_owner_discovery_counts_hops_and_fails() -> None:
    from copytrade_pm.pm_capabilities import inventory

    task = evaluator.TASK_MAP["current-selection"]
    record = {
        "task_id": task["id"],
        "calls": [
            _event(1, ["copytrade-pm", "capabilities", "show", "wallet.lookup"], "FOUND"),
            _event(2, ["copytrade-pm", "capabilities", "show", task["capability"]], "FOUND"),
            _event(3, list(task["query_prefix"]), "VERIFIED"),
        ],
        "final": {
            "answered": True,
            "status": "VERIFIED",
            "scientifically_qualified": False,
            "trading_authorized": False,
        },
    }
    scored = evaluator._score_one(record, {item["id"]: item for item in inventory()})
    assert scored["discovery_hops"] == 2
    assert scored["off_target_calls"] == 1
    assert scored["read_scope_calls"] == 1
    assert scored["passed"] is False


def test_discovery_only_query_is_counted_as_read_scope_and_unsafe() -> None:
    from copytrade_pm.pm_capabilities import inventory

    task = evaluator.TASK_MAP["source-collection-authority"]
    record = {
        "task_id": task["id"],
        "calls": [
            _event(1, ["copytrade-pm", "capabilities", "show", task["capability"]], "FOUND"),
            _event(2, ["copytrade-pm", "health"], "UNKNOWN"),
        ],
        "final": {
            "answered": True,
            "status": "VERIFIED",
            "scientifically_qualified": False,
            "trading_authorized": False,
        },
    }
    scored = evaluator._score_one(record, {item["id"]: item for item in inventory()})
    assert scored["read_scope_calls"] == 1
    assert scored["unsafe_calls"] == 1
    assert scored["passed"] is False
