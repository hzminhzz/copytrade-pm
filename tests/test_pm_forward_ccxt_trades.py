"""CCXT Pro trade-cache causality: first cache not PIT; no volume invention."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from copytrade_pm.pm_forward_ccxt_market import ReadOnlyCCXTProHyperliquid
from copytrade_pm.pm_forward_ccxt_trades import TradeWindow, ReadOnlyTradeObserver
from test_pm_forward_ccxt_market import BTC, FakeCCXTClient


T = datetime.fromisoformat("2026-11-04T04:00:00+00:00")


def at(sec):
    return (T + timedelta(seconds=sec)).isoformat()


def trade(identifier, seconds, *, amount="0.3", price="100", side="buy"):
    return {
        "symbol": "BTC/USDC:USDC",
        "id": str(identifier),
        "timestamp": int((T + timedelta(seconds=seconds)).timestamp() * 1000),
        "price": price,
        "amount": amount,
        "side": side,
    }


def test_retrospective_initial_cache_excluded_new_ids_deduped():
    window = TradeWindow(BTC, "BTC/USDC:USDC", max_cache=4)
    old = [trade("a", 1), trade("b", 2)]
    baseline = window.process(old, first_known_at=at(3))
    assert baseline["status"] == "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
    assert baseline["observed_volume_base"] == "0"
    assert baseline["trades"] == []
    next_cache = [*old, trade("c", 4, amount="0.5")]
    accepted = window.process(next_cache, first_known_at=at(5))
    assert accepted["new_local_trade_count"] == 1
    assert accepted["trades"][0]["native_trade_id"] == "c"
    assert Decimal(accepted["observed_volume_base"]) == Decimal("0.5")
    assert accepted["trade_volume_complete"] is False
    assert accepted["executable_volume_base"] is None
    reused = window.process(next_cache, first_known_at=at(6))
    assert reused["new_local_trade_count"] == 0
    assert window.unique_count == 1
    assert Decimal(window.status()["observed_volume_lower_bound"]) == Decimal("0.5")


def test_reconnect_gap_and_overflow_quarantine():
    win = TradeWindow(BTC, "BTC/USDC:USDC", max_cache=2)
    win.process([trade("a", 1)], first_known_at=at(2))
    with pytest.raises(ValueError, match="CCXT_TRADE_CACHE_CONTINUITY_LOST"):
        win.process([trade("b", 3), trade("c", 4)], first_known_at=at(5))
    assert win.quarantined
    with pytest.raises(ValueError, match="CCXT_TRADE_STREAM_QUARANTINED"):
        win.process([], first_known_at=at(6))
    # New epoch starts as baseline and never bridges a disconnected interval.
    another = TradeWindow(BTC, "BTC/USDC:USDC", max_cache=2)
    assert another.epoch != win.epoch
    assert another.process([trade("d", 7)], first_known_at=at(8))["trades"] == []


def test_future_trade_id_conflict_and_clock_regression_fail_closed():
    for bad, reason in (
        (trade("a", 9), "CCXT_TRADE_FUTURE_EVENT"),
        ({**trade("a", 1), "id": None}, "CCXT_TRADE_NATIVE_ID_UNKNOWN"),
        ({**trade("a", 1), "amount": "-2"}, "CCXT_TRADE_NONPOSITIVE"),
        ({**trade("a", 1), "symbol": "ETH/USDC:USDC"}, "CCXT_TRADE_SYMBOL_MISMATCH"),
    ):
        win = TradeWindow(BTC, "BTC/USDC:USDC")
        with pytest.raises(ValueError, match=reason):
            win.process([bad], first_known_at=at(5))
        assert win.quarantined
    win = TradeWindow(BTC, "BTC/USDC:USDC")
    win.process([trade("a", 1)], first_known_at=at(2))
    with pytest.raises(ValueError, match="CCXT_TRADE_IDENTITY_CONFLICT"):
        win.process([trade("a", 1, price="101")], first_known_at=at(4))
    assert win.quarantined


def test_new_older_trade_disallowed_after_latest_processed():
    win = TradeWindow(BTC, "BTC/USDC:USDC")
    win.process([trade("a", 2)], first_known_at=at(3))
    win.process([trade("a", 2), trade("b", 4)], first_known_at=at(5))
    with pytest.raises(ValueError, match="CCXT_TRADE_NEW_ID_CLOCK_REGRESSION"):
        win.process([trade("a", 2), trade("c", 3)], first_known_at=at(6))


class FakeTrades(FakeCCXTClient):
    def __init__(self, config):
        super().__init__(config)
        self.has["watchTrades"] = True
        self.trade_caches = [[trade("a", 1)], [trade("a", 1), trade("b", 2)]]

    async def watch_trades(self, symbol, since, limit):
        self.calls.append(("watch_trades", symbol, since, limit))
        return self.trade_caches.pop(0)


def test_observer_uses_same_public_connection_and_no_order_api():
    async def run():
        client = FakeTrades({})
        observations = iter([at(1), at(3), at(4)])
        feed = ReadOnlyCCXTProHyperliquid(
            (BTC,), factory=lambda _: client, now=lambda: next(observations)
        )
        await feed.open()
        observer = ReadOnlyTradeObserver(feed, now=lambda: at(3), max_cache=10)
        assert (await observer.observe(BTC))["status"] == "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
        observer.now = lambda: at(4)
        batch = await observer.observe(BTC)
        assert batch["new_local_trade_count"] == 1
        assert batch["trade_volume_complete"] is False
        await feed.close()
        assert client.closed
        assert not any("order" in call[0] for call in client.calls)

    asyncio.run(run())
