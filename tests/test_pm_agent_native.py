"""Agent-native discovery, authority routing and read-only contract benchmark."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from hashlib import sha256
import shutil
import subprocess
import sys

import pytest

from copytrade_pm import pm_capabilities as cap
from copytrade_pm import pm_operations as ops
from copytrade_pm import pm_runtime_readonly as runtime
from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_catalog as catalog
from test_wallet_registry_catalog import _v2_snapshot, AFTER, BEFORE

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _synthetic_whale(monkeypatch: pytest.MonkeyPatch) -> None:
    whale = "0x5f94" + "0" * 36
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(whale.encode()).hexdigest())


def _run(argv: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = ops.cli(argv)
    return code, json.loads(output.getvalue())


def test_inventory_covers_actual_entry_points_and_safe_owner() -> None:
    result = cap.validate(ROOT)
    assert result["status"] == "VERIFIED", result["errors"]
    assert result["cli_count"] >= 28
    entries = {x["id"]: x for x in cap.inventory(ROOT)}
    assert entries["account.pm03"]["authority"] == "PM03_FINANCIAL_AUTHORITY"
    assert entries["research.offline"]["classification"] == "LOCAL_MUTATION"
    assert set(entries["paper.journal_status"]["required_arguments"]) == {"--db", "--run-id"}
    assert entries["operations.cli"]["required_arguments"] is None
    assert entries["registry.operation.wallet.alias"]["required_arguments"] == ["--alias ALIAS"]
    assert "JOB" in entries["research.offline"]["required_arguments"]
    assert entries["source.collection"]["classification"] == "PROTECTED_MUTATION"
    assert entries["registry.operation.sync.apply"]["classification"] == "PROTECTED_MUTATION"
    assert entries["registry.operation.sync.dry.run"]["classification"] == "READ_ONLY"
    assert entries["paper.status"]["authority"] == "INDEPENDENT_JOURNAL_AND_WORKER"
    assert entries["portfolio.current"]["owner"] == "copytrade_pm.wallet_registry_catalog"
    assert entries["market.native"]["available"]
    assert entries["research.polars"]["available"]
    assert entries["release.verify"]["available"]
    assert len(entries) == len(cap.inventory(ROOT))


def test_cli_unknown_capability_and_catalog_drifts_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, response = _run(["capabilities", "show", "nonexistent.command"])
    assert code == 2 and response["status"] == "UNKNOWN"
    original = cap.GROUPS.copy()
    monkeypatch.delitem(cap.GROUPS, "copytrade-pm-replay")
    bad = cap.validate(ROOT)
    assert bad["status"] == "BLOCKED"
    assert "UNREVIEWED_ENTRY_POINTS" in bad["errors"]
    monkeypatch.setattr(cap, "GROUPS", original)


def test_native_portfolio_parity_and_namespace_separation(tmp_path: Path) -> None:
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    current = ops._read_registry(db, ["portfolio", "--current"], "portfolio.current", AFTER)
    assert current["status"] == "VERIFIED"
    with io.StringIO() as stdout, redirect_stdout(stdout):
        assert reg.cli(["--db", str(db), "portfolio", "--current", "--asof", AFTER]) == 0
        native = json.loads(stdout.getvalue())
    assert current["data"] == native
    assert current["source"]["observed_at"] is not None
    assert current["observed_at"] != current["source"]["observed_at"]
    assert current["data"]["portfolios"][0]["portfolio_id"] == "gemini.phase4/E6"
    e6 = ops._read_registry(db, ["portfolio", "E6"], "portfolio.show", AFTER)
    assert e6["data"]["gemini.phase4/E6"]["members"] == current["data"]["portfolios"][0]["members"]
    q3 = ops._read_registry(db, ["portfolio", "q3/B"], "portfolio.show", AFTER)
    phase5 = ops._read_registry(db, ["portfolio", "gemini.phase5/B"], "portfolio.show", AFTER)
    assert set(q3["data"]) == {"B"}
    assert set(phase5["data"]) == {"gemini.phase5/B"}
    assert (
        ops._read_registry(db, ["portfolio", "B"], "portfolio.show", AFTER)["status"] == "UNKNOWN"
    )


def test_asof_wallet_and_unknown_vs_error(tmp_path: Path) -> None:
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    after = ops._read_registry(db, ["wallet", "--alias", "W083"], "wallet.lookup", AFTER)
    before = ops._read_registry(db, ["wallet", "--alias", "W083"], "wallet.lookup", BEFORE)
    assert after["data"]["found"] is True
    assert before["data"]["found"] is False
    assert before["status"] == "NOT_REGISTERED_AT_ASOF"
    absent = ops._read_registry(tmp_path / "no.sqlite", ["portfolio"], "portfolio.list")
    assert absent["status"] == "UNKNOWN"
    assert absent["error_code"] == "REGISTRY_READ_FAILED"
    assert absent["data"] is None


def test_aggregate_partial_failure_preserves_known_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "installed_release", lambda _root: {"state": "UNKNOWN"})
    monkeypatch.setattr(runtime, "paper_unit_inventory", lambda: {"state": "UNKNOWN"})
    state = ops._health(tmp_path / "missing.sqlite", ROOT)
    components = state["data"]["components"]
    assert state["status"] == "DEGRADED"
    assert components["repository"]["status"] == "VERIFIED"
    assert components["registry"]["status"] == "UNKNOWN"
    assert components["registry_source_parity"]["status"] == "UNKNOWN"
    assert components["paper"]["status"] == "UNKNOWN"
    assert components["installed_release"]["status"] == "UNKNOWN"
    assert components["market_provider"]["status"] == "UNKNOWN"
    assert components["scientific_qualification"]["status"] == "BLOCKED"
    assert state["trading_authorized"] is False


def test_live_doctor_marks_stored_current_generation_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stale_cli(argv: list[str]) -> int:
        assert argv[-1] == "doctor"
        print(json.dumps({"counts_match": False, "freshness": "CURRENT"}))
        return 2

    monkeypatch.setattr(reg, "cli", stale_cli)
    stale = ops._doctor(Path("/nonexistent/registry.sqlite"))
    assert stale["status"] == "STALE"
    assert stale["error_code"] == "REGISTRY_SQLITE_INTEGRITY_FAILED"


def test_no_indexed_paper_run_does_not_claim_running(tmp_path: Path) -> None:
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    response = ops._paper(db)
    assert response["status"] == "UNKNOWN"
    assert response["data"]["registered_run_count"] == 0
    assert response["data"]["global_running_count"] == "UNKNOWN"
    assert response["scientifically_qualified"] is False


def test_no_private_state_modified_by_readonly_adapter(tmp_path: Path) -> None:
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    before = db.read_bytes()
    before_names = {p.name for p in db.parent.iterdir()}
    for cmd in (
        ["portfolio"],
        ["portfolio", "--current"],
        ["wallet", "--alias", "W083"],
        ["paper"],
        ["status"],
    ):
        item = ops._read_registry(db, cmd, "test.read")
        assert item["status"] == "VERIFIED"
    assert db.read_bytes() == before
    # SQLite mode=ro can create its own -wal/-shm interprocess sidecars.
    # Those are not application mutations; reject any other new private files.
    newly_created = {p.name for p in db.parent.iterdir()} - before_names
    assert newly_created <= {db.name + "-wal", db.name + "-shm"}


def test_static_agent_resolution_cases_and_docs() -> None:
    entries = {x["id"]: x for x in cap.inventory(ROOT)}
    for question, name in (
        ("saved portfolios", "portfolio.show"),
        ("W083", "wallet.lookup"),
        ("current E6", "portfolio.current"),
        ("P1 running", "paper.status"),
        ("Polars jobs", "research.offline"),
        ("market audit", "market.audit"),
        ("PM03 equity", "account.pm03"),
        ("worker health", "runtime.health"),
        ("trading route", "source.collection"),
        ("source admission", "paper.admission"),
    ):
        found = entries[name]
        assert found["available"], question
        assert (ROOT / found["documentation"]).is_file(), question
        assert found["authority"] and found["classification"], question
    assert ops._research("research.list")["status"] == "UNKNOWN"
    assert "native_interface" in ops._research("research.list")["data"]


def test_required_native_first_agent_instructions() -> None:
    docs = [
        "AGENTS.md",
        "docs/INDEX.md",
        "docs/ARCHITECTURE.md",
        "docs/RUNBOOK.md",
        "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
    ]
    for path in docs:
        content = (ROOT / path).read_text()
        assert "AGENT-NATIVE-OPERATIONS.md" in content
    agents = (ROOT / "AGENTS.md").read_text()
    for instruction in ("capabilities list", "capabilities show", "capabilities validate"):
        assert instruction in agents


EXPECTED_NATIVE_EXCLUDE_FLAGS = {
    "--expected-inventory-sha",
    "--expected-manifest-sha",
    "--manifest",
}


def test_registry_exclude_required_flags_and_access_metadata() -> None:
    code_preview, preview = _run(["capabilities", "show", "registry.operation.native.exclude"])
    code_apply, apply_entry = _run(
        ["capabilities", "show", "registry.operation.native.exclude.apply"]
    )
    assert code_preview == 0 and code_apply == 0
    assert preview["classification"] == "READ_ONLY"
    assert apply_entry["classification"] == "PROTECTED_MUTATION"
    assert {item.split()[0] for item in preview["required_arguments"]} == (
        EXPECTED_NATIVE_EXCLUDE_FLAGS
    )
    assert {item.split()[0] for item in apply_entry["required_arguments"]} == (
        EXPECTED_NATIVE_EXCLUDE_FLAGS
    )
    assert preview["access"] == {
        "read_targets": [
            "private_sqlite_registry",
            "private_evidence_archive",
            "private_exclusion_manifest",
        ],
        "write_targets": [],
        "network": False,
        "credentials": False,
        "privacy": "OWNER_PRIVATE_REDACTED",
    }
    assert apply_entry["access"] == {
        "read_targets": [
            "private_sqlite_registry",
            "private_evidence_archive",
            "private_exclusion_manifest",
        ],
        "write_targets": [
            "private_sqlite_registry",
            "private_sqlite_backup",
            "private_evidence_archive",
        ],
        "network": False,
        "credentials": False,
        "privacy": "OWNER_PRIVATE_REDACTED",
    }
    entries = {item["id"]: item for item in cap.inventory(ROOT)}
    for cap_id in (
        "registry.operation.status",
        "registry.operation.report.redacted",
    ):
        reads = set(entries[cap_id]["access"]["read_targets"])
        assert {"optional_private_paper_journal", "decision_repo"} <= reads, cap_id
    for cap_id in ("registry.operation.native.status", "registry.operation.doctor"):
        reads = set(entries[cap_id]["access"]["read_targets"])
        assert "private_evidence_archive" in reads, cap_id
        assert "optional_private_paper_journal" not in reads, cap_id
    assert "decision_repo" in entries["registry.operation.doctor"]["access"]["read_targets"]
    assert "decision_repo" in entries["registry.operation.portfolio"]["access"]["read_targets"]
    assert (
        "optional_auditor_public_key"
        in entries["registry.operation.qualification"]["access"]["read_targets"]
    )
    # Unverified CLI/NATIVE entries remain explicitly UNKNOWN without classification inference.
    _, replay = _run(["capabilities", "show", "historical.replay"])
    _, pm03 = _run(["capabilities", "show", "account.pm03"])
    assert replay["classification"] == "LOCAL_MUTATION"
    assert replay["access"] == {
        "read_targets": "UNKNOWN",
        "write_targets": "UNKNOWN",
        "network": "UNKNOWN",
        "credentials": "UNKNOWN",
        "privacy": "UNKNOWN",
    }
    assert pm03["access"] == replay["access"]


def _copy_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    shutil.copytree(ROOT / "src", repo / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "docs", repo / "docs")
    shutil.copytree(
        ROOT / "scripts", repo / "scripts", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    return repo


def test_registry_validator_catches_unlisted_changed_leaves_and_unsafe_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Unlisted top-level registry leaf fails closed.
    repo_top = _copy_repo(tmp_path, "top")
    reg_top = repo_top / "src/copytrade_pm/wallet_registry.py"
    reg_top.write_text(
        reg_top.read_text().replace(
            '    sub.add_parser("runtime")\n',
            '    sub.add_parser("runtime")\n    sub.add_parser("prune")\n',
            1,
        )
    )
    res_top = cap.validate(repo_top)
    assert res_top["status"] == "BLOCKED"
    assert any("prune" in err for err in res_top["errors"])

    # 2. Unlisted nested native leaf fails closed.
    repo_nested = _copy_repo(tmp_path, "nested")
    reg_nested = repo_nested / "src/copytrade_pm/wallet_registry.py"
    reg_nested.write_text(
        reg_nested.read_text().replace(
            '    native_sub.add_parser("status")\n',
            '    native_sub.add_parser("status")\n    native_sub.add_parser("prune")\n',
            1,
        )
    )
    res_nested = cap.validate(repo_nested)
    assert res_nested["status"] == "BLOCKED"
    assert any("native prune" in err for err in res_nested["errors"])

    # 3. Renamed nested leaf catches both stale catalog leaf and unlisted leaf.
    repo_renamed = _copy_repo(tmp_path, "renamed")
    reg_renamed = repo_renamed / "src/copytrade_pm/wallet_registry.py"
    reg_renamed.write_text(
        reg_renamed.read_text().replace(
            '    native_exclude = native_sub.add_parser(\n        "exclude",',
            '    native_exclude = native_sub.add_parser(\n        "omit",',
            1,
        )
    )
    res_renamed = cap.validate(repo_renamed)
    assert res_renamed["status"] == "BLOCKED"
    assert any("native exclude" in err for err in res_renamed["errors"])
    assert any("native omit" in err for err in res_renamed["errors"])

    # 4. Adding --apply to a registry leaf without a cataloged --apply operation fails closed.
    repo_apply = _copy_repo(tmp_path, "apply_flag")
    reg_apply = repo_apply / "src/copytrade_pm/wallet_registry.py"
    reg_apply.write_text(
        reg_apply.read_text().replace(
            '    sub.add_parser("runtime")\n',
            '    runtime_cmd = sub.add_parser("runtime")\n'
            '    runtime_cmd.add_argument("--apply", action="store_true")\n',
            1,
        )
    )
    res_apply = cap.validate(repo_apply)
    assert res_apply["status"] == "BLOCKED"
    assert any("runtime --apply" in err for err in res_apply["errors"])

    # 5. Unsafe READ_ONLY classification on --apply fails closed.
    monkeypatch.setitem(cap.REGISTRY_OPERATIONS, "native exclude --apply", "READ_ONLY")
    res_unsafe = cap.validate(ROOT)
    assert res_unsafe["status"] == "BLOCKED"
    assert any("native exclude --apply" in err for err in res_unsafe["errors"])
    monkeypatch.undo()

    # 6. T08 expansion deferral: uncataloged copytrade-pm leaves do not fail T07.
    repo_ops = _copy_repo(tmp_path, "ops_t08")
    ops_file = repo_ops / "src/copytrade_pm/pm_operations.py"
    ops_file.write_text(
        ops_file.read_text().replace(
            '    top.add_parser("health")\n',
            '    top.add_parser("health")\n    top.add_parser("t08-preview")\n',
            1,
        )
    )
    assert cap.validate(repo_ops)["status"] == "VERIFIED"


def test_registry_required_args_dispatch_and_unsupported_ast_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Adding a parser-required flag without updating REGISTRY_REQUIRED_ARGUMENTS fails.
    repo_req = _copy_repo(tmp_path, "req_add")
    reg_req = repo_req / "src/copytrade_pm/wallet_registry.py"
    reg_req.write_text(
        reg_req.read_text().replace(
            '    native_exclude.add_argument("--apply", action="store_true")\n',
            '    native_exclude.add_argument("--reason", required=True)\n'
            '    native_exclude.add_argument("--apply", action="store_true")\n',
            1,
        )
    )
    res_req = cap.validate(repo_req)
    assert res_req["status"] == "BLOCKED"
    assert "MISSING_REGISTRY_REQUIRED_ARG:native exclude:--reason" in res_req["errors"]

    # 2. Dropping a parser-required flag from REGISTRY_REQUIRED_ARGUMENTS fails.
    monkeypatch.setitem(
        cap.REGISTRY_REQUIRED_ARGUMENTS,
        "native exclude",
        ["--expected-inventory-sha SHA256", "--manifest PRIVATE_PATH"],
    )
    res_missing = cap.validate(ROOT)
    assert res_missing["status"] == "BLOCKED"
    assert (
        "MISSING_REGISTRY_REQUIRED_ARG:native exclude:--expected-manifest-sha"
        in res_missing["errors"]
    )
    monkeypatch.undo()

    # 3. Extra/stale flag in REGISTRY_REQUIRED_ARGUMENTS fails.
    monkeypatch.setitem(
        cap.REGISTRY_REQUIRED_ARGUMENTS,
        "native exclude",
        [
            "--expected-inventory-sha SHA256",
            "--expected-manifest-sha SHA256",
            "--manifest PRIVATE_PATH",
            "--bogus VALUE",
        ],
    )
    res_stale = cap.validate(ROOT)
    assert res_stale["status"] == "BLOCKED"
    assert "STALE_REGISTRY_REQUIRED_ARG:native exclude:--bogus" in res_stale["errors"]
    monkeypatch.undo()

    # 4. Dispatch-level required flags stay distinct from parser-required flags and validate option presence.
    entries = {item["id"]: item for item in cap.inventory(ROOT)}
    assert set(entries["registry.operation.paper.apply"]["required_arguments"]) == {
        "--run-dir PATH",
        "--portfolio NAME",
    }
    monkeypatch.setitem(
        cap.REGISTRY_DISPATCH_REQUIRED_ARGUMENTS,
        "paper --apply",
        ("--run-dir", "--portfolio", "--bogus"),
    )
    res_dispatch = cap.validate(ROOT)
    assert res_dispatch["status"] == "BLOCKED"
    assert "STALE_REGISTRY_DISPATCH_ARG:paper --apply:--bogus" in res_dispatch["errors"]
    monkeypatch.undo()
    monkeypatch.setitem(cap.REGISTRY_REQUIRED_ARGUMENTS, "paper --apply", ["--run-dir PATH"])
    res_dispatch_missing = cap.validate(ROOT)
    assert res_dispatch_missing["status"] == "BLOCKED"
    assert (
        "MISSING_REGISTRY_DISPATCH_ARG:paper --apply:--portfolio" in res_dispatch_missing["errors"]
    )
    monkeypatch.undo()

    # 5. Unsupported parser constructs fail closed with explicit error codes.
    unsupported_cases = [
        (
            "loop_parser",
            '    sub.add_parser("runtime")\n',
            '    for name in ("runtime",):\n        sub.add_parser(name)\n',
        ),
        (
            "dynamic_parser",
            '    sub.add_parser("runtime")\n',
            '    cmd = "runtime"\n    sub.add_parser(cmd)\n',
        ),
        (
            "kwargs_arg",
            '    native_exclude.add_argument("--apply", action="store_true")\n',
            '    extra = {"action": "store_true"}\n    native_exclude.add_argument("--apply", **extra)\n',
        ),
        (
            "deep_subparsers",
            '    native_exclude.add_argument("--apply", action="store_true")\n',
            '    native_exclude.add_argument("--apply", action="store_true")\n'
            '    deep_sub = native_exclude.add_subparsers(dest="deep")\n',
        ),
        (
            "parent_required",
            '    sub = parser.add_subparsers(dest="command", required=True)\n',
            '    parser.add_argument("--secret", required=True)\n'
            '    sub = parser.add_subparsers(dest="command", required=True)\n',
        ),
        (
            "parser_aliases",
            '    sub.add_parser("runtime")\n',
            '    sub.add_parser("runtime", aliases=("rt",))\n',
        ),
    ]
    for case_name, target, replacement in unsupported_cases:
        repo_bad = _copy_repo(tmp_path, case_name)
        reg_bad = repo_bad / "src/copytrade_pm/wallet_registry.py"
        reg_bad.write_text(reg_bad.read_text().replace(target, replacement, 1))
        res_bad = cap.validate(repo_bad)
        assert res_bad["status"] == "BLOCKED", case_name
        assert any(
            err.startswith("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:") for err in res_bad["errors"]
        ), (case_name, res_bad["errors"])


def test_capability_discovery_performs_no_optional_imports_or_writes(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path, "readonly_check")
    before = {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }
    script = """
