"""Read-only WR-07 adapter using FP PR73's actual SQLite WAL journal contract.

All fixtures model published FP fields; no account execution or runtime worker is
fabricated. Separate cross-branch smoke exercises the actual FP PaperJournal API.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_fp_journal as fp
from copytrade_pm import wallet_registry_portfolios as portfolios
from copytrade_pm import wallet_registry_runs as runs
from test_wallet_registry_runs import _db

T = datetime.now(timezone.utc)
AT = T.isoformat()


def _build(
    tmp_path: Path,
    portfolio_sha: str,
    *,
    account: str = "paper-acct-a",
    run_id: str = "paper-run-a",
    change: bool = False,
) -> Path:
    # Map the WR sealed decision to FP's distinct, frozen portfolio SHA,
    # exactly as actual FP PaperPortfolioView requires. Unknown hashes stay
    # unchanged so negative mismatch cases still fail independently.
    review = portfolios.read_decisions(
        Path(__file__).resolve().parents[1], reg.PORTFOLIOS, observed_at=AT
    )
    for name, record in review.items():
        if portfolio_sha == record["definition_sha256"]:
            candidate = fp.fp_portfolio_sha(
                {
                    "portfolio_id": name,
                    "definition_sha256": portfolio_sha,
                    "members": list(reg.PORTFOLIOS[name]),
                    "sizing_contract": record["payload"]["sizing_contract"],
                }
            )
            if candidate:
                portfolio_sha = candidate
            break
    root = tmp_path / "paper"
    root.mkdir(mode=0o700, parents=True)
    db = root / "paper-events.sqlite3"
    document = {
        "schema": "paper_run_manifest_v1",
        "run_id": run_id,
        "account_id": account,
        "portfolio_sha": portfolio_sha,
        "policy_sha": "b" * 64,
        "release_sha": "c" * 64,
        "market_manifest_sha": "d" * 64,
        "selected_at": (T - timedelta(minutes=3)).isoformat(),
        "started_at": (T - timedelta(minutes=2)).isoformat(),
        "rulebook": {"initial_balance": "10000", "confirmed": False},
        "order_route": "NONE",
        "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
    }
    old = {"cash": "10000", "risk": "GREEN", "quantities": {}}
    new = {"cash": "10000", "risk": "HALT", "quantities": {}}
    contents = fp.canonical(document).decode()
    with closing(sqlite3.connect(db)) as con:
        con.executescript("""
        CREATE TABLE runs(
            run_id TEXT PRIMARY KEY,account_id TEXT NOT NULL UNIQUE,
            manifest TEXT NOT NULL,manifest_sha TEXT NOT NULL,
            snapshot TEXT NOT NULL,snapshot_sha TEXT NOT NULL,
            last_event_at TEXT NOT NULL,cursor INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE events(
            run_id TEXT NOT NULL,seq INTEGER NOT NULL,
            event_id TEXT NOT NULL,event_at TEXT NOT NULL,
            input TEXT NOT NULL,input_sha TEXT NOT NULL,prior_sha TEXT NOT NULL,
            post_sha TEXT NOT NULL,chain_sha TEXT NOT NULL,
            PRIMARY KEY(run_id,seq),UNIQUE(run_id,event_id)
        );
        """)
        last_at = document["started_at"]
        cursor = int(change)
        if change:
            event = {"kind": "HALT", "event_at": (T - timedelta(minutes=1)).isoformat()}
            event_sha = fp.digest(event)
            prior = fp.digest(old)
            post = fp.digest(new)
            chain = fp.digest([run_id, 1, "halt-1", event_sha, prior, post])
            con.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    1,
                    "halt-1",
                    event["event_at"],
                    fp.canonical(event).decode(),
                    event_sha,
                    prior,
                    post,
                    chain,
                ),
            )
            last_at = event["event_at"]
        con.execute(
            "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
            (
                run_id,
                account,
                contents,
                fp.digest(document),
                fp.canonical(new if change else old).decode(),
                fp.digest(new if change else old),
                last_at,
                cursor,
            ),
        )
        con.commit()
    db.chmod(0o600)
    return root


def _sel(db: Path, portfolio: str = "P1") -> dict:
    with closing(reg.connect(db, False)) as con:
        return portfolios.select_asof(con, portfolio, AT)


def test_fp_frozen_p1_p14_shas_match_actual_parallel_portfolio_contract(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    p1 = _sel(inventory)
    p14 = _sel(inventory, "P14")
    # Independently observed from FP PR73 FrozenPaperPortfolio.sha.
    assert fp.fp_portfolio_sha(p1) == (
        "14c0b361145354b0012e297d01fe93b72cd8af5426ab8a13e51d0bc3c41e59cf"
    )
    assert fp.fp_portfolio_sha(p14) == (
        "fe50ebdafd4cacca5273d393f7abe10b099b26b95c3a129bf864b6ca23f39223"
    )
    assert fp.fp_portfolio_sha({**p1, "members": ["S035", "S051", "S053"]}) is None
    assert fp.fp_portfolio_sha({**p14, "sizing_contract": "BUDGET_1000"}) is None
    assert fp.fp_portfolio_sha(_sel(inventory, "P16")) is None
    assert p1["definition_sha256"] != fp.fp_portfolio_sha(p1)


def test_fp01_journal_matches_registry_pit_without_claiming_running(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    run_dir = _build(tmp_path, selected["definition_sha256"], change=True)
    database = run_dir / "paper-events.sqlite3"
    original_hash = sha256(database.read_bytes()).hexdigest()
    observed = runs.inspect_run(run_dir, selected, run_id="paper-run-a", now=T)
    assert observed["state"] == "NOT_RUNNING"
    assert observed["reason"] == "FP_JOURNAL_ONLY_WORKER_UNVERIFIED"
    assert observed["manifest_sha256"] and len(observed["manifest_sha256"]) == 64
    assert observed["portfolio_id"] == "P1"
    assert observed["portfolio_definition_sha256"] == selected["definition_sha256"]
    assert observed["fp_portfolio_sha256"] == fp.fp_portfolio_sha(selected)
    assert observed["portfolio_identity_bridge"] == (
        "REVIEWED_ALIASES_ONLY_NOT_SOURCE_IDENTITY_PROOF"
    )
    assert observed["journal_seq_reported"] == 1
    assert observed["journal_tail_rows_verified"] == 1
    assert observed["paper_admission"] == "UNKNOWN"
    assert observed["scientifically_qualified"] is False
    assert observed["trading_authorized"] is False
    assert observed["source_identity_proven"] is False
    public = runs.sanitized(observed)
    assert "paper-acct-a" not in json.dumps(public)
    assert "paper-run-a" not in json.dumps(public)
    assert "run_id" not in public
    assert len(public["run_ref_sha256"]) == 64
    assert "run_root" not in public
    assert sha256(database.read_bytes()).hexdigest() == original_hash


def test_fp_source_can_be_indexed_but_never_assumed_active(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    root = _build(tmp_path, selected["definition_sha256"], change=False)
    observed = runs.inspect_run(root, selected, run_id="paper-run-a", now=T)
    with closing(reg.connect(inventory, True)) as con, con:
        runs.store_observation(con, observed, observed_at=AT)
    with closing(reg.connect(inventory, False)) as con:
        current = reg.registered_paper_status(con, now=T)
        assert len(current) == 1
        assert current[0]["state"] == "NOT_RUNNING"
        assert current[0]["journal_seq_reported"] == 0
        assert con.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    status = reg.db_status(inventory)["counts"]
    assert status["registered_paper_runs"] == 1
    assert status["paper_running_observed"] == 0
    # Destroy source evidence without editing inventory: read-only view must
    # change to UNKNOWN, not reuse cached NOT_RUNNING / hypothetical RUNNING.
    with closing(sqlite3.connect(root / "paper-events.sqlite3")) as con, con:
        con.execute("UPDATE runs SET manifest_sha='a' WHERE run_id='paper-run-a'")
    with closing(reg.connect(inventory, False)) as con:
        assert reg.registered_paper_status(con, now=T)[0]["state"] == "UNKNOWN"
    assert reg.db_status(inventory)["counts"]["paper_running_observed"] == 0


def test_fp_portfolio_hash_and_retroactive_decisions_fail_closed(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    root = _build(tmp_path, "f" * 64)
    mismatch = runs.inspect_run(root, selected, run_id="paper-run-a", now=T)
    assert mismatch["state"] == "UNKNOWN"
    assert mismatch["reason"] == "PORTFOLIO_MISMATCH"
    with closing(sqlite3.connect(root / "paper-events.sqlite3")) as con:
        con.execute("UPDATE runs SET manifest_sha='f' WHERE run_id='paper-run-a'")
        con.commit()
    assert runs.inspect_run(root, selected, run_id="paper-run-a", now=T)["state"] == "UNKNOWN"
    root = _build(tmp_path / "earlier", selected["definition_sha256"])
    early = {**selected, "selection_known_at": (T + timedelta(days=1)).isoformat()}
    result = runs.inspect_run(root, early, run_id="paper-run-a", now=T)
    assert result["state"] == "UNKNOWN"
    assert result["reason"] == "PIT_SELECTION_CLOCK_INVALID"


def test_registry_refuses_forged_running_state_and_identity_drift(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    root = _build(tmp_path, selected["definition_sha256"], change=True)
    observed = runs.inspect_run(root, selected, run_id="paper-run-a", now=T)
    with closing(reg.connect(inventory, True)) as con:
        with pytest.raises(ValueError, match="re-verification"):
            with con:
                runs.store_observation(
                    con, {**observed, "state": "PAPER_RUNNING_OBSERVED"}, observed_at=AT
                )
        with con:
            runs.store_observation(con, observed, observed_at=AT)
    # Change the previously trusted manifest and account while preserving FP
    # source-internal hashes: registry must catch its indexed identity drift.
    db = root / "paper-events.sqlite3"
    with closing(sqlite3.connect(db)) as con, con:
        text = con.execute("SELECT manifest FROM runs WHERE run_id='paper-run-a'").fetchone()[0]
        manifest = json.loads(text)
        manifest["account_id"] = "paper-acct-replaced"
        con.execute(
            "UPDATE runs SET account_id=?, manifest=?, manifest_sha=? WHERE run_id=?",
            (
                "paper-acct-replaced",
                fp.canonical(manifest).decode(),
                fp.digest(manifest),
                "paper-run-a",
            ),
        )
    with closing(reg.connect(inventory, False)) as con:
        current = reg.registered_paper_status(con, now=T)
    assert current[0]["state"] == "UNKNOWN"
    assert current[0]["reason"] == "REGISTERED_PAPER_IDENTITY_DRIFT"


def test_fp_status_does_not_depend_on_inventory_writability(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    root = _build(tmp_path, selected["definition_sha256"])
    with closing(reg.connect(inventory, True)) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            observed = runs.inspect_run(root, selected, run_id="paper-run-a", now=T)
            assert observed["state"] == "NOT_RUNNING"
            assert observed["journal_seq_reported"] == 0
        finally:
            con.execute("ROLLBACK")


def test_fp_chain_tamper_and_privacy_fail_closed(tmp_path: Path) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    root = _build(tmp_path, selected["definition_sha256"], change=True)
    db = root / "paper-events.sqlite3"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("UPDATE events SET chain_sha=? WHERE seq=1", ("f" * 64,))
    report = runs.inspect_run(root, selected, now=T)
    assert report["state"] == "UNKNOWN"
    assert report["reason"] == "FP_JOURNAL_UNAVAILABLE_OR_INTEGRITY_FAILURE"
    db.chmod(0o644)
    assert runs.inspect_run(root, selected, now=T)["reason"] == "INSECURE_OR_MISSING_JOURNAL"
    db.chmod(0o600)
    db.unlink()
    db.symlink_to(tmp_path / "other-db")
    assert runs.inspect_run(root, selected, now=T)["state"] == "UNKNOWN"


def test_fp_cli_requires_explicit_portfolio_and_never_writes_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory = _db(tmp_path)
    selected = _sel(inventory)
    root = _build(tmp_path, selected["definition_sha256"], change=False)
    source = root / "paper-events.sqlite3"
    before = sha256(source.read_bytes()).hexdigest()
    assert reg.cli(["--db", str(inventory), "paper", "--run-dir", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "PORTFOLIO_REQUIRED_FOR_FP_JOURNAL"
    assert (
        reg.cli(
            [
                "--db",
                str(inventory),
                "paper",
                "--run-dir",
                str(root),
                "--portfolio",
                "P1",
                "--run-id",
                "paper-run-a",
                "--apply",
            ]
        )
        == 0
    )
    value = json.loads(capsys.readouterr().out)
    assert value["state"] == "NOT_RUNNING"
    assert value["order_route"] == "NONE"
    assert sha256(source.read_bytes()).hexdigest() == before
    assert reg.cli(["--db", str(inventory), "paper"]) == 0
    collected = json.loads(capsys.readouterr().out)
    assert collected["observations"][0]["state"] == "NOT_RUNNING"
    assert collected["global_running_count"] == "UNKNOWN"
