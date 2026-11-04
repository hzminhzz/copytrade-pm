"""Wallet registry: fail-closed identity, provenance, and SQLite durability."""

from __future__ import annotations

import csv
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as registry


def address(i: int) -> str:
    return f"0x{i:040x}"


def fixture(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "source"
    root.mkdir()
    for i, (cohort, relative) in enumerate(registry.RESEARCH.items()):
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=["address", "local_fill_rows"])
            writer.writeheader()
            writer.writerow({"address": address(i + 1), "local_fill_rows": 3})
    (root / registry.EXCLUSIONS).write_text(
        "address,exclusion_reason\n" + address(9) + ",excluded\n"
    )
    snapshot = {
        "cohorts": {
            "research-108": {address(1)},
            "nansen-20": {address(2)},
            "hyperx-30": {address(3)},
        },
        "base_rows": {address(1): {"local_fill_rows": "3"}},
        "exclusions": {address(9): "excluded"},
        "roster": {
            address(2): {"total_fills": "1"},
            address(3): {"total_fills": "2"},
        },
        "sources": {
            "research-108": "a" * 64,
            "nansen-20": "b" * 64,
            "hyperx-30": "c" * 64,
            "exclusions": "d" * 64,
            "new50_roster": "e" * 64,
            "new50_audit": "f" * 64,
        },
        "desired": {address(1), address(8)},
        "subscribed": {address(8)},
        "monitoring_status": "OBSERVED",
    }
    return root, snapshot


def test_normalize_rejects_bad_or_injected_address() -> None:
    assert registry.normalize(address(1).upper().replace("0X", "0x")) == address(1)
    for value in ("not-a-wallet", address(1) + "' OR 1=1", "0x" + "a" * 39, ""):
        with pytest.raises(ValueError, match="redacted"):
            registry.normalize(value)


