"""Bounded queues and retained public sockets for the observer lifecycle."""

from __future__ import annotations

import asyncio
from collections import deque
from hashlib import sha256
import json
import sqlite3
from time import monotonic

from .pm_e4_prospective import MAX_BODY, WS_URL


async def _complete_admitted(future):
    """Repeated cancellation cannot release an admitted write/close early."""
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not future.cancelled():
            future.exception()  # Observe a failure even when cancellation wins.
        raise


class SerialWriter:
    """One bounded serialization point; cancellation cannot undo a committed job."""

    def __init__(self, *, max_pending: int = 256):
        if type(max_pending) is not int or not 1 <= max_pending <= 4096:
            raise ValueError("STREAM_WRITER_QUEUE_BOUND_INVALID")
        self.queue = asyncio.Queue(max_pending)
        self.failed = None
        self.high_water = 0
        self.write_count = 0
        self.write_failures = 0
        self.write_max_ms = 0.0
        self.write_total_ms = 0.0
        self.task = None

    async def __aenter__(self):
        self.task = asyncio.create_task(self._run(), name="observer-sqlite-writer")
        return self

    async def _run(self):
        while True:
            job = await self.queue.get()
            try:
                if job is None:
                    return
                function, future = job
                if self.failed is not None:
                    future.set_exception(self.failed)
                    continue
                started = monotonic()
                try:
                    result = await asyncio.to_thread(function)
                except Exception as exc:
                    self.write_failures += 1
                    if isinstance(exc, (OSError, sqlite3.Error)) or (
                        isinstance(exc, ValueError)
                        and any(
                            token in str(exc)
                            for token in (
                                "DIVERGENCE",
                                "CURSOR_CONFLICT",
                                "BUSY_OR_UNAVAILABLE",
                            )
                        )
                    ):
                        self.failed = exc
                    future.set_exception(exc)
                else:
                    future.set_result(result)
                finally:
                    elapsed_ms = (monotonic() - started) * 1000
                    self.write_count += 1
                    self.write_total_ms += elapsed_ms
                    self.write_max_ms = max(self.write_max_ms, elapsed_ms)
            finally:
                self.queue.task_done()

    async def submit(self, function):
        if self.failed is not None:
            raise self.failed
        future = asyncio.get_running_loop().create_future()
        # Consume any eventual exception if the submitter is cancelled after
        # enqueue. The writer still completes; restart reads durable truth.
        future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        try:
            self.queue.put_nowait((function, future))
        except asyncio.QueueFull as exc:
            raise ValueError("STREAM_WRITER_QUEUE_OVERFLOW") from exc
        self.high_water = max(self.high_water, self.queue.qsize())
        return await _complete_admitted(future)

    async def __aexit__(self, *_):
        async def close():
            await self.queue.join()
            await self.queue.put(None)
            await self.task

        await _complete_admitted(asyncio.create_task(close()))


class ConnectionBudget:
    """Shared process dial limiter, below the provider's 30/min/IP ceiling."""

    def __init__(self, *, per_minute: int = 20):
        if not 1 <= per_minute <= 25:
            raise ValueError("STREAM_DIAL_RATE_INVALID")
        self.per_minute = per_minute
        self.attempts = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            while self.attempts and self.attempts[0] <= monotonic() - 60:
                self.attempts.popleft()
            if len(self.attempts) >= self.per_minute:
                await asyncio.sleep(max(0, 60 - (monotonic() - self.attempts[0])))
                while self.attempts and self.attempts[0] <= monotonic() - 60:
                    self.attempts.popleft()
            self.attempts.append(monotonic())


