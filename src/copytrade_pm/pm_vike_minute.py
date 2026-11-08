"""Causal read-only Vike 1-minute trade-price observations.

The latest candle is not L2 liquidity. A forming candle's 'close' is the
latest trade as of REST receipt, never its eventual finalized close.
No historical/backfilled row may acquire a prospective first-known clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Mapping

from .pm03_account import Instrument, clock, digest, number

SCHEMA = "vike_perp_minute_price_observation_v1"
MAX_BAR_AGE_SECONDS = 120


def _positive(value: object, reason: str) -> Decimal:
    try:
        item = number(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(reason) from exc
    if item <= 0 or not item.is_finite():
        raise ValueError(reason)
    return item


def _nonnegative(value: object, reason: str) -> Decimal:
    try:
        item = number(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(reason) from exc
    if item < 0 or not item.is_finite():
        raise ValueError(reason)
    return item


def minute_observation(row: Mapping, *, received_at: str) -> dict:
    """Normalize one actual REST response row, preserving venue-native identity."""
    known = clock(received_at)
    if not isinstance(row, Mapping) or type(row.get("ts")) is not int:
        raise ValueError("VIKE_MINUTE_TIMESTAMP_INVALID")
    if row["ts"] <= 0 or row["ts"] % 60000:
        raise ValueError("VIKE_MINUTE_TIMESTAMP_NOT_ALIGNED")
    start = datetime.fromtimestamp(row["ts"] / 1000, UTC)
    end = start + timedelta(minutes=1)
    age = (known - start).total_seconds()
    if not 0 <= age <= MAX_BAR_AGE_SECONDS:
        raise ValueError("VIKE_MINUTE_FUTURE_OR_STALE")
    symbol, dex = row.get("symbol"), row.get("dex")
    if (
        not isinstance(symbol, str)
        or not symbol
        or len(symbol) > 32
        or not isinstance(dex, str)
        or not dex
        or len(dex) > 16
        or row.get("kind", "perp") not in ("perp", None)
    ):
        raise ValueError("VIKE_MINUTE_NATIVE_MARKET_INVALID")
    if symbol.startswith("#"):
        raise ValueError("VIKE_MINUTE_OUTCOME_NOT_PERP")
    prices = {
        name: _positive(row.get(name), "VIKE_MINUTE_PRICE_INVALID")
        for name in ("open", "high", "low", "close")
    }
    if not (
        prices["low"] <= prices["open"] <= prices["high"]
        and prices["low"] <= prices["close"] <= prices["high"]
    ):
        raise ValueError("VIKE_MINUTE_OHLC_INCONSISTENT")
    volume = _nonnegative(row.get("volume"), "VIKE_MINUTE_VOLUME_INVALID")
    volume_usd = _nonnegative(row.get("volume_usd"), "VIKE_MINUTE_VOLUME_INVALID")
    trades = row.get("n_trades")
    if type(trades) is not int or trades < 0:
        raise ValueError("VIKE_MINUTE_TRADE_COUNT_INVALID")
    if (volume == 0) != (trades == 0):
        raise ValueError("VIKE_MINUTE_VOLUME_TRADE_CONFLICT")
    # Do not extrapolate a 1-minute trading volume to instantaneous order depth.
    forming = known < end
    if dex == "HL":
        if ":" in symbol:
            raise ValueError("VIKE_MINUTE_CORE_SYMBOL_HAS_DEX_PREFIX")
        native = symbol
    elif ":" in symbol:
        prefix, token = symbol.split(":", 1)
        if prefix.lower() != dex.lower() or not token or ":" in token:
            raise ValueError("VIKE_MINUTE_HIP3_PREFIX_MISMATCH")
        native = dex.lower() + ":" + token
    else:
        native = f"{dex.lower()}:{symbol}"
    record = {
        "schema": SCHEMA,
        "provider": "VIKE_HYPERLIQUID_1M_FILLS_ROLLUP",
        "native_symbol": native,
        "dex": dex,
        "symbol": symbol,
        "bar_start_at": start.isoformat(),
        "bar_end_at": end.isoformat(),
        "first_known_at": known.isoformat(),
        "price": str(prices["close"]),
        "price_semantics": "LAST_OBSERVED_TRADE_AS_OF_RECEIPT" if forming else "FINAL_BAR_CLOSE",
        "forming": forming,
        "volume_base": str(volume),
        "volume_usd": str(volume_usd),
        "n_trades": trades,
        "execution_liquidity_verified": False,
        "order_route": "NONE",
    }
    record["observation_sha"] = digest(record)
    return record


def validate_observation(observation: Mapping) -> None:
    """Reject tampered, malformed or causally impossible durable minute prices."""
    if not isinstance(observation, Mapping) or observation.get("schema") != SCHEMA:
        raise ValueError("VIKE_MINUTE_STORED_SCHEMA_INVALID")
    if digest({k: v for k, v in observation.items() if k != "observation_sha"}) != (
        observation.get("observation_sha")
    ):
        raise ValueError("VIKE_MINUTE_STORED_HASH_INVALID")
    start, end, known = (
        clock(observation[key]) for key in ("bar_start_at", "bar_end_at", "first_known_at")
    )
    if end - start != timedelta(minutes=1):
        raise ValueError("VIKE_MINUTE_STORED_INTERVAL_INVALID")
    if not 0 <= (known - start).total_seconds() <= MAX_BAR_AGE_SECONDS:
        raise ValueError("VIKE_MINUTE_STORED_CLOCK_INVALID")
    forming = known < end
    if observation.get("forming") is not forming or observation.get("price_semantics") != (
        "LAST_OBSERVED_TRADE_AS_OF_RECEIPT" if forming else "FINAL_BAR_CLOSE"
    ):
        raise ValueError("VIKE_MINUTE_STORED_FORMING_SEMANTICS_INVALID")
    symbol, dex = observation.get("symbol"), observation.get("dex")
    if not isinstance(symbol, str) or not isinstance(dex, str):
        raise ValueError("VIKE_MINUTE_STORED_IDENTITY_INVALID")
    if dex == "HL":
        expected = symbol
        if ":" in symbol:
            raise ValueError("VIKE_MINUTE_STORED_IDENTITY_INVALID")
    elif ":" in symbol:
        prefix, token = symbol.split(":", 1)
        if prefix.lower() != dex.lower() or not token or ":" in token:
            raise ValueError("VIKE_MINUTE_STORED_IDENTITY_INVALID")
        expected = f"{dex.lower()}:{token}"
    else:
        expected = f"{dex.lower()}:{symbol}"
    if observation.get("native_symbol") != expected:
        raise ValueError("VIKE_MINUTE_STORED_IDENTITY_INVALID")
    native_instrument(expected)
    _positive(observation.get("price"), "VIKE_MINUTE_STORED_PRICE_INVALID")
    _nonnegative(observation.get("volume_base"), "VIKE_MINUTE_STORED_VOLUME_INVALID")
    if observation.get("execution_liquidity_verified") is not False:
        raise ValueError("VIKE_MINUTE_STORED_LIQUIDITY_CLAIM_FORBIDDEN")
    if observation.get("order_route") != "NONE":
        raise ValueError("VIKE_MINUTE_STORED_ORDER_ROUTE_FORBIDDEN")


def native_instrument(native: str) -> str:
    """Map a native Hyperliquid perp name without losing its HIP-3 DEX."""
    if not isinstance(native, str) or not native or native.startswith("#"):
        raise ValueError("VIKE_MINUTE_NATIVE_MARKET_INVALID")
    if ":" in native:
        dex, symbol = native.split(":", 1)
        if not dex or not symbol or ":" in symbol:
            raise ValueError("VIKE_MINUTE_NATIVE_MARKET_INVALID")
        return Instrument("hyperliquid", "mainnet:perp:" + dex, symbol).key
    return Instrument("hyperliquid", "mainnet:perp:default", native).key


def minute_latest(doc: Mapping, *, received_at: str) -> dict[str, dict]:
    """Return valid native perp markets; never silently reinterpret outcome rows."""
    if not isinstance(doc, Mapping) or doc.get("interval") != "1m" or doc.get("market") != "perp":
        raise ValueError("VIKE_MINUTE_RESPONSE_SCOPE_INVALID")
    candles = doc.get("candles")
    if not isinstance(candles, list):
        raise ValueError("VIKE_MINUTE_RESPONSE_CANDLES_INVALID")
    result: dict[str, dict] = {}
    for row in candles:
        if not isinstance(row, dict) or row.get("kind") not in (None, "perp"):
            continue
        try:
            observation = minute_observation(row, received_at=received_at)
        except ValueError:
            continue
        key = observation["native_symbol"]
        if key in result:
            raise ValueError("VIKE_MINUTE_DUPLICATE_NATIVE_MARKET")
        result[key] = observation
    return result


class EstimatedMinuteExecutionModel:
    """One modeled order, with conservative costs and bounded minute participation.

    This estimate is NOT a broker fill, verified executable depth or permission
    to trade. Unknown volume/size capacity is unpriceable, especially on exits.
    """

    def __init__(
        self,
        *,
        taker_fee_bps: Decimal = Decimal("5"),
        half_spread_bps: Decimal = Decimal("4"),
        slippage_bps: Decimal = Decimal("8"),
        max_participation: Decimal = Decimal("0.1"),
        impact_bps_at_cap: Decimal = Decimal("10"),
    ) -> None:
        self.fee = number(taker_fee_bps)
        self.spread = number(half_spread_bps)
        self.slippage = number(slippage_bps)
        self.cap = number(max_participation)
        self.impact = number(impact_bps_at_cap)
        if any(x < 0 for x in (self.fee, self.spread, self.slippage, self.impact)) or not Decimal(
            "0"
        ) < self.cap <= Decimal("1"):
            raise ValueError("VIKE_MINUTE_ESTIMATE_PARAMETERS_INVALID")

    def price(
        self,
        quantity: Decimal,
        observation: Mapping,
        *,
        step: Decimal,
        minimum_notional: Decimal,
        decision_at: str,
    ) -> dict:
        if observation.get("schema") != SCHEMA:
            raise ValueError("VIKE_MINUTE_EXECUTION_REQUIRES_EXPLICIT_PRICE_SCHEMA")
        if digest(
            {k: v for k, v in observation.items() if k != "observation_sha"}
        ) != observation.get("observation_sha"):
            raise ValueError("VIKE_MINUTE_OBSERVATION_HASH_MISMATCH")
        decision = clock(decision_at)
        received = clock(observation["first_known_at"])
        if not 0 <= (decision - received).total_seconds() <= MAX_BAR_AGE_SECONDS:
            return {"status": "UNPRICEABLE_STALE_OR_FUTURE"}
        if (
            observation["forming"]
            and observation["price_semantics"] != "LAST_OBSERVED_TRADE_AS_OF_RECEIPT"
        ):
            raise ValueError("VIKE_MINUTE_FORMING_FUTURE_CLOSE_FORBIDDEN")
        qty, step, minimum = number(quantity), number(step), number(minimum_notional)
        if not qty or step <= 0 or minimum <= 0:
            return {"status": "REJECTED_NATIVE_AMOUNT"}
        if abs(qty) % step:
            return {"status": "REJECTED_NATIVE_STEP"}
        price = _positive(observation["price"], "VIKE_MINUTE_PRICE_INVALID")
        volume = _nonnegative(observation["volume_base"], "VIKE_MINUTE_VOLUME_INVALID")
        if not volume or abs(qty) > volume * self.cap:
            return {
                "status": "UNPRICEABLE_CAPACITY_NOT_VERIFIED",
                "minute_volume_base": str(volume),
                "max_participation": str(self.cap),
            }
        if abs(qty) * price < minimum:
            return {"status": "REJECTED_MIN_NOTIONAL"}
        direction = Decimal("1") if qty > 0 else Decimal("-1")
        participation = abs(qty) / volume
        costs_bps = self.spread + self.slippage + self.impact * participation / self.cap
        modeled_price = (
            price * (Decimal("1") + direction * costs_bps / Decimal("10000"))
        ).quantize(Decimal("0.00000001"))
        fee = (abs(qty * modeled_price) * self.fee / Decimal("10000")).quantize(
            Decimal("0.00000001")
        )
        return {
            "status": "FILLED",
            "quantity": str(qty),
            "vwap": str(modeled_price),
            "fee": str(fee),
            "modeled_only": True,
            "real_order_count": 0,
            "single_market_intent": True,
            "execution_evidence": "ESTIMATED_EXECUTION",
            "liquidity_verified": False,
            "price_observation_sha": observation["observation_sha"],
            "cost_bps_ex_fee": str(costs_bps),
            "participation": str(participation),
        }
