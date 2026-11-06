"""Adversarial public-entrypoint and pinned transport verification."""

import asyncio
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_continuous import (
    ContinuousObserver,
    _private_candidate_path,
    load_continuous_config,
)
from copytrade_pm.pm_forward_continuous_transport import native_session, SerialWriter
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_public_trades import (
    PersistentPublicMarket,
    validate_public_market_catalog,
)
from copytrade_pm.pm_forward_stream_journal import verify_streams
from test_pm_forward_continuous_integration import FakeEnvironment
from test_pm_forward_ccxt_market import BTC, BRENT
from test_pm_forward_public_trades import BUYER, SELLER, known, trade
from test_pm_e4_prospective import WALLET


@pytest.mark.filterwarnings("ignore:enable_cleanup_closed ignored:DeprecationWarning")
def test_real_pinned_ccxt_raw_message_clock_and_reconnect_budget(monkeypatch):
    hyperliquid = pytest.importorskip("ccxt.pro").hyperliquid
    from aiohttp import WSMessage, WSMsgType
    from ccxt.async_support.base.ws.client import Client
    from copytrade_pm.pm_forward_ccxt_market import CCXTLocalReceiptClock

    async def run():
        exchange = hyperliquid({"newUpdates": False})
        times = iter([known(2), known(4), known(6)])
        dispatched = []
        exchange.handle_message = lambda client, message: dispatched.append(message)
        dials = []

        async def fake_dial(client, session):
            dials.append("dial")
            return session

        monkeypatch.setattr(Client, "create_connection", fake_dial)

        class Limiter:
            async def acquire(self):
                dials.append("budget")

        timer = CCXTLocalReceiptClock(exchange, now=lambda: next(times), limiter=Limiter())
        client = exchange.client("wss://api.hyperliquid.xyz/ws")
        assert exchange.client(client.url) is client
        try:
            for _ in range(2):
                await client.create_connection(None)
            assert dials == ["budget", "dial", "budget", "dial"]
            wire = {"channel": "trades", "data": [trade(7, 1)]}
            client.handle_message(WSMessage(WSMsgType.TEXT, json.dumps(wire), ""))
            first = timer.stamp("trades", "BTC")
            tid = "7@" + str(wire["data"][0]["time"])
            assert timer.trade_clocks("BTC", first["epoch"])[tid] == known(2)
            client.handle_message(WSMessage(WSMsgType.TEXT, json.dumps(wire), ""))
            assert timer.trade_clocks("BTC", first["epoch"])[tid] == known(2)
            client.on_connected_callback(client)
            client.handle_message(WSMessage(WSMsgType.TEXT, json.dumps(wire), ""))
            second = timer.stamp("trades", "BTC")
            assert second["epoch"] != first["epoch"]
            assert timer.trade_clocks("BTC", second["epoch"])[tid] == known(6)
            assert dispatched == [wire, wire, wire]
            assert len(timer.clients) == 1
        finally:
            await exchange.close()

    asyncio.run(run())


