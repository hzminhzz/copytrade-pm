"""Public orchestration with fake public transports, real SQLite and independent health."""

import asyncio
from collections import deque
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import sqlite3
from time import monotonic

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_continuous import ContinuousObserver, SubscriptionBudget
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observer_health import inspect_continuous_observer
from copytrade_pm.pm_forward_stream_journal import verify_streams
from test_pm_e4_prospective import WALLET, SUB, sample_state
from test_pm_forward_ccxt_market import BTC, BRENT, ccxt_market


def test_fatal_storage_error_closes_all_public_transports(tmp_path, monkeypatch):
    import pytest

    async def run():
        env = FakeEnvironment()
        journal = PaperJournal(tmp_path / "candidate")
        manifest = {
            "schema": "paper_continuous_preflight_v1",
            "revision": "a" * 40,
            "source_nav_attested": False,
            "order_route": "NONE",
        }
        manifest["manifest_sha"] = digest(manifest)
        observer = ContinuousObserver(
            journal=journal,
            manifest=manifest,
            parents={"S035": WALLET},
            watched={WALLET: "wallet:17"},
            configured=(BTC, BRENT),
            budget=SubscriptionBudget(),
            info=env.info,
            connect=env.connect,
            ccxt_factory=env.factory,
            receipt_clock_factory=lambda client: client.timer,
            now=env.now,
            refresh_seconds=0.4,
            heartbeat_seconds=0.05,
            min_free_bytes=0,
        )
        real = journal.append_market_quote
        calls = 0

        def unavailable(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError(28, "Injected disk full")
            return real(*args, **kwargs)

        monkeypatch.setattr(journal, "append_market_quote", unavailable)
        with pytest.raises(OSError):
            await observer.run(asyncio.Event(), duration_seconds=3)
        assert env.clients and env.sockets
        assert all(client.closed for client in env.clients)
        assert all(socket.closed for socket in env.sockets)
        assert verify_streams(journal.path)["integrity"] == "VERIFIED"
        with closing(sqlite3.connect(journal.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)

    asyncio.run(run())


class FakeEnvironment:
    def __init__(self):
        self.start = monotonic()
        self.base = datetime.now(UTC) - timedelta(seconds=1)
        self.sockets, self.clients, self.requests = [], [], []
        self.public_fills = []
        self.native_counter = 0

    def now(self):
        return (self.base + timedelta(seconds=monotonic() - self.start)).isoformat()

    def stamp(self):
        return int(datetime.fromisoformat(self.now()).timestamp() * 1000)

    def info(self, request):
        self.requests.append(request)
        kind = request["type"]
        if kind == "perpDexs":
            value = [None, {"name": "xyz"}]
        elif kind == "subAccounts":
            value = None
        elif kind == "spotClearinghouseState":
            value = {"balances": []}
        elif kind == "userAbstraction":
            value = "disabled"
        elif kind == "userFillsByTime":
            value = [
                deepcopy(row)
                for row in self.public_fills
                if request["startTime"] <= row["time"] <= request["endTime"]
            ]
        elif kind == "meta":
            value = {
                "universe": [{"name": "xyz:BRENTOIL"}] if request.get("dex") else [{"name": "BTC"}]
            }
        else:
            raise AssertionError("Unexpected non-public request: " + kind)
        raw = json.dumps(value).encode()
        return value, raw, sha256(raw).hexdigest()

    def connect(self, *args, **kwargs):
        socket = NativeSocket(self)
        self.sockets.append(socket)
        return socket

    def factory(self, config):
        assert "apiKey" not in config and config["newUpdates"] is False
        client = MarketSocket(self)
        self.clients.append(client)
        return client


class NativeSocket:
    def __init__(self, env):
        self.env, self.sent, self.subs, self.pending = env, [], [], deque()
        self.closed = False
        self.index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def send(self, raw):
        request = json.loads(raw)
        self.sent.append(request)
        if request["method"] == "ping":
            self.pending.append({"channel": "pong"})
        else:
            assert request["method"] == "subscribe"
            self.subs.append(request["subscription"])
            self.pending.append({"channel": "subscriptionResponse", "data": request})

    async def recv(self):
        if self.pending:
            return json.dumps(self.pending.popleft())
        await asyncio.sleep(0.025)
        sub = self.subs[self.index % len(self.subs)]
        self.index += 1
        if sub["type"] == "allDexsClearinghouseState":
            state = sample_state()
            state["user"] = sub["user"]
            for _, row in state["clearinghouseStates"]:
                row["time"] = self.env.stamp()
            state["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["szi"] = str(
                self.index / 10
            )
            state["clearinghouseStates"][1][1]["assetPositions"][0]["position"]["coin"] = (
                "xyz:BRENTOIL"
            )
            return json.dumps({"channel": "allDexsClearinghouseState", "data": state})
        self.env.native_counter += 1
        fill = {
            "coin": sub["coin"],
            "side": "B",
            "px": "100",
            "sz": "0.1",
            "time": self.env.stamp(),
            "tid": self.env.native_counter,
            "hash": "0x" + "1" * 64,
            "users": [WALLET, SUB],
        }
        self.env.public_fills.append({k: v for k, v in fill.items() if k != "users"})
        return json.dumps({"channel": "trades", "data": [fill]})


class FakeReceiptClock:
    def __init__(self, env):
        self.env, self.rows, self.clocks = env, {}, {}
        self.epoch = "c" * 32

    def stamp(self, channel, coin, native_time=None):
        row = self.rows[(channel, coin)]
        if native_time is not None:
            assert row["native_time"] == native_time
        return row

    def trade_clocks(self, coin, epoch):
        assert epoch == self.epoch
        return dict(self.clocks.get(coin, {}))

    def transport_at(self):
        return max((row["known_at"] for row in self.rows.values()), default=None)


class MarketSocket:
    has = {"watchOrderBook": True, "watchTrades": True}

    def __init__(self, env):
        self.env, self.calls, self.closed, self.count = env, [], False, 0
        self.timer = FakeReceiptClock(env)
        self.caches = {}

    async def load_markets(self):
        self.calls.append("load_markets")
        return {"BTC": ccxt_market(), "BRENT": ccxt_market("xyz:BRENTOIL", hip3=True)}

    def coin(self, symbol):
        return "BTC" if symbol == "BTC/USDC:USDC" else "xyz:BRENTOIL"

    async def watch_order_book(self, symbol, limit):
        self.calls.append("watch_order_book")
        await asyncio.sleep(0.03)
        stamp, known = self.env.stamp(), self.env.now()
        self.timer.rows[("quote", self.coin(symbol))] = {
            "known_at": known,
            "epoch": self.timer.epoch,
            "native_time": stamp,
        }
        return {"symbol": symbol, "timestamp": stamp, "bids": [[100, 2]], "asks": [[101, 2]]}

    async def watch_trades(self, symbol, since, limit):
        self.calls.append("watch_trades")
        await asyncio.sleep(0.035)
        self.count += 1
        coin, stamp, known = self.coin(symbol), self.env.stamp(), self.env.now()
        native = str(self.count)
        row = {
            "symbol": symbol,
            "id": native,
            "timestamp": stamp,
            "side": "buy",
            "price": "100",
            "amount": "0.1",
        }
        cache = self.caches.setdefault(symbol, [])
        cache.append(row)
        self.timer.rows[("trades", coin)] = {"known_at": known, "epoch": self.timer.epoch}
        self.timer.clocks.setdefault(coin, {})[native + "@" + str(stamp)] = known
        return list(cache[-1000:])

    async def close(self):
        self.closed = True


def test_full_candidate_to_independent_watchdog_reopen_and_backup(tmp_path):
    async def run():
        env = FakeEnvironment()
        journal = PaperJournal(tmp_path / "candidate")
        manifest = {
            "schema": "paper_continuous_preflight_v1",
            "revision": "a" * 40,
            "source_nav_attested": False,
            "order_route": "NONE",
        }
        manifest["manifest_sha"] = digest(manifest)
        observer = ContinuousObserver(
            journal=journal,
            manifest=manifest,
            parents={"S035": WALLET, "S051": SUB},
            watched={WALLET: "wallet:17", SUB: "wallet:18"},
            configured=(BTC, BRENT),
            budget=SubscriptionBudget(),
            info=env.info,
            connect=env.connect,
            ccxt_factory=env.factory,
            receipt_clock_factory=lambda client: client.timer,
            now=env.now,
            refresh_seconds=0.4,
            heartbeat_seconds=0.05,
            min_free_bytes=0,
        )
        stop = asyncio.Event()
        task = asyncio.create_task(observer.run(stop, duration_seconds=5))
        report = None
        for _ in range(100):
            await asyncio.sleep(0.02)
            if task.done():
                await task  # Surface a real supervisor failure before checking health.
            report = inspect_continuous_observer(journal.root, as_of=env.now())
            if report["feed_health"] == "CURRENT_FEEDS_OBSERVED":
                break
        assert report["feed_health"] == "CURRENT_FEEDS_OBSERVED", report
        await asyncio.sleep(0.15)
        stop.set()
        result = await task
        assert result["financial_events_committed"] == 0
        original = verify_streams(journal.path)
        assert original["streams"]["account:S035"]["observation_count"] > 0
        assert original["streams"]["ccxt_l2:" + BTC.key]["observation_count"] > 0
        assert original["streams"]["ccxt_trades:" + BTC.key]["observation_count"] > 0
        assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)["receipts"] > 0
        with closing(sqlite3.connect(journal.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM runs").fetchone() == (0,)
            assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
        journal.backup(tmp_path / "backup")
        assert verify_streams(tmp_path / "backup/paper-events.sqlite3") == original
        assert verify_streams(PaperJournal(journal.root).path) == original
        assert len(env.clients) == 1
        assert len(env.sockets) == 2
        assert all(client.closed for client in env.clients)
        assert all(socket.closed for socket in env.sockets)
        assert all(
            request["type"]
            in {
                "perpDexs",
                "subAccounts",
                "spotClearinghouseState",
                "userAbstraction",
                "userFillsByTime",
                "meta",
            }
            for request in env.requests
        )

    asyncio.run(run())
