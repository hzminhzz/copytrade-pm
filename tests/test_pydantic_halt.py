"""PYDN-02 public-interface regression oracles; engineering fixtures only."""

from contextlib import closing
from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm03_account import Account, RiskState
from copytrade_pm.pm03_execution import execute_targets
from copytrade_pm.pm_forward_journal import PaperJournal
from test_pm03_extended import BTC, T, book, cost, quote
from test_pm_forward_funding import _filled, _funding


@pytest.mark.parametrize("diagnostic", ["funding", "margin", "source"])
def test_halt_survives_diagnostics_and_sqlite_restart(tmp_path, diagnostic):
    campaign, journal = _filled(tmp_path)
    before = campaign.record_event(
        "run_1",
        "halt",
        {"kind": "HALT", "event_at": "2026-11-04T04:02:00+00:00", "reason": "OWNER_HALT"},
    )
    event = {
        "funding": {"kind": "FUNDING_UNKNOWN", "event_at": "2026-11-04T04:05:00+00:00"},
        "margin": _funding(margin=False),
        "source": {
            "kind": "SIMULATED_DECISION",
            "event_at": "2026-11-04T04:05:00+00:00",
            "hypothetical_fill_at": "2026-11-04T04:05:01+00:00",
            "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
            "order_route": "NONE",
            "source_book": None,
        },
    }[diagnostic]
    after = campaign.record_event("run_1", "diagnostic", event)
    assert after["account"]["risk"] == "HALT"
    assert after["account"]["halt_reason"] == "OWNER_HALT"
    assert after["account"]["quantities"] == before["account"]["quantities"]
    assert after["account"]["risk_reasons"]  # Operational diagnosis remains visible.
    reopened = PaperJournal(journal.root)
    recovered = reopened.restore("run_1")
    assert recovered["account"] == after["account"]
    assert recovered["journal_head_sha"] == after["journal_head_sha"]
    assert reopened.append("run_1", "diagnostic", event) == recovered
    with pytest.raises(ValueError, match="CONFLICTING_PAPER_EVENT"):
        reopened.append("run_1", "diagnostic", {**event, "risk_semantics_version": 1})


@pytest.mark.parametrize("failure", ["missing", "stale", "unsupported", "unknown_capacity"])
def test_halt_quote_failure_then_valid_reduction_never_reopens_risk(failure):
    account = Account.start(book(), T)
    account.simulate_fill(BTC, D("2"), D("100"), D("0"), accepted=True, allocated={"A": D("2")})
    account.risk = RiskState.HALT
    account.halt_reason = "OWNER_HALT"
    observation = {
        "missing": {},
        "stale": {BTC: quote()},
        "unsupported": {BTC: quote(supported=False)},
        "unknown_capacity": {BTC: replace(quote(), volume_base=None)},
    }[failure]
    at = "2026-10-31T04:10:00+00:00" if failure == "stale" else T
    fill_at = "2026-10-31T04:10:01+00:00" if failure == "stale" else "2026-10-31T04:00:01+00:00"
    blocked = execute_targets(
        account,
        {},
        observation,
        cost(),
        decision_at=at,
        hypothetical_fill_at=fill_at,
        permitted=True,
    )
    assert blocked["status"] == "BLOCKED"
    assert account.quantities[BTC] == D("2")
    assert account.risk == RiskState.HALT
    assert account.halt_reason == "OWNER_HALT"
    restored = Account.from_snapshot(book(), account.snapshot())
    current = replace(quote(), event_at=at, first_known_at=at)
    execute_targets(
        restored,
        {"A": {BTC: D("3")}},
        {BTC: current},
        cost(),
        decision_at=at,
        hypothetical_fill_at=fill_at,
        permitted=True,
    )
    assert restored.quantities[BTC] == D("2")  # No new risk after the diagnostic.
    reduced = execute_targets(
        restored,
        {},
        {BTC: current},
        cost(),
        decision_at=at,
        hypothetical_fill_at=fill_at,
        permitted=True,
    )
    assert reduced["fills"]
    assert not restored.quantities.get(BTC)
    assert restored.risk == RiskState.HALT
    with pytest.raises(ValueError, match="RESET_NOT_AUTHORIZED"):
        restored.manual_reset(authorization="", as_of=at)
    restored.manual_reset(authorization="existing-paper-reset-contract", as_of=at)
    assert restored.risk == RiskState.GREEN


def test_archived_buggy_event_hashes_remain_readable_but_cannot_reopen_risk(tmp_path):
    """Recorded on 175d54d before the fix, independently of the new reducer."""
    fixture = json.loads((Path(__file__).parent / "fixtures/pydantic_legacy_halt.json").read_text())
    journal = PaperJournal(tmp_path / "legacy")
    with closing(sqlite3.connect(journal.path)) as db, db:
        db.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)", fixture["runs"])
        db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", fixture["events"])
    archived = journal.restore("run_1")
    assert archived["account"]["risk"] == "RED"
    assert archived["account"]["halt_reason"] == "OWNER_HALT"
    assert archived["journal_head_sha"] == fixture["events"][-1][-1]
    next_event = {"kind": "FUNDING_UNKNOWN", "event_at": "2026-11-04T04:06:00+00:00"}
    current = journal.append("run_1", "new-diagnostic", next_event)
    assert current["account"]["risk"] == "HALT"
    assert current["account"]["quantities"] == archived["account"]["quantities"]
    assert PaperJournal(journal.root).restore("run_1") == current
    with closing(sqlite3.connect(journal.path)) as db:
        rows = db.execute("SELECT * FROM events WHERE seq <= 3 ORDER BY seq").fetchall()
    assert [list(row) for row in rows] == fixture["events"]
    with pytest.raises(ValueError, match="LEGACY_RISK_SEMANTICS_READ_ONLY"):
        journal.append("run_1", "downgrade", {**next_event, "risk_semantics_version": 1})
