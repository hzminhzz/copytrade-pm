"""Fixture-only engineering acceptance for the Combo 2 paper core."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_combo2 import Combo2PaperTracker, _round_zero

BASE = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
BTC = "hyperliquid/mainnet:perp:default/BTC"
OTHER = "hyperliquid/mainnet:perp:default/ETH"
IDS = {"W028": "a" * 64, "CA-008": "b" * 64, "W015": "c" * 64}


def time(seconds=0):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def quote(
    seconds=300,
    mark="100000",
    *,
    lot="0.0000001",
    capacity="1000",
    supported=True,
    open_market=True,
):
    return {
        "first_known_at": time(seconds),
        "mark": mark,
        "lot": lot,
        "minimum": lot,
        "volume_base": capacity,
        "fee_bps": "0",
        "spread_bps": "0",
        "slippage_bps": "0",
        "session_open": open_market,
        "supported": supported,
        "native_market_id": "BTC-PERP",
    }


def source(
    manager="W028",
    *,
    seconds=300,
    equity="100000",
    quantity="3",
    mark="100000",
    complete=True,
    extra=None,
):
    positions = {BTC: {"quantity": quantity, "mark": mark}}
    positions.update(extra or {})
    return {
        "manager": manager,
        "subject_sha": IDS[manager],
        "quality": "OFFICIAL_ALL_DEXS_READ_ONLY",
        "full_book": complete,
        "all_dexes_complete": complete,
        "equity": equity,
        "positions": positions,
        "event_at": time(seconds),
        "first_known_at": time(seconds),
    }


def tracker(tmp_path):
    return Combo2PaperTracker(
        tmp_path, run_id="fixture", started_at=time(), source_subject_hashes=IDS
    )


def receipt(engine, manager="W028", *, instrument=BTC, eid="r1", sec=0):
    return engine.record(
        kind="SOURCE_RECEIPT",
        event_id=eid,
        source_event_at=time(sec),
        first_known_at=time(sec),
        decision_at=time(sec),
        hypothetical_fill_at=time(sec),
        data={"manager": manager, "instrument": instrument},
    )


def rebalance(engine, *, eid="d1", seconds=300, sources=None, markets=None, shocks=None, hedge="0"):
    return engine.record(
        kind="PAPER_REBALANCE",
        event_id=eid,
        source_event_at=time(0),
        first_known_at=time(seconds),
        decision_at=time(seconds),
        hypothetical_fill_at=time(seconds),
        data={
            "leaders": sources if sources is not None else {"W028": source(seconds=seconds)},
            "markets": markets if markets is not None else {BTC: quote(seconds)},
            "shocks": shocks if shocks is not None else [{BTC: "-0.01"}],
            "hedge_break_loss": hedge,
        },
    )


def mark(engine, *, eid="m1", seconds=360, price="90000"):
    return engine.record(
        kind="PAPER_MARK",
        event_id=eid,
        source_event_at=time(seconds),
        first_known_at=time(seconds),
        decision_at=time(seconds),
        hypothetical_fill_at=time(seconds),
        data={"markets": {BTC: quote(seconds, mark=price)}},
    )


def test_equity_leverage_gross_cap_and_replay(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    with pytest.raises(ValueError, match="NO_DUE"):
        rebalance(engine, seconds=299)
    result = rebalance(engine)
    report = result["meta"]["last_report"]
    assert D(report["desired"]["W028"][BTC]) == D(".03")
    assert D(report["allowed"]["W028"][BTC]) == D(".0125")
    assert report["portfolio_clamp_factor"] == "1"
    assert D(result["account"]["quantities"][BTC]) == D(".0125")
    assert D(result["account"]["equity"]) == D("5000")
    assert report["actions"][0]["hypothetical"] is True
    assert engine.state()["live_trading_authorized"] is False
    assert (
        Combo2PaperTracker(
            tmp_path, run_id="fixture", started_at=time(), source_subject_hashes=IDS
        ).state()
        == result
    )
    assert _round_zero(D("-1.25"), D("0.1")) == D("-1.2")


def test_no_duplicate_source_receipt_or_duplicate_paper_order(tmp_path):
    engine = tracker(tmp_path)
    first = receipt(engine)
    assert receipt(engine) == first
    rebalance(engine)
    with pytest.raises(ValueError, match="NO_DUE"):
        rebalance(engine, eid="second", seconds=400)
    assert len(engine.ledger.read()) == 2


def test_invalid_coherent_source_fails_atomically(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    before = engine.state()
    with pytest.raises(ValueError, match="SOURCE_EQUITY_NONPOSITIVE"):
        rebalance(engine, sources={"W028": source(equity="0")})
    assert engine.state() == before
    assert len(engine.ledger.read()) == 1
    with pytest.raises(ValueError, match="INCOMPLETE_SOURCE_BOOK"):
        rebalance(engine, sources={"W028": source(complete=False)})
    assert engine.state() == before


def test_two_opposing_managers_are_gross_clamped_before_zero_net(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine, manager="W028", eid="r1")
    receipt(engine, manager="W015", eid="r2")
    state = rebalance(
        engine,
        sources={
            "W028": source(quantity="1"),
            "W015": source("W015", quantity="-1"),
        },
        hedge="1",
        shocks=[{}],
    )
    report = state["meta"]["last_report"]
    assert D(report["coin_clamp_factors"][BTC]) == D(".625")
    assert D(state["account"]["quantities"].get(BTC, "0")) == D("0")
    assert D(state["account"]["pm_quantities"]["W028"][BTC]) == D(".00625")
    assert D(state["account"]["pm_quantities"]["W015"][BTC]) == D("-.00625")
    assert any(a["kind"] == "INTERNAL_CROSS" for a in report["actions"])
    assert sum(D(x) for x in state["account"]["pm_cash"].values()) == 0


def test_minimum_opening_and_reducible_dust(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    state = rebalance(
        engine,
        sources={"W028": source(quantity="0.00999")},
        markets={BTC: quote()},
        shocks=[{BTC: "-0.01"}],
    )
    assert not state["account"]["quantities"]
    assert state["meta"]["last_report"]["actions"][0]["status"] == "MIN_NOTIONAL"


def test_circuit_freeze_latches_even_after_mark_recovers_and_restart(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    rebalance(engine)
    state = mark(engine)
    assert state["account"]["equity"] == "4875.0000000"
    assert state["meta"]["frozen_daily_key"] == "2026-11-02"
    assert state["meta"]["status"] == "FROZEN"
    mark(engine, eid="m2", seconds=370, price="100000")
    assert engine.state()["meta"]["status"] == "FROZEN"
    restored = Combo2PaperTracker(
        tmp_path, run_id="fixture", started_at=time(), source_subject_hashes=IDS
    )
    assert restored.state() == engine.state()


def test_new_risk_needs_complete_stress_scenarios(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    with pytest.raises(ValueError, match="MISSING_STRESS_SCENARIOS"):
        rebalance(engine, shocks=[])
    assert len(engine.ledger.read()) == 1


def test_missing_instrument_fails_closed_with_partial_book_flag(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    state = rebalance(
        engine, sources={"W028": source(extra={OTHER: {"quantity": "5", "mark": "2000"}})}
    )
    assert state["meta"]["last_report"]["partial_book"]
    assert OTHER in state["meta"]["last_report"]["skipped_unlisted"]


def test_authoritative_source_hash_and_manifest_cannot_change(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    with pytest.raises(ValueError, match="IMMUTABLE_FILE_CONFLICT"):
        Combo2PaperTracker(
            tmp_path,
            run_id="fixture",
            started_at=time(),
            source_subject_hashes={"W028": "0" * 64, "CA-008": "b" * 64, "W015": "c" * 64},
        )
    assert engine.state()["paper_only"]


def test_intrabar_adverse_touch_latches_even_when_mark_recovers(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    rebalance(engine)
    row = quote(360)
    row["adverse_low"] = "90000"
    row["adverse_high"] = "100000"
    state = engine.record(
        kind="PAPER_MARK",
        event_id="adverse",
        source_event_at=time(360),
        first_known_at=time(360),
        decision_at=time(360),
        hypothetical_fill_at=time(360),
        data={"markets": {BTC: row}},
    )
    assert state["account"]["equity"] == "5000.0000000"
    assert state["meta"]["status"] == "FROZEN"
    assert state["meta"]["halt_reason"] == "PAPER_DAILY_SOFT_80_PERCENT"


def test_reversal_is_two_separate_hypothetical_legs(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    rebalance(engine)
    receipt(engine, eid="new-short", sec=360)
    state = rebalance(
        engine,
        eid="flip",
        seconds=660,
        sources={"W028": source(seconds=660, quantity="-3")},
        markets={BTC: quote(660)},
        shocks=[{BTC: "0.01"}],
    )
    assert D(state["account"]["quantities"][BTC]) == D("-.0125")
    actions = state["meta"]["last_report"]["actions"]
    external = [a for a in actions if a["kind"] == "EXTERNAL_PAPER"]
    assert len(external) == 2
    assert [D(a["quantity"]) for a in external] == [D("-.0125"), D("-.0125")]


def test_crash_fault_and_corrupted_journal_detected(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    path = engine.ledger.events_path
    with path.open("ab") as stream:
        stream.write(b"partial")
    with pytest.raises(ValueError, match="TRUNCATED_EVENT_TAIL"):
        engine.restore()
