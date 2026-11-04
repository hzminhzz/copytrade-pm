"""Bounded read-only Hyperliquid public quote+trade capture for paper research.

One CCXT Pro session handles per-market websocket L2 and trade-cache tasks.
It does NOT subscribe to private wallets, start a background service, set
execution volume, simulate fills, or emit a paper RUNNING status.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import json
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from .pm03_account import Instrument
from .pm_forward_ccxt_market import ReadOnlyCCXTProHyperliquid, _now
from .pm_forward_ccxt_trades import ReadOnlyTradeObserver
from .pm_forward_journal import PaperJournal


class BoundedMarketCapture:
    def __init__(
        self,
        requested: tuple[Instrument, ...],
        *,
        journal: PaperJournal,
        hip3_dexes: tuple[str, ...] = (),
        factory: Callable[..., Any] | None = None,
        now: Callable[[], str] = _now,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not 1 <= len(requested) <= 10:
            raise ValueError("CCXT_STREAM_PROBE_LIMIT_TEN_MARKETS")
        self.requested = requested
        self.journal = journal
        self.feed = ReadOnlyCCXTProHyperliquid(
            requested,
            hip3_dexes=hip3_dexes,
            factory=factory,
            now=now,
            timeout_seconds=timeout_seconds,
        )
        self.now = now

    async def run(
        self,
        *,
        duration_seconds: float = 10,
        max_updates_per_channel: int = 15,
    ) -> dict:
        if not (0.5 <= duration_seconds <= 120):
            raise ValueError("CCXT_STREAM_DURATION_OUTSIDE_BOUNDED_WINDOW")
        if not 1 <= max_updates_per_channel <= 1000:
            raise ValueError("CCXT_STREAM_CAPTURE_BUDGET_INVALID")
        counters: dict[str, dict[str, int]] = defaultdict(
            lambda: {"quote": 0, "trade": 0, "trade_baseline": 0}
        )
        failures: dict[str, list[str]] = defaultdict(list)
        trade_observer = ReadOnlyTradeObserver(self.feed, now=self.now)
        write_lock = asyncio.Lock()
        try:
            await self.feed.open()
            until = monotonic() + duration_seconds

            async def watch(inst: Instrument, channel: str) -> None:
                for _ in range(max_updates_per_channel):
                    if monotonic() >= until:
                        break
                    try:
                        # Bound even if a CCXT exchange ignores the requested
                        # timeout. Never swallow CancellationError.
                        remaining = max(0.01, until - monotonic())
                        if channel == "quote":
                            value = await asyncio.wait_for(self.feed.quote(inst), timeout=remaining)
                            async with write_lock:
                                result = await asyncio.to_thread(
                                    self.journal.append_market_quote, value.payload()
                                )
                            if result["status"] == "RECORDED_L2_ONLY_CAPACITY_UNKNOWN":
                                counters[inst.key]["quote"] += 1
                        else:
                            batch = await asyncio.wait_for(
                                trade_observer.observe(inst), timeout=remaining
                            )
                            async with write_lock:
                                result = await asyncio.to_thread(
                                    self.journal.append_market_trade_batch, batch
                                )
                            if result["status"] == "RECORDED_PARTIAL_TRADES_ONLY":
                                counters[inst.key]["trade"] += batch["new_local_trade_count"]
                                counters[inst.key]["trade_baseline"] += (
                                    batch["status"] == "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
                                )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        # A stream fault terminates that instrument's channel
                        # and cannot silently be treated as a healthy feed.
                        failures[inst.key].append(
                            channel + ":" + type(exc).__name__ + ":" + str(exc)[:120]
                        )
                        break

            tasks = [
                asyncio.create_task(watch(inst, channel), name=f"readonly-{channel}-{inst.key}")
                for inst in self.requested
                if inst in self.feed.catalog
                for channel in ("quote", "trade")
            ]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks), timeout=max(0.1, until - monotonic())
                )
            except TimeoutError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            return {
                "schema": "paper_ccxt_public_bounded_capture_v1",
                "observed_at": self.now(),
                "duration_budget_seconds": duration_seconds,
                "market_catalog": self.feed.status(),
                "receipt_counts": dict(counters),
                "stream_failures": dict(failures),
                "market_quote_tapes": {
                    inst.key: self.journal.market_quote_status(inst.key)
                    for inst in self.requested
                    if inst in self.feed.catalog
                },
                "market_trade_tapes": {
                    inst.key: self.journal.market_trade_status(inst.key)
                    for inst in self.requested
                    if inst in self.feed.catalog
                },
                "continuous_24h_feed_verified": False,
                "trade_volume_complete": False,
                "executable_volume_base": None,
                "source_wallet_equity_attested": False,
                "market_observed_only": True,
                "paper_observed": False,
                "order_route": "NONE",
            }
        finally:
            await self.feed.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded read-only CCXT public quotes/trades; NO paper fills or broker"
    )
    parser.add_argument("--instrument", action="append", required=True)
    parser.add_argument("--hip3-dex", action="append", default=[])
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=10)
    parser.add_argument("--max-updates", type=int, default=15)
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        part in {".devspace", ".git"} for part in args.state_root.resolve().parts
    ):
        parser.error("state root must be an absolute private non-worktree path")
    collector = BoundedMarketCapture(
        tuple(Instrument.parse(item) for item in args.instrument),
        journal=PaperJournal(args.state_root),
        hip3_dexes=tuple(args.hip3_dex),
    )
    result = asyncio.run(
        collector.run(
            duration_seconds=args.duration_seconds,
            max_updates_per_channel=args.max_updates,
        )
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
