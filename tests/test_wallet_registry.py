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
