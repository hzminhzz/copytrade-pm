"""The abandoned JSONL projection must never claim an FP worker is running."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_portfolios as selections
from copytrade_pm import wallet_registry_runs as runs
from test_wallet_registry import fixture

REPO = Path(__file__).resolve().parents[1]
IMPORT = datetime.now(timezone.utc).isoformat()


def _db(tmp_path: Path) -> Path:
    _, snapshot = fixture(tmp_path)
    contracts = selections.read_decisions(REPO, registry.PORTFOLIOS, observed_at=IMPORT)
    snapshot["portfolio_contracts"] = contracts
    snapshot["sources"].update(
        {
            f"portfolio_doc:{name}": item["payload"]["source_doc_sha256"]
            for name, item in contracts.items()
        }
    )
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, IMPORT)
    return db


def _legacy_source(tmp_path: Path) -> Path:
    directory = tmp_path / "legacy"
    directory.mkdir(mode=0o700)
    for name, contents in {
        "manifest.json": {
            "schema": "paper_run_manifest_v1",
            "run_id": "fake-worker",
            "portfolio_id": "P1",
            "account_id": "fake-account",
            "order_route": "NONE",
        },
        "status.json": {
            "schema": "paper_run_status_v1",
            "worker_state": "RUNNING",
            "heartbeat_at": IMPORT,
            "worker_pid": 1,
        },
    }.items():
        output = directory / name
        output.write_text(json.dumps(contents))
        output.chmod(0o600)
    journal = directory / "events.jsonl"
    journal.write_text("")
    journal.chmod(0o600)
    return directory


def test_legacy_jsonl_v1_can_never_claim_running_or_index(tmp_path: Path) -> None:
    db = _db(tmp_path)
    directory = _legacy_source(tmp_path)
    with closing(registry.connect(db, False)) as con:
        selection = selections.select_asof(con, "P1", IMPORT)
    result = runs.inspect_run(directory, selection)
    assert result["state"] == "UNKNOWN"
    assert result["reason"] == "UNSUPPORTED_LEGACY_PROJECTION_OR_MISSING_JOURNAL"
    assert result["scientifically_qualified"] is False
    assert result["trading_authorized"] is False
    baseline = registry.db_status(db)
    assert (
        registry.cli(
            [
                "--db",
                str(db),
                "paper",
                "--run-dir",
                str(directory),
                "--portfolio",
                "P1",
                "--apply",
            ]
        )
        == 2
    )
    assert registry.db_status(db) == baseline


def test_missing_native_fp_source_is_unknown_not_stopped_or_running(tmp_path: Path) -> None:
    selection = {
        "portfolio_id": "P1",
        "version": 1,
        "definition_sha256": "a" * 64,
        "selection_known_at": "2026-11-01T00:00:00+00:00",
    }
    result = runs.inspect_run(tmp_path / "absent", selection)
    assert result["state"] == "UNKNOWN"
    assert result["order_route"] == "NONE"
    assert result["trading_authorized"] is False


def test_untrusted_input_cannot_create_registry_run(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with closing(registry.connect(db, True)) as con:
        with pytest.raises(ValueError, match="unverified"):
            with con:
                runs.store_observation(con, {"state": "UNKNOWN"}, observed_at=IMPORT)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 0
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
