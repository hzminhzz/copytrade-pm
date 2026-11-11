"""Source startup O(log N) admission fence: no downtime replay or JSON full scans."""

from __future__ import annotations

from contextlib import closing
import sqlite3

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import (
    ObservedP1Paper,
    _prestart_source_cursor,
)
from test_pm_forward_observed_paper import RAW_MARKET, add_quote, add_source, at, registry


def test_prestart_head_uses_covering_index_with_bounded_sqlite_steps():
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute(
            "CREATE TABLE source_receipts("
            "source_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT,"
            "PRIMARY KEY(source_id,seq))"
        )
        db.executemany(
            "INSERT INTO source_receipts VALUES (?,?,?)",
            (
                ("S035", i, '{"first_known_at":"2026-11-10T00:00:00+00:00"}')
                for i in range(1, 50001)
            ),
        )
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT seq FROM source_receipts "
            "WHERE source_id=? ORDER BY seq DESC LIMIT 1",
            ("S035",),
        ).fetchall()
        assert any("COVERING INDEX" in item[3] for item in plan)
        calls = 0

        def budget():
            nonlocal calls
            calls += 1
            return calls > 20

        db.set_progress_handler(budget, 100)
        try:
            assert _prestart_source_cursor(db, "S035", 1) == 50000
            assert _prestart_source_cursor(db, "UNKNOWN", 0) == 0
            with pytest.raises(ValueError, match="PAPER_ORIGINAL_SOURCE_CURSOR_REGRESSED"):
                _prestart_source_cursor(db, "S035", 50001)
            with pytest.raises(ValueError, match="PAPER_DURABLE_SOURCE_CURSOR_INVALID"):
                _prestart_source_cursor(db, "S035", -1)
        finally:
            db.set_progress_handler(None, 0)
        assert calls <= 20


def test_restart_skips_unobserved_source_downtime_without_resetting_run(tmp_path):
    observed = PaperJournal(tmp_path / "official-source")
    market = {RAW_MARKET["symbol"]: RAW_MARKET}
    add_quote(observed, 10)
    root = tmp_path / "isolated-ledger"
    reg = registry(tmp_path / "registry.sqlite")
    original = ObservedP1Paper(
        source_db=observed.path,
        state_root=root,
        run_id="p1_restart_fence",
        catalog=market,
        registry_db=reg,
        started_at=at(0),
    )
    assert original.last_seen["S035"] == 0
    # The source changes after the run was first declared, but the consumer
    # was down: the transition is already stale at this process restart.
    add_source(observed, 1, 12, {})
    revived = ObservedP1Paper(
        source_db=observed.path,
        state_root=root,
        run_id="p1_restart_fence",
        catalog=market,
        registry_db=reg,
        source_startup_policy="NO_DOWNTIME_REPLAY",
    )
    assert revived.started_at == at(0)
    assert revived.last_seen["S035"] == 1
    result = revived.step(at(14))
    assert result["source_results"]["S035"] == "PRE_START_UNMODELED"
    assert all(row["event"]["kind"] != "PM04_PAPER_SOURCE" for row in revived.run.ledger.read())
    # Genuine future transitions must still be processed normally, with
    # frozen original T0/k and all original risk/market guards.
    add_source(observed, 2, 20, {})
    result = revived.step(at(21))
    assert result["source_results"]["S035"] == "RECORDED_PAPER_SOURCE"
    assert revived.last_seen["S035"] == 2
    assert revived.run.account.quantities == {}
