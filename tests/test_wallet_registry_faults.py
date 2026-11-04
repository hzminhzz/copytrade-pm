"""Wallet registry fault matrix without any production service or source writes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from copytrade_pm import wallet_registry as registry
from test_wallet_registry import address, fixture


def test_two_writer_imports_serialize_and_keep_one_generation(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"

    def worker(i: int) -> dict:
        return registry.apply(db, snapshot, f"2026-11-04T00:00:0{i}+00:00")

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(worker, range(6)))
    assert len(results) == 6
    assert all(r["manifest_sha256"] == results[0]["manifest_sha256"] for r in results)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_sigkill_mid_transaction_restores_previous_committed_generation(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    before = registry.db_status(db)
    code = (
        "import os,sqlite3,sys,time;"
        "con=sqlite3.connect(sys.argv[1]);"
        "con.execute('BEGIN IMMEDIATE');"
        "con.execute('INSERT INTO wallets(venue,network,address) VALUES(?,?,?)',"
        "('hyperliquid','mainnet',sys.argv[2]));"
        "print('READY',flush=True);time.sleep(30)"
    )
    worker = subprocess.Popen(
        [sys.executable, "-c", code, str(db), address(9999)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert worker.stdout is not None
        assert worker.stdout.readline().strip() == "READY"
        worker.kill()  # SIGKILL: no finalizer, no COMMIT, leave WAL recovery to SQLite.
        worker.wait(timeout=5)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)
        if worker.stdout is not None:
            worker.stdout.close()
        if worker.stderr is not None:
            worker.stderr.close()
    assert registry.db_status(db) == before
    with closing(registry.connect(db, False)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM wallets WHERE address=?", (address(9999),)
            ).fetchone()[0]
            == 0
        )
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_modified_source_after_snapshot_is_rejected_without_side_effects(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    baseline = registry.db_status(db)
    src = tmp_path / "input.csv"
    src.write_text("address\n" + address(1) + "\n")
    new = {
        **snapshot,
        "source_paths": {"research-108": src},
        "sources": {**snapshot["sources"], "research-108": registry.digest(src)},
    }
    src.write_text("address\n" + address(2) + "\n")
    with pytest.raises(ValueError, match="source changed since staged"):
        registry.apply(db, new, "2026-11-05T00:00:00+00:00")
    assert registry.db_status(db) == baseline


def test_sqlite_full_rollback_preserves_prior_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    with closing(registry.connect(db, False)) as con:
        existing_pages = con.execute("PRAGMA page_count").fetchone()[0]
    before = registry.db_status(db)
    original_connect = registry.connect

    def page_limited(path: Path, writable: bool):
        con = original_connect(path, writable)
        if writable:
            assert (
                con.execute(f"PRAGMA max_page_count={existing_pages}").fetchone()[0]
                == existing_pages
            )
        return con

    monkeypatch.setattr(registry, "connect", page_limited)
    oversized = {
        **snapshot,
        "desired": {address(i + 10_000) for i in range(5_000)},
        "sources": {**snapshot["sources"], "desired_wallets": "8" * 64},
    }
    with pytest.raises(sqlite3.OperationalError, match="full"):
        registry.apply(db, oversized, "2026-11-05T00:00:00+00:00")
    assert registry.db_status(db) == before
    with closing(registry.connect(db, False)) as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_untrusted_paper_run_cannot_mutate_registry_or_reuse_an_account(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    original = registry.db_status(db)
    assert registry.cli(["--db", str(db), "paper"]) == 0
    assert registry.db_status(db) == original
    assert (
        registry.cli(["--db", str(db), "paper", "--run-dir", str(tmp_path / "absent"), "--apply"])
        == 2
    )
    assert registry.db_status(db) == original
    with closing(registry.connect(db, False)) as con:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE portfolio_runs SET heartbeat_at='BAD'")


def test_docs_guide_links_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "docs/WALLET-STATUS.md",
        "docs/WALLET-REGISTRY-ACCEPTANCE-20261104.md",
        "docs/WALLET-REGISTRY-STATUS-20261104.md",
        "docs/WALLET-REGISTRY-PAPER-CONTRACT-20261104.md",
        "docs/WALLET-REGISTRY-SQLITE-ADOPTION-PLAN-20261104.md",
    ):
        assert (root / rel).is_file()
