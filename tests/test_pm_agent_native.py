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


def test_inspection_cache_is_content_bound_and_returns_independent_results(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path, "cache_invalidation")
    module = "copytrade_pm.pm_forward_public_trades"
    path = repo / "src/copytrade_pm/pm_forward_public_trades.py"

    requirements = cap._required_cli_args(module, repo)
    assert requirements is not None
    expected = requirements.copy()
    requirements.append("--forged-required")
    assert cap._required_cli_args(module, repo) == expected

    spec, errors = cap._inspect_group_script_parser(
        path, "copytrade-pm-public-trades", allow_policies_loop=False
    )
    assert not errors and spec is not None
    spec["options"]["--forged-option"] = {}
    again, again_errors = cap._inspect_group_script_parser(
        path, "copytrade-pm-public-trades", allow_policies_loop=False
    )
    assert not again_errors and again is not None
    assert "--forged-option" not in again["options"]

    original = path.read_text()
    assert 'choices=("observe", "plan")' in original
    path.write_text(original.replace('choices=("observe", "plan")', 'choices=("observe",)', 1))
    changed, changed_errors = cap._inspect_group_script_parser(
        path, "copytrade-pm-public-trades", allow_policies_loop=False
    )
    assert not changed_errors and changed is not None
    assert changed["options"]["--mode"]["choices"] != again["options"]["--mode"]["choices"]

    path.unlink()
    assert cap._required_cli_args(module, repo) is None
    missing, missing_errors = cap._inspect_group_script_parser(
        path, "copytrade-pm-public-trades", allow_policies_loop=False
    )
    assert missing is None
    assert missing_errors == ["MISSING_ENTRY_MODULE:copytrade-pm-public-trades"]


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

    # 6. T08 enforcement: uncataloged copytrade-pm leaves fail closed.
    repo_ops = _copy_repo(tmp_path, "ops_t08")
    ops_file = repo_ops / "src/copytrade_pm/pm_operations.py"
    ops_file.write_text(
        ops_file.read_text().replace(
            '    top.add_parser("health")\n',
            '    top.add_parser("health")\n    top.add_parser("t08-preview")\n',
            1,
        )
    )
    res_ops = cap.validate(repo_ops)
    assert res_ops["status"] == "BLOCKED"
    assert "UNLISTED_OPERATIONS_LEAF:t08-preview" in res_ops["errors"]


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


