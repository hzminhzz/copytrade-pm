"""Generate contract test fixtures and golden Parquet files in tests/fixtures/wallet_store/."""

from __future__ import annotations

import json
from pathlib import Path
import polars as pl

from copytrade_pm.wallet_store.adapters import from_hyperx_camel, from_hyperx_snake, from_vike
from copytrade_pm.wallet_store.schema import FILLS_POLARS_SCHEMA
from copytrade_pm.wallet_store.store import ensure_mode_600, ensure_mode_700

FIXTURES_DIR = Path("/home/quant/dev/copytrade-pm/tests/fixtures/wallet_store")
ensure_mode_700(FIXTURES_DIR)

TEST_WALLET = "0x1111111111111111111111111111111111111111"

# 1. HyperX camelCase sample (includes trade_id > i64, spot @107, A/B side, epoch ms)
camel_raw = {
    "label": "TEST_CAMEL",
    "address": TEST_WALLET,
    "cohort": "test",
    "primary_coin": "BTC",
    "equity": 50000.0,
    "fills": [
        {
            "coin": "xyz:TSLA",
            "px": "245.50",
            "sz": "10.0",
            "side": "B",
            "time": 1787165851785,
            "startPosition": "0.0",
            "dir": "Open Long",
            "closedPnl": "0.0",
            "hash": "0x123456",
            "oid": 520077658387,
            "crossed": True,
            "fee": "0.15",
            "tid": 14318806847495222257,  # > i64!
            "feeToken": "USDC",
        },
        {
            "coin": "@107",  # spot-like
            "px": "1.25",
            "sz": "100.0",
            "side": "A",
            "time": 1787165852000,
            "startPosition": "100.0",
            "dir": "Close Long",
            "closedPnl": "25.0",
            "hash": "0x234567",
            "oid": 520077658388,
            "crossed": False,
            "fee": "0.05",
            "tid": 110386023261628,
            "feeToken": "USDC",
        },
    ],
}

camel_json_path = FIXTURES_DIR / "sample_hyperx_camel.json"
with open(camel_json_path, "w", encoding="utf-8") as f:
    json.dump(camel_raw, f, indent=2)
ensure_mode_600(camel_json_path)

# Golden Parquet for Camel
camel_fills = [from_hyperx_camel(r, wallet=TEST_WALLET, source="hyperx") for r in camel_raw["fills"]]
camel_df = pl.DataFrame(
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
        for f in camel_fills
    ],
    schema=FILLS_POLARS_SCHEMA,
)
camel_df.write_parquet(FIXTURES_DIR / "golden_hyperx_camel.parquet", compression="zstd")
ensure_mode_600(FIXTURES_DIR / "golden_hyperx_camel.parquet")

# 2. HyperX snake_case sample (includes spot #1730, snake fields)
snake_raw = {
    "alias": "TEST_SNAKE",
    "address": TEST_WALLET,
    "equity": 25000.0,
    "fills": [
        {
            "coin": "BTC",
            "px": "90000.0",
            "sz": "0.5",
            "side": "B",
            "time": 1787165900000,
            "start_position": "0.0",
            "dir": "Open Long",
            "closed_pnl": "0.0",
            "oid": 520077658390,
            "tid": 110386023261630,
            "crossed": True,
            "fee": "4.5",
            "fee_token": "USDC",
            "user": TEST_WALLET,
        },
        {
            "coin": "#1730",  # spot-like
            "px": "3.50",
            "sz": "20.0",
            "side": "A",
            "time": 1787165905000,
            "start_position": "20.0",
            "dir": "Close Long",
            "closed_pnl": "5.0",
            "oid": 520077658391,
            "tid": 110386023261631,
            "crossed": False,
            "fee": "0.07",
            "fee_token": "USDC",
            "user": TEST_WALLET,
        },
    ],
}

snake_json_path = FIXTURES_DIR / "sample_hyperx_snake.json"
with open(snake_json_path, "w", encoding="utf-8") as f:
    json.dump(snake_raw, f, indent=2)
ensure_mode_600(snake_json_path)

snake_fills = [from_hyperx_snake(r, wallet=TEST_WALLET, source="hyperx") for r in snake_raw["fills"]]
snake_df = pl.DataFrame(
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
        for f in snake_fills
    ],
    schema=FILLS_POLARS_SCHEMA,
)
snake_df.write_parquet(FIXTURES_DIR / "golden_hyperx_snake.parquet", compression="zstd")
ensure_mode_600(FIXTURES_DIR / "golden_hyperx_snake.parquet")

# 3. Vike sample (ISO-8601 string, null start_position)
vike_raw = {
    "wallet": TEST_WALLET,
    "fills": [
        {
            "ts": "2026-08-05T12:30:00.123000+00:00",
            "symbol": "ETH",
            "side": "buy",
            "direction": "buy",
            "size_token": 5.0,
            "price": 3200.0,
            "size_usd": 16000.0,
            "fee": 1.6,
            "fee_token": "USDC",
            "is_maker": False,
            "crossed": True,
            "closed_pnl": 0.0,
            "order_id": "580000000001",
            "trade_id": "990000000001",
            "dex_name": "HL",
        }
    ],
}
vike_json_path = FIXTURES_DIR / "sample_vike.json"
with open(vike_json_path, "w", encoding="utf-8") as f:
    json.dump(vike_raw, f, indent=2)
ensure_mode_600(vike_json_path)

vike_fills = [from_vike(r, wallet=TEST_WALLET, source="vike") for r in vike_raw["fills"]]
vike_df = pl.DataFrame(
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
        for f in vike_fills
    ],
    schema=FILLS_POLARS_SCHEMA,
)
vike_df.write_parquet(FIXTURES_DIR / "golden_vike.parquet", compression="zstd")
ensure_mode_600(FIXTURES_DIR / "golden_vike.parquet")

# 4. Dextra JSONL sample
dextra_lines = [
    {
        "ts": "2026-10-20T03:53:05.428000+00:00",
        "symbol": "xyz:SPCX",
        "side": "buy",
        "direction": "buy",
        "size_token": 0.06,
        "price": 148.23,
        "size_usd": 8.8938,
        "fee": 0.000181,
        "fee_token": "USDC",
        "is_maker": True,
        "crossed": False,
        "closed_pnl": -0.2328,
        "order_id": 579986647460,
        "trade_id": 14318806847495222257,  # > i64!
        "dex_name": "XYZ",
    }
]
dextra_jsonl_path = FIXTURES_DIR / "sample_dextra.jsonl"
with open(dextra_jsonl_path, "w", encoding="utf-8") as f:
    for line in dextra_lines:
        f.write(json.dumps(line) + "\n")
ensure_mode_600(dextra_jsonl_path)

dextra_fills = [from_vike(r, wallet=TEST_WALLET, source="dextra") for r in dextra_lines]
dextra_df = pl.DataFrame(
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
        for f in dextra_fills
    ],
    schema=FILLS_POLARS_SCHEMA,
)
dextra_df.write_parquet(FIXTURES_DIR / "golden_dextra.parquet", compression="zstd")
ensure_mode_600(FIXTURES_DIR / "golden_dextra.parquet")

print("Generated fixtures and golden Parquets in", FIXTURES_DIR)
