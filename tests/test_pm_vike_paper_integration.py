"""Vike estimated minute-price path through the existing PM03 ledger."""

from datetime import timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_vike_minute import minute_observation
from copytrade_pm.pm_vike_market_catalog import NativePaperContract
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from test_pm_forward_observed_paper import (
    ADDRESSES,
    BTC,
    RAW_MARKET,
    T,
    add_source,
    at,
    registry,
)


def price(tape, seconds, *, volume=1000):
    started = (T + timedelta(seconds=seconds)).replace(second=0, microsecond=0)
    row = {
        "ts": int(started.timestamp() * 1000),
        "symbol": "BTC",
        "dex": "HL",
        "kind": "perp",
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": volume,
        "volume_usd": volume * 101,
        "n_trades": 50 if volume else 0,
    }
    observation = minute_observation(row, received_at=at(seconds))
    return tape.append_vike_minute(observation)


def new_paper(tmp_path, source, prices, *, run_id="vike_estimated"):
    return ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        registry_db=registry(tmp_path / "registry.sqlite"),
        state_root=tmp_path / "vike_virtual",
        run_id=run_id,
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        started_at=at(0),
    )


def official_frame(seconds, quantity):
    positions = [{"position": {"coin": "BTC", "szi": str(quantity)}}] if quantity else []
    return {
        "channel": "allDexsClearinghouseState",
        "data": {
            "user": ADDRESSES["S035"],
            "clearinghouseStates": [
                [
                    "",
                    {
                        "marginSummary": {
                            "accountValue": "100",
                            "totalNtlPos": "100",
                            "totalMarginUsed": "10",
                        },
                        "assetPositions": positions,
                        "time": int((T + timedelta(seconds=seconds)).timestamp() * 1000),
                    },
                ],
            ],
        },
    }


def official_observer(source):
    obs = PersistentAccount(
        journal=source,
        alias="S035",
        address=ADDRESSES["S035"],
        dex_catalog=[None],
        subaccounts=None,
        parent_alias="S035",
        scope_sha=digest(["S035", "default"]),
    )
    obs.begin(at(0))
    obs.observe(official_frame(1, 0), at(2))
    return obs


def test_future_fixed_k_requires_official_position_value_and_distinct_follower_quote(
    tmp_path, monkeypatch
):
    """A self-hashed mark is insufficient; the official stream link must verify."""
    source = PaperJournal(tmp_path / "official_source")
    prices = PaperJournal(tmp_path / "prices")
    native = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "forward_official",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="future_price_proof",
        catalog={},
        native_contracts={BTC.key: native},
        started_at=at(0),
        source_mark_age_seconds=600,  # synthetic venue cutoff, not production-authorized
    )
    official = official_observer(source)
    frame = official_frame(12, 20)
    frame["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["positionValue"] = (
        "2400"
    )
    observed = official.observe(frame, at(13))
    assert observed["classification"] == "OBSERVED_STATE_CHANGE"
    assert paper.step(at(14))["quantity_count"] == 0
    price(prices, 312)
    # Adversarial locally hashable attempt: the durable reducer must
    # independently recompute the native fixed-k quantity before commit.
    from copy import deepcopy
    from dataclasses import replace

    previous_record = paper.run.record

    def forged_follower_target(event):
        if event.kind == "PM04_PAPER_EXECUTE":
            payload = deepcopy(event.payload)
            payload["input"]["targets"][BTC.key] = "999"
            return previous_record(replace(event, payload=payload))
        return previous_record(event)

    with monkeypatch.context() as scope:
        scope.setattr(paper.run, "record", forged_follower_target)
        with pytest.raises(ValueError, match="PAPER_NATIVE_PRICE_TARGET_MISMATCH"):
            paper.step(at(313))
    assert not any(row["event"]["kind"] == "PM04_PAPER_EXECUTE" for row in paper.run.ledger.read())
    opened = paper.step(at(313))
    assert opened["quantity_count"] == 1
    events = [
        row["event"]
        for row in paper.run.ledger.read()
        if row["event"]["kind"] == "PM04_PAPER_EXECUTE"
    ]
    assert len(events) == 1
    effect = events[0]["payload"]["input"]
    assert D(effect["native_source_price_proof"]["marks"][BTC.key]) == D("120")
    assert D(effect["quotes"][BTC.key]["mid_quote"]) != D("120")
    assert effect["decision_source_chain_sha"]
    assert effect["decision_cutoff"] == at(313)
    assert effect["decision_source_first_known_at"] == at(13)
    assert D(opened["positions"][BTC.key]) > D("0.60")
    assert opened["order_route"] == "NONE"

    unpriced = PaperJournal(tmp_path / "unpriced_source")
    prices_unpriced = PaperJournal(tmp_path / "unpriced_prices")
    observer = official_observer(unpriced)
    observer.observe(official_frame(12, 20), at(13))
    blocked_paper = ObservedP1Paper(
        source_db=unpriced.path,
        price_db=prices_unpriced.path,
        price_mode="vike_minute",
        state_root=tmp_path / "unpriced_forward",
        registry_db=tmp_path / "registry.sqlite",
        run_id="future_missing_native_mark",
        catalog={},
        native_contracts={BTC.key: native},
        started_at=at(0),
        source_mark_age_seconds=600,
    )
    blocked_paper.step(at(14))
    price(prices_unpriced, 312)
    blocked = blocked_paper.step(at(313))
    assert "SOURCE_MARK_EVIDENCE_MISSING" in str(blocked["execution_results"])
    assert blocked["quantity_count"] == 0