import json, sys
from pathlib import Path
from copytrade_pm import pm_capabilities as cap
root = Path(sys.argv[1])
inv = cap.inventory(root)
val = cap.validate(root)
forbidden = [
    m for m in (
        "copytrade_pm.wallet_registry",
        "polars",
        "ccxt",
        "websockets",
        "prefect",
        "httpx",
    )
    if m in sys.modules
]
print(json.dumps({"status": val["status"], "count": len(inv), "forbidden": forbidden}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["status"] == "VERIFIED"
    assert payload["forbidden"] == []
    after = {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }
    assert after == before


def test_registry_cli_parser_matches_catalog_required_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_connect(*args: object, **kwargs: object) -> object:
        raise AssertionError("DB connect should not be called during parser validation")

    monkeypatch.setattr(reg, "connect", _fail_connect)
    db = tmp_path / "unused.sqlite"

    for cap_id, mode_flags in (
        ("registry.operation.native.exclude", []),
        ("registry.operation.native.exclude.apply", ["--apply"]),
    ):
        code, detail = _run(["capabilities", "show", cap_id])
        assert code == 0
        required_flags = [tok.split()[0] for tok in detail["required_arguments"]]
        assert set(required_flags) == EXPECTED_NATIVE_EXCLUDE_FLAGS
        base_values = {
            "--expected-inventory-sha": "a" * 64,
            "--expected-manifest-sha": "b" * 64,
            "--manifest": str(tmp_path / "exclude.json"),
        }
        for omitted in required_flags:
            argv = ["--db", str(db), "native", "exclude", *mode_flags]
            for flag in required_flags:
                if flag != omitted:
                    argv.extend([flag, base_values[flag]])
            with pytest.raises(SystemExit) as exc:
                reg.cli(argv)
            assert exc.value.code == 2

    # Dispatch-level --apply flags pass argparse parse time and fail at dispatch before DB access.
    with pytest.raises(ValueError, match="requires an explicit private run directory"):
        reg.cli(["--db", str(db), "paper", "--apply"])
    with pytest.raises(ValueError, match="requires independent signed evidence"):
        reg.cli(["--db", str(db), "qualification", "--apply"])
