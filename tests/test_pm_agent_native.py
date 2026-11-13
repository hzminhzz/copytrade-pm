"""Agent-native discovery, authority routing and read-only contract benchmark."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from hashlib import sha256

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
