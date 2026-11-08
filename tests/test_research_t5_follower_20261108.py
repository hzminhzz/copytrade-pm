"""Historical-oracle follower screening invariants; fixtures are not alpha evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from research_t5_follower_oracle_20261108 import (  # noqa: E402
    CostModel,
    MarketObservation,
    Instrument,
    pod_stop_state,
    strict_minute,
)
from research_t5_native_source_20261108 import (  # noqa: E402
    build_events_native,
    native_events_from_coin,
    native_inst,
    training_k_native,
)
from research_t5_vike_inferred_source_20261108 import (  # noqa: E402
    infer_with_trade_anchors,
)
from copytrade_pm.pm03_account import Account, Rulebook  # noqa: E402


def _clock(day: int = 1, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(2026, 7, day, hh, mm, ss, tzinfo=UTC)


def test_strict_5minute_then_next_open_no_instant_fills() -> None:
    assert strict_minute(_clock(), 5) == _clock(hh=0, mm=6)
    assert strict_minute(_clock(ss=37), 5) == _clock(mm=6)
    assert strict_minute(_clock(mm=59), 0) == _clock(hh=1)
    assert strict_minute(_clock(mm=1, ss=12), 5) > _clock(mm=6, ss=12)


def test_peak_to_trough_loss_latches_after_previous_profit() -> None:
    peak, triggered = pod_stop_state(D("100"), D("0"), D("200"))
    assert peak == D("100") and not triggered
    peak, triggered = pod_stop_state(D("-101"), peak, D("200"))
    assert peak == D("100") and triggered
    with pytest.raises(ValueError, match="INVALID_POD_STOP_BUDGET"):
        pod_stop_state(D("0"), D("0"), D("0"))


def test_native_start_position_reconstructs_only_flat_to_flat() -> None:
    rows = [
        {
            "coin": "BTC", "ms": int(_clock(hh=1).timestamp() * 1000),
            "tid": "1", "side": "B", "before": "0", "qty": 2, "px": 100,
        },
        {
            "coin": "BTC", "ms": int(_clock(hh=2).timestamp() * 1000),
            "tid": "2", "side": "A", "before": "2", "qty": 2, "px": 101,
        },
        {
            "coin": "BTC", "ms": int(_clock(hh=3).timestamp() * 1000),
            "tid": "3", "side": "B", "before": "9", "qty": 1, "px": 100,
        },
    ]
    observed, counts = native_events_from_coin(rows)
    assert len(observed) == 2
    assert observed[0]["source_qty_after"] == D("2")
    assert observed[0]["source_after_notional"] == D("200")
    assert observed[1]["source_qty_after"] == D("0")
    assert counts["complete_flat_to_flat_episodes"] == 1
    assert counts["unlinked_position_chain"] >= 1


def test_vike_closed_trade_future_max_size_is_never_used_for_order_quantity() -> None:
    opening = "2026-07-01T01:00:00+00:00"
    closing = "2026-07-01T02:00:00+00:00"
    fills = [
        {"symbol":"BTC","ts":opening,"trade_id":1,"side":"buy","size_token":2,"price":100},
        {"symbol":"BTC","ts":closing,"trade_id":2,"side":"sell","size_token":2,"price":101},
    ]
    trade = {
        "symbol":"BTC","open_ts":opening,"close_ts":closing,
        "is_complete":True,"close_observed":True,"direction":"long",
        "max_size_token":10000,
    }
    events, metrics = infer_with_trade_anchors(fills,[trade])
    assert len(events)==2 and metrics["valid_inferred_flat_to_flat_cycles"]==1
    assert events[0]["source_qty_after"]==D("2")
    assert events[0]["source_after_notional"]==D("200")
    changed={**trade,"max_size_token":D("9999999999")}
    second,_ = infer_with_trade_anchors(fills,[changed])
    assert second == events


def test_vike_missing_exact_boundary_never_creates_ghost_position() -> None:
    trade = {
        "symbol":"BTC","open_ts":"2026-07-01T01:00:00+00:00",
        "close_ts":"2026-07-01T02:00:00+00:00",
        "is_complete":True,"close_observed":True,"direction":"long",
    }
    fillings = [
        {"symbol":"BTC","ts":"2026-07-01T01:01:00+00:00","trade_id":1,"side":"buy","size_token":2,"price":100},
        {"symbol":"BTC","ts":trade["close_ts"],"trade_id":2,"side":"sell","size_token":2,"price":101},
    ]
    events,metrics=infer_with_trade_anchors(fillings,[trade])
    assert not events and metrics["missing_exact_boundary_fills"]==1


def test_fixed_k_training_never_reads_later_trade_sizes() -> None:
    inst=native_inst("BTC")
    events=[]
    for i in range(26):
        timestamp=_clock()+timedelta(hours=i)
        events.append({"at":timestamp,"inst":inst,"symbol":"BTC",
                       "source_after_notional":D("5000"),"event_id":str(i)})
    future={"at":_clock()+timedelta(days=32),"inst":inst,"symbol":"BTC",
            "source_after_notional":D("1000000000"),"event_id":"future"}
    k,cut,n,p90=training_k_native(events+[future])
    k2,cut2,n2,p902=training_k_native(events)
    assert (k,cut,n,p90)==(k2,cut2,n2,p902)
    assert k==D("0.4") and p90==D("5000")


def test_native_minute_batches_same_coin_into_single_source_target() -> None:
    inst=native_inst("BTC")
    t0=_clock(hh=8)
    events=[
        {"at":t0+timedelta(seconds=12),"inst":inst,"symbol":"BTC","source_after_notional":D("100"),"event_id":"a"},
        {"at":t0+timedelta(seconds=33),"inst":inst,"symbol":"BTC","source_after_notional":D("300"),"event_id":"b"},
        {"at":t0+timedelta(minutes=20),"inst":inst,"symbol":"BTC","source_after_notional":D("0"),"event_id":"c"},
    ]
    actions,counts=build_events_native(events,t0,5)
    assert len(actions)==2
    assert actions[t0+timedelta(minutes=6)]=={"BTC":D("300")}
    assert actions[t0+timedelta(minutes=26)]=={"BTC":D("0")}
    assert counts["selected_source_fills"]==3


def test_first_signal_waits_five_minutes_and_collapses_subsequent_wallet_changes() -> None:
    inst_btc = native_inst("BTC")
    inst_eth = native_inst("ETH")
    t0 = _clock(hh=3, mm=4, ss=17)
    updates = [
        {"at": t0, "inst": inst_btc, "symbol": "BTC", "source_after_notional": D("100"), "event_id": "1"},
        {"at": t0 + timedelta(minutes=2), "inst": inst_eth, "symbol": "ETH", "source_after_notional": D("-200"), "event_id": "2"},
        {"at": t0 + timedelta(minutes=3), "inst": inst_btc, "symbol": "BTC", "source_after_notional": D("0"), "event_id": "3"},
        {"at": t0 + timedelta(minutes=6), "inst": inst_eth, "symbol": "ETH", "source_after_notional": D("0"), "event_id": "4"},
    ]
    batches, metrics = build_events_native(updates, _clock(hh=3), 5)
    assert list(batches) == [_clock(hh=3, mm=10), _clock(hh=3, mm=16)]
    # The transient BTC position opened and closed during the wait.
    assert batches[_clock(hh=3, mm=10)] == {"BTC": D("0"), "ETH": D("-200")}
    assert batches[_clock(hh=3, mm=16)] == {"ETH": D("0")}
    assert metrics["selected_source_fills"] == 4
    assert metrics["coalesced_source_events"] == 2


def test_source_change_at_decision_open_waits_for_new_batch() -> None:
    inst = native_inst("BTC")
    t0 = _clock(hh=1)
    updates = [
        {"at": t0, "inst": inst, "symbol": "BTC", "source_after_notional": D("500"), "event_id": "1"},
        {"at": t0 + timedelta(minutes=6), "inst": inst, "symbol": "BTC", "source_after_notional": D("0"), "event_id": "2"},
    ]
    batches, _ = build_events_native(updates, _clock(), 5)
    assert batches == {
        _clock(hh=1, mm=6): {"BTC": D("500")},
        _clock(hh=1, mm=12): {"BTC": D("0")},
    }


def test_native_pm03_taker_execution_price_and_fee_not_free() -> None:
    instrument=Instrument("hyperliquid","mainnet:perp:default","BTC")
    bar=MarketObservation(instrument,"2026-07-01T01:00:00+00:00",
         "2026-07-01T01:00:00+00:00", D("100"),D("100"),
         quality="OHLCV_1M_PROXY",supported=False)
    cost=CostModel(D("5"),D("3"),D("5"),D("20"),D("0.05"),0,0)
    buy, fee_buy,_=cost.price_and_fee(D("1"),bar)
    sell,fee_sell,_=cost.price_and_fee(D("-1"),bar)
    assert buy>100>sell
    assert fee_buy>0 and fee_sell>0


def test_pm03_flat_day_resets_daily_contract_floor() -> None:
    book=Rulebook(
        program="FIXTURE",stage="evaluation",source="SYNTHETIC_ONLY",
        observed_at="2026-07-01T00:00:00+00:00",version="fixture-v1",
        timezone="UTC",initial_balance=D("10000"),
        profit_target=D("1500"),daily_loss=D("450"),
        static_loss=None,trailing_loss=D("1000"),
        permitted=(),confirmed=True,account_terms_confirmed=False,
    )
    account=Account.start(book,"2026-07-01T00:00:00+00:00")
    account.mark({},"2026-07-02T01:00:00+00:00")
    assert account.daily_key == "2026-07-02"
    floor,_=account.floor()
    assert floor == D("9550")
