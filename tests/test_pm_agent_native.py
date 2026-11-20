"""Agent-native discovery, authority routing and read-only contract checks.

The installed surface is one entry point with five domain groups plus
`capabilities`. Discovery must stay static, read-only, and free of optional
provider imports; every retired path fails closed instead of being shimmed.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from copytrade_pm import pm_capabilities as cap
from copytrade_pm import pm_operations as ops

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {"capabilities", "facts", "research", "roster", "paper", "release"}


def _run(argv: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = ops.cli(argv)
    return code, json.loads(output.getvalue())


def _copy_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    shutil.copytree(ROOT / "src", repo / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "docs", repo / "docs")
    shutil.copytree(
        ROOT / "scripts", repo / "scripts", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    return repo


def test_inventory_covers_the_single_installed_entry_point() -> None:
    result = cap.validate(ROOT)
    assert result["status"] == "VERIFIED", result["errors"]
    assert result["cli_count"] == 1
    entries = {x["id"]: x for x in cap.inventory(ROOT)}
    assert len(entries) == result["capability_count"]
    assert entries["operations.cli"]["interface"] == "copytrade-pm"
    assert entries["operations.cli"]["classification"] == "READ_ONLY"
    assert entries["operations.release.sign"]["classification"] == "PROTECTED_MUTATION"
    assert entries["operations.roster.commit"]["classification"] == "PROTECTED_MUTATION"
    assert entries["operations.facts.verify"]["classification"] == "READ_ONLY"
    assert entries["operations.paper.status"]["classification"] == "READ_ONLY"
    assert entries["operations.release.status"]["classification"] == "READ_ONLY"
    assert all(item["classification"] != "UNCLASSIFIED" for item in entries.values())
    # The retired registry CLI is not discoverable in any form.
    assert not [key for key in entries if key.startswith("registry.")]


def test_cli_unknown_capability_and_catalog_drifts_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, response = _run(["capabilities", "show", "nonexistent.command"])
    assert code == 2 and response["status"] == "UNKNOWN"
    original = cap.GROUPS.copy()
    monkeypatch.delitem(cap.GROUPS, "copytrade-pm")
    bad = cap.validate(ROOT)
    assert bad["status"] == "BLOCKED"
    assert "UNREVIEWED_ENTRY_POINTS" in bad["errors"]
    monkeypatch.setattr(cap, "GROUPS", original)


def test_static_agent_resolution_cases_and_docs() -> None:
    entries = {x["id"]: x for x in cap.inventory(ROOT)}
    for question, name in (
        ("seat book", "operations.roster.show"),
        ("paper mandates", "operations.paper.mandates"),
        ("signed release", "operations.release.sign"),
        ("fact coverage", "operations.facts.coverage"),
        ("contract EV", "research.contract_selector.compare"),
        ("health capture", "operations.facts.capture-health"),
        ("runtime health", "runtime.health"),
        ("PM03 equity", "account.pm03"),
        ("worker health", "runtime.paper_units"),
        ("market observer", "runtime.market_observer"),
    ):
        found = entries[name]
        assert found["available"], question
        assert (ROOT / found["documentation"]).is_file(), question
        assert found["authority"] and found["classification"], question
    assert ops._research("research.list")["status"] == "UNKNOWN"
    assert "native_interface" in ops._research("research.list")["data"]


def test_required_native_first_agent_instructions() -> None:
    for path in ("AGENTS.md", "docs/INDEX.md", "docs/ARCHITECTURE.md", "docs/RUNBOOK.md"):
        assert "AGENT-NATIVE-OPERATIONS.md" in (ROOT / path).read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    for instruction in ("capabilities list", "capabilities show", "capabilities validate"):
        assert instruction in agents


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


def test_operations_subcommands_are_cataloged_for_the_five_groups() -> None:
    entries = {item["id"]: item for item in cap.inventory(ROOT)}
    leaves = set(cap.OPERATIONS_SUBCOMMANDS)
    assert {leaf.split()[0] for leaf in leaves} == GROUPS
    for leaf in leaves:
        spec = cap.OPERATIONS_SUBCOMMANDS[leaf]
        item = entries[spec["id"]]
        assert item["classification"] == spec["classification"]
        if spec["classification"] == "READ_ONLY":
            assert item["access"]["write_targets"] == [], leaf
        else:
            assert item["access"]["write_targets"], leaf
        assert "UNKNOWN" not in item["access"].values(), leaf

    assert entries["operations.release.chapter2.verify"]["required_arguments"] == ["--stage STAGE"]
    assert (
        "--receipt PATH"
        in entries["operations.release.chapter2.verify"]["runtime_required_arguments"]
    )
    sign_required = set(entries["operations.release.sign"]["required_arguments"])
    assert "--reviewer-public ED25519_PUBLIC_KEY_PATH" in sign_required
    assert "--source-observer-public ED25519_PUBLIC_KEY_PATH" in sign_required
    assert entries["operations.facts.capture-health"]["classification"] == "LOCAL_MUTATION"
    assert entries["operations.release.export"]["classification"] == "READ_ONLY"
    assert entries["operations.facts.benchmark"]["access"]["privacy"] == "SYNTHETIC"


def test_operations_validator_fails_closed_on_leaf_and_classification_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = cap.validate(ROOT)
    assert baseline["status"] == "VERIFIED", baseline["errors"]

    # 1. A renamed leaf is both unlisted and stale.
    repo_rename = _copy_repo(tmp_path, "ops_rename")
    target = repo_rename / "src/copytrade_pm/pm_operations.py"
    target.write_text(
        target.read_text().replace(
            'roster_verbs.add_parser("show"', 'roster_verbs.add_parser("view"', 1
        )
    )
    res_rename = cap.validate(repo_rename)
    assert res_rename["status"] == "BLOCKED"
    assert "UNLISTED_OPERATIONS_LEAF:roster view" in res_rename["errors"]
    assert "STALE_OPERATIONS_LEAF:roster show" in res_rename["errors"]

    # 2. A parser drift in the imported Chapter 2 owner fails closed.
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
    assert (
        "MISSING_OPERATIONS_REQUIRED_ARG:release chapter2 verify:--new-token" in res_cwsa["errors"]
    )

    # 3. Reading a mutation as READ_ONLY fails closed.
    bad = dict(cap.OPERATIONS_SUBCOMMANDS["roster commit"])
    bad["classification"] = "READ_ONLY"
    monkeypatch.setitem(cap.OPERATIONS_SUBCOMMANDS, "roster commit", bad)
    res_unsafe = cap.validate(ROOT)
    assert res_unsafe["status"] == "BLOCKED"
    assert any("roster commit" in err for err in res_unsafe["errors"])
    monkeypatch.undo()


def test_public_cli_capabilities_and_no_optional_imports_or_writes(tmp_path: Path) -> None:
    code_list, payload_list = _run(["capabilities", "list", "--json"])
    assert code_list == 0
    listed_ids = {item["id"] for item in payload_list["capabilities"]}
    assert {
        "operations.release.chapter2.verify",
        "operations.capabilities.show",
        "operations.roster.show",
        "operations.facts.capture-health",
        "operations.release.sign",
    } <= listed_ids

    for target_id in (
        "operations.release.chapter2.verify",
        "operations.facts.verify",
        "operations.paper.status",
    ):
        code_show, detail = _run(["capabilities", "show", target_id, "--json"])
        assert code_show == 0, (target_id, detail)
        assert detail["id"] == target_id
        assert "UNKNOWN" not in detail["access"].values()

    code_val, payload_val = _run(["capabilities", "validate", "--json"])
    assert code_val == 0
    assert payload_val["status"] == "VERIFIED" and payload_val["errors"] == []

    repo = _copy_repo(tmp_path, "cli_readonly")
    before = {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }
    home_missing = tmp_path / "no_credentials_home"
    script = """
