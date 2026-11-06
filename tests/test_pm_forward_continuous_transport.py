import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from copytrade_pm.pm_forward_continuous_transport import native_session, SerialWriter


class Socket:
    def __init__(self, stop, *, burst=False, bad_ack=False):
        self.stop, self.burst, self.bad_ack = stop, burst, bad_ack
        self.sent = []
        self.frames = asyncio.Queue()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def send(self, wire):
        message = json.loads(wire)
        self.sent.append(message)
        if message["method"] == "subscribe":
            sub = message["subscription"] if not self.bad_ack else {"type": "trades", "coin": "BAD"}
            self.frames.put_nowait(
                json.dumps(
                    {
                        "channel": "subscriptionResponse",
                        "data": {"method": "subscribe", "subscription": sub},
                    }
                )
            )
            for i in range(20 if self.burst else 3):
                self.frames.put_nowait(json.dumps({"channel": "trades", "data": [{"step": i}]}))
        if message["method"] == "ping":
            self.frames.put_nowait('{"channel":"pong"}')

    async def recv(self):
        return await self.frames.get()


def test_retained_native_socket_and_raw_first_known_before_parse():
    async def run():
        stop = asyncio.Event()
        socket = Socket(stop)
        now_steps = iter(
            [
                "2026-11-04T04:00:00+00:00",
                "2026-11-04T04:00:01+00:00",
                "2026-11-04T04:02:20+00:00",
                "2026-11-04T04:02:21+00:00",
                "2026-11-04T04:02:22+00:00",
            ]
        )
        observed = []

        async def handle(frame, known, raw_sha, wire):
            observed.append((frame, known, raw_sha))
            if len(observed) == 3:
                stop.set()

        async def transport(known):
            pass

        result = await native_session(
            subscriptions=[{"type": "trades", "coin": "BTC"}],
            handle=handle,
            on_transport=transport,
            stop=stop,
            now=lambda: next(now_steps),
            connect=lambda *a, **k: socket,
        )
        assert len(observed) == 3
        assert observed[1][1] == "2026-11-04T04:02:20+00:00"
        assert sum(s["method"] == "subscribe" for s in socket.sent) == 1
        assert result["acknowledged"] == 1
        assert socket.closed
        assert all(s["method"] in {"subscribe", "ping"} for s in socket.sent)

    asyncio.run(run())


@pytest.mark.parametrize("fault", ["overflow", "ack"])
def test_explicit_native_transport_faults(fault):
    async def run():
        stop = asyncio.Event()
        socket = Socket(stop, burst=fault == "overflow", bad_ack=fault == "ack")

        async def handler(*args):
            await asyncio.sleep(1)

        with pytest.raises(
            ValueError, match="QUEUE_OVERFLOW" if fault == "overflow" else "ACK_MISMATCH"
        ):
            await native_session(
                subscriptions=[{"type": "trades", "coin": "BTC"}],
                handle=handler,
                on_transport=handler,
                stop=stop,
                now=lambda: "2026-11-04T04:00:00+00:00",
                connect=lambda *a, **k: socket,
                queue_size=2 if fault == "overflow" else 30,
            )
        assert socket.closed

    asyncio.run(run())


def test_cancelled_waiter_does_not_cancel_writer_commit():
    async def run():
        completed = []

        def commit():
            time.sleep(0.03)
            completed.append("committed")

        async with SerialWriter(max_pending=1) as writer:
            job = asyncio.create_task(writer.submit(commit))
            await asyncio.sleep(0.01)
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
            assert completed == ["committed"]  # Safe to reopen a projection now.
        assert completed == ["committed"]

    asyncio.run(run())


@pytest.mark.parametrize("channel", ["quote", "trades"])
def test_ccxt_result_and_receipt_clock_are_captured_before_scheduler_yields(channel):
    from copytrade_pm.pm03_account import Instrument
    from copytrade_pm.pm_forward_continuous import _ccxt_channel

    async def run():
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        first = "2026-11-04T04:00:01+00:00"
        later = "2026-11-04T04:00:02+00:00"
        stamp = {"known_at": first, "epoch": "a" * 32, "native_time": 1000}
        clocks = {"one@1000": first}
        captured = []

        def next_frame():
            stamp.update(known_at=later, native_time=2000)
            clocks["two@2000"] = later

        async def watch(*args):
            # Another socket callback is queued before the outer supervisor
            # resumes. It must not change the already returned snapshot's clock.
            loop.call_soon(next_frame)
            if channel == "quote":
                return {"timestamp": 1000}
            return [{"id": "one", "timestamp": 1000}]

        def record(raw, known, **kwargs):
            captured.append((raw, known, kwargs.get("first_known_by_id")))
            loop.call_soon_threadsafe(stop.set)
            return {}

        market = SimpleNamespace(
            market=SimpleNamespace(
                instrument=Instrument.parse("hyperliquid/mainnet:perp:default/BTC"),
                ccxt_symbol="BTC/USDC:USDC",
            ),
            begin=lambda *args: {},
            gap=lambda *args: {},
            quote=record,
            trades=record,
        )
        timer = SimpleNamespace(
            stamp=lambda *args, **kwargs: dict(stamp),
            trade_clocks=lambda *args: dict(clocks),
            transport_at=lambda: stamp["known_at"],
        )
        feed = SimpleNamespace(
            _exchange=SimpleNamespace(watch_order_book=watch, watch_trades=watch)
        )
        async with SerialWriter(max_pending=4) as writer:
            await asyncio.wait_for(
                _ccxt_channel(
                    market,
                    channel,
                    feed=feed,
                    timer=timer,
                    writer=writer,
                    stop=stop,
                    now=lambda: first,
                ),
                timeout=2,
            )
        assert len(captured) == 1
        assert captured[0][1] == first
        if channel == "trades":
            assert captured[0][2] == {"one@1000": first}
        assert clocks["two@2000"] == later  # The racing callback really ran.

    asyncio.run(run())
