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


def test_missing_authoritative_registry_fails_closed(
    source, monkeypatch: pytest.MonkeyPatch, http_server: str
):
    monkeypatch.setattr(server, "REGISTRY_DB", Path("/nonexistent/no-registry.sqlite"))
    code, _, raw = request(http_server + "/api/state")
    assert code == 503
    assert json.loads(raw) == {"error": "Registry unavailable"}
