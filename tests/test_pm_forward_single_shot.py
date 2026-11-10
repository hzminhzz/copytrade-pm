"""Forward-paper bounded execution: test observable ledger and account outcomes."""

from datetime import timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper, _event, _exclusive_runner
from copytrade_pm.pm_forward_single_shot import SingleShotMarketExecutionModel, apply_paper_event
from copytrade_pm.pm_paper_contracts import PaperOpportunity
from test_pm_forward_observed_paper import (
    BTC,
    RAW_MARKET,
    T,
    add_quote,
    add_source,
    at,
    registry,
)


def new_paper(tmp_path, tape, *, run_id="single_attempt"):
    return ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id=run_id,
        registry_db=registry(tmp_path / "registry.sqlite"),
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        started_at=at(0),
    )


def entry_attempts(paper):
    return [
        r["event"] for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXECUTE"
    ]


def test_second_writer_cannot_open_same_campaign(tmp_path):
    with _exclusive_runner(tmp_path / "private", "p1_v2"):
        with pytest.raises(ValueError, match="PAPER_RUN_ALREADY_HAS_A_PROCESS"):
            with _exclusive_runner(tmp_path / "private", "p1_v2"):
                pytest.fail("second writer admitted")


def test_first_known_waits_exactly_300_seconds_and_attempts_once(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    initial = paper.step(at(14))
    assert initial["execution_intents"]["S035"]["first_known_at"] == at(13)
    assert initial["execution_intents"]["S035"]["due_at"] == at(313)
    add_quote(tape, 310, size=200)
    not_due = paper.step((T + timedelta(seconds=312, milliseconds=999)).isoformat())
    assert not_due["positions"] == {}
    add_quote(tape, 312, size=200)
    due = paper.step(at(313))
    assert D(due["positions"][BTC.key]) == D("0.564")
    assert due["execution_intents"]["S035"]["status"] == "FILLED"
    assert len(entry_attempts(paper)) == 1
    again = paper.step(at(318))
    assert D(again["positions"][BTC.key]) == D("0.564")
    assert len(entry_attempts(paper)) == 1


def test_t300_original_k_and_release_survive_coalesce_restart_and_attempt(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    pending = paper.step(at(14))["execution_intents"]["S035"]
    original_k = paper.profile.k["S035"]
    original_release = paper.policy_sha
    assert pending["frozen_k"] == original_k
    assert pending["release_sha256"] == original_release
    assert pending["due_at"] == at(313)
    assert PaperOpportunity.model_validate(pending).frozen_k == original_k

    with pytest.raises(ValueError, match="PAPER_OPPORTUNITY_K_RELEASE_INCOMPLETE"):
        PaperOpportunity.model_validate({**pending, "release_sha256": None})
    with pytest.raises(ValueError, match="PAPER_OPPORTUNITY_FROZEN_K_INVALID"):
        PaperOpportunity.model_validate({**pending, "frozen_k": "0"})

    add_source(tape, 2, 199, {BTC.key: "10"})
    revised = paper.step(at(201))["execution_intents"]["S035"]
    assert revised["frozen_k"] == original_k
    assert revised["release_sha256"] == original_release
    assert revised["due_at"] == pending["due_at"]

    restarted = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="single_attempt",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    replayed = restarted.run.account.pm04_state["paper_execution"]["history"][revised["intent_id"]]
    assert replayed["frozen_k"] == original_k
    assert replayed["release_sha256"] == original_release
    add_quote(tape, 312, size=200)
    due = restarted.step(at(313))
    assert due["execution_intents"]["S035"]["status"] == "FILLED"
    attempt = entry_attempts(restarted)[0]["payload"]["input"]
    assert attempt["frozen_k"] == original_k
    assert attempt["release_sha256"] == original_release
    assert len(entry_attempts(restarted)) == 1


def test_t300_rejects_tampered_source_release_before_cursor_mutation(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    bad = _event(
        paper.run,
        "PM04_PAPER_SOURCE",
        "tampered_source_release",
        at(101),
        at(99),
        {
            "pod": "S035",
            "source_seq": 2,
            "source_sha": "f" * 64,
            "positions": {BTC.key: "10"},
            "first_known_at": at(100),
            "frozen_k": paper.profile.k["S035"],
            "release_sha256": "0" * 64,
        },
        first_known_at=at(100),
    )
    before = paper.run.account.snapshot()
    with pytest.raises(ValueError, match="PAPER_SOURCE_K_RELEASE_DRIFT"):
        apply_paper_event(paper.run.account, bad, None, "RESEARCH_SYNTHETIC")
    assert paper.run.account.snapshot() == before


def test_t300_rejects_rebased_k_attempt_without_mutating_account(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    intent = paper.step(at(14))["execution_intents"]["S035"]
    bad = _event(
        paper.run,
        "PM04_PAPER_EXECUTE",
        "tampered_attempt_" + intent["intent_id"],
        at(313),
        at(12),
        {
            "intent_id": intent["intent_id"],
            "source_seq": intent["source_seq"],
            "source_sha": intent["source_sha"],
            "frozen_k": "999",
            "release_sha256": intent["release_sha256"],
        },
        first_known_at=intent["first_known_at"],
    )
    before = paper.run.account.snapshot()
    with pytest.raises(ValueError, match="PAPER_ATTEMPT_K_RELEASE_DRIFT"):
        apply_paper_event(paper.run.account, bad, None, "RESEARCH_SYNTHETIC")
    assert paper.run.account.snapshot() == before
    assert entry_attempts(paper) == []


def test_updates_during_wait_preserve_clock_and_use_latest_complete_book(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_source(tape, 2, 199, {BTC.key: "10"})
    updated = paper.step(at(201))
    assert updated["execution_intents"]["S035"]["due_at"] == at(313)
    assert updated["execution_intents"]["S035"]["source_seq"] == 2
    add_quote(tape, 312)
    result = paper.step(at(313))
    assert D(result["positions"][BTC.key]) == D("0.282")
    assert len(entry_attempts(paper)) == 1


def test_close_before_maturity_cancels_pending_entry(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_source(tape, 2, 100, {})
    closed = paper.step(at(102))
    assert closed["execution_intents"]["S035"]["status"] == "CANCELED"
    add_quote(tape, 312)
    after = paper.step(at(313))
    assert after["positions"] == {}
    assert entry_attempts(paper) == []


def test_missing_quote_expires_without_retroactive_execution(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    assert paper.step(at(313))["execution_results"]["S035"].startswith("WAIT_MARKET_OR_TARGET:")
    expired = paper.step(at(344))
    assert expired["execution_intents"]["S035"]["status"] == "EXPIRED_NO_TRADE"
    add_quote(tape, 345)
    later = paper.step(at(347))
    assert later["positions"] == {}
    assert entry_attempts(paper) == []
    assert paper.run.restore()["account"] == paper.run.account.snapshot()


def test_identical_new_receipt_does_not_retry_rejected_order(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=1)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 313, size=0.1)
    rejected = paper.step(at(314))
    assert rejected["execution_intents"]["S035"]["status"] == "REJECTED"
    add_source(tape, 2, 319, {BTC.key: "20"})
    add_quote(tape, 320, size=200)
    again = paper.step(at(322))
    assert again["execution_intents"]["S035"]["status"] == "REJECTED"
    assert len(entry_attempts(paper)) == 1
    assert again["positions"] == {}


def test_fresh_source_close_exits_without_300_second_wait(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312)
    opening = paper.step(at(313))
    assert D(opening["positions"][BTC.key]) > 0
    add_quote(tape, 319)
    add_source(tape, 2, 319, {})
    closed = paper.step(at(322))
    assert closed["positions"] == {}
    assert closed["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert closed["unresolved_exposures"] == {}
    assert len(entry_attempts(paper)) == 1
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1
    restarted = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="single_attempt",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    assert restarted.run.account.snapshot() == paper.run.account.snapshot()
    assert restarted.step(at(323))["positions"] == {}


def test_pod_drawdown_halt_closes_actual_inventory_without_new_source(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="risk_exit")
    add_source(tape, 1, 12, {BTC.key: "200"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    opened = paper.step(at(313))
    assert D(opened["positions"][BTC.key]) == D("5.64")

    native = parse_ccxt_market(RAW_MARKET, first_known_at=at(1), expected=BTC)
    dropped = parse_ccxt_book(
        native,
        {
            "symbol": RAW_MARKET["symbol"],
            "timestamp": int((T + timedelta(seconds=320)).timestamp() * 1000),
            "bids": [[40, 200]],
            "asks": [[40.2, 200]],
        },
        first_known_at=at(321),
    )
    tape.append_market_quote(dropped.payload())
    stopped = paper.step(at(322))
    assert stopped["pod_risk"]["S035"]["state"] == "SUSPENDED"
    assert stopped["pending_exits"]["S035"]["reason"] == "POD_RISK_LATCHED"
    assert stopped["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert stopped["positions"] == {}
    assert stopped["execution_results"] == {}
    assert stopped["unresolved_exposures"] == {}
    assert len(entry_attempts(paper)) == 1
    paper.step(at(323))
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1


def test_risk_latch_overrides_terminal_failed_source_exit_once(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="risk_after_unfilled_exit")
    add_source(tape, 1, 12, {BTC.key: "200"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    opened = paper.step(at(313))
    assert D(opened["positions"][BTC.key]) == D("5.64")

    add_quote(tape, 319, size=0.01)
    add_source(tape, 2, 319, {BTC.key: "100"})
    rejected = paper.step(at(321))
    failed_id = rejected["pending_exits"]["S035"]["exit_id"]
    assert rejected["pending_exits"]["S035"]["status"] == "UNRESOLVED_EXPOSURE"
    assert D(rejected["positions"][BTC.key]) == D("5.64")

    market = parse_ccxt_market(RAW_MARKET, first_known_at=at(1), expected=BTC)
    dropped = parse_ccxt_book(
        market,
        {
            "symbol": RAW_MARKET["symbol"],
            "timestamp": int((T + timedelta(seconds=329)).timestamp() * 1000),
            "bids": [[40, 200]],
            "asks": [[40.2, 200]],
        },
        first_known_at=at(330),
    )
    tape.append_market_quote(dropped.payload())
    stopped = paper.step(at(331))
    assert stopped["pod_risk"]["S035"]["state"] == "SUSPENDED"
    assert stopped["positions"] == {}
    assert stopped["pending_exits"]["S035"]["reason"] == "POD_RISK_LATCHED"
    assert stopped["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert stopped["pending_exits"]["S035"]["exit_id"] != failed_id
    assert stopped["unresolved_exposures"] == {}
    history = paper.run.account.pm04_state["paper_execution"]["exit_history"]
    assert history[failed_id]["status"] == "UNRESOLVED_EXPOSURE"
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 2
    paper.step(at(333))
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 2


def test_failed_exit_remains_unresolved_real_paper_liability(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312)
    paper.step(at(313))
    add_source(tape, 2, 339, {})
    pending = paper.step(at(345))
    assert D(pending["positions"][BTC.key]) > 0
    expired = paper.step(at(372))
    assert expired["pending_exits"]["S035"]["status"] == "UNRESOLVED_EXPOSURE"
    assert D(expired["unresolved_exposures"]["S035"][BTC.key]) > 0
    assert D(expired["positions"][BTC.key]) > 0


def test_exit_one_full_market_order_not_separate_fill_groups(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="exit_order")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    opening = paper.step(at(313))
    assert D(opening["positions"][BTC.key]) == D("0.564")

    native = parse_ccxt_market(RAW_MARKET, first_known_at=at(1), expected=BTC)
    book = parse_ccxt_book(
        native,
        {
            "symbol": RAW_MARKET["symbol"],
            "timestamp": int((T + timedelta(seconds=319)).timestamp() * 1000),
            "bids": [[100, 0.1], [99.5, 10]],
            "asks": [[101, 10], [102, 10]],
        },
        first_known_at=at(320),
    )
    tape.append_market_quote(book.payload())
    add_source(tape, 2, 319, {})
    close = paper.step(at(321))
    assert close["positions"] == {}
    exits = [r["event"] for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]
    assert len(exits) == 1
    outcome = close["execution_outcomes"][close["pending_exits"]["S035"]["exit_id"]]
    order = outcome[BTC.key]
    assert D(order["requested"]) == D("-0.564")
    assert order["status"] == "FILLED"
    assert len(order["fills"]) == 2
    assert sum((D(x["quantity"]) for x in order["fills"]), D("0")) == D("-0.564")
    assert D(order["fee"]) > 0
    assert close["pending_exits"]["S035"]["attempted_at"] == at(321)
    assert close["pending_exits"]["S035"]["terminal_at"] == at(321)
    assert close["real_broker_fills"] == 0

    add_quote(tape, 330, size=200)
    assert paper.step(at(331))["positions"] == {}
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1
    restarted = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="exit_order",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    assert restarted.run.account.snapshot() == paper.run.account.snapshot()


def test_short_cover_is_one_immediate_ask_side_market_order(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="short_cover")
    add_source(tape, 1, 12, {BTC.key: "-20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    opened = paper.step(at(313))
    assert D(opened["positions"][BTC.key]) == D("-0.564")
    add_quote(tape, 319, size=200)
    add_source(tape, 2, 319, {})
    covered = paper.step(at(321))
    assert covered["positions"] == {}
    exit_row = covered["pending_exits"]["S035"]
    order = covered["execution_outcomes"][exit_row["exit_id"]][BTC.key]
    assert exit_row["status"] == "EXIT_FILLED"
    assert D(order["requested"]) == D("0.564")
    assert D(order["vwap"]) > D("101")
    assert len(order["fills"]) == 1
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1
    assert paper.run.restore()["account"] == paper.run.account.snapshot()


def test_partial_leader_reduction_is_one_exit_without_delayed_rebalance(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="partial_reduce")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    paper.step(at(313))
    add_quote(tape, 319, size=200)
    add_source(tape, 2, 319, {BTC.key: "10"})
    reduced = paper.step(at(321))
    assert D(reduced["positions"][BTC.key]) == D("0.282")
    assert reduced["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert reduced["execution_intents"]["S035"]["status"] == "FILLED"
    order = reduced["execution_outcomes"][reduced["pending_exits"]["S035"]["exit_id"]][BTC.key]
    assert D(order["requested"]) == D("-0.282")
    assert D(order["quantity"]) == D("-0.282")
    add_quote(tape, 700, size=200)
    after = paper.step(at(701))
    assert D(after["positions"][BTC.key]) == D("0.282")
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1
    assert len(entry_attempts(paper)) == 1


def test_two_distinct_exit_signals_cannot_reuse_same_displayed_bid_depth(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="same_book_no_double_sell")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    paper.step(at(313))

    add_quote(tape, 319, size=200)
    add_source(tape, 2, 319, {BTC.key: "15"})
    first = paper.step(at(321))
    assert D(first["positions"][BTC.key]) == D("0.423")
    first_exit_id = first["pending_exits"]["S035"]["exit_id"]
    assert first["pending_exits"]["S035"]["status"] == "EXIT_FILLED"

    # A newer leader reduction is distinct, but the same observed bid
    # liquidity cannot be sold a second time without a new quote receipt.
    add_source(tape, 3, 322, {BTC.key: "10"})
    second = paper.step(at(324))
    second_exit_id = second["pending_exits"]["S035"]["exit_id"]
    assert second_exit_id != first_exit_id
    assert second["execution_outcomes"][second_exit_id][BTC.key]["status"] == (
        "REJECTED_REUSED_L2_QUOTE"
    )
    assert second["pending_exits"]["S035"]["status"] == "UNRESOLVED_EXPOSURE"
    assert D(second["positions"][BTC.key]) == D("0.423")
    add_quote(tape, 329, size=200)
    later = paper.step(at(331))
    assert D(later["positions"][BTC.key]) == D("0.423")
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 2


def test_pending_exit_canceled_if_leader_restores_size_before_quote(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="cancel_exit")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    paper.step(at(313))
    add_source(tape, 2, 345, {BTC.key: "10"})
    first = paper.step(at(347))
    assert first["pending_exits"]["S035"]["status"] == "PENDING_EXIT"
    add_source(tape, 3, 350, {BTC.key: "20"})
    restored = paper.step(at(353))
    assert restored["pending_exits"]["S035"]["status"] == "CANCELED_SOURCE_RESTORED"
    add_quote(tape, 355, size=200)
    later = paper.step(at(357))
    assert D(later["positions"][BTC.key]) == D("0.564")
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 0


def test_genuinely_new_source_reduction_can_create_new_terminal_exit(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="new_exit_signal")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    paper.step(at(313))
    add_quote(tape, 319, size=0.01)
    add_source(tape, 2, 319, {BTC.key: "10"})
    failed = paper.step(at(321))
    first_id = failed["pending_exits"]["S035"]["exit_id"]
    assert failed["pending_exits"]["S035"]["status"] == "UNRESOLVED_EXPOSURE"
    add_quote(tape, 326, size=200)
    add_source(tape, 3, 326, {})
    closed = paper.step(at(328))
    assert closed["positions"] == {}
    assert closed["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert closed["pending_exits"]["S035"]["exit_id"] != first_id
    history = paper.run.account.pm04_state["paper_execution"]["exit_history"]
    assert history[first_id]["status"] == "UNRESOLVED_EXPOSURE"
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 2


def test_exit_does_not_retry_on_new_source_increase_below_stale_actual(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="no_exit_chasing")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    assert D(paper.step(at(313))["positions"][BTC.key]) == D("0.564")
    add_quote(tape, 319, size=0.01)
    add_source(tape, 2, 319, {BTC.key: "10"})
    unsuccessful = paper.step(at(321))
    assert unsuccessful["pending_exits"]["S035"]["status"] == "UNRESOLVED_EXPOSURE"
    assert D(unsuccessful["positions"][BTC.key]) == D("0.564")
    first_id = unsuccessful["pending_exits"]["S035"]["exit_id"]
    assert unsuccessful["execution_intents"]["S035"]["status"] == "FILLED"

    # This is a genuine newer receipt, but NOT a new reduction by the leader.
    add_quote(tape, 326, size=200)
    add_source(tape, 3, 326, {BTC.key: "15"})
    after = paper.step(at(328))
    assert after["pending_exits"]["S035"]["exit_id"] == first_id
    assert after["pending_exits"]["S035"]["status"] == "UNRESOLVED_EXPOSURE"
    assert D(after["positions"][BTC.key]) == D("0.564")
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1


def test_two_exit_updates_before_a_quote_preserve_original_once_only_opportunity(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    paper = new_paper(tmp_path, tape, run_id="coalesced_exit")
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312, size=200)
    paper.step(at(313))

    add_source(tape, 2, 345, {BTC.key: "10"})
    first = paper.step(at(347))
    assert first["pending_exits"]["S035"]["status"] == "PENDING_EXIT"
    first_id = first["pending_exits"]["S035"]["exit_id"]
    first_deadline = first["pending_exits"]["S035"]["deadline_at"]
    add_source(tape, 3, 350, {})
    second = paper.step(at(353))
    assert second["pending_exits"]["S035"]["status"] == "PENDING_EXIT"
    assert second["pending_exits"]["S035"]["exit_id"] == first_id
    assert second["pending_exits"]["S035"]["deadline_at"] == first_deadline
    assert second["pending_exits"]["S035"]["source_seq"] == 3
    add_quote(tape, 355, size=200)
    closed = paper.step(at(357))
    assert closed["positions"] == {}
    assert closed["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1


def test_single_market_intent_can_use_multiple_book_levels_with_vwap():
    model = SingleShotMarketExecutionModel(taker_fee_bps=D("5"), extra_slippage_bps=D("0"))
    book = {
        "best_bid": "99",
        "bid_size": "1",
        "best_ask": "101",
        "ask_size": "0.2",
        "ask_levels": [["101", "0.2"], ["102", "0.8"], ["103", "1.0"]],
        "bid_levels": [["99", "0.2"], ["98", "0.8"], ["97", "1.0"]],
    }
    bought = model.price(D("1"), book, step=D("0.1"), minimum_notional=D("1"))
    assert bought["status"] == "FILLED"
    assert len(bought["fills"]) == 2
    assert D(bought["vwap"]) == D("101.8")
    assert D(bought["fee"]) == D("0.0509")
    sold = model.price(D("-1"), book, step=D("0.1"), minimum_notional=D("1"))
    assert D(sold["vwap"]) == D("98.2")
    assert len(sold["fills"]) == 2
    too_large = model.price(D("3"), book, step=D("0.1"), minimum_notional=D("1"))
    assert too_large["status"] == "UNPRICEABLE_MARKET_ORDER"
    assert "fills" not in too_large


def test_observed_multilevel_book_preserves_depth_integrity_and_prices_vwap(tmp_path):
    market = parse_ccxt_market(RAW_MARKET, first_known_at=at(1), expected=BTC)
    quote = parse_ccxt_book(
        market,
        {
            "symbol": RAW_MARKET["symbol"],
            "timestamp": int((T + timedelta(seconds=10)).timestamp() * 1000),
            "bids": [[100, 0.1], [99, 20]],
            "asks": [[101, 0.1], [102, 20]],
        },
        first_known_at=at(11),
    )
    tape = PaperJournal(tmp_path / "depth")
    tape.append_market_quote(quote.payload())
    assert quote.payload()["ask_levels"] == [["101", "0.1"], ["102", "20"]]
    model = SingleShotMarketExecutionModel(extra_slippage_bps=D("0"))
    priced = model.price(D("1"), quote.payload(), step=D("0.1"), minimum_notional=D("1"))
    assert priced["status"] == "FILLED"
    assert D(priced["vwap"]) == D("101.9")


def test_invalid_lot_and_depth_fail_closed_without_fabricated_partial():
    model = SingleShotMarketExecutionModel()
    book = {"best_ask": "101", "ask_size": "0.2", "best_bid": "99", "bid_size": "0.2"}
    assert (
        model.price(D("1"), book, step=D("0.1"), minimum_notional=D("1"))["status"]
        == "UNPRICEABLE_MARKET_ORDER"
    )
    assert (
        model.price(D("0.25"), book, step=D("0.1"), minimum_notional=D("1"))["status"]
        == "REJECTED_NATIVE_STEP"
    )
    assert (
        model.price(D("0.1"), book, step=D("0.1"), minimum_notional=D("100"))["status"]
        == "REJECTED_MIN_NOTIONAL"
    )
    corrupted = {**book, "ask_levels": [["102", "200"]]}
    assert (
        model.price(D("1"), corrupted, step=D("0.1"), minimum_notional=D("1"))["status"]
        == "UNPRICEABLE_MARKET_ORDER"
    )


def test_due_intent_restart_is_executed_exactly_once(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    restarted = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="single_attempt",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    add_quote(tape, 312)
    assert D(restarted.step(at(313))["positions"][BTC.key]) == D("0.564")
    completed = ObservedP1Paper(
        source_db=tape.path,
        state_root=tmp_path / "private",
        run_id="single_attempt",
        registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    completed.step(at(320))
    assert len(entry_attempts(completed)) == 1
    assert D(completed.run.account.quantities[BTC]) == D("0.564")
