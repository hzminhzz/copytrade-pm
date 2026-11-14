"""Read-only first-local CCXT Pro Hyperliquid trade observations.

CCXT Pro watch_trades returns a rolling cache, NOT a new-trades-only stream.
The first cache window is baseline-only; subsequent events are deduplicated
by native trade id. No interval is promoted to complete executable volume:
a client stream lacks native sequence guarantees and reconnect spans are gaps.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable, Mapping
from uuid import uuid4

from .pm03_account import Instrument, clock, digest, number
from .pm_forward_ccxt_market import ReadOnlyCCXTProHyperliquid


def _millis(value: Any) -> str:
    if type(value) is not int or value <= 0:
        raise ValueError("CCXT_TRADE_SOURCE_TIMESTAMP_REQUIRED")
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    except (ValueError, OverflowError) as exc:
        raise ValueError("CCXT_TRADE_SOURCE_TIMESTAMP_INVALID") from exc


class TradeWindow:
    """Ephemeral single-subscription epoch; any integrity failure quarantines."""

    def __init__(self, instrument: Instrument, ccxt_symbol: str, *, max_cache: int = 1000):
        if max_cache < 2:
            raise ValueError("CCXT_TRADE_CACHE_BOUND_INVALID")
        self.instrument = instrument
        self.ccxt_symbol = ccxt_symbol
        self.epoch = uuid4().hex
        self._cache_limit = max_cache
        self._seen: dict[str, str] = {}
        self._order: deque[str] = deque()
        self._initialized = False
        self._last_event: str | None = None
        self._last_known: str | None = None
        self.quarantined = False
        self.receipts = 0
        self.unique_count = 0
        self.observed_volume = Decimal("0")

    def _parse(self, item: Mapping[str, Any], *, first_known_at: str) -> dict:
        if item.get("symbol") != self.ccxt_symbol:
            raise ValueError("CCXT_TRADE_SYMBOL_MISMATCH")
        native_id = item.get("id")
        if not isinstance(native_id, str) or not native_id or len(native_id) > 180:
            raise ValueError("CCXT_TRADE_NATIVE_ID_UNKNOWN")
        event_at = _millis(item.get("timestamp"))
        if clock(event_at) > clock(first_known_at):
            raise ValueError("CCXT_TRADE_FUTURE_EVENT")
        try:
            price, amount = number(item["price"]), number(item["amount"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("CCXT_TRADE_PRICE_OR_AMOUNT_UNKNOWN") from exc
        if price <= 0 or amount <= 0:
            raise ValueError("CCXT_TRADE_NONPOSITIVE_PRICE_OR_AMOUNT")
        side = item.get("side")
        if side not in ("buy", "sell"):
            raise ValueError("CCXT_TRADE_SIDE_UNKNOWN")
        return {
            "native_trade_id": native_id,
            "instrument": self.instrument.key,
            "source_event_at": event_at,
            "source_timestamp_ms": item["timestamp"],
            "first_known_at": first_known_at,
            "price": str(price),
            "amount_base": str(amount),
            "aggressor_side": side,
            "source": "CCXT_PRO_HYPERLIQUID_PUBLIC_TRADES",
            "provider_signed": False,
            "broker_order_route": "NONE",
        }

    def process(self, trades: list[Mapping[str, Any]], *, first_known_at: str) -> dict:
        clock(first_known_at)
        if self.quarantined:
            raise ValueError("CCXT_TRADE_STREAM_QUARANTINED_REBASELINE_REQUIRED")
        try:
            if not isinstance(trades, list):
                raise ValueError("CCXT_TRADE_CACHE_SHAPE_UNKNOWN")
            if self._last_known is not None and clock(first_known_at) < clock(self._last_known):
                raise ValueError("CCXT_TRADE_LOCAL_CLOCK_REGRESSION")
            self._last_known = first_known_at
            rows = [self._parse(raw, first_known_at=first_known_at) for raw in trades]
            if len(rows) > self._cache_limit:
                raise ValueError("CCXT_TRADE_CACHE_OVERFLOW")
            # Same trade id must always identify the same immutable exchange event.
            # Do not bind first_known into a trade's native identity.
            next_rows: list[dict] = []
            seen_this_batch: dict[str, str] = {}
            for row in rows:
                identity = {k: v for k, v in row.items() if k != "first_known_at"}
                native_sha = digest(identity)
                trade_id = row["native_trade_id"]
                if (trade_id in seen_this_batch and seen_this_batch[trade_id] != native_sha) or (
                    trade_id in self._seen and self._seen[trade_id] != native_sha
                ):
                    raise ValueError("CCXT_TRADE_IDENTITY_CONFLICT")
                is_new = trade_id not in self._seen and trade_id not in seen_this_batch
                seen_this_batch[trade_id] = native_sha
                if is_new:
                    if (
                        self._initialized
                        and self._last_event is not None
                        and clock(row["source_event_at"]) < clock(self._last_event)
                    ):
                        raise ValueError("CCXT_TRADE_NEW_ID_CLOCK_REGRESSION")
                    next_rows.append(row)
            # The first CCXT cache window may contain retrospective trades
            # not observed locally at actual event time. Label as baseline.
            baseline = not self._initialized
            if not baseline and len(rows) == self._cache_limit and self._seen:
                # Full rotating cache no longer overlaps our previous ids.
                if not any(row["native_trade_id"] in self._seen for row in rows):
                    raise ValueError("CCXT_TRADE_CACHE_CONTINUITY_LOST")
            for row in rows:
                identity = {k: v for k, v in row.items() if k != "first_known_at"}
                native_sha = digest(identity)
                trade_id = row["native_trade_id"]
                if trade_id not in self._seen:
                    self._seen[trade_id] = native_sha
                    self._order.append(trade_id)
                    if self._last_event is None or clock(row["source_event_at"]) > clock(
                        self._last_event
                    ):
                        self._last_event = row["source_event_at"]
            while len(self._order) > self._cache_limit * 2:
                old = self._order.popleft()
                self._seen.pop(old, None)
            self._initialized = True
            accepted = [] if baseline else next_rows
            added = sum((number(row["amount_base"]) for row in accepted), Decimal("0"))
            self.observed_volume += added
            self.unique_count += len(accepted)
            self.receipts += 1
            result = {
                "schema": "paper_ccxt_trade_cache_observation_v1",
                "instrument": self.instrument.key,
                "stream_epoch": self.epoch,
                "first_known_at": first_known_at,
                "status": "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
                if baseline
                else "PARTIAL_LOCAL_TRADES",
                "native_cache_rows": len(rows),
                "new_local_trade_count": len(accepted),
                "observed_volume_base": str(added),
                "cumulative_local_volume_base": str(self.observed_volume),
                "trades": accepted,
                "first_cache_window_excluded": True,
                "trade_volume_complete": False,
                "executable_volume_base": None,
                "coverage_reason": "NO_EXCHANGE_TRADE_SEQUENCE_ATTESTATION",
                "broker_order_route": "NONE",
                "paper_observed": False,
            }
            return result
        except ValueError, TypeError, KeyError:
            self.quarantined = True
            raise

    def status(self) -> dict:
        return {
            "schema": "paper_ccxt_trade_window_status_v1",
            "instrument": self.instrument.key,
            "stream_epoch": self.epoch,
            "quarantined": self.quarantined,
            "initialized": self._initialized,
            "last_trade_event_at": self._last_event,
            "last_received_at": self._last_known,
            "observed_volume_lower_bound": str(self.observed_volume),
            "trade_volume_complete": False,
            "order_route": "NONE",
        }


class ReadOnlyTradeObserver:
    """Use the already-public, open CCXT client. No private requests or orders."""

    def __init__(
        self,
        feed: ReadOnlyCCXTProHyperliquid,
        *,
        now: Callable[[], str],
        max_cache: int = 1000,
    ):
        self.feed = feed
        self.now = now
        self.max_cache = max_cache
        self.windows: dict[Instrument, TradeWindow] = {}

    async def observe(self, instrument: Instrument) -> dict:
        if not self.feed.is_open:
            raise ValueError("CCXT_FEED_NOT_OPEN")
        if instrument in self.feed.quarantined:
            raise ValueError("CCXT_MARKET_QUARANTINED_REBASELINE_REQUIRED")
        market = self.feed.catalog.get(instrument)
        if market is None:
            raise ValueError("CCXT_NATIVE_MARKET_UNAVAILABLE")
        if not self.feed.supports_trades_ws:
            raise ValueError("CCXT_TRADES_WS_UNSUPPORTED")
        window = self.windows.setdefault(
            instrument, TradeWindow(instrument, market.ccxt_symbol, max_cache=self.max_cache)
        )
        try:
            cached = await asyncio.wait_for(
                self.feed.watch_raw_trades(market.ccxt_symbol, None, self.max_cache),
                timeout=self.feed.timeout_seconds,
            )
            return window.process(list(cached), first_known_at=self.now())
        except Exception:
            window.quarantined = True
            self.feed.quarantined.add(instrument)
            raise