def test_v4_native_catalog_freezes_quiet_market_before_first_price(tmp_path):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    native = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "v4_native",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="quiet_then_live",
        catalog={},
        native_contracts={BTC.key: native},
        started_at=at(0),
    )
    assert BTC in paper.run.account.rulebook.permitted
    official = official_observer(source)
    transition = official.observe(official_frame(12, 20), at(13))
    assert transition["classification"] == "OBSERVED_STATE_CHANGE"
    pending = paper.step(at(14))
    assert pending["execution_intents"]["S035"]["due_at"] == at(313)
    assert pending["quantity_count"] == 0
    assert pending["tick"] == "NO_ACTIVE_TARGETS"
    price(prices, 312)
    opened = paper.step(at(313))
    assert D(opened["positions"][BTC.key]) == D("0.564")
    assert opened["execution_intents"]["S035"]["status"] == "FILLED"
    assert opened["real_broker_fills"] == 0
    assert opened["order_route"] == "NONE"
    # A verified official position reduction bypasses the 300s entry delay.
    price(prices, 319)
    official.observe(official_frame(319, 0), at(320))
    closed = paper.step(at(321))
    assert closed["positions"] == {}
    assert closed["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
    assert closed["real_broker_fills"] == 0
    # Exact catalog and risk manifest must replay after restart.
    restored = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "v4_native",
        registry_db=tmp_path / "registry.sqlite",
        run_id="quiet_then_live",
        catalog={},
        native_contracts={BTC.key: native},
    )
    assert restored.run.account.snapshot() == paper.run.account.snapshot()
    changed_contract = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.01"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["changed", BTC.key]),
        hip3=False,
    )
    with pytest.raises(ValueError, match="NATIVE_CONTRACT_METADATA_DRIFT"):
        ObservedP1Paper(
            source_db=source.path,
            price_db=prices.path,
            price_mode="vike_minute",
            state_root=tmp_path / "v4_native",
            registry_db=tmp_path / "registry.sqlite",
            run_id="quiet_then_live",
            catalog={},
            native_contracts={BTC.key: changed_contract},
        )