def test_operations_subcommands_and_group_modes_cataloged() -> None:
    entries = {item["id"]: item for item in cap.inventory(ROOT)}

    # Already-cataloged copytrade-pm leaves retain NATIVE kind/IDs without duplicate SUBCOMMAND rows.
    for existing_native_id in (
        "wallet.inventory",
        "wallet.lookup",
        "portfolio.current",
        "portfolio.show",
        "research.report.catalog",
        "paper.status",
        "research.contract_selector",
        "runtime.health",
    ):
        assert entries[existing_native_id]["kind"] == "NATIVE"

    # Missing copytrade-pm leaves are cataloged as SUBCOMMAND with stable IDs and verified access.
    expected_ops = {
        "operations.cwsa.chapter2.verify": (["--stage STAGE"], True, True),
        "operations.cwsa.chapter2.projection": (["--release-sha SHA40"], False, False),
        "operations.capabilities.list": ([], False, False),
        "operations.capabilities.show": (["ID"], False, False),
        "operations.capabilities.validate": ([], False, False),
        "portfolio.list": ([], False, False),
        "research.show": (["ID"], False, False),
        "research.contract_selector.rules": ([], False, False),
        "operations.status": ([], False, False),
    }
    for cap_id, (req_args, net, creds) in expected_ops.items():
        item = entries[cap_id]
        assert item["kind"] == "SUBCOMMAND"
        assert item["classification"] == "READ_ONLY"
        assert item["required_arguments"] == req_args
        assert item["access"]["write_targets"] == []
        assert item["access"]["network"] is net
        assert item["access"]["credentials"] is creds
        assert "UNKNOWN" not in item["access"].values()

    # Argparse-required vs conditional runtime-required distinction.
    assert entries["research.show"]["required_arguments"] == ["ID"]
    assert entries["research.show"]["runtime_required_arguments"] == ["--cache-root PATH"]
    assert entries["research.contract_selector"]["required_arguments"] == [
        "--portfolio NAMESPACE/ID"
    ]
    assert entries["research.contract_selector"]["runtime_required_arguments"] == [
        "--tape PRIVATE_TAPE"
    ]
    assert entries["research.report.catalog"]["required_arguments"] == []
    assert entries["research.report.catalog"]["runtime_required_arguments"] == ["--cache-root PATH"]
    assert (
        "--receipt PATH" in entries["operations.cwsa.chapter2.verify"]["runtime_required_arguments"]
    )

    # Conservative parent GROUPS classifications remain intact while mode variants expose real effects.
    assert entries["paper.public_unit"]["classification"] == "PROTECTED_MUTATION"
    assert entries["paper.public_unit.preview"]["kind"] == "SUBCOMMAND"
    assert entries["paper.public_unit.preview"]["classification"] == "READ_ONLY"
    assert entries["paper.public_unit.preview"]["access"]["write_targets"] == []
    assert entries["paper.public_unit.apply"]["kind"] == "SUBCOMMAND"
    assert entries["paper.public_unit.apply"]["classification"] == "PROTECTED_MUTATION"
    assert "systemd_user_unit_file" in entries["paper.public_unit.apply"]["access"]["write_targets"]

    assert entries["source.public_trades"]["classification"] == "PROTECTED_MUTATION"
    assert entries["source.public_trades.observe"]["classification"] == "PROTECTED_MUTATION"
    assert entries["source.public_trades.observe"]["access"]["network"] is True
    assert entries["source.public_trades.plan"]["classification"] == "PROTECTED_MUTATION"
    assert entries["source.public_trades.plan"]["access"]["network"] is False
    assert entries["source.public_trades.plan"]["access"]["write_targets"] == [
        "private_observer_journal"
    ]

    assert entries["source.receipts"]["classification"] == "PROTECTED_MUTATION"
    assert entries["source.receipts.inspect"]["classification"] == "READ_ONLY"
    assert entries["source.receipts.inspect"]["runtime_required_arguments"] == ["--asof UTC"]
    assert entries["source.receipts.ingest"]["classification"] == "PROTECTED_MUTATION"
    assert entries["source.receipts.ingest"]["runtime_required_arguments"] == ["--receipts PATH"]
    for action in ("init", "audit", "outcome"):
        assert entries[f"source.receipts.{action}"]["classification"] == "PROTECTED_MUTATION"

    assert entries["account.pm03.simulate"]["classification"] == "LOCAL_MUTATION"
    for action in ("compare", "compare_pm04", "replay"):
        assert entries[f"account.pm03.simulate.{action}"]["kind"] == "SUBCOMMAND"
        assert entries[f"account.pm03.simulate.{action}"]["classification"] == "LOCAL_MUTATION"

    assert entries["paper.unit_bundle"]["classification"] == "LOCAL_MUTATION"
    assert entries["paper.unit_bundle.verify"]["classification"] == "READ_ONLY"
    assert entries["paper.unit_bundle.stage"]["classification"] == "LOCAL_MUTATION"
    assert entries["paper.unit_bundle.stage"]["runtime_required_arguments"] == ["--revision SHA40"]

    assert entries["production.export.cli"]["classification"] == "LOCAL_MUTATION"
    assert entries["production.export.cli.stdout"]["classification"] == "READ_ONLY"
    assert entries["production.export.cli.write"]["classification"] == "LOCAL_MUTATION"
    assert entries["production.export.cli.write"]["runtime_required_arguments"] == [
        "--private-output PATH"
    ]
    assert entries["paper.observer.diagnose_preflight"]["classification"] == "READ_ONLY"
    assert entries["paper.observer.diagnose_preflight"]["runtime_required_arguments"] == [
        "--continuous-config PATH",
        "--diagnose-preflight",
        "--preflight-only",
    ]
    assert entries["paper.observer.finite"]["classification"] == "PROTECTED_MUTATION"
    assert entries["paper.observer_health"]["classification"] == "LOCAL_MUTATION"
    assert entries["paper.observer_health.heartbeat"]["classification"] == "READ_ONLY"
    assert entries["paper.identity.audit"]["classification"] == "READ_ONLY"
    assert entries["market.ccxt.probe"]["classification"] == "READ_ONLY"
    assert entries["market.ccxt.probe"]["access"]["network"] is True
    assert entries["market.ccxt.record"]["classification"] == "LOCAL_MUTATION"
    assert entries["market.ccxt.record"]["access"]["write_targets"] == [
        "private_market_canary_record"
    ]
    assert entries["paper.observer.preflight"]["runtime_required_arguments"] == [
        "--continuous-config PATH",
        "--preflight-only",
    ]
    assert entries["paper.observer.continuous_health"]["runtime_required_arguments"] == [
        "--continuous"
    ]
    assert entries["paper.observer.continuous_watchdog"]["runtime_required_arguments"] == [
        "--continuous",
        "--watch",
    ]
    assert entries["paper.observer.shadow_report"]["runtime_required_arguments"] == [
        "--shadow-report"
    ]
    assert entries["market.continuous_canary"]["runtime_required_arguments"] == [
        "--ack-shared-ip-connection-budget",
        "--continuous-canary-seconds SECONDS",
        "--record-root PATH",
    ]
    assert entries["paper.identity_reseal_preview"]["runtime_required_arguments"] == [
        "--prospective-reseal-preview"
    ]
    assert entries["paper.standby.worker"]["classification"] == "PROTECTED_MUTATION"
    assert entries["paper.standby.watchdog"]["classification"] == "PROTECTED_MUTATION"
    assert entries["paper.observed_execution.l2"]["access"]["network"] is True
    assert entries["paper.observed_execution.vike_minute"]["access"]["network"] is False
    assert entries["agent.trace.eval.list_tasks"]["classification"] == "READ_ONLY"
    assert entries["agent.trace.eval.trace"]["runtime_required_arguments"] == ["--trace PATH"]


