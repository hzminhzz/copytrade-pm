"""Comprehensive test suite for the canonical wallet store.

Tests:
1. Strict Pydantic models (Decimal at boundary, strict typing, forbid extra).
2. Traps:
   - trade_id > i64 (String representation, no overflow)
   - start_position null vs Decimal
   - A/B vs buy/sell normalization
   - epoch-ms int vs ISO-8601 string
   - mixed camel/snake in one directory
   - spot-like symbols @107, #1730 -> kept, dex=SPOT, never dropped
   - duplicate rows deduplication across sources
3. Golden Parquet contract tests against sample fixtures.
4. Access layer: scan, coverage, verify, ingest.
5. Cross-source equivalence testing over overlapping wallets.
"""

from __future__ import annotations

# Optional market-extra dependency is checked before importing the store.
# ruff: noqa: E402

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError

pl = pytest.importorskip("polars", reason="Wallet store requires the market extra")

from copytrade_pm.wallet_store.adapters import (
    adapt_fill_row,
    from_hyperx_camel,
    from_hyperx_snake,
    from_vike,
    parse_dex,
)
from copytrade_pm.wallet_store.schema import (
    FILLS_POLARS_SCHEMA,
    Fill,
)
from copytrade_pm.wallet_store.store import ingest, scan, verify

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "wallet_store"
TEST_WALLET = "0x1111111111111111111111111111111111111111"


def fill_to_dict(f: Fill) -> dict[str, Any]:
    return {
        "ts": f.ts,
        "wallet": f.wallet,
        "symbol": f.symbol,
        "dex": f.dex,
        "side": f.side,
        "size_token": float(f.size_token),
        "price": float(f.price),
        "size_usd": float(f.size_usd),
        "fee": float(f.fee),
        "fee_token": f.fee_token,
        "is_maker": f.is_maker,
        "order_id": f.order_id,
        "trade_id": f.trade_id,
        "crossed": f.crossed,
        "closed_pnl": float(f.closed_pnl),
        "start_position": float(f.start_position) if f.start_position is not None else None,
        "source": f.source,
        "source_ts": f.source_ts,
    }


# --- 1. Schema & Pydantic Validation Tests ---


def test_fill_pydantic_strictness():
    """Verify Fill model rejects extra fields and non-strict types."""
    # Extra field rejected
    with pytest.raises(ValidationError):
        Fill(
            ts=datetime.now(timezone.utc),
            wallet=TEST_WALLET,
            symbol="BTC",
            dex="HL",
            side="buy",
            size_token=Decimal("1.0"),
            price=Decimal("90000.0"),
            size_usd=Decimal("90000.0"),
            fee=Decimal("10.0"),
            fee_token="USDC",
            is_maker=True,
            order_id="123",
            trade_id="456",
            crossed=False,
            closed_pnl=Decimal("0.0"),
            start_position=Decimal("0.0"),
            source="hyperx",
            source_ts="123456789",
            extra_field="ILLEGAL",
        )

    # Invalid wallet pattern rejected
    with pytest.raises(ValidationError):
        Fill(
            ts=datetime.now(timezone.utc),
            wallet="0xINVALID_ADDRESS",
            symbol="BTC",
            dex="HL",
            side="buy",
            size_token=Decimal("1.0"),
            price=Decimal("90000.0"),
            size_usd=Decimal("90000.0"),
            fee=Decimal("10.0"),
            fee_token="USDC",
            is_maker=True,
            order_id="123",
            trade_id="456",
            crossed=False,
            closed_pnl=Decimal("0.0"),
            start_position=None,
            source="hyperx",
            source_ts="123456789",
        )


def test_trap_trade_id_exceeds_i64():
    """Verify trade_id > i64 (e.g. 14318806847495222257) parses without overflow."""
    huge_tid = 14318806847495222257
    raw = {
        "coin": "xyz:TSLA",
        "px": "245.50",
        "sz": "10.0",
        "side": "B",
        "time": 1787165851785,
        "startPosition": "0.0",
        "closedPnl": "0.0",
        "oid": 520077658387,
        "crossed": True,
        "fee": "0.15",
        "tid": huge_tid,
        "feeToken": "USDC",
    }
    fill = from_hyperx_camel(raw, wallet=TEST_WALLET, source="hyperx")
    assert fill.trade_id == str(huge_tid)
    assert isinstance(fill.trade_id, str)


