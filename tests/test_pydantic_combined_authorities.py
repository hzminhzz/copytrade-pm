"""Combined source, broker and risk faults through retained public owners."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import threading

import pytest

from copytrade_pm.pm03_account import digest, RiskState
from copytrade_pm.pm_forward_continuous_transport import SerialWriter
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_source_contracts import SourceObservationRejected
from test_pm_forward_observed_paper import BTC, ADDRESSES, add_quote, add_source, at
from test_pm_forward_single_shot import new_paper
from test_pm_vike_paper_integration import official_observer, official_frame, price
from test_pydantic_continuity import paper_for


def decision_at(stamp, *, fresh_quote):
    from test_pm_forward_fill import _decision

    event = _decision()
    event["event_at"] = stamp
    event["hypothetical_fill_at"] = (
        datetime.fromisoformat(stamp) + timedelta(seconds=1)
    ).isoformat()
    event["proposed"] = {}
    book = event["source_book"]
    book.update(first_known_at=stamp, source_event_at=stamp)
    book["snapshot_sha"] = digest({k: v for k, v in book.items() if k != "snapshot_sha"})
    contract = event["market_contracts"][BTC.key]
    contract["first_known_at"] = stamp
    contract["contract_sha"] = digest({k: v for k, v in contract.items() if k != "contract_sha"})
    if fresh_quote:
        event["observations"][0].update(first_known_at=stamp, source_at=stamp)
    return event


@pytest.mark.parametrize("loss_amount,can_reduce", [("-150", True), ("-1500", False)])
def test_cf02_loss_halt_funding_stale_exit_restart_reduction_or_unresolved(
    tmp_path, loss_amount, can_reduce
):
    from test_pm_forward_funding import _filled, _funding

    campaign, journal = _filled(tmp_path)
    funding = _funding()
    funding.update(amount=loss_amount, allocated={"PM_A": loss_amount})
    loss = campaign.record_event("run_1", "loss", funding)
    assert Decimal(loss["account"]["equity"]) < 10000
    if can_reduce:
        loss = journal.append(
            "run_1",
            "loss-budget-halt",
            {
                "kind": "HALT",
                "reason": "LOSS_BUDGET_HALT",
                "event_at": "2026-11-04T04:05:00+00:00",
            },
        )
    assert loss["account"]["risk"] == "HALT"
    reason = loss["account"]["halt_reason"]
    unknown = journal.append(
        "run_1",
        "unknown",
        {
            "kind": "FUNDING_UNKNOWN",
            "event_at": "2026-11-04T04:05:01+00:00",
        },
    )
    assert unknown["account"]["risk"] == "HALT"
    stale = decision_at("2026-11-04T04:10:00+00:00", fresh_quote=False)
    blocked = journal.append("run_1", "failed-exit", stale)
    assert blocked["account"]["quantities"][BTC.key] == "1"
    assert blocked["account"]["risk"] == "HALT"
    resumed = PaperJournal(journal.root)
    assert resumed.restore("run_1") == blocked
    valid = decision_at("2026-11-04T04:10:01+00:00", fresh_quote=True)
    reduced = resumed.append("run_1", "valid-reduction", valid)
    expected = 0 if can_reduce else 1
    assert Decimal(reduced["account"]["quantities"].get(BTC.key, "0")) == expected
    if not can_reduce:
        assert "UNAUTHORIZED_OR_BREACHED" in reduced["last_event_result"]["execution"]["rejections"]
    assert reduced["account"]["risk"] == "HALT"
    assert reduced["account"]["halt_reason"] == reason
    assert resumed.append("run_1", "valid-reduction", valid) == reduced
    with pytest.raises(ValueError, match="PAPER_ORDER_ROUTE_FORBIDDEN"):
        resumed.append("run_1", "broker-route", {**valid, "order_route": "BROKER"})
    assert resumed.restore("run_1") == reduced


def test_cf03_cancel_late_fill_writer_cancellation_restart_duplicate_snapshot(
    tmp_path, monkeypatch
):
    from copytrade_pm.pm04_broker import pending_quantities
    from copytrade_pm.pm_forward_observed_paper import _event

    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312)
    paper.step(at(313))

    def event(name, kind, seconds, **extra):
        observation = {
            "schema": "pm04_broker_observation_v1",
            "evidence_id": name,
            "kind": kind,
            "event_at": at(seconds),
            "first_known_at": at(seconds),
            **extra,
        }
        return _event(
            paper.run, "PM04_BROKER", name, at(seconds), at(seconds), {"observation": observation}
        )

    paper.run.record(
        event(
            "intent",
            "ORDER_INTENT",
            330,
            order_id="O1",
            instrument=BTC.key,
            quantity="3",
            provider_sequence=1,
        )
    )
    paper.run.record(event("cancel", "CANCEL", 340, order_id="O1", provider_sequence=2))
    late = event(
        "late-fill", "PARTIAL_FILL", 350, order_id="O1", cumulative_filled="1", provider_sequence=3
    )
    entered, released = threading.Event(), threading.Event()
    append = paper.run.ledger.append

    def durable_then_wait(row, **kwargs):
        result = append(row, **kwargs)
        if row.event_id == late.event_id:
            entered.set()
            assert released.wait(5)
        return result

    monkeypatch.setattr(paper.run.ledger, "append", durable_then_wait)

    async def cancel_during_commit():
        async with SerialWriter() as writer:
            task = asyncio.create_task(writer.submit(lambda: paper.run.record(late)))
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            released.set()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(cancel_during_commit())
    state = paper.run.restore()["account"]
    assert state == paper.run.account.snapshot()
    paper.run.record(late)
    stale = event(
        "old-snapshot",
        "POSITION_SNAPSHOT",
        360,
        event_at=at(335),
        complete=True,
        positions={BTC.key: "0"},
    )
    paper.run.record(stale)
    once = paper.run.account.snapshot()
    paper.run.record(stale)
    assert paper.run.account.snapshot() == once
    assert pending_quantities(paper.run.account, at(361))[BTC] == 2
    assert paper.run.account.risk == RiskState.HALT
    assert paper.run.restore()["account"] == once
    assert sum(r["event"]["event_id"] == late.event_id for r in paper.run.ledger.read()) == 1
    assert once["cash"] == state["cash"] and once["costs"] == state["costs"]


def test_cf06_retrospective_recovery_cannot_repair_official_gap_or_pm02(tmp_path):
    from copytrade_pm.pm_forward_ccxt_trades import TradeWindow
    from copytrade_pm.pm_manager import rank
    from test_pm_forward_ccxt_trades import trade, at as trade_at
    from test_pm_manager import replay, ALIASES, ASOF
    from test_pm_forward_public_trades import normalized

    source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
    official = official_observer(source)
    paper = paper_for(tmp_path, source, prices)
    official.observe(official_frame(12, 20), at(13))
    before = paper.step(at(14))["execution_intents"]["S035"]
    official.gap(at(180), "OFFICIAL_WS_DISCONNECTED")
    cache = TradeWindow(BTC, "BTC/USDC:USDC")
    historical = cache.process([trade("old", 1)], first_known_at=trade_at(190))
    assert historical["status"] == "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
    assert historical["trades"] == []
    source.append_public_wallet_trades(normalized(1, 40, known_seconds=200))
    from contextlib import closing
    from copytrade_pm.pm_vike_selected_fills import (
        apply_frame,
        had_gap,
        open_selected_journal,
        record_event,
    )
    from test_pm_vike_selected_fills import event as vike_event

    address = ADDRESSES["S035"]
    with closing(open_selected_journal(tmp_path / "selected-fills")) as db:
        assert (
            apply_frame(
                db,
                {"type": "gap", "channel": "hl.fills", "cursor": "1793930404464-0001"},
                (address,),
                at(190),
            )
            == "GAP"
        )
        recovered = vike_event(wallet=address)
        recovered["ts"] = at(180)
        assert (
            record_event(
                db,
                recovered,
                cursor="1793930404464-0002",
                known_at=at(200),
                wallets=(address,),
                prospective=False,
            )
            == "RECOVERED_FILL"
        )
        assert had_gap(db)
        assert db.execute("SELECT prospective FROM selected_fills").fetchone()[0] == 0
    report = rank(replay(), ALIASES, ASOF.isoformat())
    assert report["qualified_count"] == 0
    assert all(seat["state"] == "EMPTY" for seat in report["five_seats"])
    assert report["live_trading_authorized"] is False
    price(prices, 312)
    after = paper.step(at(313))
    assert not official.checkpoint["baseline_valid"]
    assert official.checkpoint["positions"][BTC.key] == "20"
    assert after["execution_intents"]["S035"]["intent_id"] == before["intent_id"]
    assert after["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert after["positions"] == {}
    assert after["real_broker_fills"] == 0


def test_cf12_numeric_equivalence_conflict_late_correction_and_native_regression(
    tmp_path, monkeypatch
):
    from copytrade_pm import pm_forward_journal as journal_module
    from test_pm_forward_public_trades import FixedDateTime, known, normalized

    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
    official = official_observer(source)
    paper = paper_for(tmp_path, source, prices)
    frame = official_frame(12, 20)
    official.observe(frame, at(13))
    initial = paper.step(at(14))["execution_intents"]["S035"]
    formatted = deepcopy(frame)
    formatted["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["szi"] = "20.0"
    assert official.observe(formatted, at(15))["classification"] == "UNCHANGED_STATE"
    assert paper.step(at(16))["execution_intents"]["S035"]["intent_id"] == initial["intent_id"]
    conflict = deepcopy(frame)
    conflict["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["szi"] = "21"
    with pytest.raises(SourceObservationRejected, match="SAME_CLOCK"):
        official.observe(conflict, at(17))
    source.append_public_wallet_trades(normalized(1, 40))
    bucket = source.observed_utc_net_delta(
        "wallet:17", BTC.key, bucket_start_at=known(0), as_of=known(301)
    )
    sealed = source.persist_observed_utc_bucket(bucket)

    class LateDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 12, 6, tzinfo=UTC)

    monkeypatch.setattr(journal_module, "datetime", LateDateTime)
    source.append_public_wallet_trades(normalized(2, 60))
    corrected = source.observed_utc_net_delta(
        "wallet:17", BTC.key, bucket_start_at=known(0), as_of=known(361)
    )
    with pytest.raises(ValueError, match="CORRECTION"):
        source.persist_observed_utc_bucket(corrected)
    assert source.persist_observed_utc_bucket(bucket) == sealed
    old = official_frame(11, 0)
    with pytest.raises(SourceObservationRejected):
        official.observe(old, at(18))
    price(prices, 312)
    outcome = paper.step(at(313))
    assert outcome["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert outcome["positions"] == {}
    assert Decimal(official.checkpoint["positions"][BTC.key]) == 20
