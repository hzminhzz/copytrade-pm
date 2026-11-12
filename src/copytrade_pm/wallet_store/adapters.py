"""Source-specific adapters to canonical wallet data models.

Exposes exactly three entry points for fills — from_hyperx_camel,
from_hyperx_snake, from_vike — each an explicit field map with exact Decimal parsing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .schema import DexLiteral, Fill, SourceLiteral


def to_decimal(val: Any) -> Decimal:
    """Parse exact Decimal from str, int, float, or Decimal."""
    if val is None:
        raise ValueError("Cannot convert None to Decimal")
    if isinstance(val, Decimal):
        return val
    # If string or int, convert directly to preserve exact representation
    if isinstance(val, (str, int)):
        return Decimal(str(val))
    # Float: convert string representation of float to Decimal
    if isinstance(val, float):
        return Decimal(str(val))
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {val!r}") from exc


def to_utc_datetime(val: Any) -> datetime:
    """Convert int/float epoch ms or ISO-8601 string or datetime to UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        # Epoch milliseconds
        return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
    if isinstance(val, str):
        val_str = val.strip()
        # Check if digits (epoch ms as string)
        if val_str.isdigit():
            return datetime.fromtimestamp(int(val_str) / 1000.0, tz=timezone.utc)
        # Parse ISO format
        # Replace Z with +00:00 for fromisoformat compatibility
        clean_str = val_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise ValueError(f"Cannot parse datetime from: {val!r}")


def parse_dex(symbol: str, raw_dex: str | None = None) -> DexLiteral:
    """Determine DEX name: SPOT for @/#, prefix for colon, HL for main-dex."""
    if symbol.startswith("@") or symbol.startswith("#"):
        return "SPOT"
    if raw_dex:
        clean = raw_dex.strip().upper()
        if clean in ("HL", "XYZ", "SPOT", "UNKNOWN", "PARA", "IO", "MKTS", "HYNA"):
            return clean  # type: ignore[return-value]
    if ":" in symbol:
        prefix = symbol.split(":", 1)[0].upper()
        if prefix in ("HL", "XYZ", "SPOT", "UNKNOWN", "PARA", "IO", "MKTS", "HYNA"):
            return prefix  # type: ignore[return-value]
        return "XYZ" if prefix == "XYZ" else "UNKNOWN"
    return "HL"


def normalize_side(side: str) -> str:
    """Normalize side: B -> buy, A -> sell, buy -> buy, sell -> sell."""
    s = str(side).strip().upper()
    if s in ("B", "BUY"):
        return "buy"
    if s in ("A", "SELL"):
        return "sell"
    raise ValueError(f"Unrecognized side value: {side!r}")


def from_hyperx_camel(raw: dict[str, Any], wallet: str, source: SourceLiteral = "hyperx") -> Fill:
    """Map HyperX vendor camelCase fill dict to canonical Fill model."""
    if "startPosition" not in raw and "closedPnl" not in raw and "feeToken" not in raw:
        raise ValueError("Row is not HyperX camelCase schema")

    symbol = str(raw["coin"])
    price = to_decimal(raw["px"])
    size_token = to_decimal(raw["sz"])
    side_str = normalize_side(str(raw["side"]))
    ts = to_utc_datetime(raw["time"])
    source_ts = str(raw["time"])

    start_pos_raw = raw.get("startPosition")
    start_pos = to_decimal(start_pos_raw) if start_pos_raw is not None else None
    closed_pnl = to_decimal(raw["closedPnl"])
    fee = to_decimal(raw["fee"])
    fee_token = str(raw["feeToken"])
    order_id = str(raw["oid"])
    trade_id = str(raw["tid"])
    crossed = bool(raw["crossed"])
    is_maker = bool(raw.get("is_maker", not crossed))

    size_usd = (
        to_decimal(raw["size_usd"])
        if "size_usd" in raw and raw["size_usd"] is not None
        else size_token * price
    )
    dex = parse_dex(symbol, raw.get("dex"))
    wallet_addr = (raw.get("user") or raw.get("address") or wallet).lower().strip()

    return Fill(
        ts=ts,
        wallet=wallet_addr,
        symbol=symbol,
        dex=dex,
        side=side_str,  # type: ignore[arg-type]
        size_token=size_token,
        price=price,
        size_usd=size_usd,
        fee=fee,
        fee_token=fee_token,
        is_maker=is_maker,
        order_id=order_id,
        trade_id=trade_id,
        crossed=crossed,
        closed_pnl=closed_pnl,
        start_position=start_pos,
        source=source,
        source_ts=source_ts,
    )


