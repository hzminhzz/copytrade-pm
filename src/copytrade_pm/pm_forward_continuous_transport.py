"""Bounded serial journal writes that drain admitted work through cancellation."""

from __future__ import annotations

import asyncio
import sqlite3
from time import monotonic

from typing import Any, Callable, Self


async def _complete_admitted(future: asyncio.Future[Any]) -> Any:
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

    def __init__(self, *, max_pending: int = 256) -> None:
        if type(max_pending) is not int or not 1 <= max_pending <= 4096:
            raise ValueError("STREAM_WRITER_QUEUE_BOUND_INVALID")
        self.queue: asyncio.Queue[tuple[Callable[[], Any], asyncio.Future[Any]] | None] = (
            asyncio.Queue(max_pending)
        )
        self.failed: Exception | None = None
        self.high_water = 0
        self.write_count = 0
        self.write_failures = 0
        self.write_max_ms = 0.0
        self.write_total_ms = 0.0
        self.task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        self.task = asyncio.create_task(self._run(), name="observer-sqlite-writer")
        return self

    async def _run(self) -> None:
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

    async def submit(self, function: Callable[[], Any]) -> Any:
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

    async def __aexit__(self, *_: object) -> None:
        async def close() -> None:
            await self.queue.join()
            await self.queue.put(None)
            if self.task is not None:
                await self.task

        await _complete_admitted(asyncio.create_task(close()))
