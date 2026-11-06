import asyncio
import json
import time

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