def test_native_raw_wire_sha_retained_and_failed_commit_does_not_publish(tmp_path, monkeypatch):
    journal = PaperJournal(tmp_path / "journal")
    feed = PersistentPublicMarket(
        journal, BTC, {BUYER: "wallet:17", SELLER: "wallet:18"}, scope_sha="a" * 64
    )
    feed.begin(known(1))

    def observe(row, at):
        wire = json.dumps({"channel": "trades", "data": [row]})
        return feed.observe([row], at, raw_sha=sha256(wire.encode()).hexdigest(), raw_text=wire)

    observe(trade(1, 1), known(2))
    before = dict(feed._seen)
    real = journal.append_public_wallet_trades

    def fail(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(journal, "append_public_wallet_trades", fail)
    with pytest.raises(OSError):
        observe(trade(2, 3), known(4))
    assert feed._seen == before
    monkeypatch.setattr(journal, "append_public_wallet_trades", real)
    assert observe(trade(2, 3), known(4))["new_receipts"] == 2
    event = verify_streams(journal.path)["streams"]["public:" + BTC.key]["event"]
    assert sha256(event["details"]["native_wire"].encode()).hexdigest() == event["raw_sha"]
    assert "recent_ids" not in event["checkpoint"]


@pytest.mark.parametrize(
    "acknowledge,pattern", [(True, "SILENT_TRANSPORT"), (False, "ACK_TIMEOUT")]
)
def test_silent_transport_and_missing_ack_fail_closed(acknowledge, pattern):
    async def run():
        stop, frames = asyncio.Event(), asyncio.Queue()

        class Silent:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def send(self, raw):
                request = json.loads(raw)
                if acknowledge and request["method"] == "subscribe":
                    frames.put_nowait(
                        json.dumps({"channel": "subscriptionResponse", "data": request})
                    )

            async def recv(self):
                return await frames.get()

        async def consume(*args):
            pass

        with pytest.raises(ValueError, match=pattern):
            await native_session(
                subscriptions=[{"type": "trades", "coin": "BTC"}],
                handle=consume,
                on_transport=consume,
                stop=stop,
                now=lambda: known(1),
                connect=lambda *a, **k: Silent(),
                transport_timeout=0.06,
                acknowledgement_timeout=0.02,
            )

    asyncio.run(run())


def test_writer_queue_overflow_is_explicit_and_storage_failure_is_terminal():
    import threading

    async def run():
        started, release = threading.Event(), threading.Event()

        def blocked():
            started.set()
            release.wait(timeout=2)

        async with SerialWriter(max_pending=1) as writer:
            active = asyncio.create_task(writer.submit(blocked))
            while not started.is_set():
                await asyncio.sleep(0.001)
            pending = asyncio.create_task(writer.submit(lambda: "second"))
            await asyncio.sleep(0)
            with pytest.raises(ValueError, match="QUEUE_OVERFLOW"):
                await writer.submit(lambda: "third")
            release.set()
            await active
            assert await pending == "second"

            def disk_full():
                raise OSError(28, "No space left on device")

            with pytest.raises(OSError):
                await writer.submit(disk_full)
            with pytest.raises(OSError):
                await writer.submit(lambda: "cannot advance")

    asyncio.run(run())


def test_candidate_rejects_symlink_hardlink_and_financial_collision(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir(mode=0o700)
    target = tmp_path / "target"
    target.write_bytes(b"old")
    path = root / "paper-events.sqlite3"
    path.symlink_to(target)
    with pytest.raises(ValueError, match="SYMLINK"):
        _private_candidate_path(root, ())
    path.unlink()
    path.hardlink_to(target)
    target.chmod(0o600)
    with pytest.raises(ValueError, match="PERMISSION"):
        _private_candidate_path(root, ())
    path.unlink()
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE runs(value)")
        db.execute("INSERT INTO runs VALUES(1)")
        db.commit()
    path.chmod(0o600)
    with pytest.raises(ValueError, match="FINANCIAL_JOURNAL_COLLISION"):
        _private_candidate_path(root, ())


def test_native_catalog_partial_does_not_substitute_same_symbol_other_dex():
    env = FakeEnvironment()
    absent = type(BTC)("hyperliquid", "mainnet:perp:xyz", "BTC")
    report = validate_public_market_catalog((BTC, absent), info=env.info, allow_partial=True)
    assert report["markets_verified"] == 1
    assert report["unavailable_markets"] == ["xyz:BTC"]
    with pytest.raises(ValueError, match="MARKET_UNAVAILABLE"):
        validate_public_market_catalog((BTC, absent), info=env.info)


def test_config_pins_actual_top40_layout(tmp_path):
    scope = Path("docs/FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json").resolve()
    config = {
        "schema": "paper_continuous_observer_config_v1",
        "revision": "a" * 40,
        "inventory_sha256": "b" * 64,
        "protected_roots": [str(tmp_path / "old")],
        "budget": {},
        "portfolio_ids": ["P1", "P14"],
        "duration_seconds": 0,
        "market_scope_file": str(scope),
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    loaded, markets, budget = load_continuous_config(path)
    assert len(markets) == 40
    assert len(loaded["configured_groups"]) == 5
    assert len(loaded["market_scope_sha"]) == 64
    assert budget.plan(markets, account_count=5)["subscription_count"] == 125


@pytest.mark.parametrize("preflight_only", [True, False])
def test_public_cli_preflight_and_capture_with_fake_transports(
    tmp_path, monkeypatch, capsys, preflight_only
):
    import copytrade_pm.pm_forward_continuous as module
    import copytrade_pm.pm_forward_observer as cli
    import copytrade_pm.pm_forward_registry_identity as identity
    import copytrade_pm.pm_forward_source_campaign as campaign

    env, root = FakeEnvironment(), tmp_path / "candidate"
    config = {
        "schema": "paper_continuous_observer_config_v1",
        "revision": "a" * 40,
        "inventory_sha256": "b" * 64,
        "protected_roots": [str(tmp_path / "old")],
        "budget": {},
        "portfolio_ids": ["P1"],
        "duration_seconds": 0.25,
        "instruments": [BTC.key, BRENT.key],
        "min_free_bytes": 100_000_000,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    manifest = {
        "schema": "paper_continuous_preflight_v1",
        "revision": "a" * 40,
        "source_nav_attested": False,
        "order_route": "NONE",
    }
    manifest["manifest_sha"] = digest(manifest)
    monkeypatch.setattr(module, "runtime_revision", lambda: "a" * 40)
    monkeypatch.setattr(module, "candidate_preflight", lambda **kwargs: manifest)
    monkeypatch.setattr(module, "registry_watched_addresses", lambda *a, **k: {WALLET: "wallet:17"})
    monkeypatch.setattr(identity, "P1", ("member",))
    monkeypatch.setattr(identity, "audit_frozen_member_resolution", lambda **k: None)
    monkeypatch.setattr(identity, "_private_locator", lambda *a, **k: (None, WALLET, None))
    monkeypatch.setattr(campaign, "_ALIAS", {"member": "S035"})

    def observer(**kwargs):
        return ContinuousObserver(
            **kwargs,
            info=env.info,
            connect=env.connect,
            ccxt_factory=env.factory,
            receipt_clock_factory=lambda client: client.timer,
            now=env.now,
            heartbeat_seconds=0.05,
            refresh_seconds=0.1,
        )

    monkeypatch.setattr(module, "ContinuousObserver", observer)
    args = [
        "observe",
        "--registry",
        str(tmp_path / "registry"),
        "--primary-dir",
        str(tmp_path),
        "--secondary-dir",
        str(tmp_path),
        "--state-root",
        str(root),
        "--continuous-config",
        str(path),
    ]
    if preflight_only:
        args.append("--preflight-only")
    monkeypatch.setattr("sys.argv", args)
    cli.main()
    report = json.loads(capsys.readouterr().out)
    assert report["order_route"] == "NONE"
    if preflight_only:
        assert not root.exists() and env.requests == []
    else:
        assert report["financial_events_committed"] == 0
        assert verify_streams(root / "paper-events.sqlite3")["integrity"] == "VERIFIED"
        assert all(socket.closed for socket in env.sockets)