import io, json, socket, sys
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
    ["--root", root, "capabilities", "show", "operations.release.chapter2.verify", "--json"],
    ["--root", root, "capabilities", "show", "operations.roster.show", "--json"],
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
    "chapter2_req": results[1][1]["required_arguments"],
    "chapter2_rt": results[1][1]["runtime_required_arguments"],
    "new_forbidden": new_forbidden,
}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(repo)],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "", "HOME": str(home_missing)},
    )
    payload = json.loads(proc.stdout)
    assert payload["codes"] == [0, 0, 0, 0]
    assert payload["validate_status"] == "VERIFIED"
    assert payload["chapter2_req"] == ["--stage STAGE"]
    assert "--receipt PATH" in payload["chapter2_rt"]
    assert payload["new_forbidden"] == []
    after = {
        str(p.relative_to(repo)): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()
    }
    assert after == before


def test_operations_parser_enforces_required_arguments_and_group_ownership() -> None:
    p = ops.parser()
    for bad_argv in (
        ["release", "chapter2", "verify"],
        ["release", "chapter2", "projection"],
        ["research", "show"],
        ["research", "contracts", "compare"],
        ["paper", "status"],
    ):
        with pytest.raises(SystemExit) as exc:
            p.parse_args(bad_argv)
        assert exc.value.code == 2

    args_show = p.parse_args(["research", "show", "job-1"])
    assert args_show.id == "job-1" and args_show.cache_root is None
    args_rules = p.parse_args(["research", "contracts", "rules"])
    assert args_rules.group == "research" and args_rules.contract_verb == "rules"
    code_rules, rules_payload = _run(["research", "contracts", "rules"])
    assert code_rules == 0
    assert rules_payload["contracts"]

    # Retired groups are rejected by argparse rather than shimmed.
    for retired in (["wallets", "list"], ["portfolios", "current"], ["status"], ["health"]):
        with pytest.raises(SystemExit) as exc_retired:
            p.parse_args(retired)
        assert exc_retired.value.code == 2