def test_private_atomic_idempotent_import(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    expected = registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    repeat = registry.apply(db, snapshot, "2026-11-05T00:00:00+00:00")
    assert repeat["manifest_sha256"] == expected["manifest_sha256"]
    assert repeat["unchanged"] is True
    s = registry.db_status(db)
    assert s["counts"]["research_unique"] == 3
    assert s["counts"]["desired"] == 2
    assert s["counts"]["subscribed"] == 1
    with closing(registry.connect(db, False)) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM portfolio_versions").fetchone()[0] == 7
        assert connection.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM wallets")


def test_bad_import_does_not_destroy_previous_generation(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    baseline = registry.db_status(db)
    bad = {**snapshot, "roster": {**snapshot["roster"]}}
    bad["roster"][address(2)] = {"total_fills": "not-a-number"}
    with pytest.raises(ValueError):
        registry.apply(db, bad, "2026-11-05T00:00:00+00:00")
    assert registry.db_status(db) == baseline
    with closing(registry.connect(db, False)) as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_private_permissions(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    private = tmp_path / "private"
    db = private / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    assert private.stat().st_mode & 0o777 == 0o700
    assert db.stat().st_mode & 0o777 == 0o600
    private.chmod(0o755)
    with pytest.raises(PermissionError):
        registry.apply(db, snapshot, "2026-11-05T00:00:00+00:00")


def test_wal_reader_snapshot_survives_atomic_generation_change(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    changed = {
        **snapshot,
        "cohorts": {**snapshot["cohorts"], "research-108": {address(4)}},
        "sources": {**snapshot["sources"], "research-108": "f" * 64},
    }
    with closing(registry.connect(db, False)) as reader:
        reader.execute("BEGIN")
        old = reader.execute(
            "SELECT value FROM snapshot_meta WHERE key='manifest_sha256'"
        ).fetchone()[0]
        registry.apply(db, changed, "2026-11-05T00:00:00+00:00")
        assert (
            reader.execute(
                "SELECT value FROM snapshot_meta WHERE key='manifest_sha256'"
            ).fetchone()[0]
            == old
        )
        reader.rollback()
        assert (
            reader.execute(
                "SELECT value FROM snapshot_meta WHERE key='manifest_sha256'"
            ).fetchone()[0]
            != old
        )


def test_wallet_alias_resolution_is_private_and_asof(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    snapshot["frozen_aliases"] = {"W001": address(1)}
    t0 = "2026-11-04T00:00:00+00:00"
    registry.apply(db, snapshot, t0)
    import json

    assert (
        registry.cli(
            [
                "--db",
                str(db),
                "wallet",
                "--alias",
                "W001",
                "--asof",
                "2026-11-03T00:00:00+00:00",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"found": False}
    assert registry.cli(["--db", str(db), "wallet", "--alias", "W001"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["found"] is True
    assert result["cohorts"] == ["research-108"]
    assert "0x" not in json.dumps(result)


def test_alias_conflict_rolls_back_mid_transaction(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    initial = {**snapshot, "frozen_aliases": {"W001": address(1)}}
    registry.apply(db, initial, "2026-11-04T00:00:00+00:00")
    before = registry.db_status(db)
    changed = {
        **initial,
        "frozen_aliases": {"W001": address(7)},
        "sources": {**initial["sources"], "research-108": "8" * 64},
    }
    with pytest.raises(ValueError, match="identity drift"):
        registry.apply(db, changed, "2026-11-05T00:00:00+00:00")
    assert registry.db_status(db) == before
    with closing(registry.connect(db, False)) as con:
        assert (
            con.execute("SELECT COUNT(*) FROM wallets WHERE address=?", (address(7),)).fetchone()[0]
            == 0
        )
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_source_drift_preserves_prior_cohorts_and_run_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    t0 = "2026-11-04T00:00:00+00:00"
    t1 = "2026-11-05T00:00:00+00:00"
    registry.apply(db, snapshot, t0)
    with closing(registry.connect(db, True)) as con, con:
        con.execute(
            "INSERT INTO portfolio_runs VALUES(?,?,?,?,?,?,?)",
            ("synthetic-run", "P1", 1, "test-account", "test-journal", None, t0),
        )
        con.execute(
            "INSERT INTO qualification_decisions VALUES(?,?,?,?,?,?)",
            ("synthetic-verdict", 1, "test-policy", "a" * 64, t0, "UNQUALIFIED"),
        )
    changed = {
        **snapshot,
        "cohorts": {**snapshot["cohorts"], "research-108": {address(4)}},
        "sources": {**snapshot["sources"], "research-108": "9" * 64},
        "desired": {address(1)},
        "subscribed": set(),
    }
    registry.apply(db, changed, t1)
    assert registry.db_status(db)["counts"]["research_unique"] == 3
    assert registry.db_status(db)["counts"]["desired"] == 1
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 2
        assert (
            con.execute("SELECT COUNT(*) FROM cohorts WHERE cohort_id='research-108'").fetchone()[0]
            == 2
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM evidence_versions WHERE source_key='research-108'"
            ).fetchone()[0]
            == 2
        )
        assert con.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM qualification_decisions").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    import json

    registry.cli(["--db", str(db), "wallet", "--address", address(1), "--asof", t0])
    assert "research-108" in json.loads(capsys.readouterr().out)["cohorts"]
    registry.cli(["--db", str(db), "wallet", "--address", address(1), "--asof", t1])
    assert "research-108" not in json.loads(capsys.readouterr().out)["cohorts"]


def test_indexed_ledger_observes_without_claiming_admission(tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite"
    con = sqlite3.connect(db)
    try:
        con.executescript("""
        CREATE TABLE ledger_meta(ledger_id TEXT,current_seq INTEGER,retention_floor INTEGER);
        CREATE TABLE outbox_events(seq INTEGER PRIMARY KEY,wallet_id TEXT,
                                   kind TEXT,known_at TEXT);
        CREATE INDEX idx_outbox_wallet ON outbox_events(wallet_id);
        INSERT INTO ledger_meta VALUES('synthetic',2,0);
        """)
        con.execute(
            "INSERT INTO outbox_events VALUES(1,?,?,?)",
            (address(1), "ACCOUNT_SNAPSHOT", "2026-01-01T00:00:00+00:00"),
        )
        con.commit()
    finally:
        con.close()
    result = registry.observe_ledger(db, {address(1), address(2)})
    assert result["queried_wallets"] == 2
    assert result["stale_outbox_observation"] == 1
    assert result["no_indexed_event"] == 1
    assert result["runtime_admitted"] == "UNKNOWN"
    assert result["receipt_health"] == "UNKNOWN"
    prior = registry.observation_ledger_identity(db)
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("UPDATE ledger_meta SET ledger_id='replacement'")
        connection.commit()
    assert registry.observation_ledger_identity(db) != prior
    with pytest.raises(ValueError, match="budget"):
        registry.observe_ledger(db, {address(1), address(2)}, max_wallets=1)
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("DROP INDEX idx_outbox_wallet")
        connection.commit()
    with pytest.raises(ValueError, match="index"):
        registry.observe_ledger(db, {address(1)})
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("UPDATE ledger_meta SET retention_floor=3")
        connection.commit()
    with pytest.raises(ValueError, match="cursor"):
        registry.observation_ledger_identity(db)


def test_asof_and_backup_restore(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    assert (
        registry.cli(
            [
                "--db",
                str(db),
                "portfolio",
                "P1",
                "--asof",
                "2026-11-03T00:00:00+00:00",
            ]
        )
        == 0
    )
    import json

    assert json.loads(capsys.readouterr().out)["P1"]["status"] == "UNKNOWN_AT_ASOF"
    assert (
        registry.cli(
            [
                "--db",
                str(db),
                "wallet",
                "--address",
                address(1),
                "--asof",
                "2026-11-03T00:00:00+00:00",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["cohorts"] == []
    with pytest.raises(ValueError):
        registry.asof_cutoff("2026-11-03T00:00:00")
    copy = tmp_path / "backup" / "backup.sqlite"
    registry.backup(db, copy)
    assert registry.db_status(copy) == registry.db_status(db)
    assert copy.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        registry.backup(db, copy)
    second = tmp_path / "private" / "backups" / "backup.sqlite"
    assert registry.cli(["--db", str(db), "backup", "--to", str(second)]) == 0
    assert registry.db_status(second) == registry.db_status(db)
    with pytest.raises(ValueError, match="private"):
        registry.cli(["--db", str(db), "backup", "--to", str(tmp_path / "outside.sqlite")])


def test_portfolios_not_running_or_authorized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    assert registry.cli(["--db", str(db), "portfolio", "P1"]) == 0
    import json

    result = json.loads(capsys.readouterr().out)
    assert result["P1"]["status"] == "RESEARCH_ONLY"
    assert result["P1"]["actual_run"] == "UNKNOWN"
    assert result["P1"]["authorized"] is False
