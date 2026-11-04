"""Strict paper-run observer is read-only to publisher and fail-closed."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat

import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_portfolios as selections
from copytrade_pm import wallet_registry_runs as runs
from test_wallet_registry import fixture

REPO = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc)
IMPORT = NOW.isoformat()


def _private_write(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o600)


def _payloads(
    tmp_path: Path,
    *,
    account_id: str = "virtual-paper-one",
    run_id: str = "run-01",
    portfolio_name: str = "P1",
) -> tuple[Path, dict]:
    run_dir = tmp_path / run_id
    run_dir.mkdir(mode=0o700)
    source = selections.read_decisions(REPO, registry.PORTFOLIOS, observed_at=IMPORT)
    selected = source[portfolio_name]
    selection = {
        "portfolio_id": portfolio_name,
        "version": 1,
        "definition_sha256": selected["definition_sha256"],
        "source_commit": selected["payload"]["source_commit"],
    }
    manifest = {
        "schema": runs.SCHEMA_MANIFEST,
        "run_id": run_id,
        "portfolio_id": portfolio_name,
        "portfolio_version": 1,
        "portfolio_definition_sha256": selected["definition_sha256"],
        "account_id": account_id,
        "journal_name": "events.jsonl",
        "environment": "PAPER",
        "order_route": "NONE",
    }
    status = {
        "schema": runs.SCHEMA_STATUS,
        "run_id": run_id,
        "portfolio_definition_sha256": selected["definition_sha256"],
        "account_id": account_id,
        "worker_pid": os.getpid(),
        "worker_start_ticks": runs.process_start_ticks(os.getpid()),
        "heartbeat_at": IMPORT,
        "transport_heartbeat_at": IMPORT,
        "quote_heartbeat_at": IMPORT,
        "journal_seq": 0,
        "journal_head_sha256": "0" * 64,
        "worker_state": "RUNNING",
    }
    _private_write(run_dir / "manifest.json", json.dumps(manifest).encode())
    _private_write(run_dir / "status.json", json.dumps(status).encode())
    _private_write(run_dir / "events.jsonl", b"")
    return run_dir, selection


def _update_status(run_dir: Path, **changed) -> None:
    path = run_dir / "status.json"
    contents = json.loads(path.read_text())
    contents.update(changed)
    _private_write(path, json.dumps(contents).encode())


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


def test_healthy_paper_observation_does_not_mutate_publisher(tmp_path: Path) -> None:
    run_dir, selection = _payloads(tmp_path)
    original = {p.name: registry.digest(p) for p in run_dir.iterdir()}
    observed = runs.inspect_run(run_dir, selection, now=NOW)
    assert observed["state"] == "PAPER_RUNNING_OBSERVED"
    assert observed["paper_observation_only"] is True
    assert observed["scientifically_qualified"] is False
    assert observed["trading_authorized"] is False
    assert observed["journal_seq_reported"] == 0
    assert "run_root" not in runs.sanitized(observed)
    assert "virtual-paper-one" not in json.dumps(runs.sanitized(observed))
    assert original == {p.name: registry.digest(p) for p in run_dir.iterdir()}


def test_stale_heartbeat_lost_feed_and_quote_fail_closed(tmp_path: Path) -> None:
    run_dir, selection = _payloads(tmp_path)
    future = NOW + timedelta(minutes=5)
    assert runs.inspect_run(run_dir, selection, now=future)["state"] == "STALE"
    _update_status(run_dir, heartbeat_at=future.isoformat())
    assert runs.inspect_run(run_dir, selection, now=future)["state"] == "DEGRADED"
    _update_status(run_dir, transport_heartbeat_at=future.isoformat())
    assert runs.inspect_run(run_dir, selection, now=future)["reason"] == "QUOTE_STALE"
    _update_status(run_dir, quote_heartbeat_at=future.isoformat())
    assert runs.inspect_run(run_dir, selection, now=future)["state"] == "PAPER_RUNNING_OBSERVED"


def test_edited_definition_pid_and_unsafe_file_fail_closed(tmp_path: Path) -> None:
    run_dir, selection = _payloads(tmp_path)
    mismatch = {**selection, "definition_sha256": "f" * 64}
    assert runs.inspect_run(run_dir, mismatch, now=NOW)["reason"] == "PORTFOLIO_MISMATCH"
    _update_status(run_dir, worker_start_ticks="1")
    assert runs.inspect_run(run_dir, selection, now=NOW)["reason"] == "WORKER_UNVERIFIED"
    _update_status(run_dir, worker_start_ticks=runs.process_start_ticks(os.getpid()))
    (run_dir / "status.json").chmod(0o644)
    assert runs.inspect_run(run_dir, selection, now=NOW)["reason"] == "INSECURE_SOURCE"
    (run_dir / "status.json").chmod(0o600)
    (run_dir / "events.jsonl").unlink()
    assert runs.inspect_run(run_dir, selection, now=NOW)["reason"] == "JOURNAL_UNAVAILABLE"
    assert stat.S_IMODE((run_dir / "manifest.json").stat().st_mode) == 0o600


def test_duplicate_json_keys_or_unauthorized_route_fail_closed(tmp_path: Path) -> None:
    run_dir, selection = _payloads(tmp_path)
    _private_write(run_dir / "status.json", b'{"schema":"paper_run_status_v1","schema":"bad"}')
    assert runs.inspect_run(run_dir, selection, now=NOW)["state"] == "UNKNOWN"
    run_dir, selection = _payloads(tmp_path, run_id="run-02")
    manifest_file = run_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["order_route"] = "LIVE"
    _private_write(manifest_file, json.dumps(manifest).encode())
    assert runs.inspect_run(run_dir, selection, now=NOW)["reason"] == "INVALID_SCHEMA"


def test_registry_indexes_distinct_paper_runs_with_account_isolation(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    run_dir, _ = _payloads(tmp_path)
    with closing(registry.connect(db, False)) as con:
        selection = selections.select_asof(con, "P1", IMPORT)
    assert selection["definition_sha256"] is not None
    # The registry migration is from legacy v1, so sealed selection is v2.
    manifest_file = run_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["portfolio_version"] = selection["version"]
    _private_write(manifest_file, json.dumps(manifest).encode())
    observed = runs.inspect_run(run_dir, selection, now=NOW)
    assert observed["state"] == "PAPER_RUNNING_OBSERVED"
    with closing(registry.connect(db, True)) as con, con:
        runs.store_observation(con, observed, observed_at=IMPORT)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 1
        assert registry.registered_paper_status(con, now=NOW)[0]["state"] == (
            "PAPER_RUNNING_OBSERVED"
        )
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    second, _ = _payloads(tmp_path, account_id="virtual-paper-one", run_id="run-02")
    second_manifest = json.loads((second / "manifest.json").read_text())
    second_manifest["portfolio_version"] = selection["version"]
    _private_write(second / "manifest.json", json.dumps(second_manifest).encode())
    observed_second = runs.inspect_run(second, selection, now=NOW)
    assert observed_second["state"] == "PAPER_RUNNING_OBSERVED"
    with closing(registry.connect(db, True)) as con:
        with pytest.raises(ValueError, match="already bound"):
            with con:
                runs.store_observation(con, observed_second, observed_at=IMPORT)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 1


def test_missing_worker_status_is_unknown_not_running(tmp_path: Path) -> None:
    run_dir, selection = _payloads(tmp_path)
    (run_dir / "status.json").unlink()
    assert runs.inspect_run(run_dir, selection, now=NOW)["state"] == "UNKNOWN"
    assert runs.inspect_run(tmp_path / "does-not-exist", selection, now=NOW)["state"] == "UNKNOWN"
