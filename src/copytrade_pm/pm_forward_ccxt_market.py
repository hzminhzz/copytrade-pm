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
    args = parser.parse_args()
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