def test_operations_and_group_validators_fail_closed_on_drift_and_unsupported_ast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = cap.validate(ROOT)
    assert baseline["status"] == "VERIFIED", baseline["errors"]
    assert any("pm03_cli" in note for note in baseline["limitations"])
    assert any("production_economics" in note for note in baseline["limitations"])

    # 1. Renamed/removed copytrade-pm leaf fails closed.
    repo_rename = _copy_repo(tmp_path, "ops_rename")
    ops_rename = repo_rename / "src/copytrade_pm/pm_operations.py"
    ops_rename.write_text(
        ops_rename.read_text().replace(
            'top.add_parser("status")', 'top.add_parser("ops-status")', 1
        )
    )
    res_rename = cap.validate(repo_rename)
    assert res_rename["status"] == "BLOCKED"
    assert "UNLISTED_OPERATIONS_LEAF:ops-status" in res_rename["errors"]
    assert "STALE_OPERATIONS_LEAF:status" in res_rename["errors"]

    # 2. Drift in imported pm_cwsa_chapter2_gate.add_arguments fails closed.
    repo_cwsa = _copy_repo(tmp_path, "ops_cwsa")
    cwsa_file = repo_cwsa / "src/copytrade_pm/pm_cwsa_chapter2_gate.py"
    cwsa_file.write_text(
        cwsa_file.read_text().replace(
            "def add_arguments(p: argparse.ArgumentParser) -> None:\n",
            "def add_arguments(p: argparse.ArgumentParser) -> None:\n"
            '    p.add_argument("--new-token", required=True)\n',
            1,
        )
    )
    res_cwsa = cap.validate(repo_cwsa)
    assert res_cwsa["status"] == "BLOCKED"
    assert "MISSING_OPERATIONS_REQUIRED_ARG:cwsa chapter2 verify:--new-token" in res_cwsa["errors"]
    assert (
        "MISSING_OPERATIONS_REQUIRED_ARG:cwsa chapter2 projection:--new-token" in res_cwsa["errors"]
    )

    # 3. Confusing argparse-required with runtime-required arguments fails closed.
    monkeypatch.setitem(
        cap.NATIVE_REQUIRED_ARGUMENTS, "research.report.catalog", ["--cache-root PATH"]
    )
    res_confused_native = cap.validate(ROOT)
    assert res_confused_native["status"] == "BLOCKED"
    assert any("--cache-root" in err for err in res_confused_native["errors"])
    monkeypatch.undo()

    bad_cwsa_spec = dict(cap.OPERATIONS_SUBCOMMANDS["cwsa chapter2 verify"])
    bad_cwsa_spec["runtime_required_arguments"] = ["--stage STAGE"]
    monkeypatch.setitem(cap.OPERATIONS_SUBCOMMANDS, "cwsa chapter2 verify", bad_cwsa_spec)
    res_confused_ops = cap.validate(ROOT)
    assert res_confused_ops["status"] == "BLOCKED"
    assert any("cwsa chapter2 verify" in err for err in res_confused_ops["errors"])
    monkeypatch.undo()

    # 4. Unsafe classification or uncataloged --apply on copytrade-pm fails closed.
    repo_ops_apply = _copy_repo(tmp_path, "ops_apply")
    ops_apply = repo_ops_apply / "src/copytrade_pm/pm_operations.py"
    ops_apply.write_text(
        ops_apply.read_text().replace(
            '    top.add_parser("health")\n',
            '    health_cmd = top.add_parser("health")\n'
            '    health_cmd.add_argument("--apply", action="store_true")\n',
            1,
        )
    )
    res_ops_apply = cap.validate(repo_ops_apply)
    assert res_ops_apply["status"] == "BLOCKED"
    assert any("health" in err for err in res_ops_apply["errors"])

    # 5. GROUPS mode drift: uncataloged --apply, choice addition/removal, unsafe READ_ONLY inheritance.
    def _replace_once(file_path: Path, target: str, replacement: str) -> None:
        text = file_path.read_text()
        assert target in text, target
        file_path.write_text(text.replace(target, replacement, 1))

    repo_grp_apply = _copy_repo(tmp_path, "grp_apply")
    _replace_once(
        repo_grp_apply / "src/copytrade_pm/pm_forward_release_candidate.py",
        "    args = parser.parse_args()\n",
        '    parser.add_argument("--apply", action="store_true")\n    args = parser.parse_args()\n',
    )
    res_grp_apply = cap.validate(repo_grp_apply)
    assert res_grp_apply["status"] == "BLOCKED"
    assert (
        "UNLISTED_GROUP_MODE_FLAG:copytrade-pm-paper-candidate-verify:--apply"
        in res_grp_apply["errors"]
    )

    repo_choice = _copy_repo(tmp_path, "grp_choice")
    _replace_once(
        repo_choice / "src/copytrade_pm/pm_prospective_cli.py",
        '("init", "ingest", "audit", "outcome", "inspect")',
        '("init", "ingest", "audit", "outcome", "inspect", "purge")',
    )
    res_choice = cap.validate(repo_choice)
    assert res_choice["status"] == "BLOCKED"
    assert "UNLISTED_GROUP_MODE_CHOICE:copytrade-pm-receipts:action:purge" in res_choice["errors"]

    repo_drop = _copy_repo(tmp_path, "grp_drop")
    _replace_once(
        repo_drop / "src/copytrade_pm/pm_forward_public_trades.py",
        'choices=("observe", "plan")',
        'choices=("observe",)',
    )
    res_drop = cap.validate(repo_drop)
    assert res_drop["status"] == "BLOCKED"
    assert "STALE_GROUP_MODE_CHOICE:copytrade-pm-public-trades:--mode:plan" in res_drop["errors"]

    bad_apply = dict(cap.GROUP_OPERATIONS["paper.public_unit.apply"])
    bad_apply["classification"] = "READ_ONLY"
    monkeypatch.setitem(cap.GROUP_OPERATIONS, "paper.public_unit.apply", bad_apply)
    res_unsafe_apply = cap.validate(ROOT)
    assert res_unsafe_apply["status"] == "BLOCKED"
    assert any("paper.public_unit.apply" in err for err in res_unsafe_apply["errors"])
    monkeypatch.undo()

    monkeypatch.setitem(
        cap.GROUPS,
        "copytrade-pm-public-observer-unit",
        ("paper.public_unit", "paper", "READ_ONLY"),
    )
    res_unsafe_parent = cap.validate(ROOT)
    assert res_unsafe_parent["status"] == "BLOCKED"
    assert (
        "UNSAFE_GROUP_CLASSIFICATION:copytrade-pm-public-observer-unit"
        in res_unsafe_parent["errors"]
    )
    monkeypatch.undo()

    monkeypatch.setitem(
        cap.GROUPS,
        "copytrade-pm-paper-observer-health",
        ("paper.observer_health", "paper", "READ_ONLY"),
    )
    res_unsafe_native_parent = cap.validate(ROOT)
    assert res_unsafe_native_parent["status"] == "BLOCKED"
    assert (
        "UNSAFE_GROUP_CLASSIFICATION:copytrade-pm-paper-observer-health"
        in res_unsafe_native_parent["errors"]
    )
    monkeypatch.undo()

    monkeypatch.setitem(
        cap.GROUP_OPERATIONS,
        "paper.synthetic.apply",
        {
            "script": "copytrade-pm-paper-status",
            "owner": "copytrade_pm.pm_forward_status",
            "family": "paper",
            "interface": "copytrade-pm-paper-status --apply",
            "classification": "READ_ONLY",
            "authority": "SYNTHETIC_TEST",
            "documentation": "docs/AGENT-NATIVE-OPERATIONS.md",
            "required_arguments": ["--state-root PATH"],
            "runtime_required_arguments": [],
            "access": cap._access_entry([], []),
            "limitations": [],
        },
    )
    res_synthetic_apply = cap.validate(ROOT)
    assert res_synthetic_apply["status"] == "BLOCKED"
    assert "UNSAFE_GROUP_CLASSIFICATION:paper.synthetic.apply" in res_synthetic_apply["errors"]
    monkeypatch.undo()

    # 6. GROUPS required_arguments vs runtime_required_arguments drift fails closed.
    bad_inspect = dict(cap.GROUP_OPERATIONS["source.receipts.inspect"])
    bad_inspect["required_arguments"] = [
        "--auditor-public-key PATH",
        "--research-root PATH",
        "--asof UTC",
    ]
    monkeypatch.setitem(cap.GROUP_OPERATIONS, "source.receipts.inspect", bad_inspect)
    res_grp_req = cap.validate(ROOT)
    assert res_grp_req["status"] == "BLOCKED"
    assert any("source.receipts.inspect" in err for err in res_grp_req["errors"])
    monkeypatch.undo()

    # 7. pm03_cli dynamic JSON dispatch drift and unsupported pattern fail closed.
    repo_pm03 = _copy_repo(tmp_path, "pm03_add")
    _replace_once(
        repo_pm03 / "src/copytrade_pm/pm03_cli.py",
        '    else:\n        raise ValueError("UNKNOWN_PM03_ACTION")\n',
        '    elif spec.get("action") == "liquidate":\n        result = {}\n'
        '    else:\n        raise ValueError("UNKNOWN_PM03_ACTION")\n',
    )
    res_pm03 = cap.validate(repo_pm03)
    assert res_pm03["status"] == "BLOCKED"
    assert "UNLISTED_PM03_ACTION:liquidate" in res_pm03["errors"]

    repo_pm03_dyn = _copy_repo(tmp_path, "pm03_dyn")
    _replace_once(
        repo_pm03_dyn / "src/copytrade_pm/pm03_cli.py",
        '    if spec.get("action") == "compare":\n',
        '    handlers = {}\n    if handlers[spec.get("action")]:\n',
    )
    res_pm03_dyn = cap.validate(repo_pm03_dyn)
    assert res_pm03_dyn["status"] == "BLOCKED"
    assert any(
        err.startswith("UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:") for err in res_pm03_dyn["errors"]
    )

    # 8. Unsupported parser AST constructs fail closed rather than silently certifying completeness.
    repo_ops_dyn = _copy_repo(tmp_path, "ops_dyn")
    _replace_once(
        repo_ops_dyn / "src/copytrade_pm/pm_operations.py",
        '    top.add_parser("health")\n',
        '    for extra in list(["health"]):\n        top.add_parser(extra)\n',
    )
    res_ops_dyn = cap.validate(repo_ops_dyn)
    assert res_ops_dyn["status"] == "BLOCKED"
    assert any(
        err.startswith("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:") for err in res_ops_dyn["errors"]
    )

    repo_grp_loop = _copy_repo(tmp_path, "grp_loop")
    _replace_once(
        repo_grp_loop / "src/copytrade_pm/pm_forward_status.py",
        "    args = parser.parse_args()\n",
        '    for opt in ("--extra",):\n        parser.add_argument(opt)\n'
        "    args = parser.parse_args()\n",
    )
    res_grp_loop = cap.validate(repo_grp_loop)
    assert res_grp_loop["status"] == "BLOCKED"
    assert any(
        err.startswith("UNSUPPORTED_GROUP_PARSER_CONSTRUCT:copytrade-pm-paper-status:")
        for err in res_grp_loop["errors"]
    )

    repo_grp_sub = _copy_repo(tmp_path, "grp_sub")
    _replace_once(
        repo_grp_sub / "src/copytrade_pm/pm_forward_status.py",
        "    args = parser.parse_args()\n",
        '    parser.add_subparsers(dest="cmd")\n    args = parser.parse_args()\n',
    )
    res_grp_sub = cap.validate(repo_grp_sub)
    assert res_grp_sub["status"] == "BLOCKED"
    assert (
        "UNSUPPORTED_GROUP_PARSER_CONSTRUCT:copytrade-pm-paper-status:unexpected_subparsers"
        in res_grp_sub["errors"]
    )

    # 9. cwsa_chapter2_gate.add_arguments loop AST and GROUP runtime arg drift fail closed.
    repo_cwsa_loop = _copy_repo(tmp_path, "cwsa_loop")
    _replace_once(
        repo_cwsa_loop / "src/copytrade_pm/pm_cwsa_chapter2_gate.py",
        "def add_arguments(p: argparse.ArgumentParser) -> None:\n",
        "def add_arguments(p: argparse.ArgumentParser) -> None:\n"
        '    for opt in ("--extra",):\n        p.add_argument(opt)\n',
    )
    res_cwsa_loop = cap.validate(repo_cwsa_loop)
    assert res_cwsa_loop["status"] == "BLOCKED"
    assert any(
        err.startswith("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_")
        for err in res_cwsa_loop["errors"]
    )

    bad_runtime_grp = dict(cap.GROUP_OPERATIONS["source.receipts.ingest"])
    bad_runtime_grp["runtime_required_arguments"] = ["--nonexistent PATH"]
    monkeypatch.setitem(cap.GROUP_OPERATIONS, "source.receipts.ingest", bad_runtime_grp)
    res_stale_rt = cap.validate(ROOT)
    assert res_stale_rt["status"] == "BLOCKED"
    assert "STALE_GROUP_RUNTIME_ARG:source.receipts.ingest:--nonexistent" in res_stale_rt["errors"]
    monkeypatch.undo()


