"""Reproducible, SHA-bound local CI receipts (never a hosted-runner substitute).

Full local pre-push CI remains scripts/ci.sh all. Receipts are stored under
the worktree-specific Git dir, outside the committed source tree, and can be
rechecked offline together with pinned log files and checked-out source.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

REQUIRED_TESTS = (
    "tests/test_cwsa_chapter2_gate.py",
    "tests/test_cwsa_chapter2_dashboard_gate.py",
    "tests/test_cwsa_chapter2_qualification.py",
    "tests/test_cwsa_chapter2_projection.py",
    "tests/test_cwsa_chapter2_postdeploy.py",
    "tests/test_cwsa_chapter2_ingestion.py",
    "tests/test_cwsa_chapter2_release.py",
    "tests/test_cwsa_chapter2_mirror.py",
    "tests/test_cwsa_six_paper.py",
    "tests/test_checkpoint_source.py",
    "tests/test_checkpoint_journal.py",
    "tests/test_checkpoint_paper.py",
    "tests/test_checkpoint_campaign.py",
    "tests/test_copy_mandates.py",
)
PROTECTED_SOURCE = (
    "src/copytrade_pm/pm_cwsa_chapter2_gate.py",
    "src/copytrade_pm/pm_cwsa_chapter2_projection.py",
    "src/copytrade_pm/pm_cwsa_paper_qualification.py",
    "src/copytrade_pm/pm_ci_receipt.py",
    "src/copytrade_pm/pm_operations.py",
    "src/copytrade_pm/pm_cwsa_chapter2_release.py",
    "src/copytrade_pm/pm_cwsa_chapter2_mirror.py",
    "src/copytrade_pm/pm_cwsa_chapter2_waves.py",
    "src/copytrade_pm/pm_cwsa_six_paper.py",
    "src/copytrade_pm/pm_copy_mandate.py",
    "src/copytrade_pm/pm_checkpoint_paper.py",
    "src/copytrade_pm/pm_forward_journal.py",
    "scripts/ci.sh",
    ".githooks/pre-push",
)
ALL_HASHES = (*PROTECTED_SOURCE, *REQUIRED_TESTS, "uv.lock", "ops/control-center/package-lock.json")
REQUIRED_LOGS = ("core", "market", "adversarial", "frontend", "build")
PYTEST_RE = re.compile(r"(\d+) passed(?:, (\d+) skipped)?")
SKIP_RE = re.compile(r"(\d+) skipped")


def _run(root: Path, *argv: str) -> str:
    return subprocess.run(
        argv, cwd=root, capture_output=True, check=True, text=True, timeout=15
    ).stdout.strip()


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CI_REQUIRED_SOURCE_OR_LOG_MISSING")
    return sha256(path.read_bytes()).hexdigest()


def _pytest_counts(log: str) -> dict:
    matches = list(PYTEST_RE.finditer(log))
    if not matches:
        return {"passed": 0, "skipped": 0}
    last = matches[-1]
    suffix = log[last.start() : last.end() + 100]
    skip = SKIP_RE.search(suffix)
    return {"passed": int(last.group(1)), "skipped": int(skip.group(1)) if skip else 0}


def _verify_steps(receipt: dict) -> list[str]:
    problems = []
    if receipt.get("schema") != "copytrade_local_ci_receipt_v1":
        problems.append("RECEIPT_SCHEMA_UNKNOWN")
    if receipt.get("stage") != "premerge" or receipt.get("leg") != "all":
        problems.append("RECEIPT_NOT_COMPLETE_FULL_CI")
    if receipt.get("status") != "PASS":
        problems.append("CI_RECORDED_FAILURE")
    if set(receipt.get("logs", {})) != set(REQUIRED_LOGS):
        problems.append("MISSING_REQUIRED_LOGS")
    if set(receipt.get("commands", {})) != set(REQUIRED_LOGS):
        problems.append("MISSING_CI_COMMANDS")
    if any(not receipt.get("commands", {}).get(name) for name in REQUIRED_LOGS):
        problems.append("SKIPPED_VALIDATION_STEP")
    if set(receipt.get("sources", {})) != set(ALL_HASHES):
        problems.append("REQUIRED_CONTRACT_HASHES_MISSING")
    core, market, adversarial = (
        receipt.get("tests", {}).get(n, {}) for n in ("core", "market", "adversarial")
    )
    if (
        core.get("passed", 0) < 1500
        or market.get("passed", 0) < 1700
        or adversarial.get("passed", 0) < 40
        or adversarial.get("skipped", 0)
    ):
        problems.append("MISSING_OR_SKIPPED_REQUIRED_ADVERSARIAL_TESTS")
    checks = receipt.get("checks", {})
    if any(
        checks.get(item) != "PASS"
        for item in (
            "core",
            "market",
            "adversarial",
            "frontend",
            "build",
            "ruff",
            "format",
            "types",
        )
    ):
        problems.append("REQUIRED_BUILD_OR_LINT_GATE_NOT_PASS")
    return problems


def create_receipt(
    *,
    root: Path,
    logs: dict[str, Path],
    out: Path,
    status: str,
    stage: str = "premerge",
) -> dict:
    """Publish the evidence and exact logs without changing the Git source tree."""
    if set(logs) != set(REQUIRED_LOGS) or status not in {"PASS", "FAIL"} or stage != "premerge":
        raise ValueError("CI_RECEIPT_INVALID_INPUT")
    root = root.resolve()
    if _run(root, "git", "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("CI_RECEIPT_REQUIRES_CLEAN_COMMITTED_TREE")
    commit = _run(root, "git", "rev-parse", "HEAD")
    tree = _run(root, "git", "rev-parse", "HEAD^{tree}")
    for path in ALL_HASHES:
        if _run(root, "git", "ls-files", "--error-unmatch", path) != path:
            raise ValueError("CI_RECEIPT_SOURCE_NOT_TRACKED:" + path)
    hashes = {item: _sha(root / item) for item in ALL_HASHES}
    out = out.resolve()
    if out.exists() or out.is_symlink():
        raise ValueError("CI_RECEIPT_ALREADY_EXISTS")
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_root = out.with_suffix("")
    if log_root.exists():
        raise ValueError("CI_LOGS_ALREADY_EXIST")
    log_root.mkdir(mode=0o700)
    log_info: dict[str, dict] = {}
    for label, src in logs.items():
        dest = log_root / (label + ".log")
        shutil.copyfile(src, dest)
        dest.chmod(0o600)
        log_info[label] = {"path": str(dest), "sha256": _sha(dest)}
    core = _pytest_counts(logs["core"].read_text(errors="replace"))
    market = _pytest_counts(logs["market"].read_text(errors="replace"))
    adversarial = _pytest_counts(logs["adversarial"].read_text(errors="replace"))
    marks = {label: logs[label].read_text(errors="replace") for label in REQUIRED_LOGS}
    checks = {
        "core": "PASS" if "CI_CORE_DONE" in marks["core"] else "FAIL",
        "market": "PASS" if "CI_MARKET_DONE" in marks["market"] else "FAIL",
        "adversarial": "PASS" if "CI_ADVERSARIAL_DONE" in marks["adversarial"] else "FAIL",
        "frontend": "PASS" if "CI_FRONTEND_DONE" in marks["frontend"] else "FAIL",
        "build": "PASS" if "CI_BUILD_DONE" in marks["build"] else "FAIL",
        "ruff": "PASS" if all("CI_RUFF_DONE" in marks[n] for n in ("core", "market")) else "FAIL",
        "format": "PASS"
        if all("CI_FORMAT_DONE" in marks[n] for n in ("core", "market"))
        else "FAIL",
        "types": "PASS" if "CI_TYPES_DONE" in marks["frontend"] else "FAIL",
    }
    receipt = {
        "schema": "copytrade_local_ci_receipt_v1",
        "stage": stage,
        "leg": "all",
        "status": status,
        "repo": "hzminhzz/copytrade-pm",
        "commit_sha": commit,
        "tree_sha": tree,
        "created_at": datetime.now(UTC).isoformat(),
        "python_version": sys.version.split()[0],
        "uv_version": _run(root, "uv", "--version"),
        "dependency_lock_sha256": hashes["uv.lock"],
        "frontend_lock_sha256": hashes["ops/control-center/package-lock.json"],
        "sources": hashes,
        "tests": {"core": core, "market": market, "adversarial": adversarial},
        "commands": {
            "core": "uv sync --frozen --group dev && uv run --no-sync pytest -q tests && uv run --no-sync ruff check && uv run --no-sync ruff format --check",
            "market": "uv sync --frozen --group dev --extra market && uv run --no-sync pytest -q tests && uv run --no-sync ruff check && uv run --no-sync ruff format --check",
            "adversarial": "uv run --no-sync pytest -q " + " ".join(REQUIRED_TESTS),
            "frontend": "npm ci --no-audit --no-fund && npm run build",
            "build": "uv build",
        },
        "checks": checks,
        "logs": log_info,
    }
    issues = _verify_steps(receipt)
    receipt["status"] = "FAIL" if issues else status
    receipt["blockers"] = issues
    out.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    out.chmod(0o600)
    return receipt


def validate_receipt(path: Path | None, root: Path, sha: str) -> list[str]:
    if not path or not path.is_file() or path.is_symlink():
        return ["LOCAL_CI_RECEIPT_MISSING"]
    try:
        receipt = json.loads(path.read_text())
        problems = _verify_steps(receipt)
        if receipt.get("repo") != "hzminhzz/copytrade-pm":
            problems.append("REPOSITORY_MISMATCH")
        if receipt.get("commit_sha") != sha or receipt.get("tree_sha") != _run(
            root, "git", "rev-parse", "HEAD^{tree}"
        ):
            problems.append("STALE_OR_MISMATCHED_COMMIT_SHA")
        for item in ALL_HASHES:
            if _sha(root / item) != receipt.get("sources", {}).get(item):
                problems.append("SOURCE_CONTRACT_HASH_DRIFT:" + item)
        for name in REQUIRED_LOGS:
            entry = receipt.get("logs", {}).get(name, {})
            if _sha(Path(entry["path"])) != entry.get("sha256"):
                problems.append("CI_LOG_HASH_MISMATCH:" + name)
        for name in ("core", "market", "adversarial"):
            if (
                _pytest_counts(Path(receipt["logs"][name]["path"]).read_text(errors="replace"))
                != receipt["tests"][name]
            ):
                problems.append("PYTEST_LOG_SUMMARY_DRIFT:" + name)
        return sorted(set(problems))
    except OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError:
        return ["CI_RECEIPT_UNRECHECKABLE"]


def check_receipt(path: Path | None, *, repo_root: Path, expected_sha: str):
    from .pm_cwsa_chapter2_gate import GateCheck

    errors = validate_receipt(path, repo_root, expected_sha)
    if not errors:
        return GateCheck(
            "local_ci_receipt",
            "PASS",
            "SHA_TREE_LOCK_TESTS_AND_LOGS_RECHECKED",
            {"receipt_path": str(path), "receipt_sha256": _sha(path)},
        )
    if errors == ["LOCAL_CI_RECEIPT_MISSING"]:
        return GateCheck("local_ci_receipt", "BLOCKED_EVIDENCE", errors[0])
    return GateCheck("local_ci_receipt", "FAIL", ",".join(errors))


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m copytrade_pm.pm_ci_receipt")
    verbs = p.add_subparsers(dest="verb", required=True)
    verbs.add_parser("required-tests")
    create = verbs.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--status", required=True, choices=("PASS", "FAIL"))
    for n in REQUIRED_LOGS:
        create.add_argument("--" + n + "-log", type=Path, required=True)
    verify = verbs.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--sha", required=True)
    args = p.parse_args(argv)
    if args.verb == "required-tests":
        print("\n".join(REQUIRED_TESTS))
        return 0
    if args.verb == "create":
        receipt = create_receipt(
            root=args.root,
            out=args.output,
            status=args.status,
            logs={n: getattr(args, n + "_log") for n in REQUIRED_LOGS},
        )
        print(
            json.dumps(
                {
                    "path": str(args.output),
                    "status": receipt["status"],
                    "sha": receipt["commit_sha"],
                    "blockers": receipt["blockers"],
                }
            )
        )
        return 0 if receipt["status"] == "PASS" else 1
    problems = validate_receipt(args.receipt, args.root, args.sha)
    print(json.dumps({"status": "PASS" if not problems else "FAIL", "blockers": problems}))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(cli())
