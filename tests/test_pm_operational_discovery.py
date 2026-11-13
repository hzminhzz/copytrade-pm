"""Operational discovery contract tests (synthetic evidence, no network/broker)."""

from __future__ import annotations

from contextlib import closing, redirect_stdout
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import io
import json

import pytest

from copytrade_pm import pm_capabilities as cap
from copytrade_pm import pm_operations as ops
from copytrade_pm import pm_runtime_readonly as runtime
from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_catalog as catalog
from copytrade_pm.pm_offline_cache import ImmutableCache
from copytrade_pm.pm_offline_job import REPORT
from copytrade_pm.pm_offline_job_catalog import list_reports

from test_wallet_registry_catalog import AFTER, BEFORE, _v2_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def verified_wallets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    whale = "0x5f94" + "0" * 36
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(whale.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    registry.apply(db, snapshot, AFTER)
    return db


@pytest.fixture
def report_cache(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "cache"
    owner = ImmutableCache(root, min_free_bytes=0)
    token = sha256(b"synthetic-immutable-job").hexdigest()
    doc = {
        "schema": REPORT,
        "job_id": "smoke-historical-2026",
        "job_sha256": token,
        "job_kind": "HISTORICAL_ORACLE_NATIVE",
        "clock_basis": "HISTORICAL_ORACLE",
        "status": "COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY",
        "financial_status": "BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN",
        "financial_certified_real": False,
        "scientifically_qualified": False,
        "authorized_for_trading": False,
        "deployed": False,
        "blockers": ["NO_INDEPENDENT_FIRST_KNOWN"],
        "engineering_path_verified": True,
    }
    dependencies = {"job": token, "input": token, "market": token, "software": token}
    published = owner.publish(
        "job_report",
        dependencies,
        version=REPORT,
        content=json.dumps(doc, sort_keys=True, separators=(",", ":")).encode(),
    )
    return root, published["key"]


def _call(argv: list[str]) -> tuple[int, dict]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = ops.cli(argv)
    return code, json.loads(output.getvalue())


def test_wallet_inventory_is_private_and_asof(verified_wallets: Path) -> None:
    args = ["--db", str(verified_wallets), "wallets", "list", "--query", "W083"]
    code, data = _call(args)
    assert code == 0 and data["status"] == "VERIFIED"
    view = data["data"]
    assert view["total"] == 1
    row = view["wallets"][0]
    assert row["identity_state"] == "EVIDENCE_BOUND"
    assert isinstance(row["cohorts"], list)
    assert row["excluded"] is False
    assert row["portfolio_memberships"]
    assert "W083" in [a["alias"] for a in row["aliases"]]
    assert row["trading_authorized"] is False
    assert view["addresses_redacted"]
    assert "0x5f94" not in json.dumps(data)
    code, past = _call([*args, "--asof", BEFORE])
    assert code == 0
    assert past["data"]["total"] == 0


def test_wallet_inventory_filters_and_no_mutations(verified_wallets: Path) -> None:
    saved_bytes = verified_wallets.read_bytes()
    code, excluded = _call(
        ["--db", str(verified_wallets), "wallets", "list", "--excluded", "--limit", "100"]
    )
    assert code == 0
    assert all(row["excluded"] for row in excluded["data"]["wallets"])
    assert excluded["data"]["total"] > 0
    code, subscribed = _call(
        [
            "--db",
            str(verified_wallets),
            "wallets",
            "list",
            "--subscribed",
            "--cohort",
            "research-108",
        ]
    )
    assert code == 0
    assert all(
        x["subscribed"] is True and "research-108" in x["cohorts"]
        for x in subscribed["data"]["wallets"]
    )
    assert verified_wallets.read_bytes() == saved_bytes
    invalid_code, invalid = _call(
        ["--db", str(verified_wallets), "wallets", "list", "--limit", "999999"]
    )
    assert invalid_code == 2 and invalid["status"] == "UNKNOWN"


def test_wallet_alias_collision_is_never_resolved_by_guess(verified_wallets: Path) -> None:
    with closing(registry.connect(verified_wallets, True)) as con, con:
        ids = [
            row[0]
            for row in con.execute("SELECT wallet_id FROM wallets ORDER BY wallet_id LIMIT 2")
        ]
        con.execute(
            "INSERT OR IGNORE INTO wallet_aliases(namespace,alias,wallet_id,known_at) "
            "VALUES(?,?,?,?)",
            ("conflict_test", "COLLIDE", ids[0], AFTER),
        )
        con.execute(
            "INSERT OR IGNORE INTO wallet_aliases(namespace,alias,wallet_id,known_at) "
            "VALUES(?,?,?,?)",
            ("conflict_test_alt", "COLLIDE", ids[1], AFTER),
        )
    code, response = _call(["--db", str(verified_wallets), "wallets", "list", "--query", "COLLIDE"])
    assert code == 0 and response["data"]["total"] == 0
    code, response = _call(["--db", str(verified_wallets), "wallets", "list", "--limit", "200"])
    assert code == 0
    flagged = [row for row in response["data"]["wallets"] if row["ambiguous_alias_count"]]
    assert len(flagged) == 2
    assert all("COLLIDE" not in json.dumps(row["aliases"]) for row in flagged)


def test_sha_verified_research_reports_are_real_cache_objects(
    report_cache: tuple[Path, str],
) -> None:
    root, key = report_cache
    before = {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    reports = list_reports(root)
    assert reports["total"] == 1
    report = reports["reports"][0]
    assert report["cache_key"] == key
    assert report["scientifically_qualified"] is False
    assert report["financial_status"].startswith("BLOCKED_")
    code, query = _call(["research", "list", "--cache-root", str(root)])
    assert code == 0 and query["status"] == "VERIFIED"
    code, show = _call(
        ["research", "show", "smoke-historical-2026", "--cache-root", str(root), "--cache-key", key]
    )
    assert code == 0 and show["data"]["reports"][0] == report
    after = {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    assert after == before


def test_research_corruption_or_unverified_root_fails_closed(
    report_cache: tuple[Path, str], tmp_path: Path
) -> None:
    root, key = report_cache
    payload = root / "job_report" / key[:2] / f"{key}.data"
    payload.write_bytes(payload.read_bytes() + b"\n")
    code, status = _call(["research", "list", "--cache-root", str(root)])
    assert code == 2 and status["status"] == "BLOCKED"
    assert status["scientifically_qualified"] is False
    alias = tmp_path / "unsafe-link"
    alias.symlink_to(root, target_is_directory=True)
    code, status = _call(["research", "list", "--cache-root", str(alias)])
    assert code == 2 and status["status"] == "BLOCKED"
    code, status = _call(["research", "list"])
    assert code == 2 and status["status"] == "UNKNOWN"


def test_research_multiple_revisions_fail_closed(report_cache: tuple[Path, str]) -> None:
    root, key = report_cache
    original = json.loads((root / "job_report" / key[:2] / f"{key}.data").read_text())
    token = sha256(b"separate-source-revision").hexdigest()
    other = {**original, "job_sha256": token}
    owner = ImmutableCache(root, min_free_bytes=0)
    owner.publish(
        "job_report",
        {"job": token, "input": token, "market": token, "software": token},
        version=REPORT,
        content=json.dumps(other, sort_keys=True, separators=(",", ":")).encode(),
    )
    code, response = _call(["research", "show", original["job_id"], "--cache-root", str(root)])
    assert code == 2 and response["status"] == "BLOCKED"
    assert "AMBIGUOUS_RESEARCH_JOB_ID" in response["limitations"][0]


def test_runtime_release_uses_existing_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    returned = {
        "result": "ACTIVE_READ_ONLY_VERIFIED",
        "revision": "a" * 40,
        "registry_timer": "NOT_INSTALLED",
        "source": {"source_manifest_sha256": "b" * 64, "trading_authorized": False},
    }
    calls = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(returned), stderr="")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    res = runtime.installed_release(ROOT)
    assert res["state"] == "VERIFIED"
    assert calls[0][-1] == "verify"
    returned["source"]["trading_authorized"] = True
    assert runtime.installed_release(ROOT)["state"] == "UNKNOWN"


def test_os_units_cannot_establish_protected_paper_running(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_show(*, user_active: bool, system_active: bool, system_error: bool = False):
        def run(argv, **kwargs):
            if "--user" in argv:
                stdout = "\n\n".join(
                    "\n".join(
                        [
                            f"Id={unit}",
                            "LoadState=loaded" if user_active else "LoadState=not-found",
                            "ActiveState=active" if user_active else "ActiveState=inactive",
                            "MainPID=12345" if user_active else "MainPID=0",
                        ]
                    )
                    for unit in runtime.UNITS
                )
                return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
            assert argv[:2] == ["systemctl", "show"]
            if system_error:
                return SimpleNamespace(returncode=1, stdout="", stderr="denied")
            unit = argv[2]
            stdout = (
                f"Id={unit}\n"
                + (
                    "LoadState=loaded\nActiveState=active\nMainPID=9123\n"
                    if system_active
                    else "LoadState=not-found\nActiveState=inactive\nMainPID=0\n"
                )
                + "User=copytrade-paper-p1\nGroup=copytrade-paper-monitor\n"
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        return run

    monkeypatch.setattr(runtime.subprocess, "run", fake_show(user_active=True, system_active=False))
    active_user = runtime.paper_unit_inventory()
    assert active_user["state"] == "DEGRADED"
    assert active_user["protected_worker_attested"] is False

    monkeypatch.setattr(runtime.subprocess, "run", fake_show(user_active=False, system_active=True))
    active_system = runtime.paper_unit_inventory()
    assert active_system["state"] == "DEGRADED"
    assert len(active_system["system_units"]) == 3
    assert active_system["protected_worker_attested"] is False

    monkeypatch.setattr(
        runtime.subprocess, "run", fake_show(user_active=False, system_active=False)
    )
    stopped = runtime.paper_unit_inventory()
    assert stopped["state"] == "NOT_RUNNING"
    assert stopped["protected_worker_attested"] is False

    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        fake_show(user_active=False, system_active=False, system_error=True),
    )
    unavailable = runtime.paper_unit_inventory()
    assert unavailable["state"] == "UNKNOWN"
    assert unavailable["protected_worker_attested"] is False


def test_agent_discovery_scripted_scenarios_not_llm_claim() -> None:
    """Executable real-parser contract, not an observed LLM selection benchmark."""
    tasks = (
        (
            "show current frozen research",
            "portfolio.current",
            "copytrade_pm.wallet_registry_catalog",
        ),
        ("find W083", "wallet.lookup", "copytrade_pm.wallet_registry"),
        ("list excluded wallets", "wallet.inventory", "copytrade_pm.wallet_registry_catalog"),
        ("lookup research job", "research.report.catalog", "copytrade_pm.pm_offline_job_catalog"),
        ("read private paper status", "paper.status", "copytrade_pm.wallet_registry_runs"),
        ("verify installed registry", "runtime.pinned_release", "copytrade_pm.pm_runtime_readonly"),
        ("inspect paper units", "runtime.paper_units", "copytrade_pm.pm_runtime_readonly"),
        ("public observer quotes", "runtime.market_observer", "copytrade_pm.pm_runtime_readonly"),
        ("study replay", "research.offline", "copytrade_pm.pm_offline_job"),
        ("PM03 accounting", "account.pm03", "copytrade_pm.pm03_account"),
        ("portfolio seal", "portfolio.show", "copytrade_pm.wallet_registry_portfolios"),
        ("protected source work", "source.collection", "copytrade_pm.pm_forward_source_stream"),
        (
            "preview new P1/P14 identity seal without backdating",
            "paper.identity_reseal_preview",
            "copytrade_pm.pm_forward_registry_identity",
        ),
    )
    count = 0
    for task, capability, owner in tasks:
        code, item = _call(["capabilities", "show", capability])
        assert code == 0, task
        assert item["owner"] == owner, task
        assert item["available"] and item["documentation"], task
        count += 1
    assert count == 13
    assert cap.validate(ROOT)["status"] == "VERIFIED"