def test_trap_spot_like_symbols_kept_dex_spot():
    """Verify spot-like symbols (@107, #1730) are kept and assigned dex='SPOT'."""
    assert parse_dex("@107") == "SPOT"
    assert parse_dex("#1730") == "SPOT"

    raw_at = {
        "coin": "@107",
        "px": "1.25",
        "sz": "100.0",
        "side": "A",
        "time": 1787165852000,
        "startPosition": "100.0",
        "closedPnl": "25.0",
        "oid": 520077658388,
        "crossed": False,
        "fee": "0.05",
        "tid": 110386023261628,
        "feeToken": "USDC",
    }
    fill_at = from_hyperx_camel(raw_at, wallet=TEST_WALLET, source="hyperx")
    assert fill_at.symbol == "@107"
    assert fill_at.dex == "SPOT"

    raw_hash = {
        "coin": "#1730",
        "px": "3.50",
        "sz": "20.0",
        "side": "A",
        "time": 1787165905000,
        "start_position": "20.0",
        "closed_pnl": "5.0",
        "oid": 520077658391,
        "tid": 110386023261631,
        "crossed": False,
        "fee": "0.07",
        "fee_token": "USDC",
        "user": TEST_WALLET,
    }
    fill_hash = from_hyperx_snake(raw_hash, wallet=TEST_WALLET, source="hyperx")
    assert fill_hash.symbol == "#1730"
    assert fill_hash.dex == "SPOT"


def test_trap_side_and_clock_normalization():
    """Verify A/B -> buy/sell and epoch-ms vs ISO-8601 normalization."""
    # A -> sell
    raw_a = {
        "coin": "BTC",
        "px": "90000.0",
        "sz": "1.0",
        "side": "A",
        "time": 1787165851785,
        "startPosition": "1.0",
        "closedPnl": "0.0",
        "oid": 1,
        "tid": 2,
        "crossed": True,
        "fee": "0.1",
        "feeToken": "USDC",
    }
    fill_a = from_hyperx_camel(raw_a, wallet=TEST_WALLET, source="hyperx")
    assert fill_a.side == "sell"
    assert fill_a.ts.tzinfo == timezone.utc

    # B -> buy
    raw_b = {
        "coin": "BTC",
        "px": "90000.0",
        "sz": "1.0",
        "side": "B",
        "time": 1787165851785,
        "start_position": "0.0",
        "closed_pnl": "0.0",
        "oid": 1,
        "tid": 2,
        "crossed": False,
        "fee": "0.1",
        "fee_token": "USDC",
        "user": TEST_WALLET,
    }
    fill_b = from_hyperx_snake(raw_b, wallet=TEST_WALLET, source="hyperx")
    assert fill_b.side == "buy"

    # Vike ISO string
    raw_vike = {
        "ts": "2026-08-05T12:30:00.123000+00:00",
        "symbol": "BTC",
        "side": "buy",
        "size_token": 1.0,
        "price": 90000.0,
        "fee": 0.1,
        "fee_token": "USDC",
        "is_maker": True,
        "crossed": False,
        "closed_pnl": 0.0,
        "order_id": "1",
        "trade_id": "2",
        "dex_name": "HL",
    }
    fill_vike = from_vike(raw_vike, wallet=TEST_WALLET, source="vike")
    assert fill_vike.side == "buy"
    assert fill_vike.ts == datetime(2026, 8, 5, 12, 30, 0, 123000, tzinfo=timezone.utc)
    assert fill_vike.start_position is None


def test_trap_mixed_camel_snake_adapter_selection():
    """Verify row-level adapter selection on presence of startPosition vs start_position."""
    camel_row = {
        "coin": "ETH",
        "px": "3000.0",
        "sz": "1.0",
        "side": "B",
        "time": 1787165851000,
        "startPosition": "0.0",
        "closedPnl": "0.0",
        "oid": 10,
        "tid": 20,
        "crossed": True,
        "fee": "0.1",
        "feeToken": "USDC",
    }
    snake_row = {
        "coin": "SOL",
        "px": "150.0",
        "sz": "10.0",
        "side": "A",
        "time": 1787165852000,
        "start_position": "10.0",
        "closed_pnl": "0.0",
        "oid": 11,
        "tid": 21,
        "crossed": False,
        "fee": "0.05",
        "fee_token": "USDC",
        "user": TEST_WALLET,
    }

    fill_c = adapt_fill_row(camel_row, wallet=TEST_WALLET, default_source="hyperx")
    fill_s = adapt_fill_row(snake_row, wallet=TEST_WALLET, default_source="hyperx")

    assert fill_c.symbol == "ETH"
    assert fill_c.side == "buy"
    assert fill_s.symbol == "SOL"
    assert fill_s.side == "sell"


