"""Read-only CCXT Pro / Hyperliquid L2 market evidence for forward paper.

The public CCXT websocket is NOT a broker or independently signed price feed.
It supplies a locally first-known two-sided order-book snapshot only; best-level
depth is NOT historical traded volume.  In the absence of separately observed
completed trade capacity, modeled fills remain blocked (volume_base=None).

No credentials, user account endpoint, order API, fallback to retrospective
candles, worker activation or production service mutation exists in this module.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .pm03_account import Instrument, clock, digest, number

NATIVE_PREFIX = "hyperliquid/mainnet:perp:"
CCXT_EXCHANGE = "hyperliquid"
BOOK_QUALITY = "VERIFIED_QUOTE"
SCHEMA = "paper_ccxt_hyperliquid_l2_quote_v1"
CATALOG_SCHEMA = "paper_ccxt_hyperliquid_market_v1"
_PERP_SYMBOL = re.compile(r"^[A-Za-z0-9_.-]+$")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _positive(value: Any, *, reason: str) -> Decimal:
    try:
        x = number(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(reason) from exc
    if x <= 0:
        raise ValueError(reason)
    return x


@dataclass(frozen=True)
class NativeMarket:
    instrument: Instrument
    ccxt_symbol: str
    ccxt_id: str
    market_known_at: str
    amount_step: Decimal
    minimum_notional: Decimal
    active: bool
    hip3: bool
    catalog_sha: str

    @property
    def session_trust(self) -> str:
        # HIP-3 sessions vary with asset/deployer and require an independent
        # exchange/session attestation before simulated execution.
        return "UNKNOWN_HIP3_SESSION" if self.hip3 else "LIVE_DEFAULT_PERP_TWO_SIDED_ONLY"

    @property
    def session_eligible(self) -> bool:
        return self.active and not self.hip3


def parse_ccxt_market(
    market: Mapping[str, Any], *, first_known_at: str, expected: Instrument
) -> NativeMarket:
    """Resolve against exchange-native info.name, NEVER a numeric CCXT id.

    CCXT HIP-3 requires explicit fetchMarkets.hip3.dexes.  A unified
    'XYZ-BRENTOIL/USDC:USDC' symbol is not the canonical Hyperliquid
    'xyz:BRENTOIL' native name and cannot be guessed via string splitting.
    """
    clock(first_known_at)
    info = market.get("info")
    if not isinstance(info, dict):
        raise ValueError("CCXT_NATIVE_MARKET_METADATA_MISSING")
    native_name = info.get("name")
    if not isinstance(native_name, str) or not native_name:
        raise ValueError("CCXT_NATIVE_COIN_NAME_MISSING")
    if native_name.count(":") == 1:
        dex, token = native_name.split(":", 1)
        if (
            not _PERP_SYMBOL.fullmatch(dex)
            or not _PERP_SYMBOL.fullmatch(token)
            or info.get("dex") != dex
            or info.get("hip3") is not True
        ):
            raise ValueError("CCXT_HIP3_IDENTITY_UNATTESTED")
        inst = Instrument(CCXT_EXCHANGE, "mainnet:perp:" + dex, token)
        hip3 = True
    elif ":" not in native_name:
        if not _PERP_SYMBOL.fullmatch(native_name) or info.get("hip3") is True:
            raise ValueError("CCXT_MAIN_PERP_IDENTITY_UNATTESTED")
        if info.get("dex") not in (None, ""):
            raise ValueError("CCXT_MAIN_DEX_CONFLICT")
        inst = Instrument(CCXT_EXCHANGE, "mainnet:perp:default", native_name)
        hip3 = False
    else:
        raise ValueError("CCXT_NATIVE_MARKET_NAME_INVALID")

    if inst != expected:
        raise ValueError("CCXT_NATIVE_MARKET_ID_MISMATCH")
    if not all(
        [
            market.get("swap") is True,
            market.get("contract") is True,
            market.get("linear") is True,
            market.get("spot") is not True,
            market.get("settle") == "USDC",
            market.get("quote") == "USDC",
            market.get("type") == "swap",
        ]
    ):
        raise ValueError("CCXT_NON_PERP_OR_UNSUPPORTED_COLLATERAL")
    if market.get("active") is not True:
        raise ValueError("CCXT_MARKET_INACTIVE_OR_UNKNOWN")
    market_id = market.get("id")
    if not isinstance(market_id, str) or not market_id.isdecimal():
        raise ValueError("CCXT_MARKET_NUMERIC_ID_REQUIRED")
    if str(info.get("baseId")) != market_id:
        raise ValueError("CCXT_MARKET_ASSET_INDEX_MISMATCH")
    name = market.get("symbol")
    if not isinstance(name, str) or not name or market.get("base") is None:
        raise ValueError("CCXT_UNIFIED_MARKET_SYMBOL_MISSING")
    step = _positive(market.get("precision", {}).get("amount"), reason="CCXT_AMOUNT_STEP_UNKNOWN")
    min_notional = _positive(
        market.get("limits", {}).get("cost", {}).get("min"),
        reason="CCXT_MIN_NOTIONAL_UNKNOWN",
    )
    if info.get("szDecimals") is None:
        raise ValueError("CCXT_SIZE_DECIMALS_UNKNOWN")
    try:
        size_decimals = int(info["szDecimals"])
    except (ValueError, TypeError) as exc:
        raise ValueError("CCXT_SIZE_DECIMALS_UNKNOWN") from exc
    if size_decimals < 0 or size_decimals > 15 or step != Decimal("1").scaleb(-size_decimals):
        raise ValueError("CCXT_AMOUNT_STEP_CONFLICT")
    stable = {
        "schema": CATALOG_SCHEMA,
        "instrument": inst.key,
        "ccxt_symbol": name,
        "ccxt_market_id": market_id,
        "native_coin_name": native_name,
        "hip3": hip3,
        "amount_step": str(step),
        "minimum_notional": str(min_notional),
        "settlement": "USDC",
        "market_known_at": first_known_at,
        "session_trust": "UNKNOWN_HIP3_SESSION" if hip3 else "LIVE_DEFAULT_PERP_TWO_SIDED_ONLY",
    }
    return NativeMarket(
        instrument=inst,
        ccxt_symbol=name,
        ccxt_id=market_id,
        market_known_at=first_known_at,
        amount_step=step,
        minimum_notional=min_notional,
        active=True,
        hip3=hip3,
        catalog_sha=digest(stable),
    )


@dataclass(frozen=True)
class L2Quote:
    market: NativeMarket
    source_event_at: str
    source_timestamp_ms: int
    first_known_at: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    mid: Decimal
    spread_bps: Decimal
    book_sha: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "instrument": self.market.instrument.key,
            "ccxt_symbol": self.market.ccxt_symbol,
            "ccxt_market_id": self.market.ccxt_id,
            "source_event_at": self.source_event_at,
            "source_timestamp_ms": self.source_timestamp_ms,
            "first_known_at": self.first_known_at,
            "market_known_at": self.market.market_known_at,
            "best_bid": str(self.bid),
            "best_ask": str(self.ask),
            "bid_size": str(self.bid_size),
            "ask_size": str(self.ask_size),
            "mid_quote": str(self.mid),
            "observed_spread_bps": str(self.spread_bps),
            "catalog_sha": self.market.catalog_sha,
            "book_sha": self.book_sha,
            "volume_status": "UNKNOWN_BOOK_DEPTH_NOT_TRADED_VOLUME",
            "session_trust": self.market.session_trust,
            "source": "CCXT_PRO_HYPERLIQUID_PUBLIC_L2",
            "broker_order_route": "NONE",
            "provider_signed": False,
        }

    @property
    def quote_sha(self) -> str:
        return digest(self.payload())

    def observation(self) -> dict:
        """PM03 mark is an observed quote midpoint, NOT the exchange markPx."""
        return {
            "instrument": self.market.instrument.key,
            "event_at": self.source_event_at,
            "first_known_at": self.first_known_at,
            "mark": str(self.mid),
            "volume_base": None,
            "quality": BOOK_QUALITY,
            "supported": self.market.session_eligible,
        }

    def contract(self, *, costs: dict, as_of: str) -> dict:
        """Version modeled cost policy, observable spread and native lot gate.

        Does NOT claim HIP-3 session status, traded volume, funding or a
        particular executable fill price.
        """
        if clock(as_of) < clock(self.first_known_at):
            raise ValueError("CCXT_QUOTE_FUTURE_KNOWN")
        full_spread = _positive(costs.get("full_spread_bps"), reason="CCXT_COST_SPREAD_UNKNOWN")
        row = {
            "schema": "paper_market_contract_v1",
            "instrument": self.market.instrument.key,
            "quality": BOOK_QUALITY,
            "costs_sha": digest(costs),
            "session_open": self.market.session_eligible,
            "market_permitted": self.market.active,
            "first_known_at": self.first_known_at,
            "quote_source_event_at": self.source_event_at,
            "quote_sha": self.quote_sha,
            "provider_catalog_sha": self.market.catalog_sha,
            "quote_mid": str(self.mid),
            "observed_spread_bps": str(self.spread_bps),
            "modeled_spread_bps": str(full_spread),
            "quantity_step": str(self.market.amount_step),
            "minimum_quantity": str(self.market.amount_step),
            "minimum_notional": str(self.market.minimum_notional),
            "max_quote_age_seconds": 20,
            "session_trust": self.market.session_trust,
        }
        return {**row, "contract_sha": digest(row)}


def parse_ccxt_book(
    market: NativeMarket,
    book: Mapping[str, Any],
    *,
    first_known_at: str,
    max_age_seconds: int = 20,
    max_spread_bps: Decimal = Decimal("100"),
) -> L2Quote:
    now = clock(first_known_at)
    if clock(market.market_known_at) > now:
        raise ValueError("CCXT_BOOK_PRECEDES_MARKET_DISCOVERY")
    if book.get("symbol") not in (None, market.ccxt_symbol):
        raise ValueError("CCXT_BOOK_SYMBOL_MISMATCH")
    stamp = book.get("timestamp")
    if type(stamp) is not int or stamp <= 0:
        raise ValueError("CCXT_BOOK_EVENT_CLOCK_MISSING")
    try:
        source_at = datetime.fromtimestamp(stamp / 1000, tz=UTC).isoformat()
    except (OverflowError, ValueError) as exc:
        raise ValueError("CCXT_BOOK_EVENT_CLOCK_INVALID") from exc
    age = (now - clock(source_at)).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError("CCXT_BOOK_FUTURE_OR_STALE")
    bids = book.get("bids")
    asks = book.get("asks")
    if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
        raise ValueError("CCXT_BOOK_TWO_SIDED_REQUIRED")
    try:
        bid, bid_size = (
            _positive(bids[0][0], reason="CCXT_BID_INVALID"),
            _positive(bids[0][1], reason="CCXT_BID_SIZE_INVALID"),
        )
        ask, ask_size = (
            _positive(asks[0][0], reason="CCXT_ASK_INVALID"),
            _positive(asks[0][1], reason="CCXT_ASK_SIZE_INVALID"),
        )
    except (IndexError, TypeError, KeyError) as exc:
        raise ValueError("CCXT_BOOK_LEVELS_MALFORMED") from exc
    if bid >= ask:
        raise ValueError("CCXT_BOOK_LOCKED_OR_CROSSED")
    mid = (bid + ask) / 2
    spread_bps = (ask - bid) / mid * Decimal("10000")
    if spread_bps > max_spread_bps:
        raise ValueError("CCXT_BOOK_SPREAD_TOO_WIDE")
    raw_head = {
        "ccxt_symbol": market.ccxt_symbol,
        "timestamp": stamp,
        "bid": str(bid),
        "bid_size": str(bid_size),
        "ask": str(ask),
        "ask_size": str(ask_size),
    }
    return L2Quote(
        market=market,
        source_event_at=source_at,
        source_timestamp_ms=stamp,
        first_known_at=first_known_at,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        mid=mid,
        spread_bps=spread_bps,
        book_sha=digest(raw_head),
    )


def verify_l2_evidence(
    evidence: dict | None,
    contract: dict,
    observation: dict,
    *,
    decision_at: str,
) -> tuple[str, ...]:
    """Bind market contract and PM-03 observation to the captured L2 quote.

    Self-consistent hashes are only tamper checks on LOCAL evidence, never
    proof of an independent exchange signature or uninterrupted transport.
    """
    if not isinstance(evidence, dict):
        return ("MARKET_CCXT_L2_EVIDENCE_MISSING",)
    reasons: list[str] = []
    if (
        evidence.get("schema") != SCHEMA
        or evidence.get("source") != "CCXT_PRO_HYPERLIQUID_PUBLIC_L2"
    ):
        reasons.append("MARKET_CCXT_L2_SCHEMA_UNKNOWN")
    if evidence.get("broker_order_route") != "NONE" or evidence.get("provider_signed") is not False:
        reasons.append("MARKET_CCXT_L2_PROVENANCE_INVALID")
    if evidence.get("volume_status") != "UNKNOWN_BOOK_DEPTH_NOT_TRADED_VOLUME":
        reasons.append("MARKET_CCXT_L2_VOLUME_MISLABELED")
    if observation.get("volume_base") is not None:
        # This feed alone cannot attest traded volume. Another separately
        # authenticated trade-capacity receipt is mandatory for fills.
        reasons.append("MARKET_CCXT_L2_CAPACITY_NOT_PROVEN")
    if (
        contract.get("quote_sha") != digest(evidence)
        or contract.get("provider_catalog_sha") != evidence.get("catalog_sha")
        or contract.get("instrument") != evidence.get("instrument")
    ):
        reasons.append("MARKET_CCXT_L2_SHA_BINDING_MISMATCH")
    if (
        evidence.get("instrument") != observation.get("instrument")
        or evidence.get("source_event_at") != observation.get("event_at")
        or evidence.get("first_known_at") != observation.get("first_known_at")
        or observation.get("quality") != BOOK_QUALITY
    ):
        reasons.append("MARKET_CCXT_L2_OBSERVATION_MISMATCH")
    try:
        stamp = evidence["source_timestamp_ms"]
        if type(stamp) is not int or stamp <= 0:
            raise ValueError
        event_at = datetime.fromtimestamp(stamp / 1000, tz=UTC)
        if clock(evidence["source_event_at"]) != event_at:
            raise ValueError
        if not (
            clock(evidence["market_known_at"])
            <= clock(evidence["first_known_at"])
            <= clock(decision_at)
        ):
            raise ValueError
        if clock(evidence["source_event_at"]) > clock(evidence["first_known_at"]):
            raise ValueError
        age = (clock(decision_at) - clock(evidence["source_event_at"])).total_seconds()
        if age < 0 or age > 20:
            reasons.append("MARKET_CCXT_L2_STALE_AT_DECISION")
    except ValueError, TypeError, OverflowError, KeyError:
        reasons.append("MARKET_CCXT_L2_CLOCK_INVALID")
    try:
        bid = _positive(evidence["best_bid"], reason="INVALID_L2_BID")
        ask = _positive(evidence["best_ask"], reason="INVALID_L2_ASK")
        bid_size = _positive(evidence["bid_size"], reason="INVALID_L2_SIZE")
        ask_size = _positive(evidence["ask_size"], reason="INVALID_L2_SIZE")
        mid = _positive(evidence["mid_quote"], reason="INVALID_L2_MID")
        if bid >= ask or mid != (bid + ask) / 2:
            raise ValueError
        if mid != number(observation["mark"]) or mid != number(contract["quote_mid"]):
            reasons.append("MARKET_CCXT_L2_MARK_BINDING_MISMATCH")
        if number(evidence["observed_spread_bps"]) != (ask - bid) / mid * Decimal("10000"):
            reasons.append("MARKET_CCXT_L2_SPREAD_MISMATCH")
        raw_head = {
            "ccxt_symbol": evidence["ccxt_symbol"],
            "timestamp": evidence["source_timestamp_ms"],
            "bid": str(bid),
            "bid_size": str(bid_size),
            "ask": str(ask),
            "ask_size": str(ask_size),
        }
        if digest(raw_head) != evidence["book_sha"]:
            reasons.append("MARKET_CCXT_L2_BOOK_HASH_MISMATCH")
    except ValueError, KeyError, TypeError:
        reasons.append("MARKET_CCXT_L2_PRICE_INVALID")
    return tuple(sorted(set(reasons)))


class ReadOnlyCCXTProHyperliquid:
    """One-shot public L2 client; reconnects must create a NEW session.

    A per-instrument gap or provider error quarantines that instrument.
    Does not auto-backfill missed quotes or create a paper worker.
    """

    def __init__(
        self,
        requested: tuple[Instrument, ...],
        *,
        hip3_dexes: tuple[str, ...] = (),
        timeout_seconds: float = 15,
        max_age_seconds: int = 20,
        factory: Callable[..., Any] | None = None,
        rolling_trades: bool = False,
        now: Callable[[], str] = _now,
    ) -> None:
        if not requested or len(requested) != len(set(requested)):
            raise ValueError("CCXT_REQUESTED_MARKETS_MUST_BE_UNIQUE")
        if any(
            inst.venue != CCXT_EXCHANGE or not inst.market.startswith("mainnet:perp:")
            for inst in requested
        ):
            raise ValueError("CCXT_NATIVE_HYPERLIQUID_PERPS_ONLY")
        if any(not _PERP_SYMBOL.fullmatch(dex) or dex == "default" for dex in hip3_dexes):
            raise ValueError("CCXT_DEX_NAME_INVALID")
        required = {
            inst.market.split(":")[-1]
            for inst in requested
            if inst.market != "mainnet:perp:default"
        }
        if not required.issubset(hip3_dexes):
            raise ValueError("CCXT_HIP3_DEX_EXPLICIT_DISCOVERY_REQUIRED")
        if not 0 < timeout_seconds <= 60 or not 0 < max_age_seconds <= 120:
            raise ValueError("CCXT_FEED_TIMEOUT_OR_STALE_BOUND_INVALID")
        self.requested = requested
        self.hip3_dexes = tuple(sorted(set(hip3_dexes)))
        self.timeout_seconds = timeout_seconds
        self.max_age_seconds = max_age_seconds
        self._factory = factory
        self._rolling_trades = rolling_trades
        self._now = now
        self._exchange: Any = None
        self.catalog: dict[Instrument, NativeMarket] = {}
        self.blocked: dict[str, str] = {}
        self.quarantined: set[Instrument] = set()
        self._last: dict[Instrument, tuple[str, str]] = {}
        self._is_open = False

    async def open(self) -> dict:
        if self._is_open or self._exchange is not None:
            raise ValueError("CCXT_FEED_ALREADY_STARTED")
        make = self._factory
        if make is None:
            try:
                make = import_module("ccxt.pro").hyperliquid
            except ImportError as exc:
                raise ValueError("CCXT_PRO_OPTIONAL_EXTRA_NOT_INSTALLED") from exc
        # Do not pass API keys, authentication settings or private endpoint
        # options. load_markets() uses public REST to establish identity.
        config = {
            "enableRateLimit": True,
            "options": {
                "fetchMarkets": {
                    "types": ["swap", "hip3"] if self.hip3_dexes else ["swap"],
                    "hip3": {"dexes": list(self.hip3_dexes), "limit": len(self.hip3_dexes)},
                }
            },
        }
        if self._rolling_trades:
            config["newUpdates"] = False
            config["options"]["tradesLimit"] = 1000
        exchange = make(config)
        self._exchange = exchange
        try:
            caps = getattr(exchange, "has", {})
            if caps.get("watchOrderBook") is not True:
                raise ValueError("CCXT_EXCHANGE_WS_ORDERBOOK_UNSUPPORTED")
            markets = await asyncio.wait_for(exchange.load_markets(), self.timeout_seconds)
            known_at = self._now()
            # Match canonical native identifiers via the Hyperliquid native
            # coin name in info, never CCXT's numeric id or a string guess.
            for inst in self.requested:
                candidates = []
                for raw in markets.values():
                    info = raw.get("info", {})
                    raw_name = info.get("name") if isinstance(info, dict) else None
                    native = (
                        inst.symbol
                        if inst.market == "mainnet:perp:default"
                        else inst.market.split(":")[-1] + ":" + inst.symbol
                    )
                    if raw_name == native:
                        candidates.append(raw)
                if len(candidates) != 1:
                    self.blocked[inst.key] = "CCXT_NATIVE_MARKET_NOT_UNIQUELY_DISCOVERED"
                    continue
                try:
                    self.catalog[inst] = parse_ccxt_market(
                        candidates[0], first_known_at=known_at, expected=inst
                    )
                except ValueError as exc:
                    self.blocked[inst.key] = str(exc)
            self._is_open = True
            return self.status()
        except BaseException:
            await self.close()
            raise

    async def quote(self, instrument: Instrument) -> L2Quote:
        if not self._is_open or self._exchange is None:
            raise ValueError("CCXT_FEED_NOT_OPEN")
        if instrument in self.quarantined:
            raise ValueError("CCXT_MARKET_QUARANTINED_REBASELINE_REQUIRED")
        market = self.catalog.get(instrument)
        if market is None:
            raise ValueError("CCXT_NATIVE_MARKET_UNAVAILABLE")
        try:
            book = await asyncio.wait_for(
                self._exchange.watch_order_book(market.ccxt_symbol, 5), self.timeout_seconds
            )
            quote = parse_ccxt_book(
                market,
                book,
                first_known_at=self._now(),
                max_age_seconds=self.max_age_seconds,
            )
            previous = self._last.get(instrument)
            if previous is not None:
                last_event, last_sha = previous
                if clock(quote.source_event_at) < clock(last_event):
                    raise ValueError("CCXT_BOOK_SOURCE_CLOCK_REGRESSION")
                if quote.source_event_at == last_event and quote.book_sha == last_sha:
                    raise ValueError("CCXT_BOOK_DUPLICATE_NOT_NEW_EVIDENCE")
            self._last[instrument] = (quote.source_event_at, quote.book_sha)
            return quote
        except Exception:
            # Any timeout, reconnect or invalid provider book invalidates
            # source continuity until a NEW catalog+subscription session.
            self._last.pop(instrument, None)
            self.quarantined.add(instrument)
            raise

    def status(self) -> dict:
        return {
            "schema": "paper_ccxt_public_feed_status_v1",
            "exchange": CCXT_EXCHANGE,
            "connected": bool(self._last) and self._is_open,
            "metadata_loaded": self._is_open,
            "live_quote_verified": sorted(inst.key for inst in self._last),
            "transport_independently_attested": False,
            "catalogued": sorted(inst.key for inst in self.catalog),
            "blocked": dict(sorted(self.blocked.items())),
            "quarantined": sorted(inst.key for inst in self.quarantined),
            "source_account_complete": False,
            "trade_volume_complete": False,
            "order_route": "NONE",
            "paper_observed": False,
        }

    async def close(self) -> None:
        exchange = self._exchange
        self._exchange = None
        self._is_open = False
        self.catalog.clear()
        self._last.clear()
        if exchange is not None:
            await exchange.close()

    async def __aenter__(self) -> ReadOnlyCCXTProHyperliquid:
        await self.open()
        return self

    async def __aexit__(self, _type: object, _exc: object, _tb: object) -> None:
        await self.close()


class PersistentMarket:
    """Long-lived quote/trade projection; validation and receipt owners reused."""

    def __init__(self, journal, market: NativeMarket, *, scope_sha: str, max_cache: int = 1000):
        from .pm_forward_ccxt_trades import TradeWindow
        from .pm_forward_stream_journal import StreamProgress

        self.journal, self.market, self.scope_sha = journal, market, scope_sha
        self.max_cache = max_cache
        self.progress = {
            channel: StreamProgress(journal, prefix + market.instrument.key)
            for channel, prefix in (("quote", "ccxt_l2:"), ("trades", "ccxt_trades:"))
        }
        self.epochs = {}
        self.window = TradeWindow(market.instrument, market.ccxt_symbol, max_cache=max_cache)

    def begin(self, channel: str, known_at: str) -> dict:
        from uuid import uuid4
        from .pm_forward_ccxt_trades import TradeWindow

        progress, epoch = self.progress[channel], uuid4().hex
        state = {
            **progress.checkpoint,
            "baseline_valid": False,
            "transport": "CONNECTING",
            "scope_sha": self.scope_sha,
            "gap_reason": "NEW_CONNECTION_OR_CHANNEL_EPOCH",
        }
        event = progress.propose(
            epoch=epoch,
            kind="GAP",
            known_at=known_at,
            checkpoint=state,
            details={"reason": state["gap_reason"]},
        )
        result = progress.commit(event)
        self.epochs[channel] = epoch
        if channel == "trades":
            self.window = TradeWindow(
                self.market.instrument, self.market.ccxt_symbol, max_cache=self.max_cache
            )
            self.window.epoch = epoch
        return result

    def gap(self, channel: str, known_at: str, reason: str) -> dict:
        progress = self.progress[channel]
        state = {
            **progress.checkpoint,
            "baseline_valid": False,
            "transport": "DEGRADED",
            "gap_reason": reason,
        }
        return progress.commit(
            progress.propose(
                epoch=self.epochs[channel],
                kind="GAP",
                known_at=known_at,
                checkpoint=state,
                details={"reason": reason},
            )
        )

    def transport(self, channel: str, known_at: str) -> dict:
        progress = self.progress[channel]
        state = {**progress.checkpoint, "last_transport_at": known_at, "transport": "CONNECTED"}
        return progress.commit(
            progress.propose(
                epoch=self.epochs[channel],
                kind="TRANSPORT",
                known_at=known_at,
                checkpoint=state,
            )
        )

    def quote(self, book: dict, known_at: str) -> dict:
        quote = parse_ccxt_book(self.market, book, first_known_at=known_at)
        payload = quote.payload()
        progress = self.progress["quote"]
        prior = progress.checkpoint
        if prior.get("source_event_at"):
            if clock(quote.source_event_at) < clock(prior["source_event_at"]):
                raise ValueError("CCXT_BOOK_SOURCE_CLOCK_REGRESSION")
            if (
                quote.source_event_at == prior["source_event_at"]
                and quote.book_sha == prior["book_sha"]
            ):
                return {"status": "DUPLICATE_MARKET_QUOTE", "order_route": "NONE"}
        baseline = not prior.get("baseline_valid", False)
        state = {
            **prior,
            "baseline_valid": True,
            "transport": "CONNECTED",
            "last_transport_at": known_at,
            "last_quote_at": known_at,
            "source_event_at": quote.source_event_at,
            "book_sha": quote.book_sha,
            "quote_sha": digest(payload),
            "scope_sha": self.scope_sha,
        }
        event = progress.propose(
            epoch=self.epochs["quote"],
            kind="BASELINE" if baseline else "OBSERVATION",
            known_at=known_at,
            checkpoint=state,
            source_at=quote.source_event_at,
            raw_sha=quote.book_sha,
        )
        return progress.commit(
            event, lambda e: self.journal.append_market_quote(payload, stream_event=e)
        )

    def trades(
        self, cached: list[dict], known_at: str, *, first_known_by_id: dict | None = None
    ) -> dict:
        from copy import deepcopy

        # A candidate cache may mutate during validation; published state may not.
        candidate = deepcopy(self.window)
        normalized = [
            {**row, "id": str(row.get("id")) + "@" + str(row.get("timestamp"))} for row in cached
        ]
        if any(not isinstance(row.get("id"), str) or not row["id"] for row in cached):
            raise ValueError("CCXT_TRADE_NATIVE_ID_UNKNOWN")
        prior = self.progress["trades"].checkpoint
        if first_known_by_id is not None and prior.get("baseline_valid"):
            present = {row["id"] for row in normalized}
            if any(
                clock(at) > clock(prior["last_cache_at"]) and tid not in present
                for tid, at in first_known_by_id.items()
            ):
                raise ValueError("CCXT_NATIVE_CACHE_DROPPED_OBSERVED_TRADE")
        batch = candidate.process(normalized, first_known_at=known_at)
        if first_known_by_id is not None:
            for row in batch["trades"]:
                earliest = first_known_by_id.get(row["native_trade_id"])
                if earliest is None or not (
                    clock(row["source_event_at"]) <= clock(earliest) <= clock(known_at)
                ):
                    raise ValueError("CCXT_EARLIEST_LOCAL_RECEIPT_UNKNOWN")
                row["first_known_at"] = earliest
            batch["local_clock_semantics"] = "PER_NATIVE_TRADE_FIRST_RECEIPT"
        progress = self.progress["trades"]
        baseline = batch["status"] == "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
        state = {
            **progress.checkpoint,
            "baseline_valid": True,
            "transport": "CONNECTED",
            "last_transport_at": known_at,
            "last_cache_at": known_at,
            "last_trade_event_at": candidate._last_event,
            "cache_id_count": len(candidate._order),
            "cache_sha": digest(candidate._seen),
            "scope_sha": self.scope_sha,
            "trade_volume_complete": False,
        }
        event = progress.propose(
            epoch=self.epochs["trades"],
            kind="BASELINE" if baseline else "OBSERVATION",
            known_at=known_at,
            checkpoint=state,
            raw_sha=digest(cached),
        )
        progress.commit(
            event, lambda e: self.journal.append_market_trade_batch(batch, stream_event=e)
        )
        self.window = candidate
        return batch


class CCXTLocalReceiptClock:
    """Instrument pinned CCXT before JSON/provider normalization.

    CCXT 4.5.91 Client.handle_message receives the raw WS message. Retain the
    local timestamp there, then associate it with native book/trade identity
    in the exchange dispatch callback. A missing stamp is a coverage failure.
    """

    def __init__(self, exchange, *, now=_now, max_ids: int = 2000, limiter=None):
        from collections import OrderedDict
        from importlib.metadata import version
        from uuid import uuid4

        if version("ccxt") != "4.5.91":
            raise ValueError("CCXT_RECEIPT_CLOCK_VERSION_NOT_VERIFIED")
        self.now, self.max_ids = now, max_ids
        self.frames = {}
        self.trade_ids = {}
        self.clients = {}
        self._ordered = OrderedDict
        self._epoch = uuid4
        original_client = exchange.client
        original_dispatch = exchange.handle_message

        def client_for(url):
            client = original_client(url)
            if not getattr(client, "_observer_instrumented", False):
                client._observer_instrumented = True
                client._observer_epoch = uuid4().hex
                client._observer_wire_at = None
                original_handle = client.handle_message
                original_connected = client.on_connected_callback
                original_dial = client.create_connection

                async def dial(session):
                    if limiter is not None:
                        await limiter.acquire()
                    return await original_dial(session)

                def receive(message):
                    client._observer_wire_at = now()
                    return original_handle(message)

                def connected(current):
                    current._observer_epoch = uuid4().hex
                    return original_connected(current)

                client.handle_message = receive
                client.on_connected_callback = connected
                client.create_connection = dial
                self.clients[url] = client
            return client

        def dispatch(client, message):
            known = getattr(client, "_observer_wire_at", None)
            epoch = getattr(client, "_observer_epoch", None)
            if known is not None and epoch is not None:
                self.record(message, known, epoch)
            return original_dispatch(client, message)

        exchange.client = client_for
        exchange.handle_message = dispatch

    def record(self, message: dict, known_at: str, epoch: str):
        channel, data = message.get("channel"), message.get("data")
        if channel == "l2Book" and isinstance(data, dict):
            coin = data.get("coin")
            if isinstance(coin, str) and type(data.get("time")) is int:
                prior = self.frames.get(("quote", coin), {})
                self.frames[("quote", coin)] = {
                    "known_at": known_at,
                    "epoch": epoch,
                    "native_time": data["time"],
                    "dispatch_count": prior.get("dispatch_count", 0) + 1,
                }
        if channel == "trades" and isinstance(data, list):
            for row in data:
                if not isinstance(row, dict) or not isinstance(row.get("coin"), str):
                    continue
                coin, tid = row["coin"], str(row.get("tid")) + "@" + str(row.get("time"))
                cache = self.trade_ids.setdefault(coin, self._ordered())
                old = cache.get(tid)
                if old is None or old["epoch"] != epoch:
                    cache[tid] = {"known_at": known_at, "epoch": epoch}
                while len(cache) > self.max_ids:
                    cache.popitem(last=False)
                prior = self.frames.get(("trades", coin), {})
                self.frames[("trades", coin)] = {
                    "known_at": known_at,
                    "epoch": epoch,
                    "dispatch_count": prior.get("dispatch_count", 0) + 1,
                }

    def stamp(self, channel: str, coin: str, *, native_time: int | None = None) -> dict:
        row = self.frames.get((channel, coin))
        if row is None or (native_time is not None and row.get("native_time") != native_time):
            raise ValueError("CCXT_EARLIEST_LOCAL_RECEIPT_UNKNOWN")
        return dict(row)

    def trade_clocks(self, coin: str, epoch: str) -> dict:
        return {
            tid: row["known_at"]
            for tid, row in self.trade_ids.get(coin, {}).items()
            if row["epoch"] == epoch
        }

    def transport_at(self) -> str | None:
        # A connected flag alone is insufficient; require actual inbound frames
        # on the pinned CCXT client and let the independent watchdog age them.
        values = [
            c._observer_wire_at
            for c in self.clients.values()
            if getattr(c, "isConnected", False)
            and c._observer_wire_at is not None
            and not getattr(c, "error", None)
        ]
        return max(values, key=clock) if values else None


async def persistent_market_canary(
    instruments, *, root: Path, seconds: float, shared_ip_budget_checked: bool
) -> dict:
    """Bounded real transport probe; it does not resolve or select source wallets."""
    from .pm_forward_continuous import (
        SubscriptionBudget,
        _private_candidate_path,
        run_ccxt_markets,
        run_native_public,
        runtime_revision,
    )
    from .pm_forward_continuous_transport import SerialWriter, ConnectionBudget, wait_or_stop
    from .pm_forward_journal import PaperJournal
    from .pm_forward_observer import exclusive_observer_lease
    from .pm_forward_observer_health import _atomic_private_json
    from .pm_forward_public_trades import PersistentPublicMarket
    from .pm_forward_stream_journal import StreamProgress, verify_streams
    from time import monotonic

    if not shared_ip_budget_checked or not 2 <= seconds <= 300 or not 1 <= len(instruments) <= 5:
        raise ValueError("CONTINUOUS_CANARY_BUDGET_OR_DURATION_INVALID")
    _private_candidate_path(root, ())
    if root.exists():
        raise ValueError("CONTINUOUS_CANARY_REQUIRES_NEW_PRIVATE_ROOT")
    revision = runtime_revision()
    plan = SubscriptionBudget().plan(instruments, account_count=0)
    journal = PaperJournal(root)
    started, started_at = monotonic(), _now()
    with exclusive_observer_lease(journal):
        async with SerialWriter(max_pending=256) as writer:
            stop, limiter = asyncio.Event(), ConnectionBudget(per_minute=6)
            public = [
                PersistentPublicMarket(journal, item, {}, scope_sha=plan["scope_sha"])
                for item in instruments
            ]
            control = StreamProgress(journal, "observer:market_canary")
            from uuid import uuid4

            epoch = uuid4().hex
            await writer.submit(
                lambda: control.commit(
                    control.propose(
                        epoch=epoch,
                        kind="START",
                        known_at=started_at,
                        checkpoint={
                            "revision": revision,
                            "started_at": started_at,
                            "plan": plan,
                            "watched_wallet_count": 0,
                            "order_route": "NONE",
                        },
                    )
                )
            )
            jobs = [
                asyncio.create_task(
                    run_ccxt_markets(
                        instruments,
                        journal=journal,
                        writer=writer,
                        stop=stop,
                        now=_now,
                        scope_sha=plan["scope_sha"],
                        limiter=limiter,
                    )
                ),
                asyncio.create_task(
                    run_native_public(
                        public, writer=writer, stop=stop, connect=None, now=_now, limiter=limiter
                    )
                ),
            ]
            deadline = asyncio.create_task(wait_or_stop(stop, seconds))
            try:
                done, _ = await asyncio.wait([*jobs, deadline], return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
            finally:
                stop.set()
                deadline.cancel()
                for task in jobs:
                    task.cancel()
                outcomes = await asyncio.gather(*jobs, return_exceptions=True)
                await asyncio.gather(deadline, return_exceptions=True)
                for outcome in outcomes:
                    if isinstance(outcome, Exception):
                        raise outcome
                if writer.failed:
                    raise writer.failed
                await writer.submit(
                    lambda: control.commit(
                        control.propose(
                            epoch=epoch,
                            kind="STOP",
                            known_at=_now(),
                            checkpoint={**control.checkpoint, "stopped_at": _now()},
                        )
                    )
                )
    audit = verify_streams(journal.path)
    report = {
        "schema": "paper_persistent_market_canary_v1",
        "revision": revision,
        "started_at": started_at,
        "stopped_at": _now(),
        "elapsed_seconds": monotonic() - started,
        "journal_integrity": audit["integrity"],
        "stream_head_sha": audit["head_sha"],
        "scope": plan,
        "streams": {
            sid: {
                k: row[k]
                for k in (
                    "cursor",
                    "chain_sha",
                    "gap_count",
                    "baseline_count",
                    "observation_count",
                    "epoch_count",
                )
            }
            for sid, row in audit["streams"].items()
        },
        "watched_wallet_count": 0,
        "matched_wallet_fills": 0,
        "source_coverage": "NOT_REQUESTED_MARKET_TRANSPORT_PROBE",
        "source_nav_attested": False,
        "paper_observed": False,
        "order_route": "NONE",
    }
    _atomic_private_json(root, "persistent-market-canary.json", report)
    return report


async def _probe(
    insts: tuple[Instrument, ...],
    *,
    dexes: tuple[str, ...],
    timeout: float,
    record_root: Path | None = None,
) -> dict:
    journal = None
    if record_root is not None:
        from .pm_forward_journal import PaperJournal

        if not record_root.is_absolute() or any(
            part in {".devspace", ".git"} for part in record_root.resolve().parts
        ):
            raise ValueError("CCXT_PROBE_PERSISTENCE_MUST_BE_CANONICAL_PRIVATE_PATH")
        journal = PaperJournal(record_root)
    async with ReadOnlyCCXTProHyperliquid(insts, hip3_dexes=dexes, timeout_seconds=timeout) as feed:
        result = {"schema": "paper_ccxt_readonly_probe_v1", "status": feed.status(), "quotes": {}}
        for inst in insts:
            if inst not in feed.catalog:
                result["quotes"][inst.key] = {
                    "status": "BLOCKED",
                    "reason": feed.blocked.get(inst.key),
                }
                continue
            try:
                quote = await feed.quote(inst)
                result["quotes"][inst.key] = {
                    "status": "L2_ONLY_CAPACITY_UNKNOWN",
                    "quote": quote.payload(),
                    "quote_sha": quote.quote_sha,
                    "pm03_observation": quote.observation(),
                }
                if journal is not None:
                    result["quotes"][inst.key]["market_receipt"] = journal.append_market_quote(
                        quote.payload()
                    )
            except Exception as exc:
                result["quotes"][inst.key] = {
                    "status": "BLOCKED",
                    "reason": type(exc).__name__ + ":" + str(exc)[:120],
                }
        result["status"] = feed.status()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-shot CCXT Pro Hyperliquid read-only L2 canary; no broker or paper fills"
    )
    parser.add_argument("--instrument", action="append", required=True)
    parser.add_argument("--hip3-dex", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--record-root", type=Path)
    parser.add_argument("--continuous-canary-seconds", type=float)
    parser.add_argument("--ack-shared-ip-connection-budget", action="store_true")
    args = parser.parse_args()
    if args.continuous_canary_seconds is not None:
        if args.record_root is None:
            parser.error("--continuous-canary-seconds requires --record-root")
        print(
            json.dumps(
                asyncio.run(
                    persistent_market_canary(
                        tuple(Instrument.parse(x) for x in args.instrument),
                        root=args.record_root,
                        seconds=args.continuous_canary_seconds,
                        shared_ip_budget_checked=args.ack_shared_ip_connection_budget,
                    )
                ),
                sort_keys=True,
                indent=2,
            )
        )
        return
    if len(args.instrument) > 5:
        parser.error("one-shot canary limited to five markets")
    result = asyncio.run(
        _probe(
            tuple(Instrument.parse(inst) for inst in args.instrument),
            dexes=tuple(args.hip3_dex),
            timeout=args.timeout,
            record_root=args.record_root,
        )
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
