"""Bounded two-channel public-market capture: no trades, no fabricated capacity."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from copytrade_pm.pm_forward_market_stream import BoundedMarketCapture
from copytrade_pm.pm_forward_journal import PaperJournal
from test_pm_forward_ccxt_market import BTC, orderbook
from test_pm_forward_ccxt_trades import FakeTrades, trade


T = datetime.fromisoformat("2026-11-04T04:00:00+00:00")


class PublicClient(FakeTrades):
    def __init__(self, config):
        super().__init__(config)
        self.books = [
            orderbook(seconds=2),
            orderbook(seconds=3, bid=100.5, ask=101.5),
        ]
        self.trade_caches = [
            [trade("a", 1)],
            [trade("a", 1), trade("b", 3)],
        ]

    async def watch_trades(self, symbol, since, limit):
        answer = await super().watch_trades(symbol, since, limit)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_bounded_public_dual_stream_is_durable_readonly_and_no_order(tmp_path: Path):
    async def run():
        client = PublicClient({})
        journal = PaperJournal(tmp_path / "private")
        stamp = 0

        def now():
            nonlocal stamp
            stamp += 1
            return (T + timedelta(seconds=stamp + 3)).isoformat()

        capture = BoundedMarketCapture(
            (BTC,), journal=journal, factory=lambda config: client, now=now
        )
        report = await capture.run(duration_seconds=1, max_updates_per_channel=2)
        assert report["schema"] == "paper_ccxt_public_bounded_capture_v1"
        assert report["market_catalog"]["bounded_session_ended"] is True
        assert report["market_catalog"]["connected"] is False
        assert report["receipt_counts"][BTC.key]["quote"] == 2
        assert report["receipt_counts"][BTC.key]["trade_baseline"] == 1
        assert report["receipt_counts"][BTC.key]["trade"] == 1
        assert report["stream_failures"] == {}
        assert report["requested_market_count"] == 1
        assert report["catalogued_market_count"] == 1
        assert report["missing_native_markets"] == []
        assert report["full_requested_market_scope_observed"] is False
        assert report["market_quote_tapes"][BTC.key]["cursor"] == 2
        assert report["market_trade_tapes"][BTC.key]["cursor"] == 2
        assert report["market_trade_tapes"][BTC.key]["locally_observed_trade_count"] == 1
        assert report["executable_volume_base"] is None
        assert not report["trade_volume_complete"]
        assert not report["paper_observed"]
        assert not report["continuous_24h_feed_verified"]
        assert report["order_route"] == "NONE"
        assert client.closed
        assert not any(
            name in ("create_order", "cancel_order", "set_leverage") for name, *_ in client.calls
        )
        assert PaperJournal(journal.root).market_trade_status(BTC.key)["cursor"] == 2
        assert PaperJournal(journal.root).market_quote_status(BTC.key)["cursor"] == 2

    asyncio.run(run())


def test_missing_native_market_is_explicitly_blocked_not_silently_skipped(tmp_path):
    class MissingMarketClient(PublicClient):
        async def load_markets(self):
            await super().load_markets()
            return {}

    async def run():
        client = MissingMarketClient({})
        result = await BoundedMarketCapture(
            (BTC,),
            journal=PaperJournal(tmp_path / "private"),
            factory=lambda config: client,
            now=lambda: (T + timedelta(seconds=6)).isoformat(),
        ).run(duration_seconds=0.5, max_updates_per_channel=1)
        assert result["requested_market_count"] == 1
        assert result["catalogued_market_count"] == 0
        assert result["missing_native_markets"] == [BTC.key]
        assert result["stream_failures"][BTC.key] == [
            "identity:CCXT_NATIVE_MARKET_NOT_UNIQUELY_DISCOVERED"
        ]
        assert result["market_quote_tapes"] == {}
        assert result["market_trade_tapes"] == {}
        assert result["full_requested_market_scope_observed"] is False
        assert client.closed

    asyncio.run(run())


def test_feed_failure_reports_gap_and_still_never_executes(tmp_path):
    async def run():
        client = PublicClient({})
        client.trade_caches = [TimeoutError("ws feed drop")]
        journal = PaperJournal(tmp_path / "private")
        capture = BoundedMarketCapture(
            (BTC,),
            journal=journal,
            factory=lambda config: client,
            now=lambda: (T + timedelta(seconds=6)).isoformat(),
        )
        result = await capture.run(duration_seconds=1, max_updates_per_channel=2)
        assert result["stream_failures"][BTC.key]
        assert result["missing_native_markets"] == []
        assert any("trade:TimeoutError" in x for x in result["stream_failures"][BTC.key])
        assert not result["paper_observed"]
        assert result["market_trade_tapes"][BTC.key]["cursor"] == 0
        assert client.closed

    asyncio.run(run())