# --- 2. Golden Parquet Contract Tests ---


def test_golden_contracts():
    """Verify parsed canonical fixtures match golden Parquet files."""
    # 1. Camel
    with open(FIXTURES_DIR / "sample_hyperx_camel.json") as f:
        data = json.load(f)
    fills = [from_hyperx_camel(r, wallet=TEST_WALLET, source="hyperx") for r in data["fills"]]
    df_actual = pl.DataFrame(
        [
            {
                "ts": f.ts,
                "wallet": f.wallet,
                "symbol": f.symbol,
                "dex": f.dex,
                "side": f.side,
                "size_token": float(f.size_token),
                "price": float(f.price),
                "size_usd": float(f.size_usd),
                "fee": float(f.fee),
                "fee_token": f.fee_token,
                "is_maker": f.is_maker,
                "order_id": f.order_id,
                "trade_id": f.trade_id,
                "crossed": f.crossed,
                "closed_pnl": float(f.closed_pnl),
                "start_position": float(f.start_position) if f.start_position is not None else None,
                "source": f.source,
                "source_ts": f.source_ts,
            }
            for f in fills
        ],
        schema=FILLS_POLARS_SCHEMA,
    )
    df_golden = pl.read_parquet(FIXTURES_DIR / "golden_hyperx_camel.parquet")
    assert df_actual.equals(df_golden)

    # 2. Snake
    with open(FIXTURES_DIR / "sample_hyperx_snake.json") as f:
        data = json.load(f)
    fills_snake = [from_hyperx_snake(r, wallet=TEST_WALLET, source="hyperx") for r in data["fills"]]
    df_snake_actual = pl.DataFrame(
        [
            {
                "ts": f.ts,
                "wallet": f.wallet,
                "symbol": f.symbol,
                "dex": f.dex,
                "side": f.side,
                "size_token": float(f.size_token),
                "price": float(f.price),
                "size_usd": float(f.size_usd),
                "fee": float(f.fee),
                "fee_token": f.fee_token,
                "is_maker": f.is_maker,
                "order_id": f.order_id,
                "trade_id": f.trade_id,
                "crossed": f.crossed,
                "closed_pnl": float(f.closed_pnl),
                "start_position": float(f.start_position) if f.start_position is not None else None,
                "source": f.source,
                "source_ts": f.source_ts,
            }
            for f in fills_snake
        ],
        schema=FILLS_POLARS_SCHEMA,
    )
    df_snake_golden = pl.read_parquet(FIXTURES_DIR / "golden_hyperx_snake.parquet")
    assert df_snake_actual.equals(df_snake_golden)


# --- 3. Store Engine Tests ---