def test_v4_gap_cancels_pending_risk_without_inventing_flat(tmp_path):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    official = official_observer(source)
    official.observe(official_frame(12, 20), at(13))
    contract = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "native",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="gap_recovery",
        catalog={},
        native_contracts={BTC.key: contract},
        started_at=at(0),
    )
    first = paper.step(at(14))
    assert first["execution_intents"]["S035"]["due_at"] == at(313)
    official.gap(at(200), "SIMULATED_SOCKET_LOSS")
    price(prices, 312)
    canceled = paper.step(at(313))
    assert canceled["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert canceled["positions"] == {}
    assert canceled["real_broker_fills"] == 0

    # Reconnection baseline must not authorize entries, even if flat.
    official.begin(at(320))
    official.observe(official_frame(321, 0), at(322))
    baseline = paper.step(at(323))
    assert (
        baseline["source_results"]["S035"] == "BLOCKED_SOURCE_NOT_PROSPECTIVE_POSITION_TRANSITION"
    )
    assert baseline["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    # A genuinely new transition gets its own non-resetting deadline.
    official.observe(official_frame(330, 10), at(331))
    resumed = paper.step(at(332))
    assert resumed["execution_intents"]["S035"]["due_at"] == at(631)
    assert resumed["positions"] == {}


def test_v4_reconnect_before_old_deadline_starts_fresh_t300(tmp_path):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    official = official_observer(source)
    official.observe(official_frame(12, 20), at(13))
    contract = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "native",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="early_reconnect",
        catalog={},
        native_contracts={BTC.key: contract},
        started_at=at(0),
    )
    first = paper.step(at(14))
    old_id = first["execution_intents"]["S035"]["intent_id"]
    assert first["execution_intents"]["S035"]["due_at"] == at(313)

    official.gap(at(100), "SIMULATED_DISCONNECT")
    official.begin(at(120))
    official.observe(official_frame(121, 0), at(122))
    official.observe(official_frame(130, 10), at(131))
    resumed = paper.step(at(132))
    assert resumed["source_gap_results"]["S035"] == "CANCELED_SOURCE_GAP"
    assert resumed["execution_intents"]["S035"]["due_at"] == at(431)
    assert resumed["execution_intents"]["S035"]["intent_id"] != old_id
    assert (
        paper.run.account.pm04_state["paper_execution"]["history"][old_id]["status"]
        == "CANCELED_SOURCE_GAP"
    )
    assert resumed["positions"] == {}
    assert resumed["real_broker_fills"] == 0


def test_v4_due_uses_latest_known_official_position_not_stale_pending(tmp_path):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    official = official_observer(source)
    official.observe(official_frame(12, 20), at(13))
    contract = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "native",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="stale_target",
        catalog={},
        native_contracts={BTC.key: contract},
        started_at=at(0),
    )
    assert paper.step(at(14))["execution_intents"]["S035"]["due_at"] == at(313)
    # The consumer is delayed. A later source frame changes the target, but
    # is already stale when the consumer eventually wakes at due time.
    official.observe(official_frame(20, 30), at(21))
    price(prices, 312)
    result = paper.step(at(313))
    assert result["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert result["positions"] == {}
    assert result["real_broker_fills"] == 0


def test_v4_rejects_forged_position_transition_without_observer_link(tmp_path):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    contract = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "native",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="forged_position",
        catalog={},
        native_contracts={BTC.key: contract},
        started_at=at(0),
    )
    add_source(source, 1, 12, {BTC.key: "20"})
    result = paper.step(at(14))
    assert result["source_results"]["S035"] == "BLOCKED_OFFICIAL_POSITION_STREAM_PROOF"
    assert result["positions"] == {}
    assert not result["execution_intents"]


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
        source_db=source.path,
        price_db=market.path,
        price_mode="vike_minute",
        registry_db=tmp_path / "registry.sqlite",
        state_root=tmp_path / "vike_virtual",
        run_id="vike_estimated",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    assert restored.run.account.snapshot() == paper.run.account.snapshot()
    with pytest.raises(ValueError, match="POLICY_DRIFT"):
        ObservedP1Paper(
            source_db=source.path,
            registry_db=tmp_path / "registry.sqlite",
            state_root=tmp_path / "vike_virtual",
            run_id="vike_estimated",
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
            source_db=source.path,
            price_mode="vike_minute",
            state_root=tmp_path / "campaign",
            run_id="vike",
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        )
