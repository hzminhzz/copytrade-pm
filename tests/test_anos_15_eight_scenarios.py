"""ANOS-15 (#349) cross-owner end-to-end verification of all eight #334 scenarios.

Exercises the approved Ops Control Center UI/HTTP/CLI target, T02 baseline
comparison limits (#101 host-trace block), and preserved #313 boundaries via
public owner entrypoints without authorizing protected writes or trading.
"""

from __future__ import annotations

from contextlib import closing, contextmanager, redirect_stdout
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
import pytest

from copytrade_pm import (
    pm_agent_trace_eval as trace_eval,
    pm_bounded_acquisition as acq,
    pm_capabilities as cap,
    pm_ci_receipt as ci_receipt,
    pm_copy_mandate as mandates,
    pm_cwsa_chapter2_gate as ch2_gate,
    pm_cwsa_chapter2_projection as ch2_proj,
    pm_cwsa_six_paper as six_paper,
    pm_k_recalibration as k_recal,
    pm_k_release as k_rel,
    pm_offline_job_catalog as job_catalog,
    pm_operations as ops,
    pm_runtime_readonly as runtime,
    pm_v4_sixteen_scenarios as v4_sixteen,
    wallet_registry as reg,
    wallet_registry_catalog as reg_cat,
    wallet_registry_fp_journal as fp_journal,
    wallet_registry_native as reg_native,
    wallet_registry_portfolios as reg_portfolios,
    wallet_registry_qualification as reg_qual,
    wallet_registry_runs as reg_runs,
    wallet_registry_signed_catalog as reg_signed,
)
from copytrade_pm.pm03_account import Instrument, digest
from copytrade_pm.pm03_rules import propr_rulebook
from copytrade_pm.pm_checkpoint_journal import CheckpointScope, CwsaPolicy, SamplingLimits
from copytrade_pm.pm_checkpoint_source import GRID_MS, collect_checkpoint
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_journal import PaperJournal, PaperManifest
from copytrade_pm.pm_offline_cache import ImmutableCache
from copytrade_pm.pm_offline_job import REPORT as OFFLINE_REPORT_SCHEMA
from copytrade_pm.pm_paper_contracts import OpportunityUpdate, PaperOpportunity
from copytrade_pm.production_manifest import sign

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_dashboard_server():
    spec = importlib.util.spec_from_file_location(
        "dashboard_server", REPO_ROOT / "scripts" / "dashboard_server.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dashboard_server: Any = _load_dashboard_server()
RAW_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}\b")
BOUNDARY_MS = int(datetime(2026, 11, 12, 0, 5, tzinfo=UTC).timestamp()) * 1000
REGISTRY_LOCK_AT = "2026-11-05T01:00:00+00:00"
SELECTION_ASOF = "2026-11-06T02:00:00+00:00"
BTC_MARKET = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
WHALE_SYNTH = "0x5f94" + "0" * 36


def _ccxt_btc_market() -> dict[str, Any]:
    return {
        "symbol": "BTC/USDC:USDC",
        "id": "0",
        "base": "BTC",
        "quote": "USDC",
        "settle": "USDC",
        "swap": True,
        "spot": False,
        "linear": True,
        "contract": True,
        "type": "swap",
        "active": True,
        "precision": {"amount": 0.00001, "price": 1.0},
        "limits": {"cost": {"min": 10}},
        "info": {
            "name": "BTC",
            "dex": None,
            "hip3": False,
            "baseId": 0,
            "szDecimals": 5,
        },
    }


@pytest.fixture(autouse=True)
def _pin_synth_whale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind synthetic whale digest so fixtures require zero private files."""
    monkeypatch.setattr(reg_cat, "WHALE_ADDRESS_SHA256", sha256(WHALE_SYNTH.encode()).hexdigest())


def _git_clean(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        text=True,
        env=runtime.clean_git_env(),
    ).strip()


def _call_cli(argv: list[str]) -> tuple[int, dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ops.cli(argv)
    return code, json.loads(buf.getvalue())


def _wallet_addr(alias: str) -> str:
    return "0x" + sha256(alias.encode()).hexdigest()[:40]


def _default_limits() -> SamplingLimits:
    return SamplingLimits(
        max_state_age_ms=4000,
        max_acquisition_ms=3000,
        max_dex_skew_ms=2000,
        publication_grace_ms=180_000,
    )


def _policy_for(tag: str) -> CwsaPolicy:
    return CwsaPolicy(limits=_default_limits(), measurement_sha=digest(["cwsa_policy", tag]))


def _build_locked_registry(
    tmp_path: Path,
) -> tuple[Path, dict[str, dict[str, Any]]]:
    """Create a sealed SQLite registry matching S1 and Chapter 2 requirements."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    db = tmp_path / "registry.sqlite"
    with closing(reg.connect(db, True)) as con:
        with con:
            con.executescript(reg.DDL)
            con.executescript(reg_portfolios.SEALED_DDL)
            con.executescript(reg_cat.DDL)
            con.executescript(reg_signed.DDL)
            con.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(8, ?)",
                (REGISTRY_LOCK_AT,),
            )
            con.execute(
                "INSERT INTO snapshot_meta(key, value) VALUES('observed_at', ?)",
                ("2026-10-01T00:00:00+00:00",),
            )
            v2 = reg_cat.read_v2(REPO_ROOT, observed_at=SELECTION_ASOF)
            wallet_id = 1
            alias_to_id: dict[str, int] = {}
            all_aliases = sorted(
                {
                    "W083",
                    "ACT04",
                    "W080",
                    *six_paper.ALL_14_WALLETS,
                    *(m for pid in reg_portfolios.DECISIONS for m in reg.PORTFOLIOS[pid]),
                    *(m for d in v2["definitions"].values() for m in d["members"]),
                }
            )
            for alias in all_aliases:
                addr = _wallet_addr(alias)
                con.execute(
                    "INSERT INTO wallets(wallet_id, venue, network, address) VALUES(?,?,?,?)",
                    (wallet_id, "hyperliquid", "mainnet", addr),
                )
                con.execute(
                    "INSERT INTO wallet_aliases(namespace, alias, wallet_id, known_at) "
                    "VALUES(?,?,?,?)",
                    ("research_v2", alias, wallet_id, REGISTRY_LOCK_AT),
                )
                alias_to_id[alias] = wallet_id
                wallet_id += 1

            con.execute(
                "INSERT INTO cohorts(cohort_id, version, source_sha256) VALUES(?,?,?)",
                ("research-108", 1, digest(["cohort", "research-108"])),
            )
            for wid in alias_to_id.values():
                con.execute(
                    "INSERT INTO cohort_memberships(cohort_id, version, wallet_id, known_at) "
                    "VALUES(?,?,?,?)",
                    ("research-108", 1, wid, REGISTRY_LOCK_AT),
                )

            seals: dict[str, dict[str, Any]] = {}
            portfolio_ids = list(
                dict.fromkeys(
                    [*reg_portfolios.DECISIONS.keys(), *six_paper.PORTFOLIO_CONFIGS.keys()]
                )
            )
            for pid in portfolio_ids:
                if pid in reg_portfolios.DECISIONS:
                    dec = reg_portfolios.DECISIONS[pid]
                    members = tuple(sorted(reg.PORTFOLIOS[pid]))
                    known_at = dec["known_at"]
                    doc_path = dec["path"]
                    doc_sha = dec["sha256"]
                    commit_sha = dec["commit"]
                    p_status = dec["status"]
                    p_sizing = dec["sizing"]
                    def_payload = {
                        "schema": reg_portfolios.SCHEMA,
                        "portfolio_id": pid,
                        "aliases": list(reg.PORTFOLIOS[pid]),
                        "source_commit": commit_sha,
                        "source_doc_sha256": doc_sha,
                        "selection_known_at": known_at,
                        "status": p_status,
                        "sizing_contract": p_sizing,
                        "source_identity_proven": False,
                        "order_route": "NONE",
                    }
                    def_sha = sha256(reg_portfolios._canonical_json(def_payload)).hexdigest()
                else:
                    cfg = six_paper.PORTFOLIO_CONFIGS[pid]
                    members = tuple(sorted(cfg["members"]))
                    known_at = "2026-11-12T00:00:00+00:00"
                    doc_path = f"docs/{pid}.md"
                    doc_sha = digest(["doc", pid])
                    commit_sha = "cafebabe" * 5
                    p_status = "PAPER_RESEARCH_CANDIDATE"
                    p_sizing = cfg["sizing_contract"]
                    def_sha = digest({"portfolio_id": pid, "version": 2, "members": members})
                con.execute(
                    "INSERT INTO portfolio_versions VALUES(?,?,?,?,?,?)",
                    (pid, 2, p_status, doc_path, known_at, p_sizing),
                )
                for member in members:
                    con.execute(
                        "INSERT INTO portfolio_memberships VALUES(?,?,?,?)",
                        (pid, 2, member, alias_to_id[member]),
                    )
                con.execute(
                    "INSERT INTO portfolio_seals VALUES(?,?,?,?,?,?)",
                    (pid, 2, def_sha, doc_sha, commit_sha, known_at),
                )
                seals[pid] = {
                    "portfolio_id": pid,
                    "version": 2,
                    "definition_sha256": def_sha,
                    "selection_known_at": known_at,
                    "members": members,
                }
            reg_cat.store_selection(con, v2, alias_to_id, REGISTRY_LOCK_AT)
    db.chmod(0o600)
    (tmp_path / "backups").mkdir(mode=0o700, exist_ok=True)
    expected_sha = reg.db_authority_health(db)["inventory_sha256"]
    reg_native.lock_legacy_import(db, expected=expected_sha, apply=True, now=REGISTRY_LOCK_AT)
    return db, seals