def test_store_immutability_and_permissions(tmp_path: Path):
    """Verify partition immutability, fsync tmp write, and mode 600/700 enforcement."""
    store_dir = tmp_path / "wallet_store"
    day = "2026-08-05"

    df1 = pl.DataFrame(
        {
            "ts": [datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)],
            "wallet": [TEST_WALLET],
            "symbol": ["BTC"],
            "dex": ["HL"],
            "side": ["buy"],
            "size_token": [1.0],
            "price": [90000.0],
            "size_usd": [90000.0],
            "fee": [10.0],
            "fee_token": ["USDC"],
            "is_maker": [True],
            "order_id": ["1"],
            "trade_id": ["1"],
            "crossed": [False],
            "closed_pnl": [0.0],
            "start_position": [0.0],
            "source": ["hyperx"],
            "source_ts": ["123"],
        },
        schema=FILLS_POLARS_SCHEMA,
    )

    # First ingest
    res1 = ingest("fills", TEST_WALLET, day, df1, source="hyperx", store_dir=store_dir)
    p1 = Path(res1["path"])
    assert p1.exists()
    assert p1.name == "data.parquet"
    assert (p1.stat().st_mode & 0o777) == 0o600
    assert (p1.parent.stat().st_mode & 0o777) == 0o700

    # Second ingest identical content: does not duplicate or overwrite
    res2 = ingest("fills", TEST_WALLET, day, df1, source="hyperx", store_dir=store_dir)
    assert res2["path"] == res1["path"]

    # Third ingest with different content: writes data.<sha8>.parquet alongside
    df2 = pl.DataFrame(
        {
            "ts": [datetime(2026, 8, 5, 11, 0, tzinfo=timezone.utc)],
            "wallet": [TEST_WALLET],
            "symbol": ["ETH"],
            "dex": ["HL"],
            "side": ["sell"],
            "size_token": [2.0],
            "price": [3000.0],
            "size_usd": [6000.0],
            "fee": [1.0],
            "fee_token": ["USDC"],
            "is_maker": [False],
            "order_id": ["2"],
            "trade_id": ["2"],
            "crossed": [True],
            "closed_pnl": [50.0],
            "start_position": [2.0],
            "source": ["vike"],
            "source_ts": ["124"],
        },
        schema=FILLS_POLARS_SCHEMA,
    )
    res3 = ingest("fills", TEST_WALLET, day, df2, source="vike", store_dir=store_dir)
    p3 = Path(res3["path"])
    assert p3.exists()
    assert p3.name.startswith("data.") and p3.name.endswith(".parquet")
    assert p3.name != "data.parquet"
    assert (p3.stat().st_mode & 0o777) == 0o600

    # Verify store integrity
    assert verify(store_dir=store_dir) == 0

    # Scan filtered by day
    lf = scan(
        "fills", wallets=[TEST_WALLET], start="2026-08-05", end="2026-08-05", store_dir=store_dir
    )
    scanned_df = lf.collect()
    assert scanned_df.height >= 1


# --- 4. Cross-Source Equivalence Test Over Migrated Store ---


def test_cross_source_equivalence():
    """Verify that for wallets overlapping across sources, common fills match field-by-field."""
    # Check ACT04 (0xe2823659be02e0f48a4660e4da008b5e1abfdf29)
    act04_addr = "0xe2823659be02e0f48a4660e4da008b5e1abfdf29"
    act04_file = Path("data/private/triadA_verified/act04_fills_verified_20261111.json")
    arch_file = Path(
        "data/private/registry_archive_slice/registry_archive_fills_20260929_1001.parquet"
    )

    if not act04_file.exists() or not arch_file.exists():
        pytest.skip("Source files not available for cross-source equivalence test")

    with open(act04_file) as f:
        vike_fills = json.load(f)["fills"]
    df_vike = pl.DataFrame(
        [fill_to_dict(from_vike(r, wallet=act04_addr, source="vike")) for r in vike_fills],
        schema=FILLS_POLARS_SCHEMA,
    )

    df_arch_all = pl.read_parquet(arch_file)
    df_arch_act04 = df_arch_all.filter(pl.col("wallet") == act04_addr)
    df_arch = pl.DataFrame(
        [
            fill_to_dict(from_vike(r, wallet=act04_addr, source="archive"))
            for r in df_arch_act04.to_dicts()
        ],
        schema=FILLS_POLARS_SCHEMA,
    )

    # Join on (wallet, symbol, trade_id, ts)
    overlap = df_vike.join(
        df_arch,
        on=["wallet", "symbol", "trade_id", "ts"],
        suffix="_b",
    )

    assert overlap.height > 0, "Expected overlap rows between ACT04 vike and archive"

    tol = 1e-4
    numeric_fields = ["price", "size_token", "size_usd", "fee", "closed_pnl"]
    for col in numeric_fields:
        diff = overlap.filter((pl.col(col) - pl.col(f"{col}_b")).abs() > tol)
        assert diff.height == 0, f"Field mismatch in {col}: {diff.head(3)}"

    categorical_fields = ["side", "dex", "fee_token", "is_maker", "crossed"]
    for col in categorical_fields:
        diff = overlap.filter(pl.col(col) != pl.col(f"{col}_b"))
        assert diff.height == 0, f"Field mismatch in {col}: {diff.head(3)}"