def from_hyperx_snake(raw: dict[str, Any], wallet: str, source: SourceLiteral = "hyperx") -> Fill:
    """Map HyperX/Nansen snake_case fill dict to canonical Fill model."""
    if "start_position" not in raw and "closed_pnl" not in raw and "fee_token" not in raw:
        raise ValueError("Row is not HyperX snake_case schema")

    symbol = str(raw["coin"])
    price = to_decimal(raw["px"])
    size_token = to_decimal(raw["sz"])
    side_str = normalize_side(str(raw["side"]))
    ts = to_utc_datetime(raw["time"])
    source_ts = str(raw["time"])

    start_pos_raw = raw.get("start_position")
    start_pos = to_decimal(start_pos_raw) if start_pos_raw is not None else None
    closed_pnl = to_decimal(raw["closed_pnl"])
    fee = to_decimal(raw["fee"])
    fee_token = str(raw["fee_token"])
    order_id = str(raw["oid"])
    trade_id = str(raw["tid"])
    crossed = bool(raw["crossed"])
    is_maker = bool(raw.get("is_maker", not crossed))

    size_usd = (
        to_decimal(raw["size_usd"])
        if "size_usd" in raw and raw["size_usd"] is not None
        else size_token * price
    )
    dex = parse_dex(symbol, raw.get("dex"))
    wallet_addr = (raw.get("user") or raw.get("address") or wallet).lower().strip()

    return Fill(
        ts=ts,
        wallet=wallet_addr,
        symbol=symbol,
        dex=dex,
        side=side_str,  # type: ignore[arg-type]
        size_token=size_token,
        price=price,
        size_usd=size_usd,
        fee=fee,
        fee_token=fee_token,
        is_maker=is_maker,
        order_id=order_id,
        trade_id=trade_id,
        crossed=crossed,
        closed_pnl=closed_pnl,
        start_position=start_pos,
        source=source,
        source_ts=source_ts,
    )


def from_vike(raw: dict[str, Any], wallet: str, source: SourceLiteral = "vike") -> Fill:
    """Map Vike / dextra / archive fill dict to canonical Fill model."""
    # Determine symbol key (symbol or asset)
    symbol = str(raw.get("symbol") or raw.get("asset") or raw.get("coin"))
    # Determine timestamp key (ts or fill_ts or time)
    ts_val = (
        raw.get("ts")
        if "ts" in raw
        else (raw.get("fill_ts") if "fill_ts" in raw else raw.get("time"))
    )
    if ts_val is None:
        raise ValueError("Missing timestamp in Vike row")
    ts = to_utc_datetime(ts_val)
    source_ts = str(ts_val)

    price = to_decimal(raw["price"] if "price" in raw else raw["px"])
    size_token = to_decimal(raw["size_token"] if "size_token" in raw else raw["sz"])
    side_str = normalize_side(str(raw["side"]))

    start_pos_raw = raw.get("start_position") or raw.get("startPosition")
    start_pos = to_decimal(start_pos_raw) if start_pos_raw is not None else None
    closed_pnl = to_decimal(raw.get("closed_pnl", raw.get("closedPnl", "0.0")))
    fee = to_decimal(raw["fee"])
    fee_token = str(raw.get("fee_token", raw.get("feeToken", "USDC")))
    order_id = str(raw.get("order_id", raw.get("oid", "")))
    trade_id = str(raw.get("trade_id", raw.get("tid", "")))
    crossed = bool(raw.get("crossed", False))
    is_maker = bool(raw.get("is_maker", not crossed))

    size_usd = (
        to_decimal(raw["size_usd"])
        if "size_usd" in raw and raw["size_usd"] is not None
        else size_token * price
    )
    raw_dex = raw.get("dex_name") or raw.get("dex")
    dex = parse_dex(symbol, raw_dex)
    wallet_addr = (
        (raw.get("wallet") or raw.get("user") or raw.get("address") or wallet).lower().strip()
    )

    return Fill(
        ts=ts,
        wallet=wallet_addr,
        symbol=symbol,
        dex=dex,
        side=side_str,  # type: ignore[arg-type]
        size_token=size_token,
        price=price,
        size_usd=size_usd,
        fee=fee,
        fee_token=fee_token,
        is_maker=is_maker,
        order_id=order_id,
        trade_id=trade_id,
        crossed=crossed,
        closed_pnl=closed_pnl,
        start_position=start_pos,
        source=source,
        source_ts=source_ts,
    )


def adapt_fill_row(raw: dict[str, Any], wallet: str, default_source: SourceLiteral) -> Fill:
    """Route fill row to the exact adapter based on present keys."""
    # HyperX camelCase has 'startPosition' or 'closedPnl' or 'feeToken'
    if "startPosition" in raw or "feeToken" in raw or "closedPnl" in raw:
        return from_hyperx_camel(raw, wallet=wallet, source=default_source)
    # HyperX snake_case has 'start_position' or 'closed_pnl' or 'fee_token'
    if "start_position" in raw or "fee_token" in raw or "closed_pnl" in raw:
        # Check if it has 'coin' and 'px' and 'sz' -> hyperx snake
        if "coin" in raw or "px" in raw:
            return from_hyperx_snake(raw, wallet=wallet, source=default_source)
    # Vike / dextra / archive has 'price' or 'size_token' or 'dex_name' or 'symbol'
    return from_vike(raw, wallet=wallet, source=default_source)