async def native_session(
    *,
    subscriptions: list[dict],
    handle,
    on_transport,
    stop: asyncio.Event,
    now,
    connect=None,
    queue_size: int = 256,
    transport_timeout: float = 45,
    acknowledgement_timeout: float = 20,
    limiter: ConnectionBudget | None = None,
    on_ack=None,
) -> dict:
    """Keep one read-only native socket until stop or an explicit fault.

    Raw local time is captured immediately after recv and before JSON parsing,
    queueing, normalization or SQLite. The finite queue cannot silently drop.
    """
    if not 1 <= queue_size <= 4096 or not 0 < acknowledgement_timeout <= transport_timeout:
        raise ValueError("STREAM_TRANSPORT_BOUNDS_INVALID")
    if not subscriptions or len(subscriptions) > 128:
        raise ValueError("STREAM_NATIVE_SUBSCRIPTION_COUNT_INVALID")
    for sub in subscriptions:
        if sub.get("type") not in {"allDexsClearinghouseState", "trades"} or set(sub) != (
            {"type", "user"} if sub["type"] == "allDexsClearinghouseState" else {"type", "coin"}
        ):
            raise ValueError("STREAM_NATIVE_READONLY_SUBSCRIPTION_REQUIRED")
    expected = {json.dumps(sub, sort_keys=True) for sub in subscriptions}
    if len(expected) != len(subscriptions):
        raise ValueError("STREAM_DUPLICATE_SUBSCRIPTION")
    if connect is None:
        from websockets import connect
    if limiter is not None:
        await limiter.acquire()
    queue = asyncio.Queue(queue_size)
    acknowledged = set()
    stats = {"frames": 0, "queue_high_water": 0, "subscriptions": len(subscriptions)}
    last_valid_transport = monotonic()
    last_known = None
    started = monotonic()

    async with connect(
        WS_URL,
        open_timeout=12,
        close_timeout=5,
        ping_interval=15,
        ping_timeout=12,
        max_size=MAX_BODY,
    ) as ws:
        for sub in subscriptions:
            await ws.send(json.dumps({"method": "subscribe", "subscription": sub}))

        async def receiver():
            while not stop.is_set():
                wire = await ws.recv()
                known = now()
                if not isinstance(wire, str) or len(wire.encode()) > MAX_BODY:
                    raise ValueError("STREAM_NATIVE_FRAME_SIZE_OR_BINARY")
                try:
                    queue.put_nowait((wire, known))
                except asyncio.QueueFull as exc:
                    raise ValueError("STREAM_NATIVE_QUEUE_OVERFLOW") from exc
                stats["queue_high_water"] = max(stats["queue_high_water"], queue.qsize())

        async def consumer():
            nonlocal last_valid_transport, last_known
            while not stop.is_set():
                wire, known = await queue.get()
                try:
                    envelope = json.loads(wire)
                    if not isinstance(envelope, dict):
                        raise ValueError("STREAM_NATIVE_FRAME_NOT_OBJECT")
                    channel = envelope.get("channel")
                    if channel == "error":
                        raise ValueError("STREAM_NATIVE_SUBSCRIPTION_REJECTED")
                    if channel == "subscriptionResponse":
                        data = envelope.get("data", {})
                        identity = json.dumps(data.get("subscription"), sort_keys=True)
                        if data.get("method") != "subscribe" or identity not in expected:
                            raise ValueError("STREAM_NATIVE_ACK_MISMATCH")
                        acknowledged.add(identity)
                        if on_ack is not None:
                            await on_ack(data["subscription"], known)
                    elif channel == "pong":
                        pass
                    elif channel in {"allDexsClearinghouseState", "trades"}:
                        await handle(envelope, known, sha256(wire.encode()).hexdigest(), wire)
                    else:
                        raise ValueError("STREAM_NATIVE_CHANNEL_UNKNOWN")
                    last_valid_transport, last_known = monotonic(), known
                    stats["frames"] += 1
                finally:
                    queue.task_done()

        async def heartbeat():
            while not stop.is_set():
                if monotonic() - started > acknowledgement_timeout and acknowledged != expected:
                    raise ValueError("STREAM_NATIVE_ACK_TIMEOUT")
                if monotonic() - last_valid_transport > transport_timeout:
                    raise ValueError("STREAM_NATIVE_SILENT_TRANSPORT")
                if last_known is not None:
                    await on_transport(last_known)
                await ws.send('{"method":"ping"}')
                try:
                    await asyncio.wait_for(stop.wait(), timeout=min(10, transport_timeout / 3))
                except TimeoutError:
                    pass

        tasks = [
            asyncio.create_task(receiver()),
            asyncio.create_task(consumer()),
            asyncio.create_task(heartbeat()),
            asyncio.create_task(stop.wait()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not tasks[-1]:
                    await task
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    return {**stats, "acknowledged": len(acknowledged), "order_route": "NONE"}


async def wait_or_stop(stop: asyncio.Event, seconds: float):
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass
