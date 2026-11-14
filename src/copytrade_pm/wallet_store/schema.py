"""Strict canonical models and schemas for the wallet-level data store.

Enforces strict Pydantic models at the ingestion boundary with Decimal representations,
deterministic JSON schema hashing, and matching Polars write schemas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Annotated, Literal

try:
    import polars as pl
except ModuleNotFoundError:  # pragma: no cover - core CI leg runs without --extra market
    pl = None  # type: ignore[assignment]
from pydantic import BaseModel, ConfigDict, Field

WalletAddress = Annotated[str, Field(pattern=r"^0x[0-9a-f]{40}$")]
DexLiteral = Literal["HL", "XYZ", "SPOT", "UNKNOWN", "PARA", "IO", "MKTS", "HYNA"]
SourceLiteral = Literal["vike", "hyperx", "dextra", "archive"]


class Fill(BaseModel):
    """Canonical Fill event."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    ts: datetime
    wallet: WalletAddress
    symbol: str
    dex: DexLiteral
    side: Literal["buy", "sell"]
    size_token: Decimal
    price: Decimal
    size_usd: Decimal
    fee: Decimal
    fee_token: str
    is_maker: bool
    order_id: str
    trade_id: str
    crossed: bool
    closed_pnl: Decimal
    start_position: Decimal | None
    source: SourceLiteral
    source_ts: str


class Position(BaseModel):
    """Canonical Position snapshot."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    snapshot_ts: datetime
    wallet: WalletAddress
    symbol: str
    dex: str
    direction: Literal["long", "short"]
    size_token: Decimal
    size_usd: Decimal
    entry_price: Decimal
    mark_price: Decimal
    liquidation_price: Decimal | None
    unrealized_pnl: Decimal
    leverage: Decimal
    leverage_type: str | None
    margin_used: Decimal
    opened_at: datetime | None
    pnl_cohort: str | None
    size_cohort: str | None
    liq_progress: Decimal | None
    source: SourceLiteral


class Equity(BaseModel):
    """Canonical Equity snapshot."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    ts: datetime
    wallet: WalletAddress
    account_value: Decimal
    perp_account_value: Decimal
    margin_used: Decimal
    cash_balance_usd: Decimal
    total_unrealized_pnl: Decimal
    account_mode: str
    source: SourceLiteral


class Funding(BaseModel):
    """Canonical Funding payment."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    ts: datetime
    wallet: WalletAddress
    symbol: str
    payment_usd: Decimal
    rate: Decimal
    source: SourceLiteral


class Ledger(BaseModel):
    """Canonical Ledger entry."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    ts: datetime
    wallet: WalletAddress
    event_type: str
    amount_usd: Decimal
    fee_usd: Decimal
    counterparty: str
    tx_hash: str
    source: SourceLiteral


# Polars explicit write schemas (mode 600, zstd)
if pl is not None:
    FILLS_POLARS_SCHEMA = pl.Schema(
        {
            "ts": pl.Datetime("ms", "UTC"),
            "wallet": pl.String,
            "symbol": pl.String,
            "dex": pl.String,
            "side": pl.String,
            "size_token": pl.Float64,
            "price": pl.Float64,
            "size_usd": pl.Float64,
            "fee": pl.Float64,
            "fee_token": pl.String,
            "is_maker": pl.Boolean,
            "order_id": pl.String,
            "trade_id": pl.String,
            "crossed": pl.Boolean,
            "closed_pnl": pl.Float64,
            "start_position": pl.Float64,
            "source": pl.String,
            "source_ts": pl.String,
        }
    )

    POSITIONS_POLARS_SCHEMA = pl.Schema(
        {
            "snapshot_ts": pl.Datetime("ms", "UTC"),
            "wallet": pl.String,
            "symbol": pl.String,
            "dex": pl.String,
            "direction": pl.String,
            "size_token": pl.Float64,
            "size_usd": pl.Float64,
            "entry_price": pl.Float64,
            "mark_price": pl.Float64,
            "liquidation_price": pl.Float64,
            "unrealized_pnl": pl.Float64,
            "leverage": pl.Float64,
            "leverage_type": pl.String,
            "margin_used": pl.Float64,
            "opened_at": pl.Datetime("ms", "UTC"),
            "pnl_cohort": pl.String,
            "size_cohort": pl.String,
            "liq_progress": pl.Float64,
            "source": pl.String,
        }
    )

    EQUITY_POLARS_SCHEMA = pl.Schema(
        {
            "ts": pl.Datetime("ms", "UTC"),
            "wallet": pl.String,
            "account_value": pl.Float64,
            "perp_account_value": pl.Float64,
            "margin_used": pl.Float64,
            "cash_balance_usd": pl.Float64,
            "total_unrealized_pnl": pl.Float64,
            "account_mode": pl.String,
            "source": pl.String,
        }
    )

    FUNDING_POLARS_SCHEMA = pl.Schema(
        {
            "ts": pl.Datetime("ms", "UTC"),
            "wallet": pl.String,
            "symbol": pl.String,
            "payment_usd": pl.Float64,
            "rate": pl.Float64,
            "source": pl.String,
        }
    )

    LEDGER_POLARS_SCHEMA = pl.Schema(
        {
            "ts": pl.Datetime("ms", "UTC"),
            "wallet": pl.String,
            "event_type": pl.String,
            "amount_usd": pl.Float64,
            "fee_usd": pl.Float64,
            "counterparty": pl.String,
            "tx_hash": pl.String,
            "source": pl.String,
        }
    )
else:  # pragma: no cover - core CI leg runs without --extra market
    FILLS_POLARS_SCHEMA = None
    POSITIONS_POLARS_SCHEMA = None
    EQUITY_POLARS_SCHEMA = None
    FUNDING_POLARS_SCHEMA = None
    LEDGER_POLARS_SCHEMA = None

DATASET_SCHEMAS = {
    "fills": (Fill, FILLS_POLARS_SCHEMA),
    "positions": (Position, POSITIONS_POLARS_SCHEMA),
    "equity": (Equity, EQUITY_POLARS_SCHEMA),
    "funding": (Funding, FUNDING_POLARS_SCHEMA),
    "ledger": (Ledger, LEDGER_POLARS_SCHEMA),
}

SCHEMA_VERSION = "1.0.0"


def compute_model_sha256(model_cls: type[BaseModel]) -> str:
    """Compute deterministic SHA-256 hash of a Pydantic model's JSON schema."""
    schema_json = json.dumps(model_cls.model_json_schema(), sort_keys=True)
    return hashlib.sha256(schema_json.encode("utf-8")).hexdigest()


DATASET_SHA256 = {
    kind: compute_model_sha256(model_cls) for kind, (model_cls, _) in DATASET_SCHEMAS.items()
}
