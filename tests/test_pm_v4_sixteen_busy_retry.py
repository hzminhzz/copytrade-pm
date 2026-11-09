"""Pydantic V4 16-portfolio supervisor: contention is retryable, corruption is not."""

from __future__ import annotations

import sqlite3

from copytrade_pm.pm_v4_sixteen_paper import _is_retryable_sqlite_busy, _tick_runs


def _ok(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "tick": "NO_ACTIVE_TARGETS",
        "net_pnl": "0",
        "source_results": {"S035": "ALREADY_SEEN"},
        "execution_results": {},
        "exit_results": {},
        "execution_outcomes": {},
        "risk": "GREEN",
    }


class FakeRun:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def step(self):
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_sqlite_busy_keeps_all_portfolios_eligible_and_recovers_without_fake_fill():
    a = FakeRun(sqlite3.OperationalError("database is locked"), _ok("p1"))
    b = FakeRun(_ok("e1"), _ok("e1"))
    runs = {"P1": a, "E1": b}
    prior, quarantined, retrying = {}, {}, set()
    first = _tick_runs(runs, prior, quarantined, retrying)
    assert set(first) == {"P1", "E1"}
    assert first["P1"] == {
        "tick": "WAIT_SQLITE_BUSY_RETRY",
        "reason": "TRANSIENT_SQLITE_BUSY",
        "order_route": "NONE",
    }
    assert first["E1"]["real_broker_fills"] == 0
    assert prior.keys() == {"E1"}
    assert quarantined == {}
    assert retrying == {"P1"}

    second = _tick_runs(runs, prior, quarantined, retrying)
    assert set(second) == {"P1"}
    assert second["P1"]["run_id"] == "p1"
    assert second["P1"]["recovered_from_sqlite_busy"] is True
    assert second["P1"]["execution_results"] == {}
    assert second["P1"]["real_broker_fills"] == 0
    assert prior.keys() == {"P1", "E1"}
    assert quarantined == {}
    assert retrying == set()


def test_repeated_busy_logs_once_and_preserves_previous_financial_projection():
    a = FakeRun(
        _ok("p1"),
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database is locked"),
        _ok("p1"),
    )
    prior, quarantined, retrying = {}, {}, set()
    assert _tick_runs({"P1": a}, prior, quarantined, retrying)["P1"]["tick"] == "NO_ACTIVE_TARGETS"
    previous = prior["P1"]
    assert (
        _tick_runs({"P1": a}, prior, quarantined, retrying)["P1"]["tick"]
        == "WAIT_SQLITE_BUSY_RETRY"
    )
    assert _tick_runs({"P1": a}, prior, quarantined, retrying) == {}
    assert prior["P1"] == previous
    assert retrying == {"P1"}
    restored = _tick_runs({"P1": a}, prior, quarantined, retrying)
    assert restored["P1"]["recovered_from_sqlite_busy"] is True
    assert quarantined == {}
    assert retrying == set()


def test_nonbusy_database_error_still_quarantines_ledger_only():
    a = FakeRun(sqlite3.OperationalError("disk I/O error"))
    b = FakeRun(_ok("e1"), _ok("e1"))
    prior, quarantined, retrying = {}, {}, set()
    changed = _tick_runs({"P1": a, "E1": b}, prior, quarantined, retrying)
    assert changed["P1"]["tick"] == "BLOCKED_PAPER_LEDGER"
    assert changed["E1"]["run_id"] == "e1"
    assert "P1" in quarantined and "E1" not in quarantined
    assert retrying == set()
    _tick_runs({"P1": a, "E1": b}, prior, quarantined, retrying)
    assert a.calls == 1


def test_only_explicit_sqlite_contention_is_retryable():
    assert _is_retryable_sqlite_busy(sqlite3.OperationalError("database is locked"))
    assert _is_retryable_sqlite_busy(sqlite3.OperationalError("database table is locked"))
    assert not _is_retryable_sqlite_busy(
        sqlite3.OperationalError("database disk image is malformed")
    )
    assert not _is_retryable_sqlite_busy(ValueError("database is locked"))
