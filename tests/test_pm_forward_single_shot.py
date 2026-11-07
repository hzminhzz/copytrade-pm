"""Forward-paper bounded execution: test observable ledger and account outcomes."""

from datetime import timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper, _exclusive_runner
from copytrade_pm.pm_forward_single_shot import SingleShotMarketExecutionModel
from test_pm_forward_observed_paper import (
    BTC, RAW_MARKET, T, add_quote, add_source, at, registry,
)


def new_paper(tmp_path, tape, *, run_id="single_attempt"):
    return ObservedP1Paper(
        source_db=tape.path, state_root=tmp_path / "private",
        run_id=run_id, registry_db=registry(tmp_path / "registry.sqlite"),
        catalog={RAW_MARKET["symbol"]: RAW_MARKET}, started_at=at(0),
    )


def entry_attempts(paper):
    return [
        r["event"] for r in paper.run.ledger.read()
        if r["event"]["kind"] == "PM04_PAPER_EXECUTE"
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
    assert len([r for r in paper.run.ledger.read()
                if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1
    restarted = ObservedP1Paper(
        source_db=tape.path, state_root=tmp_path / "private",
        run_id="single_attempt", registry_db=tmp_path / "registry.sqlite",
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
    assert len([r for r in paper.run.ledger.read()
                if r["event"]["kind"] == "PM04_PAPER_EXIT"]) == 1


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


def test_single_market_intent_can_use_multiple_book_levels_with_vwap():
    model = SingleShotMarketExecutionModel(
        taker_fee_bps=D("5"), extra_slippage_bps=D("0")
    )
    book = {
        "best_bid": "99", "bid_size": "1",
        "best_ask": "101", "ask_size": "0.2",
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
    priced = model.price(D("1"), quote.payload(), step=D("0.1"),
                         minimum_notional=D("1"))
    assert priced["status"] == "FILLED"
    assert D(priced["vwap"]) == D("101.9")


def test_invalid_lot_and_depth_fail_closed_without_fabricated_partial():
    model = SingleShotMarketExecutionModel()
    book = {"best_ask": "101", "ask_size": "0.2",
            "best_bid": "99", "bid_size": "0.2"}
    assert model.price(D("1"), book, step=D("0.1"),
                       minimum_notional=D("1"))["status"] == "UNPRICEABLE_MARKET_ORDER"
    assert model.price(D("0.25"), book, step=D("0.1"),
                       minimum_notional=D("1"))["status"] == "REJECTED_NATIVE_STEP"
    assert model.price(D("0.1"), book, step=D("0.1"),
                       minimum_notional=D("100"))["status"] == "REJECTED_MIN_NOTIONAL"
    corrupted = {**book, "ask_levels": [["102", "200"]]}
    assert model.price(D("1"), corrupted, step=D("0.1"),
                       minimum_notional=D("1"))["status"] == "UNPRICEABLE_MARKET_ORDER"


def test_due_intent_restart_is_executed_exactly_once(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    restarted = ObservedP1Paper(
        source_db=tape.path, state_root=tmp_path / "private",
        run_id="single_attempt", registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    add_quote(tape, 312)
    assert D(restarted.step(at(313))["positions"][BTC.key]) == D("0.564")
    completed = ObservedP1Paper(
        source_db=tape.path, state_root=tmp_path / "private",
        run_id="single_attempt", registry_db=tmp_path / "registry.sqlite",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    completed.step(at(320))
    assert len(entry_attempts(completed)) == 1
    assert D(completed.run.account.quantities[BTC]) == D("0.564")
