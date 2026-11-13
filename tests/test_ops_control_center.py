"""Read-only Ops Control Center: contract, provenance, HTTP and hostile request tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import dashboard_server as server


@pytest.fixture()
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    registry = tmp_path / "wallet_registry.sqlite"
    projection = tmp_path / "projection.sqlite"
    ops = tmp_path / "ops.sqlite"
    with closing(sqlite3.connect(registry)) as con:
        con.executescript("""
            CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY, address TEXT NOT NULL);
            CREATE TABLE wallet_aliases(wallet_id INTEGER, alias TEXT, known_at TEXT);
            CREATE TABLE portfolio_memberships(wallet_id INTEGER, portfolio_id TEXT, version INTEGER, member_alias TEXT);
            CREATE TABLE import_runs(manifest_sha256 TEXT, observed_at TEXT);
            CREATE TABLE exclusions(wallet_id INTEGER, reason TEXT);
            CREATE TABLE portfolio_seals(portfolio_id TEXT, version INTEGER, definition_sha256 TEXT, selection_known_at TEXT);
            INSERT INTO wallets VALUES (1, '0xSECRET_ONE'), (2, '0xSECRET_TWO');
            INSERT INTO wallet_aliases VALUES (1, 'W001', '2026-10-01T00:00:00+00:00');
            INSERT INTO wallet_aliases VALUES (1, 'FUTURE_ALIAS', '2050-10-01T00:00:00+00:00');
            INSERT INTO portfolio_seals VALUES ('P1', 1, 'original-seal-sha', '2026-10-04T00:00:00+00:00');
            INSERT INTO portfolio_memberships VALUES (1, 'P1', 1, 'W001');
            INSERT INTO import_runs VALUES ('not-live-inventory', '2026-10-01T00:00:00+00:00');
            INSERT INTO exclusions VALUES (2, 'reviewed-exclusion');
        """)
        con.commit()
    with closing(sqlite3.connect(projection)) as con:
        con.executescript("""
            CREATE TABLE expert_equity(wallet_id TEXT, account_value TEXT);
            INSERT INTO expert_equity VALUES ('0xsecret_one', '1245.75');
        """)
        con.commit()
    with closing(sqlite3.connect(ops)) as con:
        con.executescript("""
            CREATE TABLE ops_records(
                id TEXT, category TEXT, title TEXT, status TEXT, basis TEXT,
                quality TEXT, severity TEXT, owner TEXT, source_ref TEXT,
                details TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE event_log(
                id INTEGER, entity_type TEXT, entity_id TEXT, action TEXT,
                actor TEXT, created_at TEXT
            );
            INSERT INTO ops_records VALUES (
                'forged', 'decision', 'Historical seed approval', 'approved',
                'paper', 'verified', 'normal', 'old', 'AGENTS.md',
                'not an independent signature', '2026-10-01', '2026-10-01'
            );
            INSERT INTO event_log VALUES (1,'ops_record','forged','created','old','2026-10-01');
        """)
        con.commit()
    monkeypatch.setattr(server, "REGISTRY_DB", registry)
    monkeypatch.setattr(server, "PROJECTION_DB", projection)
    monkeypatch.setattr(server, "OPS_DB", ops)
    return registry, projection, ops


def test_registry_seal_alias_as_of_and_unknowns(source):
    registry, projection, ops = source
    before = [sha256(path.read_bytes()).hexdigest() for path in source]
    data = server.get_sqlite_state(registry, projection, ops)
    assert [sha256(path.read_bytes()).hexdigest() for path in source] == before
    assert len(data["wallets"]) == 2
    assert data["wallets"][0]["alias"] == "W001"  # 2050 alias not known now
    assert data["wallets"][1]["alias"] is None
    assert data["wallets"][0]["address"] == "registry-wallet-1"
    assert data["wallets"][0]["sourceEquityUsd"] == "1245.75"
    assert data["wallets"][0]["eligibility"] == "pending"
    assert data["wallets"][1]["eligibility"] == "ineligible"
    assert data["wallets"][0]["drawdownPct"] is None
    assert data["portfolios"][0]["walletAddressesJson"] == '["W001"]'
    assert data["portfolios"][0]["totalRiskUsd"] is None
    assert data["portfolios"][0]["podCount"] is None
    assert data["portfolios"][0]["detailsJson"].find('"paperRunning": "UNKNOWN"') >= 0
    assert data["records"][0]["reportedStatus"] == "approved"
    assert data["records"][0]["status"] == "pending"
    assert data["records"][0]["quality"] == "unverified"
    assert data["registrySync"]["latestAccepted"] is None
    attempt = data["registrySync"]["latestAttempt"]
    assert attempt["databaseIntegrity"] == "VERIFIED"
    assert attempt["inventorySha256"] is None
    assert attempt["sourceManifestSha256"] == "not-live-inventory"
    assert attempt["walletUnresolved"] == 1
    assert data["runtime"]["observerMode"] == "NO_TRADE"
    assert "0xSECRET_ONE" not in json.dumps(data)


@pytest.fixture()
def http_server(source):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.DashboardHandler)
    worker = Thread(target=srv.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()
        srv.server_close()
        worker.join(timeout=2)


def request(url: str, method: str = "GET", data: bytes | None = None):
    r = Request(
        url,
        method=method,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://malicious.example",
        },
    )
    try:
        with urlopen(r, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        with closing(error):
            return error.code, dict(error.headers), error.read()


def test_http_api_cors_cache_and_no_trade(http_server: str):
    status, headers, raw = request(http_server + "/api/state")
    assert status == 200
    assert headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert "Access-Control-Allow-Origin" not in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    # Cloudflare's request-specific JS Detection bootstrap is inline. This
    # unprivileged viewer has no public writer and forbids event attributes.
    assert "script-src 'self' 'unsafe-inline'" in headers["Content-Security-Policy"]
    assert "script-src-attr 'none'" in headers["Content-Security-Policy"]
    payload = json.loads(raw)
    assert len(payload["wallets"]) == 2
    assert payload["registrySync"]["latestAccepted"] is None
    assert json.loads(request(http_server + "/api/health")[2])["mode"] == "NO_TRADE"
    for method, target in [
        ("POST", "/api/records"),
        ("PATCH", "/api/records/forged"),
        ("PUT", "/api/records/forged"),
        ("DELETE", "/api/records/forged"),
        ("OPTIONS", "/api/state"),
    ]:
        code, denied_headers, denied_body = request(
            http_server + target, method, b'{"status":"approved"}'
        )
        assert code == 403, (method, code)
        assert b"Read-only" in denied_body
        assert "Access-Control-Allow-Origin" not in denied_headers
    assert request(http_server + "/api/unknown")[0] == 404
    assert request(http_server + "/api/records")[0] == 200
    assert request(http_server + "/")[0] == 200
    assert request(http_server + "/does-not-exist")[0] == 404


def test_concurrent_readers_no_write_or_sqlite_pin(http_server: str, source):
    before = [sha256(path.read_bytes()).hexdigest() for path in source]
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda _: request(http_server + "/api/state")[0], range(24)))
    assert replies == [200] * 24
    assert [sha256(path.read_bytes()).hexdigest() for path in source] == before


def test_owner_view_http_is_exact_cli_view_and_read_only(source, http_server, monkeypatch):
    """One bounded portfolio query delegates to the existing CLI decision owner."""
    from copytrade_pm import pm_operations
    from copytrade_pm import pm_cwsa_chapter2_projection as projection

    original = {
        "schema": "cwsa_chapter2_task_explanation_v1",
        "observed_at": "2026-11-13T00:00:12+00:00",
        "assessment_asof": "2026-11-13T00:00:12+00:00",
        "scope": {
            "operation": "EXPLAIN_CHAPTER2_PORTFOLIO",
            "portfolio": "A",
            "inspection": "evidence",
            "epoch": "epoch-test",
            "version": 2,
            "selection_known_at": "2026-11-01T00:00:00Z",
            "new_risk_source_status": "BLOCKED_EVIDENCE",
        },
        "owner_heads": {
            "registry": {"inventory_sha256": "c" * 64},
            "source": {
                "head_sha256": "a" * 64,
                "source_heads_by_wallet": {"W028": "b" * 64},
                "receipt_first_known_ms_by_wallet": {"W028": 1794500000123},
                "original_checkpoint_by_wallet_ms": {"W028": 1794500000000},
                "published_ms_by_wallet": {"W028": 1794500000130},
                "policy_epochs_by_wallet": {"W028": "c" * 64},
            },
        },
        "dimensions": {
            "source_observation": {
                "state": "BLOCKED_EVIDENCE",
                "owner": "pm_checkpoint_journal",
                "evidence": {"private_raw_journal": "PRIVATE_CANARY"},
            },
            "paper_finance": {"state": "UNKNOWN", "owner": "pm03_account"},
            "guardian_authorization": {"state": "UNKNOWN", "owner": "prop-production Guardian"},
        },
        "blockers": [
            {"reason_code": "SOURCE_CHECKPOINT_STALE", "owner": "source", "affected_portfolio": "A"}
        ],
        "generation_consistency": {"state": "MIXED", "reasons": ["SOURCE_POLICY_EPOCHS_MIXED"]},
        "fault_isolation": {
            "affected_portfolios": ["A", "Combo2"],
            "unaffected_source_portfolios": ["B", "C"],
            "shared_account_risk": {"state": "UNKNOWN", "owner": "prop-production Guardian"},
        },
        "prior_to_current": None,
        "economics": {
            "realized_pnl_usd": None,
            "total_costs_usd": None,
            "current_equity_usd": None,
            "drawdown_usd": None,
        },
        "next_operation": {
            "id": "operations.cwsa.chapter2.explain",
            "effect_class": "READ_ONLY",
            "auto_dispatched": False,
            "required_arguments": ["--inspection evidence"],
            "owner": "copytrade_pm.pm_cwsa_chapter2_projection",
        },
        "trading_authorized": False,
        "order_route": "NONE",
        "financially_active": False,
        "scientifically_qualified": False,
        "raw_account": "PRIVATE_CANARY",
    }
    calls = []

    def fake_explain(args):
        calls.append((args.verb, args.portfolio, args.inspection, args.registry_db))
        return original

    monkeypatch.setattr(projection, "explain_task", fake_explain)
    monkeypatch.setattr(
        server,
        "_invoke_owner_cli",
        lambda argv: pm_operations.dispatch(pm_operations.parser().parse_args(argv)),
    )
    expected = pm_operations.dispatch(
        pm_operations.parser().parse_args(
            [
                "cwsa",
                "chapter2",
                "site-view",
                "--portfolio",
                "A",
                "--inspection",
                "evidence",
                "--registry-db",
                str(source[0]),
            ]
        )
    )
    before = [sha256(path.read_bytes()).hexdigest() for path in source]
    code, headers, raw = request(http_server + "/api/owner-view?portfolio=A&inspection=evidence")
    assert code == 200
    assert "Access-Control-Allow-Origin" not in headers
    assert headers["Cache-Control"].startswith("no-store")
    assert json.loads(raw) == expected
    assert calls == [
        ("site-view", "A", "evidence", source[0]),
        ("site-view", "A", "evidence", source[0]),
    ]
    assert "PRIVATE_CANARY" not in raw.decode()
    assert json.loads(raw)["economics"]["realized_pnl_usd"] is None
    assert [sha256(path.read_bytes()).hexdigest() for path in source] == before


@pytest.mark.parametrize(
    "query",
    [
        "portfolio=UNKNOWN",
        "portfolio=0x0123456789abcdef0123456789abcdef01234567",
        "portfolio=A&portfolio=B",
        "portfolio=A&inspection=finance",
        "portfolio=A&inspection=evidence&path=/etc/passwd",
        "portfolio=A%2FB",
        "",
        "portfolio=A&inspection=evidence&inspection=metadata",
    ],
)
def test_owner_view_denies_unbounded_scopes(http_server, query):
    code, headers, raw = request(http_server + "/api/owner-view?" + query)
    assert code == 400
    assert "Access-Control-Allow-Origin" not in headers
    assert b"/home/quant" not in raw


def test_owner_view_fails_closed_when_owner_unavailable(http_server, monkeypatch):
    def unavailable(_args):
        raise OSError("PRIVATE_JOURNAL_PATH_MUST_NOT_ESCAPE")

    monkeypatch.setattr(server, "_invoke_owner_cli", unavailable)
    code, _, raw = request(http_server + "/api/owner-view?portfolio=A&inspection=evidence")
    assert code == 503
    assert b"PRIVATE_JOURNAL" not in raw
    assert json.loads(raw)["status"] == "UNKNOWN"
    for method in ("POST", "PATCH", "PUT", "DELETE", "OPTIONS"):
        assert request(http_server + "/api/owner-view?portfolio=A", method, b"{}")[0] == 403


def test_owner_view_portfolio_allowlist_is_the_native_owner():
    from copytrade_pm.pm_cwsa_six_paper import PORTFOLIO_CONFIGS

    assert server._CHAPTER2_PORTFOLIOS == set(PORTFOLIO_CONFIGS)


def test_owner_view_uses_explicit_dependency_complete_interpreter(source, monkeypatch):
    """Actual pinned CLI module runs externally, not in the system Python daemon."""
    monkeypatch.delenv("COPYTRADE_OPS_OWNER_PYTHON", raising=False)
    with pytest.raises(FileNotFoundError, match="interpreter"):
        server._invoke_owner_cli(["cwsa", "chapter2", "site-view", "--portfolio", "A"])
    monkeypatch.setenv("COPYTRADE_OPS_OWNER_PYTHON", sys.executable)
    payload = server._invoke_owner_cli(
        [
            "cwsa",
            "chapter2",
            "site-view",
            "--portfolio",
            "A",
            "--inspection",
            "metadata",
            "--registry-db",
            str(source[0]),
        ]
    )
    assert payload["schema"] == "cwsa_chapter2_site_owner_view_v1"
    assert payload["scope"]["portfolio"] == "A"
    assert payload["trading_authorized"] is False
    assert payload["economics"]["realized_pnl_usd"] is None


def test_owner_view_rejects_owner_error_exit_and_untrusted_permission(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("COPYTRADE_OPS_OWNER_PYTHON", sys.executable)
    result = {
        "schema": "cwsa_chapter2_site_owner_view_v1",
        "trading_authorized": False,
        "order_route": "NONE",
    }

    def owner_error(*_args, **_kwargs):
        return SimpleNamespace(returncode=2, stdout=json.dumps(result), stderr="PRIVATE_KEY")

    monkeypatch.setattr(server.subprocess, "run", owner_error)
    with pytest.raises(OSError, match="inspection failed"):
        server._invoke_owner_cli(["cwsa", "chapter2", "site-view"])

    result["trading_authorized"] = True

    def unauthorized(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="PRIVATE_KEY")

    monkeypatch.setattr(server.subprocess, "run", unauthorized)
    with pytest.raises(ValueError, match="permission"):
        server._invoke_owner_cli(["cwsa", "chapter2", "site-view"])


def test_missing_authoritative_registry_fails_closed(
    source, monkeypatch: pytest.MonkeyPatch, http_server: str
):
    monkeypatch.setattr(server, "REGISTRY_DB", Path("/nonexistent/no-registry.sqlite"))
    code, _, raw = request(http_server + "/api/state")
    assert code == 503
    assert json.loads(raw) == {"error": "Registry unavailable"}
