"""First-known clocks and independent follower finance through public step."""

from decimal import Decimal

import pytest


from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from test_pm_forward_observed_paper import BTC, RAW_MARKET, add_quote, add_source, at
from test_pm_forward_single_shot import new_paper, entry_attempts


def test_verified_flat_exit_releases_obsolete_quote_requirement(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312)
    paper.step(at(313))
    add_quote(tape, 319)
    add_source(tape, 2, 319, {})
    result = paper.step(at(322))
    assert result["positions"] == {}
    assert result["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert paper.run.account.pm04_state["routed_targets"]["S035"] == {}
    restart = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="single_attempt",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    later = restart.step(at(900))
    assert later["tick"] == "NO_ACTIVE_TARGETS"
    assert later["positions"] == {}
    assert len(entry_attempts(restart)) == 1
    assert restart.run.restore()["account"] == restart.run.account.snapshot()


def test_coalesced_due_restart_records_actual_attempt_clock(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    initial = paper.step(at(14))["execution_intents"]["S035"]
    add_source(tape, 2, 199, {BTC.key: "10"})
    updated = paper.step(at(201))["execution_intents"]["S035"]
    assert updated["intent_id"] == initial["intent_id"]
    assert updated["first_known_at"] == at(13)
    assert updated["due_at"] == at(313)
    paper = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="single_attempt",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    add_quote(tape, 317)
    result = paper.step(at(318))
    timing = result["execution_intents"]["S035"]["timing"]
    assert timing["due_at"] == at(313)
    assert timing["decision_at"] == at(318)
    assert timing["modeled_attempt_at"] == at(318)
    assert timing["scheduler_jitter_seconds"] == "5"
    assert timing["reason"] == "LATE_WITHIN_GRACE"
    assert Decimal(result["positions"][BTC.key]) == Decimal("0.282")
    assert len(entry_attempts(paper)) == 1
    assert paper.run.restore()["account"] == paper.run.account.snapshot()


def test_expired_window_records_no_modeled_attempt(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    assert paper.step(at(313))["execution_results"]["S035"].startswith("WAIT_MARKET_OR_TARGET:")
    expired = paper.step(at(344))["execution_intents"]["S035"]
    assert expired["status"] == "EXPIRED_NO_TRADE"
    assert expired["timing"]["modeled_attempt_at"] is None
    assert expired["timing"]["scheduler_jitter_seconds"] == "31"
    assert expired["timing"]["reason"] == "EXPIRED_WITHOUT_ATTEMPT"
    assert entry_attempts(paper) == []


@pytest.mark.parametrize("exit_depth", [200, 0.01])
def test_reversal_never_opens_opposite_before_held_exposure_resolves(tmp_path, exit_depth):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312)
    paper.step(at(313))
    add_source(tape, 2, 319, {BTC.key: "-20"})
    add_quote(tape, 319, size=exit_depth)
    reversed_source = paper.step(at(322))
    assert Decimal(reversed_source["positions"].get(BTC.key, "0")) >= 0
    assert reversed_source["execution_intents"]["S035"]["due_at"] == at(620)
    add_quote(tape, 619)
    due = paper.step(at(620))
    if exit_depth == 200:
        assert reversed_source["positions"] == {}
        assert Decimal(due["positions"][BTC.key]) < 0
    else:
        assert reversed_source["unresolved_exposures"]
        assert due["positions"] == {}
        assert due["unresolved_exposures"] == {}
        assert paper.run.account.pm04_state["routed_targets"]["S035"] == {}
    assert len(entry_attempts(paper)) == 2
    assert paper.run.restore()["account"] == paper.run.account.snapshot()