def test_live_module_parsers_keep_their_own_fail_closed_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modules that stay reachable via `python -m` keep their own contracts."""
    from copytrade_pm import pm03_cli
    from copytrade_pm import pm_forward_protected_units as protected_units
    from copytrade_pm import pm_prospective_cli as prospective_cli
    from test_pm03_extended import book

    # argparse-required vs runtime-required remains distinct in the owner parser.
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
    with pytest.raises(ValueError, match="ASOF_REQUIRED"):
        prospective_cli.run(["inspect", *base_prosp])
    assert not (tmp_path / "ledger").exists()

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

    # pm03_cli.execute fails closed on unknown dynamic JSON action without writing reports.
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


# ---------------------------------------------------------------------------
# Ported live parsers (C4): one owner registration, mounted under a group.
# ---------------------------------------------------------------------------


def test_live_parsers_mount_under_the_existing_groups(capsys: pytest.CaptureFixture) -> None:
    p = ops.parser()
    for argv, usage in (
        (["paper", "observe", "-h"], "usage: copytrade-pm paper observe"),
        (["paper", "observer-health", "-h"], "usage: copytrade-pm paper observer-health"),
        (["paper", "run-status", "-h"], "usage: copytrade-pm paper run-status"),
        (["research", "market-audit", "-h"], "usage: copytrade-pm research market-audit"),
        (["research", "ccxt-probe", "-h"], "usage: copytrade-pm research ccxt-probe"),
    ):
        with pytest.raises(SystemExit) as exc:
            p.parse_args(argv)
        assert exc.value.code == 0, argv
        assert usage in capsys.readouterr().out, argv
    # The roster seat view keeps its own required store/account contract.
    with pytest.raises(SystemExit) as exc_status:
        p.parse_args(["paper", "status"])
    assert exc_status.value.code == 2
    seat = p.parse_args(["paper", "status", "--store", "roster.sqlite", "--account", "acct"])
    assert seat.verb == "status" and seat.account == "acct"


def test_paper_observe_is_apply_gated_and_dispatches_its_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from copytrade_pm import pm_forward_observer

    started: list[object] = []

    def forbidden(args) -> int:
        started.append(args)
        raise AssertionError("OBSERVER_STARTED_WITHOUT_APPLY")

    monkeypatch.setattr(pm_forward_observer, "run", forbidden)
    base = [
        "paper",
        "observe",
        "--registry",
        "/tmp/roster.sqlite",
        "--primary-dir",
        "/tmp/primary",
        "--secondary-dir",
        "/tmp/secondary",
        "--state-root",
        "/tmp/observer-state",
    ]
    code, payload = _run(base)
    assert code == 2 and payload["error_code"] == "OBSERVER_APPLY_REQUIRED"
    assert started == []

    def fake_run(args) -> int:
        print(json.dumps({"schema": "stub_observer_v1", "registry": str(args.registry)}))
        return 0

    monkeypatch.setattr(pm_forward_observer, "run", fake_run)
    code, payload = _run([*base, "--apply"])
    assert code == 0 and payload["registry"] == "/tmp/roster.sqlite"


def test_observer_health_gates_only_the_mutating_witness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from copytrade_pm import pm_forward_observer_health

    def fake_run(args) -> int:
        print(json.dumps({"schema": "stub_observer_health_v1", "watch": bool(args.watch)}))
        return 0

    monkeypatch.setattr(pm_forward_observer_health, "run", fake_run)
    state = str(tmp_path / "observer-state")
    code, payload = _run(["paper", "observer-health", "--state-root", state])
    assert code == 0 and payload["watch"] is False

    code, payload = _run(
        ["paper", "observer-health", "--state-root", state, "--continuous", "--watch"]
    )
    assert code == 2 and payload["error_code"] == "OBSERVER_WATCH_APPLY_REQUIRED"

    code, payload = _run(
        ["paper", "observer-health", "--state-root", state, "--continuous", "--watch", "--apply"]
    )
    assert code == 0 and payload["watch"] is True


def test_paper_run_status_reads_one_run_journal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from copytrade_pm import pm_forward_status

    calls: list[dict] = []

    def fake_status(db_path: Path, *, run_id: str, as_of: str, heartbeat_root=None) -> dict:
        calls.append({"db": str(db_path), "run_id": run_id, "heartbeat_root": heartbeat_root})
        return {"schema": "paper_operator_status_v1", "run_id": run_id, "health": "NOT_RUNNING"}

    monkeypatch.setattr(pm_forward_status, "paper_operator_status", fake_status)
    db = tmp_path / "paper-events.sqlite3"
    code, payload = _run(
        [
            "paper",
            "run-status",
            "--db",
            str(db),
            "--run-id",
            "run-1",
            "--heartbeat-root",
            str(tmp_path / "heartbeats"),
            "--as-of",
            "2026-11-20T00:00:00+00:00",
        ]
    )
    assert code == 0 and payload["run_id"] == "run-1"
    assert calls == [{"db": str(db), "run_id": "run-1", "heartbeat_root": tmp_path / "heartbeats"}]


def test_market_audit_writes_only_behind_apply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from copytrade_pm import pm_market_audit

    audited: list[tuple[str, str]] = []

    def fake_inventory(research_root: Path, market_root: Path) -> dict:
        audited.append((str(research_root), str(market_root)))
        return {
            "wallet_count": 1,
            "unique_instrument_days_audited": 1,
            "sha_verified_instrument_days": 1,
            "missing_or_invalid_instrument_days": 0,
            "gaps_by_market": [],
            "wallets": [],
        }

    def fake_write(out: Path, report: dict) -> tuple[Path, str]:
        Path(out).write_text(json.dumps({"wallets": report["wallet_count"]}))
        return Path(out), "0" * 64

    monkeypatch.setattr(pm_market_audit, "inventory", fake_inventory)
    monkeypatch.setattr(pm_market_audit, "_write_private_evidence", fake_write)
    out = tmp_path / "evidence.json"
    argv = [
        "research",
        "market-audit",
        "--research-root",
        str(tmp_path / "research"),
        "--market-root",
        str(tmp_path / "market"),
        "--out",
        str(out),
    ]
    code, payload = _run(argv)
    assert code == 0 and payload["state"] == "DRY_RUN"
    assert audited == [] and not out.exists()

    code, payload = _run([*argv, "--apply"])
    assert code == 0 and payload["evidence_sha256"] == "0" * 64
    assert audited == [(str(tmp_path / "research"), str(tmp_path / "market"))]
    assert out.is_file()


def test_ccxt_probe_is_bounded_and_gates_a_recorded_canary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from copytrade_pm import pm_forward_ccxt_market

    probes: list[dict] = []

    async def fake_probe(insts, *, dexes, timeout, record_root=None) -> dict:
        probes.append(
            {
                "instruments": [item.key for item in insts],
                "dexes": list(dexes),
                "timeout": timeout,
                "record_root": None if record_root is None else str(record_root),
            }
        )
        return {"schema": "paper_ccxt_readonly_probe_v1", "status": "STUB", "quotes": {}}

    monkeypatch.setattr(pm_forward_ccxt_market, "_probe", fake_probe)
    base = [
        "research",
        "ccxt-probe",
        "--instrument",
        "hyperliquid/mainnet:perp:default/BTC",
    ]
    code, payload = _run(base)
    assert code == 0 and payload["status"] == "STUB"
    assert probes[-1]["record_root"] is None

    record_root = str(tmp_path / "record")
    code, payload = _run([*base, "--record-root", record_root])
    assert code == 2 and payload["error_code"] == "CCXT_PROBE_APPLY_REQUIRED"
    assert len(probes) == 1

    code, payload = _run([*base, "--record-root", record_root, "--apply"])
    assert code == 0 and probes[-1]["record_root"] == record_root
    assert probes[-1]["instruments"] == ["hyperliquid/mainnet:perp:default/BTC"]
