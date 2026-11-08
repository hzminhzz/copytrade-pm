"""Vike estimated minute-price path through the existing PM03 ledger."""
from datetime import timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_vike_minute import minute_observation
from test_pm_forward_observed_paper import BTC, RAW_MARKET, T, add_source, at, registry


def price(tape, seconds, *, volume=1000):
    started = (T + timedelta(seconds=seconds)).replace(second=0, microsecond=0)
    row = {
        "ts": int(started.timestamp() * 1000), "symbol": "BTC", "dex": "HL",
        "kind": "perp", "open": 100, "high": 102, "low": 99,
        "close": 101, "volume": volume, "volume_usd": volume * 101,
        "n_trades": 50 if volume else 0,
    }
    observation = minute_observation(row, received_at=at(seconds))
    return tape.append_vike_minute(observation)


def new_paper(tmp_path, source, prices, *, run_id="vike_estimated"):
    return ObservedP1Paper(
        source_db=source.path, price_db=prices.path,
        price_mode="vike_minute",
        registry_db=registry(tmp_path / "registry.sqlite"),
        state_root=tmp_path / "vike_virtual", run_id=run_id,
        catalog={RAW_MARKET["symbol"]: RAW_MARKET}, started_at=at(0),
    )


def test_vike_minute_new_campaign_entry_exit_and_restart(tmp_path):
    source = PaperJournal(tmp_path / "source")
    market = PaperJournal(tmp_path / "price")
    price(market, 10)
    paper = new_paper(tmp_path, source, market)
    add_source(source, 1, 12, {BTC.key: "20"})
    pending = paper.step(at(14))
    assert pending["execution_intents"]["S035"]["due_at"] == at(313)
    assert pending["schema"].endswith("_v4")
    assert pending["positions"] == {}

    price(market, 312)
    opened = paper.step(at(313))
    assert D(opened["positions"][BTC.key]) == D("0.564")
    attempt = opened["execution_outcomes"][opened["execution_intents"]["S035"]["intent_id"]]
    assert attempt[BTC.key]["execution_evidence"] == "ESTIMATED_EXECUTION"
    assert attempt[BTC.key]["real_order_count"] == 0
    assert paper.step(at(315))["positions"] == opened["positions"]

    price(market, 319)
    add_source(source, 2, 319, {})
    closed = paper.step(at(322))
    assert closed["positions"] == {}
    assert closed["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert closed["real_broker_fills"] == 0
    assert closed["order_route"] == "NONE"

    restored = ObservedP1Paper(
        source_db=source.path, price_db=market.path, price_mode="vike_minute",
        registry_db=tmp_path / "registry.sqlite",
        state_root=tmp_path / "vike_virtual", run_id="vike_estimated",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    assert restored.run.account.snapshot() == paper.run.account.snapshot()
    with pytest.raises(ValueError, match="POLICY_DRIFT"):
        ObservedP1Paper(
            source_db=source.path, registry_db=tmp_path / "registry.sqlite",
            state_root=tmp_path / "vike_virtual", run_id="vike_estimated",
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        )


def test_vike_minute_duplicate_and_clock_regression_are_rejected(tmp_path):
    market = PaperJournal(tmp_path / "price")
    assert price(market, 312)["status"] == "RECORDED_ESTIMATED_PRICE_ONLY"
    assert price(market, 312)["status"] == "DUPLICATE_VIKE_MINUTE"
    with pytest.raises(ValueError, match="CLOCK_REGRESSION"):
        price(market, 10)


def test_vike_paper_cannot_run_without_independent_price_journal(tmp_path):
    source = PaperJournal(tmp_path / "source")
    with pytest.raises(ValueError, match="ISOLATED_PRICE_JOURNAL"):
        ObservedP1Paper(
            source_db=source.path, price_mode="vike_minute",
            state_root=tmp_path / "campaign", run_id="vike",
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        )
