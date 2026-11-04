"""Native SHA day adapter to TI minute bars; strictly hypothetical research."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource
from copytrade_pm.trader_intelligence_native import read_native_minutes, lake_instrument

pl = pytest.importorskip("polars")
START = datetime(2026, 11, 3, 10, tzinfo=UTC)
TI_MARKET = "hyperliquid/mainnet:perp:default/BTC"
NATIVE_MARKET = "hyperliquid:mainnet:perp:default:BTC"


def native_day(root, *, count=8):
    family = VerifiedHyperliquidMinuteSource._family(NATIVE_MARKET)
    folder = root / family / "year=2026/month=11/day=03"
    folder.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": START + timedelta(minutes=i),
            "symbol": "BTC",
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 1000.0,
        }
        for i in range(count)
    ]
    parquet = folder / "data.parquet"
    pl.DataFrame(rows).write_parquet(parquet)
    meta = {
        "sha256": sha256(parquet.read_bytes()).hexdigest(),
        "exchange": "hyperliquid_futures",
        "source_type": "candles",
        "source_symbol": "BTC",
    }
    (folder / "source.json").write_text(json.dumps(meta))
    return folder, meta


def load(root, *, final_minutes=5, known_minutes=8):
    return read_native_minutes(
        root=root,
        instrument=TI_MARKET,
        first_minute_at=START.isoformat(),
        final_minute_at=(START + timedelta(minutes=final_minutes)).isoformat(),
        known_asof=(START + timedelta(minutes=known_minutes)).isoformat(),
    )


def test_verified_native_window_produces_exact_intrabar_marks_without_fills(tmp_path):
    _, source = native_day(tmp_path)
    result = load(tmp_path)
    assert len(result.bars) == 6
    assert result.day_source_shas == (("2026-11-03", source["sha256"]),)
    assert result.bars[1].high_px == "103.0"
    assert result.bars[1].base_volume == "1000.0"
    assert result.research_only_status == "SHA_VERIFIED_1M_NOT_EXECUTION_QUALIFIED"
    assert result == load(tmp_path)
    assert result.window_sha256 == result.as_wire()["window_sha256"]


def test_time_gate_and_missing_minutes_fail_closed(tmp_path):
    native_day(tmp_path)
    with pytest.raises(ValueError, match="UNMATURED_NATIVE_WINDOW"):
        load(tmp_path, known_minutes=5)
    with pytest.raises(MarketDataBlocked, match="NATIVE_MINUTE_GAP_OR_DUPLICATE"):
        load(tmp_path, final_minutes=9, known_minutes=15)


def test_market_sidecar_parquet_tamper_is_rejected(tmp_path):
    folder, _ = native_day(tmp_path)
    with (folder / "data.parquet").open("ab") as f:
        f.write(b"changed source")
    with pytest.raises(MarketDataBlocked, match="MARKET_PARQUET_HASH_MISMATCH"):
        load(tmp_path)


def test_namespace_cannot_be_silently_remapped():
    assert lake_instrument(TI_MARKET) == NATIVE_MARKET
    for name in (
        "hyperliquid/mainnet:spot:default/BTC",
        "hyperliquid/mainnet:perp:default/BTC/USDT",
        "binance/mainnet:perp:default/BTC",
    ):
        with pytest.raises(ValueError, match="UNKNOWN_NATIVE_MINUTE_INSTRUMENT"):
            lake_instrument(name)