def test_public_cli_capabilities_and_no_new_optional_imports_or_writes(tmp_path: Path) -> None:
    # Public CLI list / show / validate on new SUBCOMMAND and GROUP mode entries.
    code_list, payload_list = _run(["capabilities", "list", "--json"])
    assert code_list == 0
    assert payload_list["schema"] == "copytrade_capability_list_v1"
    listed_ids = {item["id"] for item in payload_list["capabilities"]}
    assert {
        "operations.cwsa.chapter2.verify",
        "operations.capabilities.show",
        "portfolio.list",
        "research.show",
        "paper.public_unit.preview",
        "account.pm03.simulate.compare",
    } <= listed_ids

    for target_id in (
        "operations.cwsa.chapter2.verify",
        "research.show",
        "paper.public_unit.preview",
        "account.pm03.simulate.compare",
    ):
        code_show, detail = _run(["capabilities", "show", target_id, "--json"])
        assert code_show == 0, (target_id, detail)
        assert detail["id"] == target_id
        assert detail["kind"] == "SUBCOMMAND"
        assert "required_arguments" in detail
        assert "runtime_required_arguments" in detail
        assert "UNKNOWN" not in detail["access"].values()

    code_val, payload_val = _run(["capabilities", "validate", "--json"])
    assert code_val == 0
    assert payload_val["status"] == "VERIFIED"
    assert payload_val["errors"] == []
    assert payload_val["limitations"]

    # Subprocess public CLI check: no new optional provider imports, network, credential reads, or writes.
    repo = _copy_repo(tmp_path, "cli_readonly")
    before = {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }
    home_missing = tmp_path / "no_credentials_home"
    script = """
import io, json, os, socket, sys
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

def _forbid_network(*args, **kwargs):
    raise AssertionError("NETWORK_ACCESS_FORBIDDEN")

socket.socket.__init__ = _forbid_network
socket.create_connection = _forbid_network
socket.getaddrinfo = _forbid_network
urllib.request.urlopen = _forbid_network

from copytrade_pm import pm_operations as ops

root = sys.argv[1]
results = []
for argv in (
    ["--root", root, "capabilities", "list", "--json"],
    ["--root", root, "capabilities", "show", "operations.cwsa.chapter2.verify", "--json"],
    ["--root", root, "capabilities", "show", "paper.public_unit.preview", "--json"],
    ["--root", root, "capabilities", "validate", "--json"],
):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ops.cli(argv)
    results.append((code, json.loads(buf.getvalue())))

new_forbidden = [
    m for m in ("polars", "ccxt", "websockets", "prefect", "httpx") if m in sys.modules
]
print(json.dumps({
    "codes": [c for c, _ in results],
    "validate_status": results[-1][1]["status"],
    "show_ops_req": results[1][1]["required_arguments"],
    "show_ops_rt": results[1][1]["runtime_required_arguments"],
    "new_forbidden": new_forbidden,
}))
"""
    env = {"PATH": "", "HOME": str(home_missing)}
    proc = subprocess.run(
        [sys.executable, "-c", script, str(repo)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(proc.stdout)
    assert payload["codes"] == [0, 0, 0, 0]
    assert payload["validate_status"] == "VERIFIED"
    assert payload["show_ops_req"] == ["--stage STAGE"]
    assert "--receipt PATH" in payload["show_ops_rt"]
    assert payload["new_forbidden"] == []
    after = {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }
    assert after == before


def test_operations_and_group_owner_parser_dispatch_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from copytrade_pm import pm03_cli
    from copytrade_pm import pm_forward_protected_units as protected_units
    from copytrade_pm import pm_forward_public_unit as public_unit
    from copytrade_pm import pm_prospective_cli as prospective_cli
    from test_pm03_extended import book

    # 1. pm_operations parser enforces required_arguments vs optional runtime_required_arguments.
    p = ops.parser()
    for bad_argv in (
        ["cwsa", "chapter2", "verify"],
        ["cwsa", "chapter2", "projection"],
        ["research", "show"],
        ["contracts", "compare"],
    ):
        with pytest.raises(SystemExit) as exc:
            p.parse_args(bad_argv)
        assert exc.value.code == 2

    args_show = p.parse_args(["research", "show", "job-1"])
    assert args_show.id == "job-1" and args_show.cache_root is None
    args_rules = p.parse_args(["contracts", "rules"])
    assert args_rules.group == "contracts" and args_rules.verb == "rules"
    code_rules, rules_payload = _run(["contracts", "rules"])
    assert code_rules == 0
    assert rules_payload["contracts"]

    # 2. pm_prospective_cli distinguishes parser-required flags from runtime-required per action.
    with pytest.raises(SystemExit) as exc_prosp:
        prospective_cli.run(["inspect"])
    assert exc_prosp.value.code == 2

    class _NoWriteLedger:
        head_sha = "0" * 64

    monkeypatch.setattr(prospective_cli, "open_ledger", lambda **_: _NoWriteLedger())
    key_file = tmp_path / "pub.key"
    key_file.write_bytes(b"k" * 32)
    base_prosp = [
        "--research-root",
        str(tmp_path / "research"),
        "--ledger",
        str(tmp_path / "ledger"),
        "--auditor-public-key",
        str(key_file),
    ]
    with pytest.raises(ValueError, match="MISSING_PRODUCER_RECEIPTS_DIRECTORY"):
        prospective_cli.run(["ingest", *base_prosp])
    with pytest.raises(ValueError, match="ASOF_REQUIRED"):
        prospective_cli.run(["inspect", *base_prosp])
    with pytest.raises(ValueError, match="MISSING_SIGNED_ATTESTATION_FILE"):
        prospective_cli.run(["audit", *base_prosp])
    assert not (tmp_path / "ledger").exists()

    # 3. pm_forward_protected_units separates argparse --out from runtime --revision / --verify.
    monkeypatch.setattr(sys, "argv", ["copytrade-pm-paper-unit-bundle"])
    with pytest.raises(SystemExit) as exc_units_req:
        protected_units.main()
    assert exc_units_req.value.code == 2

    bundle_dir = tmp_path / "unused_bundle"
    monkeypatch.setattr(sys, "argv", ["copytrade-pm-paper-unit-bundle", "--out", str(bundle_dir)])
    with pytest.raises(SystemExit) as exc_units_rt:
        protected_units.main()
    assert exc_units_rt.value.code == 2
    assert not bundle_dir.exists()

    # 4. pm_forward_public_unit omits install() cleanly when --apply is absent.
    install_called = False

    def _forbid_install(*args: object, **kwargs: object) -> str:
        nonlocal install_called
        install_called = True
        raise AssertionError("install() must not run without --apply")

    monkeypatch.setattr(
        public_unit,
        "plan",
        lambda **_: (
            {"schema": "preview", "status": "PLANNED", "unit_path": str(tmp_path / "u")},
            "unit",
        ),
    )
    monkeypatch.setattr(public_unit, "install", _forbid_install)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "copytrade-pm-public-observer-unit",
            "--revision",
            "a" * 40,
            "--registry",
            str(tmp_path / "r.sqlite"),
            "--primary-dir",
            str(tmp_path / "p"),
            "--secondary-dir",
            str(tmp_path / "s"),
            "--state-root",
            str(tmp_path / "st"),
        ],
    )
    public_unit.main()
    assert install_called is False

    # 5. pm03_cli.execute fails closed on unknown dynamic JSON action without writing reports.
    out_dir = tmp_path / "pm03_out"
    with pytest.raises(ValueError, match="UNKNOWN_PM03_ACTION"):
        pm03_cli.execute(
            {
                "schema": "pm03_cli_input_v1",
                "action": "bogus",
                "mode": "RESEARCH_SYNTHETIC",
                "rulebook": book().to_dict(),
            },
            out_dir,
        )
    assert not out_dir.exists()