def _fresh_boundary_ms() -> int:
    """Return a completed 5-minute UTC boundary strictly inside the 900s freshness window."""
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    grid = (now_ms // GRID_MS) * GRID_MS
    return grid - GRID_MS if now_ms - grid < 5_000 else grid


def _server_env(env: dict[str, Any], *, release_sha: str | None = None) -> dict[str, str | None]:
    cfg: dict[str, str | None] = {
        "COPYTRADE_OPS_OWNER_PYTHON": sys.executable,
        "COPYTRADE_OPS_REGISTRY_DB": str(env["registry_db"]),
        "COPYTRADE_OPS_CWSA_SOURCE_DB": str(env["source_db"]),
        "COPYTRADE_OPS_CWSA_PAPER_ROOT": str(env["paper_root"]),
        "COPYTRADE_OPS_CWSA_QUOTE_DB": str(env["quote_db"]),
        "COPYTRADE_OPS_CWSA_EPOCH": env["epoch"],
    }
    if release_sha is not None:
        cfg["COPYTRADE_OPS_RELEASE_SHA"] = release_sha
    return cfg


def _seed_chapter2_source_and_paper(
    root: Path,
    *,
    registry_db: Path,
    boundary_ms: int | None = None,
    gap_wallets: set[str] | None = None,
    epoch_override_wallets: dict[str, CwsaPolicy] | None = None,
    checkpoint_ms_by_wallet: dict[str, int] | None = None,
    acq_offset_ms_by_wallet: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build isolated canonical source + Chapter 2 empty paper + quote journals."""
    root.mkdir(parents=True, exist_ok=True)
    b_ms = _fresh_boundary_ms() if boundary_ms is None else boundary_ms
    source = PaperJournal(root / "source")
    base_policy = _policy_for("primary")
    gap_wallets = gap_wallets or set()
    epoch_override_wallets = epoch_override_wallets or {}
    checkpoint_ms_by_wallet = checkpoint_ms_by_wallet or {}
    acq_offset_ms_by_wallet = acq_offset_ms_by_wallet or {}

    registered_policies: dict[str, CwsaPolicy] = {}
    for alias in six_paper.ALL_14_WALLETS:
        wallet_policy = epoch_override_wallets.get(alias, base_policy)
        registered_policies[alias] = wallet_policy
        addr = _wallet_addr(alias)
        sc = CheckpointScope(
            source_id=alias,
            account_sha=sha256(addr.encode()).hexdigest(),
            generation="a" * 64,
            selection_sha="b" * 64,
            dexes=("default", "xyz"),
        )
        cp_ms = checkpoint_ms_by_wallet.get(alias, b_ms)
        acq_offset = acq_offset_ms_by_wallet.get(alias, 100)
        source.register_checkpoint_source(
            sc, wallet_policy, first_checkpoint_ms=cp_ms, at_ms=cp_ms - 1
        )
        is_gap = alias in gap_wallets

        def _info(req: dict[str, Any], *, _addr: str = addr, _cp: int = cp_ms, _gap: bool = is_gap):
            if req["type"] == "perpDexs":
                body: Any = [None, {"name": "xyz"}]
            elif _gap and req.get("dex") == "xyz":
                raise TimeoutError("simulated wallet-local dex timeout")
            else:
                body = {
                    "time": _cp,
                    "assetPositions": []
                    if req.get("dex") == "xyz"
                    else [{"position": {"coin": "BTC", "szi": "2", "positionValue": "20000"}}],
                }
            raw = json.dumps(body).encode()
            return body, raw, sha256(raw).hexdigest()

        outcome = collect_checkpoint(
            sc,
            addr,
            checkpoint_ms=cp_ms,
            limits=_default_limits(),
            evidence_root=source.root,
            info=_info,
            now_ms=lambda _cp=cp_ms, _off=acq_offset: _cp + _off,
        )
        source.append_checkpoint_sample(wallet_policy.epoch, outcome, outcome.validated_ms + 1)

    paper_root = root / "paper_root"
    quote_journal = PaperJournal(root / "quotes")
    raw_mkt = _ccxt_btc_market()
    native_mkt = parse_ccxt_market(
        raw_mkt,
        first_known_at=datetime.fromtimestamp((b_ms - 1000) / 1000, UTC).isoformat(),
        expected=BTC_MARKET,
    )
    book_row = parse_ccxt_book(
        native_mkt,
        {
            "symbol": raw_mkt["symbol"],
            "timestamp": b_ms + 100,
            "bids": [[9999, 200]],
            "asks": [[10001, 200]],
        },
        first_known_at=datetime.fromtimestamp((b_ms + 101) / 1000, UTC).isoformat(),
        max_age_seconds=5,
    )
    quote_journal.append_market_quote(book_row.payload())

    supervisor = six_paper.Chapter2PaperSupervisor(
        state_root=paper_root,
        source_db=source.path,
        registry_db=registry_db,
        publication_grace_override_ms=180_000,
        quote_db=quote_journal.path,
    )
    supervisor.poll_once(now_ms=b_ms + 500)
    return {
        "source_db": source.path,
        "registry_db": registry_db,
        "paper_root": paper_root,
        "quote_db": quote_journal.path,
        "epoch": base_policy.epoch,
        "base_policy": base_policy,
        "boundary_ms": b_ms,
    }


@contextmanager
def _temp_env(overrides: dict[str, str | None]):
    prior = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def _live_ops_server(env_overrides: dict[str, str | None]):
    prior_globals = {
        "REGISTRY_DB": dashboard_server.REGISTRY_DB,
        "PROJECTION_DB": dashboard_server.PROJECTION_DB,
        "OPS_DB": dashboard_server.OPS_DB,
    }
    if env_overrides.get("COPYTRADE_OPS_REGISTRY_DB"):
        dashboard_server.REGISTRY_DB = Path(str(env_overrides["COPYTRADE_OPS_REGISTRY_DB"]))
    if env_overrides.get("COPYTRADE_OPS_PROJECTION_DB"):
        dashboard_server.PROJECTION_DB = Path(str(env_overrides["COPYTRADE_OPS_PROJECTION_DB"]))
    if env_overrides.get("COPYTRADE_OPS_RECORDS_DB"):
        dashboard_server.OPS_DB = Path(str(env_overrides["COPYTRADE_OPS_RECORDS_DB"]))
    try:
        with _temp_env(env_overrides):
            server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.DashboardHandler)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f"http://127.0.0.1:{port}"
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
    finally:
        dashboard_server.REGISTRY_DB = prior_globals["REGISTRY_DB"]
        dashboard_server.PROJECTION_DB = prior_globals["PROJECTION_DB"]
        dashboard_server.OPS_DB = prior_globals["OPS_DB"]


def _http_json(
    url: str, *, method: str = "GET", body: bytes | None = None
) -> tuple[int, dict[str, Any]]:
    req = Request(url, data=body, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        with exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"error": raw}
            return exc.code, parsed


def test_s1_portfolio_navigation_two_link_target_namespace_and_no_finance_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S1: Reach guides in <=2 doc links from AGENTS.md and resolve SQLite namespaces."""

    # Positive 1: programmatic two-link navigation measurement from AGENTS.md.
    def _doc_links(rel_path: str) -> set[str]:
        doc_file = REPO_ROOT / rel_path
        targets: set[str] = set()
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+\.md)(?:#[^)]+)?\)", doc_file.read_text()):
            if "://" in target:
                continue
            resolved = (doc_file.parent / target).resolve().relative_to(REPO_ROOT.resolve())
            targets.add(resolved.as_posix())
        return targets

    hop1 = _doc_links("AGENTS.md")
    assert "docs/INDEX.md" in hop1
    hop2 = set(hop1)
    for rel in hop1:
        if (REPO_ROOT / rel).is_file():
            hop2 |= _doc_links(rel)

    required_guides = {
        "docs/AGENT-NATIVE-OPERATIONS.md",
        "docs/CWSA-CHAPTER2-20261112.md",
        "docs/OPS-CONTROL-CENTER-20261111.md",
        "docs/ANOS-02-AGENT-EVAL-BASELINE-20261113.md",
        "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
        "docs/CANONICAL-5M-IMPLEMENTATION-313.md",
        "docs/ANOS-15-ACCEPTANCE-HANDOFF-20261113.md",
    }
    assert required_guides <= hop2

    # Positive 2: catalog validate + metadata resolution without finance or journal scans.
    code_val, val_doc = _call_cli(["capabilities", "validate", "--json"])
    assert code_val == 0 and val_doc["status"] == "VERIFIED" and val_doc["errors"] == []

    db, _ = _build_locked_registry(tmp_path / "reg")

    def _forbid(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("finance/paper reader must not run for S1 metadata discovery")

    monkeypatch.setattr(reg, "db_status", _forbid)
    monkeypatch.setattr(reg, "registered_paper_status", _forbid)
    monkeypatch.setattr(reg_runs, "inspect_run", _forbid)
    monkeypatch.setattr(fp_journal, "inspect_fp_journal", _forbid)
    monkeypatch.setattr(reg_qual, "status", _forbid)
    monkeypatch.setattr(ch2_proj, "explain_task", _forbid)

    code_q3, q3 = _call_cli(
        ["--db", str(db), "portfolios", "show", "q3/B", "--asof", SELECTION_ASOF]
    )
    code_p5, p5 = _call_cli(
        ["--db", str(db), "portfolios", "show", "gemini.phase5/B", "--asof", SELECTION_ASOF]
    )
    code_w, w083 = _call_cli(["--db", str(db), "wallets", "show", "W083", "--asof", SELECTION_ASOF])
    assert code_q3 == 0 and q3["status"] == "VERIFIED" and set(q3["data"]) == {"B"}
    assert code_p5 == 0 and p5["status"] == "VERIFIED" and set(p5["data"]) == {"gemini.phase5/B"}
    assert code_w == 0 and w083["status"] == "VERIFIED"
    assert not RAW_ADDRESS_RE.search(json.dumps([q3, p5, w083]))

    # Explicit falsifiers: bare-name collision fails closed; outdated Markdown never overrides SQLite.
    code_amb, amb = _call_cli(
        ["--db", str(db), "portfolios", "show", "B", "--asof", SELECTION_ASOF]
    )
    assert code_amb == 2
    assert amb["status"] == "UNKNOWN"
    assert amb["error_code"] == "REGISTRY_READ_FAILED"

    stale_doc = tmp_path / "stale_roster.md"
    stale_doc.write_text("# Obsolete roster: B resolves globally to W999\n")
    code_cur, cur = _call_cli(["--db", str(db), "portfolios", "current", "--asof", SELECTION_ASOF])
    assert code_cur == 0 and cur["status"] == "VERIFIED"
    assert cur["data"]["portfolios"][0]["portfolio_id"] == "gemini.phase4/E6"
    assert "W999" not in json.dumps(cur)


def _normalize_owner_view(view: dict[str, Any]) -> dict[str, Any]:
    """Normalize per-call UTC wall-clock fields before asserting HTTP vs CLI parity."""
    normalized = dict(view)
    for ts_field in ("observed_at", "assessment_asof"):
        val = normalized.get(ts_field)
        assert isinstance(val, str) and datetime.fromisoformat(val).tzinfo is not None
        normalized[ts_field] = "<UTC_TIMESTAMP>"
    return normalized


def test_s2_blocked_paper_separate_layers_and_real_ops_http_cli_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2 + T12 Ops Control Center parity: CLI site-view == real HTTP /api/owner-view."""
    db, _ = _build_locked_registry(tmp_path / "reg")
    env = _seed_chapter2_source_and_paper(tmp_path / "ch2", registry_db=db)

    b_ms = env["boundary_ms"]
    cli_argv = [
        sys.executable,
        "-m",
        "copytrade_pm.pm_operations",
        "cwsa",
        "chapter2",
        "site-view",
        "--portfolio",
        "A",
        "--inspection",
        "evidence",
        "--registry-db",
        str(env["registry_db"]),
        "--source-db",
        str(env["source_db"]),
        "--paper-root",
        str(env["paper_root"]),
        "--quote-db",
        str(env["quote_db"]),
        "--epoch",
        env["epoch"],
    ]
    cli_proc = subprocess.run(cli_argv, capture_output=True, text=True, check=False)
    assert cli_proc.returncode == 0, cli_proc.stderr
    cli_view = json.loads(cli_proc.stdout)

    assert cli_view["schema"] == "cwsa_chapter2_site_owner_view_v1"
    assert cli_view["source_schema"] == "cwsa_chapter2_task_explanation_v1"
    assert cli_view["scope"]["portfolio"] == "A"
    assert cli_view["scope"]["inspection"] == "evidence"
    assert cli_view["scope"]["new_risk_source_status"] == "SOURCE_SCOPE_READY"
    assert cli_view["trading_authorized"] is False
    assert cli_view["financially_active"] is False
    assert cli_view["scientifically_qualified"] is False
    assert cli_view["order_route"] == "NONE"
    assert cli_view["dimensions"]["portfolio_seal"]["state"] == "VERIFIED"
    assert cli_view["dimensions"]["source_observation"]["state"] == "OBSERVE_READY"
    assert cli_view["dimensions"]["source_observation"]["missing_or_stale_members"] == []
    assert cli_view["dimensions"]["paper_finance"]["state"] == "BLOCKED_EVIDENCE"
    assert cli_view["dimensions"]["guardian_authorization"]["state"] == "UNKNOWN"
    assert cli_view["fault_isolation"]["affected_portfolios"] == []
    assert cli_view["economics"]["realized_pnl_usd"] is None
    assert cli_view["economics"]["current_equity_usd"] is None
    assert cli_view["owner_heads"]["source"]["original_checkpoint_by_wallet_ms"]["W028"] == b_ms
    assert cli_view["next_operation"]["effect_class"] == "READ_ONLY"
    assert not RAW_ADDRESS_RE.search(json.dumps(cli_view))

    server_env = _server_env(env, release_sha="test-candidate-rev")
    monkeypatch.setattr(dashboard_server, "_OWNER_VIEW_CACHE", {})
    with _live_ops_server(server_env) as base_url:
        status_code, http_view = _http_json(
            f"{base_url}/api/owner-view?portfolio=A&inspection=evidence"
        )
        assert status_code == 200
        assert _normalize_owner_view(http_view) == _normalize_owner_view(cli_view)
        assert not RAW_ADDRESS_RE.search(json.dumps(http_view))

        meta_code, meta_view = _http_json(
            f"{base_url}/api/owner-view?portfolio=A&inspection=metadata"
        )
        assert meta_code == 200
        assert meta_view["scope"]["inspection"] == "metadata"
        assert meta_view["trading_authorized"] is False

        # Explicit falsifiers: POST/DELETE rejected read-only; bad portfolio/inspection rejected.
        m_post_code, m_post_body = _http_json(
            f"{base_url}/api/owner-view?portfolio=A&inspection=evidence",
            method="POST",
            body=b"{}",
        )
        m_del_code, _ = _http_json(
            f"{base_url}/api/owner-view?portfolio=A&inspection=evidence",
            method="DELETE",
        )
        assert m_post_code in {403, 405}
        assert "error" in m_post_body
        assert m_del_code in {403, 405, 501}

        bad_port_code, _ = _http_json(f"{base_url}/api/owner-view?portfolio=Z&inspection=evidence")
        bad_insp_code, _ = _http_json(f"{base_url}/api/owner-view?portfolio=A&inspection=write")
        assert bad_port_code == 400
        assert bad_insp_code == 400

    # Explicit falsifier: healthy service/active PID + empty paper journals never pass finance gate.
    fin_blocked = ch2_gate.assess_financial_runtime(
        service_active=True,
        signed_portfolios=set(),
        finance_scans={},
        source_changes={},
        journal_cursors={pid: 0 for pid in six_paper.PORTFOLIO_CONFIGS},
        latest_source_checkpoint_ms=BOUNDARY_MS,
    )
    assert fin_blocked.state == "BLOCKED_EVIDENCE"

    # Explicit falsifier: missing COPYTRADE_OPS_OWNER_PYTHON fails closed instead of fabricating PASS.
    monkeypatch.setattr(dashboard_server, "_OWNER_VIEW_CACHE", {})
    no_owner_env = {**server_env, "COPYTRADE_OPS_OWNER_PYTHON": None}
    with _live_ops_server(no_owner_env) as no_owner_url:
        fail_code, fail_body = _http_json(
            f"{no_owner_url}/api/owner-view?portfolio=A&inspection=evidence"
        )
        assert fail_code == 503
        assert fail_body["error"] == "Owner evidence unavailable"


def test_s3_deployed_identity_separates_candidate_configured_installed_and_running(
    tmp_path: Path,
) -> None:
    """S3: Independent process-to-release binding rejects unrelated or pre-T12 PIDs."""
    release = tmp_path / "releases" / "candidate"
    release.mkdir(parents=True)
    _git_clean("init", "-q", str(release))
    (release / ".gitignore").write_text(".venv/\n")
    (release / "src" / "copytrade_pm").mkdir(parents=True)
    (release / "src" / "copytrade_pm" / "__init__.py").write_text("# candidate\n")
    (release / ".gitignore").chmod(0o644)
    (release / "src" / "copytrade_pm" / "__init__.py").chmod(0o644)
    _git_clean("-C", str(release), "add", ".")
    _git_clean(
        "-C",
        str(release),
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "sealed release",
    )
    release_sha = _git_clean("-C", str(release), "rev-parse", "HEAD")
    _git_clean("-C", str(release), "checkout", "-q", "--detach")

    python_bin = release / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.symlink_to(Path(sys.executable).resolve())
    for d in (
        release.parent,
        release,
        release / "src",
        release / "src/copytrade_pm",
        release / ".venv",
        release / ".venv/bin",
    ):
        d.chmod(0o755)

    proc_root = tmp_path / "proc"
    (proc_root / "sys" / "kernel" / "random").mkdir(parents=True)
    (proc_root / "sys" / "kernel" / "random" / "boot_id").write_text(
        "4203c011-2026-4000-9000-000000000349\n"
    )
    cgroup = (
        "/user.slice/user-1001.slice/user@1001.service/app.slice/"
        "copytrade-cwsa-5m-paper-chapter2.service"
    )
    pid = 22345
    start_ticks = 500_000
    argv_str = f"{python_bin} -m copytrade_pm.pm_cwsa_six_paper --poll-seconds 5"

    def _write_proc(*, proc_pid: int, proc_cgroup: str, cwd_target: Path) -> None:
        pdir = proc_root / str(proc_pid)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "cmdline").write_bytes(b"\0".join(x.encode() for x in argv_str.split()) + b"\0")
        (pdir / "stat").write_text(
            f"{proc_pid} (python3) S " + " ".join(["0"] * 18 + [str(start_ticks), "0"]) + "\n"
        )
        (pdir / "cgroup").write_text(f"0::{proc_cgroup}\n")
        (pdir / "environ").write_bytes(b"PYTHONDONTWRITEBYTECODE=1\0")
        other_uid = os.geteuid() + 1000
        (pdir / "status").write_text(
            f"Name:\tpython\nUid:\t{other_uid}\t{other_uid}\t{other_uid}\t{other_uid}\n"
        )
        for link_name, target in (("cwd", cwd_target), ("exe", Path(sys.executable).resolve())):
            link = pdir / link_name
            if link.is_symlink():
                link.unlink()
            link.symlink_to(target)

    _write_proc(proc_pid=pid, proc_cgroup=cgroup, cwd_target=release)

    unit_props = {
        "Id": "copytrade-cwsa-5m-paper-chapter2.service",
        "LoadState": "loaded",
        "ActiveState": "active",
        "MainPID": str(pid),
        "ExecMainStartTimestampMonotonic": str(
            int(start_ticks * 1_000_000 / os.sysconf("SC_CLK_TCK"))
        ),
        "InvocationID": "feedcafe001122334455667788990349",
        "ControlGroup": cgroup,
        "WorkingDirectory": str(release),
        "FragmentPath": "/home/quant/.config/systemd/user/copytrade-cwsa-5m-paper-chapter2.service",
        "ExecStart": f"{{ path={python_bin} ; argv[]={argv_str} ; ignore_errors=no }}",
    }

    def _runner(props: dict[str, str]):
        def _run(argv: list[str], **kwargs: Any):
            if argv[0] != "systemctl":
                if argv[0] == "git":
                    kwargs = {**kwargs, "env": runtime.clean_git_env(kwargs.get("env"))}
                return subprocess.run(argv, **kwargs)
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(f"{k}={v}" for k, v in props.items()) + "\n",
                stderr="",
            )

        return _run

    matched = runtime.verify_unit_release(
        "copytrade-cwsa-5m-paper-chapter2.service",
        expected_sha=release_sha,
        manager="user",
        release_roots=(release.parent,),
        proc_root=proc_root,
        runner=_runner(unit_props),
    )
    assert matched["state"] == "VERIFIED"
    assert matched["installed"]["revision"] == release_sha
    assert matched["observed"]["pid"] == pid

    # Explicit falsifiers:
    # 1. Valid configured unit paired with unrelated PID (different cgroup) must fail closed.
    _write_proc(
        proc_pid=pid,
        proc_cgroup="/user.slice/user-1001.slice/unrelated-worker.service",
        cwd_target=release,
    )
    unrelated_pid = runtime.verify_unit_release(
        "copytrade-cwsa-5m-paper-chapter2.service",
        expected_sha=release_sha,
        manager="user",
        release_roots=(release.parent,),
        proc_root=proc_root,
        runner=_runner(unit_props),
    )
    assert unrelated_pid["state"] != "VERIFIED"

    # 2. Pre-T12 deployed release SHA (49731332ea24...) cannot pass candidate expectation.
    _write_proc(proc_pid=pid, proc_cgroup=cgroup, cwd_target=release)
    old_deployed = runtime.verify_unit_release(
        "copytrade-cwsa-5m-paper-chapter2.service",
        expected_sha="49731332ea24803a7141a48d07e74c3ee490ca30",
        manager="user",
        release_roots=(release.parent,),
        proc_root=proc_root,
        runner=_runner(unit_props),
    )
    assert old_deployed["state"] == "MISMATCH"


def test_s4_change_frozen_k_future_generation_separate_admission_retains_obligations(
    tmp_path: Path,
) -> None:
    """S4: Research k -> signed future generation -> new baseline; old exposure/HALT stay intact."""
    db, seals = _build_locked_registry(tmp_path / "reg")
    seal_a = seals["A"]
    before = "2026-11-01T00:00:00+00:00"
    proposed = "2026-11-12T00:00:00+00:00"
    effective = "2026-11-12T00:15:00+00:00"
    source_sha = digest(["src", "A"])

    trial = k_recal.Trial(
        trial_id="t1",
        candidate_id="W028",
        selection_as_of=before,
        status="ACCEPTED",
        evidence_sha256=source_sha,
        variant_k=Decimal("0.01"),
    )
    win_fwd = k_recal.FinanceWindow(
        label="FORWARD",
        class_of_evidence="PM03_PROSPECTIVE_SHADOW",
        report_sha256=digest(["rep", "fwd"]),
        known_at=before,
        period_end="2026-10-31T00:00:00+00:00",
        independent_episodes=40,
        follower_realized_net_usd=Decimal("50"),
        follower_mtm_net_usd=Decimal("50"),
        fees_usd=Decimal("2"),
        slippage_usd=Decimal("1"),
        funding_usd=Decimal("0"),
        financing_complete=True,
        capacity_verified=True,
        quote_coverage_complete=True,
        selection_frozen_before_window=True,
        cash_control_net_usd=Decimal("0"),
        matched_control_net_usd=Decimal("10"),
        market_control_net_usd=Decimal("10"),
        max_drawdown_usd=Decimal("10"),
        concentration_fraction=Decimal("0.1"),
        max_pair_correlation=Decimal("0.1"),
        uncertainty_lower_incremental_net_usd=Decimal("5"),
    )
    research_in = k_recal.KResearchInput.model_validate(
        {
            "portfolio_version": "A@v2",
            "portfolio_definition_sha256": seal_a["definition_sha256"],
            "pod_id": "W028",
            "selected_account_sha256": sha256(_wallet_addr("W028").encode()).hexdigest(),
            "sizing_policy_version": "fixed-k-v1",
            "as_of": proposed,
            "current_frozen_k": Decimal("0.01"),
            "candidate_k": Decimal("0.005"),
            "cost_policy_version": "v4-paper-5bps-2bps",
            "risk_policy_version": "pm03-v1",
            "source_sha256": source_sha,
            "trial_roster_sha256": digest([trial.model_dump(mode="json")]),
            "trials": (trial,),
            "windows": (win_fwd,),
            "pod_loss_budget_usd": Decimal("200"),
            "follower_equity_usd": Decimal("10000"),
            "max_gross_notional_usd": Decimal("1000"),
            "max_market_notional_usd": Decimal("1000"),
            "daily_headroom_usd": Decimal("500"),
            "trailing_headroom_usd": Decimal("1000"),
            "source_quantities": {BTC_MARKET.key: Decimal("1")},
            "source_marks": {BTC_MARKET.key: Decimal("100")},
            "follower_marks": {BTC_MARKET.key: Decimal("100")},
            "stress_shocks": ({BTC_MARKET.key: Decimal("-0.1")},),
            "adverse_price_extra_loss_usd": Decimal("1"),
            "latency_extra_loss_usd": Decimal("1"),
            "lot_notional_valid": True,
            "unresolved_financial_effects": False,
            "portfolio_correlation_checked": True,
            "evidence_expired": False,
        }
    )
    eval_res = k_recal.evaluate_k(research_in)
    assert eval_res.decision == "INSUFFICIENT_EVIDENCE"
    assert "PM03_ACCOUNT_SNAPSHOT_REQUIRED" in eval_res.reasons
    assert eval_res.authorized_for_trading is False and eval_res.release_activated is False

    # Explicit falsifier: out-of-bounds k (<= 0 or > 10) fails closed without changing mandates.
    for bad_k in (Decimal("0"), Decimal("-0.01"), Decimal("10.1")):
        with pytest.raises(ValidationError):
            k_recal.KResearchInput.model_validate(
                {**research_in.model_dump(mode="python"), "candidate_k": bad_k}
            )

    upward_in = k_recal.KResearchInput.model_validate(
        {**research_in.model_dump(mode="python"), "candidate_k": Decimal("0.02")}
    )
    upward_res = k_recal.evaluate_k(upward_in)
    assert upward_res.decision == "INSUFFICIENT_EVIDENCE"
    assert "INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED" in upward_res.reasons

    hold_proposals = []
    for pod in seal_a["members"]:
        pod_trial = k_recal.Trial(
            trial_id=f"t-{pod}",
            candidate_id=pod,
            selection_as_of=before,
            status="ACCEPTED",
            evidence_sha256=source_sha,
            variant_k=Decimal("0.01"),
        )
        pod_in = k_recal.KResearchInput.model_validate(
            {
                **research_in.model_dump(mode="python"),
                "pod_id": pod,
                "selected_account_sha256": sha256(_wallet_addr(pod).encode()).hexdigest(),
                "candidate_k": Decimal("0.01"),
                "trial_roster_sha256": digest([pod_trial.model_dump(mode="json")]),
                "trials": (pod_trial,),
            }
        )
        pod_res = k_recal.evaluate_k(pod_in)
        assert pod_res.decision == "HOLD"
        hold_proposals.append(pod_res)

    old_policy = {
        "fixed_k_by_pod": {m: "0.01" for m in seal_a["members"]},
        "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
    }
    rollback_sha = "1" * 64
    # Explicit falsifier: INSUFFICIENT_EVIDENCE proposal cannot mint a release candidate.
    with pytest.raises(ValidationError, match="RELEASE_PROPOSAL_SCOPE_OR_EVIDENCE_INVALID"):
        k_recal.make_candidate(
            portfolio_version="A@v2",
            portfolio_definition_sha256=seal_a["definition_sha256"],
            pod_membership=seal_a["members"],
            sizing_policy_version="fixed-k-v1",
            cost_policy_version="v4-paper-5bps-2bps",
            risk_policy_version="pm03-v1",
            effective_at=effective,
            proposed_at=proposed,
            rollback_release_sha256=rollback_sha,
            proposals=(eval_res, *hold_proposals[1:]),
            current_policy_sha256=digest(old_policy),
        )

    candidate = k_recal.make_candidate(
        portfolio_version="A@v2",
        portfolio_definition_sha256=seal_a["definition_sha256"],
        pod_membership=seal_a["members"],
        sizing_policy_version="fixed-k-v1",
        cost_policy_version="v4-paper-5bps-2bps",
        risk_policy_version="pm03-v1",
        effective_at=effective,
        proposed_at=proposed,
        rollback_release_sha256=rollback_sha,
        proposals=tuple(hold_proposals),
        current_policy_sha256=digest(old_policy),
    )
    assert candidate.activated is False and candidate.trading_authorized is False

    # Note: offline_preflight looks up SQLite portfolio_seals via portfolio_id="A", version=2.
    preflight = k_recal.offline_preflight(
        candidate,
        sealed_definition_sha256=seal_a["definition_sha256"],
        observed_current_release_sha256=rollback_sha,
        pending_opportunity_count=1,
        open_inventory_count=1,
        registry_path=db,
        registry_portfolio_id="A",
        registry_version=2,
    )
    assert preflight["registry_seal_independently_verified"] is True
    assert preflight["activated"] is False and preflight["release_eligible"] is False

    # Existing pending T+300 opportunity retains original k regardless of candidate.
    preserved = k_recal.bind_opportunity_k(
        first_known_at=proposed,
        pending_k=Decimal("0.01"),
        pending_release_sha256=digest(old_policy),
        candidate=candidate,
        opportunity_already_exists=True,
    )
    assert preserved["action"] == "PRESERVE_EXISTING_OPPORTUNITY" and preserved["k"] == "0.01"

    published = k_rel.publish_k_candidate(candidate, tmp_path / "cand_cache")
    assert published["active_policy_changed"] is False and published["trading_authorized"] is False

    snap = {
        "schema": "pm03_account_v2",
        "risk": "GREEN",
        "breached": False,
        "pm_quantities": {"W028": {BTC_MARKET.key: "0.01"}},
        "pm04": {
            "policy": old_policy,
            "paper_execution": {
                "schema": "pm04_single_shot_intents_v2",
                "history": {},
                "active": {},
            },
        },
    }
    cutover = k_rel.verify_cutover(
        candidate,
        paper_snapshot=snap,
        paper_snapshot_sha256=digest(snap),
        current_policy=old_policy,
        checked_at=proposed,
        observed_release_sha256=rollback_sha,
    )
    assert cutover["status"] == "BLOCKED_NONACTIVATING"
    assert "OPEN_INVENTORY_NEEDS_EXPLICIT_LEGACY_K" in cutover["blockers"]

    # Explicit falsifier 1: forged/historical seal drift fails closed.
    bad_seal_preflight = k_recal.offline_preflight(
        candidate,
        sealed_definition_sha256="f" * 64,
        observed_current_release_sha256=rollback_sha,
        pending_opportunity_count=0,
        open_inventory_count=0,
        registry_path=db,
        registry_portfolio_id="A",
        registry_version=2,
    )
    assert bad_seal_preflight["status"] == "BLOCKED"
    assert "SQLITE_PORTFOLIO_SEAL_MISMATCH" in bad_seal_preflight["blockers"]

    # Positive 2 + falsifier 2: separate signed future generation CopyMandate preserves prior HALT.
    rulebook = propr_rulebook(
        "classic_1step", "evaluation", Decimal("10000"), observed_at=seal_a["selection_known_at"]
    )
    key = Ed25519PrivateKey.generate()
    gen2_from = BOUNDARY_MS + GRID_MS
    m2 = mandates.CopyMandate(
        schema="copy_mandate_v1",
        mandate_id="m-w028",
        generation=2,
        source_id="W028",
        source_scope_generation="a" * 64,
        source_account_sha=sha256(_wallet_addr("W028").encode()).hexdigest(),
        account_id="acct_a",
        pod_id="W028",
        k=Decimal("0.005"),
        allowed_markets=(BTC_MARKET.key,),
        policy_epoch="e" * 64,
        risk_policy_sha=digest({"risk": "pm03"}),
        rulebook_sha=rulebook.sha,
        effective_from_ms=gen2_from,
        effective_until_ms=gen2_from + 86_400_000,
    )
    signed_m2 = sign(m2.model_dump(mode="json"), key, "copy-mandate-v1")
    verified_m2 = mandates.verify_mandate(signed_m2, key.public_key(), account_id="acct_a")
    assert verified_m2.generation == 2 and verified_m2.k == Decimal("0.005")

    with pytest.raises(ValueError, match="MANDATE_DESTINATION_MISMATCH"):
        mandates.verify_mandate(signed_m2, key.public_key(), account_id="wrong_acct")

    s0 = mandates.MandateState.initial(verified_m2)
    t_act = mandates.transition_mandate(
        verified_m2, s0, event="ACTIVATE", evidence_sha=digest(["act"]), at_ms=gen2_from - 10
    )
    t_base = mandates.transition_mandate(
        verified_m2,
        t_act.successor,
        event="COMPLETE_BASELINE",
        evidence_sha=digest(["base"]),
        at_ms=gen2_from + 1,
        checkpoint_ms=gen2_from,
    )
    assert t_base.successor.phase == "ACTIVE"

    # HALT journal entry survives independently; activating future generation does not reset HALT.
    journal = PaperJournal(tmp_path / "paper_halt")
    journal.register(
        PaperManifest(
            run_id="A",
            account_id="acct_a",
            portfolio_sha=seal_a["definition_sha256"],
            market_manifest_sha=digest(["mkt", "manifest"]),
            release_sha=rollback_sha,
            selected_at=seal_a["selection_known_at"],
            started_at=proposed,
            rulebook=rulebook,
            policy_sha=digest(old_policy),
        )
    )
    journal.append(
        "A",
        "independent-halt",
        {"kind": "HALT", "event_at": "2026-11-12T00:05:00+00:00", "reason": "risk-halt"},
    )
    journal.activate_copy_mandate(
        signed_m2, key.public_key(), account_id="acct_a", at_ms=gen2_from - 10
    )
    restored = journal.restore("A")
    assert restored["account"]["risk"] == "HALT"
    assert restored["account"]["halt_reason"] == "risk-halt"
    mandate_state = journal.copy_mandate_state(verified_m2.owner)
    assert mandate_state is not None and mandate_state.mandate_sha == verified_m2.sha
    assert mandate_state.phase == "AWAITING_BASELINE"
    assert not restored["account"].get("quantities")


def test_s5_wallet_local_source_gap_preserves_clocks_isolates_fault_and_ops_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5: Wallet-local gap isolates B without blocking A, inventing flat, or rewriting clocks."""
    db, _ = _build_locked_registry(tmp_path / "reg")
    b_ms = _fresh_boundary_ms()
    alt_policy = _policy_for("mixed-epoch")
    older_cp_ms = b_ms - GRID_MS
    env = _seed_chapter2_source_and_paper(
        tmp_path / "ch2",
        registry_db=db,
        boundary_ms=b_ms,
        gap_wallets={"W031"},
        epoch_override_wallets={"CA-005": alt_policy},
        checkpoint_ms_by_wallet={"CO-001": older_cp_ms},
        acq_offset_ms_by_wallet={"W028": 77, "W030": 101},
    )

    monkeypatch.setattr(dashboard_server, "_OWNER_VIEW_CACHE", {})
    with _live_ops_server(_server_env(env)) as base_url:
        code_a, view_a = _http_json(f"{base_url}/api/owner-view?portfolio=A&inspection=evidence")
        code_b, view_b = _http_json(f"{base_url}/api/owner-view?portfolio=B&inspection=evidence")
        code_c, view_c = _http_json(f"{base_url}/api/owner-view?portfolio=C&inspection=evidence")
        assert code_a == 200 and code_b == 200 and code_c == 200

        # A remains source-healthy and unaffected by B's W031 gap / CA-005 epoch.
        assert view_a["dimensions"]["source_observation"]["state"] == "OBSERVE_READY"
        assert view_a["scope"]["new_risk_source_status"] == "SOURCE_SCOPE_READY"
        assert view_a["dimensions"]["source_observation"]["missing_or_stale_members"] == []
        assert view_b["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
        assert "W031" in view_b["dimensions"]["source_observation"]["missing_or_stale_members"]
        assert "CA-005" in view_b["dimensions"]["source_observation"]["missing_or_stale_members"]
        assert view_b["scope"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
        assert "A" in view_b["fault_isolation"]["unaffected_source_portfolios"]
        assert "B" in view_b["fault_isolation"]["affected_portfolios"]

        # Original per-wallet checkpoint & publication clocks preserved instead of global harmonization.
        src_a = view_a["owner_heads"]["source"]
        src_c = view_c["owner_heads"]["source"]
        assert src_a["published_ms_by_wallet"]["W028"] == b_ms + 78
        assert src_a["published_ms_by_wallet"]["W030"] == b_ms + 102
        assert src_a["receipt_first_known_ms_by_wallet"]["W028"] == b_ms + 77
        assert src_c["original_checkpoint_by_wallet_ms"]["CO-001"] == older_cp_ms
        assert src_c["original_checkpoint_by_wallet_ms"]["VS066"] == b_ms

        # Mixed epochs inside B surface explicitly instead of asserting a globally uniform snapshot.
        b_epochs = view_b["owner_heads"]["source"]["policy_epochs_by_wallet"]
        assert b_epochs["CA-005"] == alt_policy.epoch
        assert b_epochs["W031"] == env["epoch"]
        assert "SOURCE_POLICY_EPOCHS_MIXED" in view_b["generation_consistency"]["reasons"]
        assert view_b["generation_consistency"]["state"] == "MIXED"

        # Negative falsifier: missing source position isolates B as COVERAGE_GAP without blocking A.
        a_status = json.loads((Path(env["paper_root"]) / "A" / "status.json").read_text())
        b_status = json.loads((Path(env["paper_root"]) / "B" / "status.json").read_text())
        assert a_status["coverage_complete"] is True
        assert a_status["source_wave_state"] == "COMPLETE"
        assert b_status["coverage_complete"] is False
        assert b_status["source_wave_state"] == "COVERAGE_GAP"
        assert b_status["source_kinds"]["W031"] == "UNAVAILABLE"


def test_s6_plan_historical_study_pit_reuse_bounded_remote_bytes_and_trials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S6: SHA-verified PIT reuse, bounded remote bytes != returned rows, fail-closed limits."""
    cache_root = tmp_path / "research_cache"
    part_root = tmp_path / "partitions"
    part_root.mkdir()
    w1, w2 = "W028", "W030"
    day1 = "2026-10-01"
    day2 = "2026-10-02"
    known_at = "2026-09-25T00:00:00+00:00"
    start = f"{day1}T00:00:00+00:00"
    end = f"{day2}T00:00:00+00:00"
    source_cols = ("time", "user", "dex", "coin", "szi")

    # Seed verified coverage for both wallets to test cache hit + dependency invalidation.
    cache = ImmutableCache(cache_root, min_free_bytes=0)
    cohort = "s6-cohort"
    input_sha = digest(["input", "s6"])
    source_sha = digest(["source", "s6"])
    market_sha = digest(["market", "s6"])
    software_sha = digest(["software", "s6"])
    job_sha = digest(["job", "s6"])
    cost_assumption = "HL_TAKER_4_5BPS"
    policy_name = "PER_FILL_ELIGIBILITY"
    cov_keys = []
    for wallet in (w1, w2):
        cov_payload = {
            "schema": job_catalog.COVERAGE_RECEIPT_SCHEMA,
            "wallet": wallet,
            "dex": "hyperliquid",
            "utc_start": start,
            "utc_end": end,
            "known_at": known_at,
            "input_sha256": input_sha,
            "source_sha256": source_sha,
            "collected": True,
            "blocked": False,
            "source_verified": True,
            "empty_verified": wallet == w2,
            "row_count": 5 if wallet == w1 else 0,
        }
        res = cache.publish(
            "coverage_receipt",
            {"input": input_sha, "source": source_sha, "span": digest(cov_payload)},
            version=job_catalog.COVERAGE_RECEIPT_SCHEMA,
            content=json.dumps(cov_payload, sort_keys=True, separators=(",", ":")).encode(),
        )
        cov_keys.append(res["key"])

    scope_sha = digest(
        {
            "cohort": cohort,
            "wallets": sorted([w1, w2]),
            "dexes": ["hyperliquid"],
            "utc_start": start,
            "utc_end": end,
            "as_of": end,
            "job_sha256": job_sha,
            "input_sha256": input_sha,
            "source_sha256": source_sha,
            "market_sha256": market_sha,
            "software_sha256": software_sha,
            "cost_assumption": cost_assumption,
            "policy": policy_name,
            "report_schema": OFFLINE_REPORT_SCHEMA,
        }
    )
    report_payload = {
        "schema": OFFLINE_REPORT_SCHEMA,
        "job_id": "job-s6-1",
        "job_sha256": job_sha,
        "job_kind": "HISTORICAL_ORACLE_NATIVE",
        "clock_basis": "PROSPECTIVE_FIRST_KNOWN",
        "policy": policy_name,
        "status": "COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY",
        "financial_status": "BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN",
        "financial_certified_real": False,
        "scientifically_qualified": False,
        "authorized_for_trading": False,
        "deployed": False,
        "blockers": [],
        "engineering_path_verified": True,
        "cohort": cohort,
        "wallets": sorted([w1, w2]),
        "dexes": ["hyperliquid"],
        "utc_start": start,
        "utc_end": end,
        "as_of": end,
        "source_sha256": source_sha,
        "cost_assumption": cost_assumption,
        "selection_known_at": known_at,
        "depends_on_cache_keys": cov_keys,
    }
    cache.publish(
        "job_report",
        {
            "job": job_sha,
            "input": input_sha,
            "market": market_sha,
            "software": software_sha,
            "source": source_sha,
            "scope": scope_sha,
        },
        version=OFFLINE_REPORT_SCHEMA,
        content=json.dumps(report_payload, sort_keys=True, separators=(",", ":")).encode(),
    )

    pit_request = {
        "cohort": cohort,
        "wallets": [w1, w2],
        "dexes": ["hyperliquid"],
        "utc_start": start,
        "utc_end": end,
        "as_of": end,
        "selection_known_at": known_at,
        "job_sha256": job_sha,
        "input_sha256": input_sha,
        "source_sha256": source_sha,
        "market_sha256": market_sha,
        "software_sha256": software_sha,
        "cost_assumption": cost_assumption,
        "report_schema": OFFLINE_REPORT_SCHEMA,
        "policy": policy_name,
        "coverage_receipts": cov_keys,
        "require_pit": True,
        "purpose": "RESEARCH_PREFLIGHT",
    }

    hit = job_catalog.assess_reuse(cache_root, pit_request)
    assert hit["state"] == "VERIFIED_CACHE_HIT"
    assert hit["reusable"] is True
    assert hit["trading_authorized"] is False

    # Falsifier 1: changed dependency SHA causes cache miss rather than stale hit.
    miss_req = {**pit_request, "market_sha256": digest(["mkt", "v2"])}
    miss = job_catalog.assess_reuse(cache_root, miss_req)
    assert miss["reusable"] is False

    # Falsifier 2: hindsight cohort (selection_known_at after window start) fails closed on require_pit.
    ex_post_req = {**pit_request, "selection_known_at": end}
    ex_post = job_catalog.assess_reuse(cache_root, ex_post_req)
    assert ex_post["reusable"] is False

    # Bounded acquisition separates compressed remote bytes from returned filtered rows.
    rg_src = [
        {
            "row_group_id": 0,
            "num_rows": 500,
            "columns": {c: {"compressed_bytes": 2_400, "has_stats": False} for c in source_cols},
        }
    ]
    bounded_req = {
        **miss_req,
        "coverage_receipts": [cov_keys[0]],
        "acquisition": {
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(source_cols)},
            "budget": {"max_requests": 5, "max_remote_bytes": 20_000, "max_disk_bytes": 20_000},
            "remote_objects": {
                f"source:hyperliquid:{day1}": {
                    "etag": '"etag-s6"',
                    "object_bytes": 50_000,
                    "schema_columns": list(source_cols),
                    "row_groups": rg_src,
                    "estimated_filtered_return_rows": 2,
                    "estimated_output_bytes": 128,
                }
            },
        },
    }
    req_file = tmp_path / "req_s6.json"
    req_file.write_text(json.dumps(bounded_req))
    code_pre = ops.cli(
        [
            "research",
            "preflight",
            "--cache-root",
            str(cache_root),
            "--request",
            str(req_file),
            "--partition-root",
            str(part_root),
            "--plan-acquisition",
        ]
    )
    assert code_pre == 2
    cli_out = json.loads(capsys.readouterr().out)
    plan = cli_out["data"]["acquisition_plan"]
    assert plan["status"] == "PLANNED"
    assert plan["forecast"]["remote_object_bytes"] == 50_000
    assert plan["forecast"]["remote_compressed_bytes"] == 12_000
    assert plan["forecast"]["disk_bytes"] == 128
    assert plan["forecast"]["estimated_filtered_return_rows"] == 2
    assert plan["forecast"]["remote_compressed_bytes"] > plan["forecast"]["disk_bytes"]
    assert plan["trading_authorized"] is False

    # Falsifier 3: tiny budget halts fail-closed instead of widening scan.
    tight_req = {
        **bounded_req,
        "acquisition": {
            **bounded_req["acquisition"],
            "budget": {"max_requests": 5, "max_remote_bytes": 1_000, "max_disk_bytes": 20_000},
        },
    }
    tight_plan = acq.plan_bounded_acquisition(cache_root, tight_req, partition_root=part_root)
    assert tight_plan["status"] == "BLOCKED"
    assert tight_plan["plan_ready"] is False


def test_s7_interrupted_action_recovery_preserves_original_intent_halt_and_floors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """S7: Reconcile interrupted T+300 paper and Guardian intents without retry or lock release."""
    t0 = datetime(2026, 11, 12, 0, 5, tzinfo=UTC)
    t_att = (t0 + timedelta(seconds=305)).isoformat()
    src_sha_s7 = digest(["source", "s7", 1])
    opp_pending = PaperOpportunity(
        intent_id=digest(["opp", "s7", 1]),
        pod="W028",
        source_seq=1,
        source_sha=src_sha_s7,
        source_event_at=t0.isoformat(),
        first_known_at=t0.isoformat(),
        due_at=(t0 + timedelta(seconds=300)).isoformat(),
        deadline_at=(t0 + timedelta(seconds=330)).isoformat(),
        created_at=t0.isoformat(),
        updated_at=t0.isoformat(),
        status="PENDING_5M",
        positions={BTC_MARKET.key: "0.02"},
        updates=[OpportunityUpdate(at=t0.isoformat(), source_seq=1, source_sha=src_sha_s7)],
        frozen_k="0.01",
        release_sha256="a" * 64,
    )
    opp_attempted = opp_pending.model_copy(
        update={"status": "REJECTED", "terminal_at": t_att, "attempted_at": t_att}
    )

    before_t300 = ch2_proj.explain_interrupted_paper(
        opp_pending, observed_at=(t0 + timedelta(seconds=60)).isoformat()
    )
    expired_pending = ch2_proj.explain_interrupted_paper(
        opp_pending, observed_at=(t0 + timedelta(seconds=360)).isoformat()
    )
    after_attempt = ch2_proj.explain_interrupted_paper(
        opp_attempted, observed_at=(t0 + timedelta(seconds=320)).isoformat()
    )
    assert before_t300["dispatch_state"] == "NOT_DISPATCHED"
    assert expired_pending["dispatch_state"] == "NOT_DISPATCHED"
    assert expired_pending["next_action"] == "NO_NEW_EFFECT_ON_ORIGINAL_OPPORTUNITY"
    assert expired_pending["retry_authorized"] is False
    assert after_attempt["dispatch_state"] == "POSSIBLY_DISPATCHED"
    assert after_attempt["retry_authorized"] is False
    assert after_attempt["original_obligation_preserved"] is True
    assert after_attempt["next_operation_effect_class"] == "READ_ONLY"
    assert after_attempt["halt"] == "UNKNOWN"
    assert after_attempt["mandate_generation"] is None
    assert after_attempt["reservation"] is None
    assert after_attempt["order_route"] == "NONE"
    assert after_attempt["trading_authorized"] is False

    # Tampered original intent update chain fails closed (duplicate/rebound intent falsifier).
    forged_opp = opp_pending.model_dump()
    forged_opp["source_sha"] = "9" * 64
    with pytest.raises(ValueError, match="PAPER_OPPORTUNITY_UPDATE_BINDING"):
        ch2_proj.explain_interrupted_paper(
            forged_opp, observed_at=(t0 + timedelta(seconds=60)).isoformat()
        )

    # Sandboxed Guardian owner fixture verifying non-null HALT and risk floors on DISPATCHING vs QUEUED.
    guardian_intent_id = "e" * 64
    release_sha = "b" * 64
    acct_sha = "c" * 64
    guardian_state = {
        "schema": "guardian_journal_v1",
        "sequence": 17,
        "active_release_sha": release_sha,
        "account_binding": "synthetic-account",
        "intents": {
            guardian_intent_id: {
                "intent_id": guardian_intent_id,
                "status": "DISPATCHING",
                "reservation_id": "decision-1",
                "release_sha": release_sha,
                "expires_at_ms": 9999,
                "sent_at_ms": 4000,
            }
        },
        "reservations": {
            "decision-1": {
                "loss": "2",
                "margin": "5",
                "cost": "1",
                "intent_ids": [guardian_intent_id],
            }
        },
        "halts": ["UNKNOWN_OUTCOME"],
        "finance": {"daily_floor": "9500", "trailing_floor": "9000", "risk_floor": "9200"},
        "runtime": {"certainty": "UNKNOWN"},
    }
    pkg = ModuleType("prop_production")
    pkg.__path__ = []
    j_mod: Any = ModuleType("prop_production.journal")
    op_mod: Any = ModuleType("prop_production.operator")

    class _FakeGuardianJournal:
        @staticmethod
        def read(_path: Path) -> dict[str, Any]:
            return json.loads(json.dumps(guardian_state))

    def _fake_project(
        snapshot: dict[str, Any], command: str, _now_ms: int, intent_id: str | None = None
    ):
        common = {
            "schema": f"operator_{command}_v1",
            "journal_sequence": snapshot["sequence"],
            "release_sha": release_sha,
            "account_binding_sha": acct_sha,
            "halts": snapshot["halts"],
        }
        if command == "intent":
            return common | {"intents": [snapshot["intents"][str(intent_id)]]}
        if command == "risk":
            return common | {
                "reservations": snapshot["reservations"],
                "finance": snapshot["finance"],
            }
        return common | {"certainty": snapshot["runtime"]["certainty"]}

    j_mod.Journal = _FakeGuardianJournal
    op_mod.project_state = _fake_project
    monkeypatch.setitem(sys.modules, "prop_production", pkg)
    monkeypatch.setitem(sys.modules, "prop_production.journal", j_mod)
    monkeypatch.setitem(sys.modules, "prop_production.operator", op_mod)

    code_grd = ops.cli(
        [
            "cwsa",
            "chapter2",
            "recover",
            "--guardian-journal",
            str(tmp_path / "guardian_synth.sqlite"),
            "--intent-id",
            guardian_intent_id,
            "--observed-at-ms",
            "5000",
        ]
    )
    assert code_grd == 0
    grd_out = json.loads(capsys.readouterr().out)
    assert grd_out["dispatch_state"] == "POSSIBLY_DISPATCHED"
    assert grd_out["reservation_active"] is True
    assert grd_out["halt_reasons"] == ["UNKNOWN_OUTCOME"]
    assert grd_out["risk_floors"]["daily_floor"] == "9500"
    assert grd_out["retry_authorized"] is False
    assert grd_out["order_route"] == "NONE"

    guardian_state["intents"][guardian_intent_id]["status"] = "QUEUED"
    guardian_state["intents"][guardian_intent_id]["sent_at_ms"] = None
    pre_grd = ch2_proj.explain_native_guardian_intent(
        journal_path=tmp_path / "guardian_synth.sqlite",
        intent_id=guardian_intent_id,
        observed_at_ms=5000,
    )
    assert pre_grd["dispatch_state"] == "NOT_DISPATCHED"
    assert pre_grd["retry_authorized"] is False

    # Missing Guardian evidence via public CLI fails closed (exit 2) without releasing locks.
    missing_journal = tmp_path / "absent_guardian.sqlite"
    valid_intent_id = "f" * 64
    code_abs = ops.cli(
        [
            "cwsa",
            "chapter2",
            "recover",
            "--guardian-journal",
            str(missing_journal),
            "--intent-id",
            valid_intent_id,
            "--observed-at-ms",
            str(BOUNDARY_MS + 1000),
        ]
    )
    assert code_abs == 2
    abs_out = json.loads(capsys.readouterr().out)
    assert abs_out["dispatch_state"] == "EVIDENCE_UNAVAILABLE"
    assert abs_out["original_obligation_preserved"] is True
    assert abs_out["retry_authorized"] is False
    assert abs_out["halt_reasons"] is None
    assert abs_out["risk_floors"] is None
    assert abs_out["order_route"] == "NONE"
    assert abs_out["trading_authorized"] is False

    # Malformed non-64-hex intent ID fails closed rather than guessing.
    with pytest.raises(ValueError, match="INVALID_GUARDIAN_INTENT_QUERY"):
        ch2_proj.explain_native_guardian_intent(
            journal_path=missing_journal,
            intent_id="g-intent-bad",
            observed_at_ms=BOUNDARY_MS + 1000,
        )


def test_s8_handoff_recovery_t02_baseline_comparison_no101_and_313_preserved(
    tmp_path: Path,
) -> None:
    """S8: Handoff durability, T02 baseline comparison, #101 block, and #313 boundaries."""
    # 1. Durable S8 handoff doc must exist and preserve T02 / #101 / #313 distinctions.
    handoff = REPO_ROOT / "docs" / "ANOS-15-ACCEPTANCE-HANDOFF-20261113.md"
    assert handoff.is_file(), f"Missing durable handoff record: {handoff}"
    handoff_text = handoff.read_text()
    for required_token in (
        "1c4ac38e76dc7ed31e3421273269750b2f03e086",
        "0eab42c8ae578d0c18e30432dc1772bd1c8c7be1",
        "BLOCKED_NO_INDEPENDENT_HOST_TRACE",
        "49731332ea24803a7141a48d07e74c3ee490ca30",
        "#101",
        "#313",
    ):
        assert required_token in handoff_text

    # 2. Candidate capability inventory compared monotonically against T02 frozen counts.
    val = cap.validate(REPO_ROOT)
    assert val["status"] == "VERIFIED" and val["errors"] == []
    assert val["capability_count"] >= 114
    assert val["cli_count"] >= 41
    assert val["module_only_count"] >= 48

    # 3. Deterministic 13-task baseline comparison preserves exact T02 invariants and #101 block.
    tasks = list(trace_eval.TASK_MAP.values())
    assert len(tasks) == 13
    runs = []
    for task in tasks:
        calls = [
            {
                "sequence": 1,
                "argv": ["copytrade-pm", "capabilities", "show", task["capability"]],
                "exit_code": 0,
                "result_status": "FOUND",
            }
        ]
        status = "VERIFIED"
        if not task["discovery_only"]:
            argv = list(task["query_prefix"])
            if argv[-1] == "--cache-root":
                argv.append("/private/owner-cache")
            if task["id"] == "paper-running":
                status = "UNKNOWN"
            elif task["id"] in {"installed-release", "protected-paper-os", "market-evidence"}:
                status = "DEGRADED"
            calls.append(
                {
                    "sequence": 2,
                    "argv": argv,
                    "exit_code": 0,
                    "result_status": status,
                }
            )
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
    bundle = {
        "schema": trace_eval.SCHEMA,
        "run_id": "anos-15-s8-synth",
        "observed_at": SELECTION_ASOF,
        "capture_kind": "SYNTHETIC",
        "tool_events_source": "TEST_FIXTURE",
        "runs": runs,
    }
    trace_path = tmp_path / "synth_trace.json"
    trace_path.write_text(json.dumps(bundle))
    trace_path.chmod(0o600)
    report = trace_eval.evaluate(trace_path)
    assert report["status"] == "UNVERIFIED_TOOL_TRACE"
    assert report["tasks_passed"] == 13
    assert report["total_calls"] == 24
    assert report["discovery_hops"] == 13
    assert report["read_scope_calls"] == 11
    assert report["repeated_work_calls"] == 0
    assert report["invented_calls"] == 0
    assert report["unsafe_calls"] == 0
    assert report["off_target_calls"] == 0
    assert report["bytes_read"] is None
    assert report["wall_time_ms"] is None
    assert report["context_tokens"] is None
    assert report["scientific_qualification"] == "NOT_ESTABLISHED"

    # Explicit falsifier: untrusted key / missing signature never produces INDEPENDENT_TRACE_PASS.
    assert trace_eval.evaluate(trace_path)["status"] != "INDEPENDENT_TRACE_PASS"

    # 4. #313 preserved boundaries: 16 canonical V4 portfolios distinct from 6 Chapter 2 provisional.
    assert len(v4_sixteen.IDENTITIES) == 16
    assert len(six_paper.PORTFOLIO_CONFIGS) == 6
    assert len(six_paper.ALL_14_WALLETS) == 14

    # 5. CI receipt fail-closed on SHA mismatch.
    fake_receipt = tmp_path / "receipt.json"
    fake_receipt.write_text(json.dumps({"sha": "0" * 40, "overall": "PASS"}))
    assert ci_receipt.validate_receipt(fake_receipt, REPO_ROOT, "1" * 40)
