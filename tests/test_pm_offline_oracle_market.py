"""Read-only SHA-sealed real historical-oracle native minute matching."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_offline_manifest import ManifestInvalid
from copytrade_pm.pm_offline_oracle_market import (
    DAY_MS,
    _day_record,
    _join_instrument,
    match_real_oracle_native,
)
from test_pm_offline_repository import _fixture

pl = pytest.importorskip("polars")


START = datetime(2026, 10, 20, tzinfo=UTC)
BTC = "hyperliquid:mainnet:perp:default:BTC"


def _native_fixture(tmp_path):
    source, market, folder = _fixture(tmp_path)
    rows = [
        {
            "timestamp": START + timedelta(minutes=i),
            "symbol": "BTC",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.0 + i,
            "volume": 100.0 + i,
        }
        for i in range(1440)
    ]
    data = folder / "data.parquet"
    pl.DataFrame(rows).write_parquet(data)
    sidecar = folder / "source.json"
    meta = json.loads(sidecar.read_text())
    meta["sha256"] = sha256(data.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(meta))
    return source, market, folder


def _run(source, market, cache, **kwargs):
    return match_real_oracle_native(
        source_root=source,
        market_root=market,
        cache_root=cache,
        start="2026-10-20T00:00:00+00:00",
        end="2026-10-21T00:00:00+00:00",
        **kwargs,
    )


def test_native_full_day_all_five_delays_cached(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    a = _run(source, market, tmp_path / "cache")
    b = _run(source, market, tmp_path / "cache")
    assert a["status"] == "HISTORICAL_ORACLE_NATIVE_SCREEN_ONLY"
    assert a["market_input_days"] == 1
    assert a["candidate_batches"] == 15
    assert a["matched_batches"] == 15
    assert a["verified_complete_native_days"] == 1
    assert a["cache_status"] == "CACHE_CREATED"
    assert b["cache_status"] == "CACHE_HIT"
    assert a["context_tape_sha256"] == b["context_tape_sha256"]
    assert a["logical_sha256"] == b["logical_sha256"]
    assert a["contractual_pass_or_breach"] == "UNKNOWN"
    assert a["price_float_screen_only"] is True


def test_missing_or_partial_native_day_is_never_a_match(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    sidecar = folder / "source.json"
    meta = json.loads(sidecar.read_text())
    meta["bars"] = 1439
    sidecar.write_text(json.dumps(meta))
    a = _run(source, market, tmp_path / "cache")
    assert a["matched_batches"] == 0
    assert a["status_counts_by_delay"][0]["match_status"] == "PARTIAL_NATIVE_DAY"
    assert a["declared_partial_or_missing_days"] == 1


def test_bad_ohlc_is_explicitly_rejected_without_poisoning_cache(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    parquet = folder / "data.parquet"
    frame = pl.read_parquet(parquet).with_columns(
        pl.when(pl.int_range(pl.len()) == 10)
        .then(pl.lit(-1.0))
        .otherwise(pl.col("low"))
        .alias("low")
    )
    frame.write_parquet(parquet)
    sidecar = folder / "source.json"
    meta = json.loads(sidecar.read_text())
    meta["sha256"] = sha256(parquet.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(meta))
    report = _run(source, market, tmp_path / "cache")
    assert report["matched_batches"] == 0
    assert report["status_counts_by_delay"][0]["match_status"] == "INVALID_NATIVE_1M_DAY"
    assert report["contractual_pass_or_breach"] == "UNKNOWN"


def test_native_market_input_tamper_between_preflight_and_scan_blocks(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    from copytrade_pm.pm_offline_manifest import ManifestBlocked

    day_number = int(START.timestamp()) // 86400
    pinned = {(BTC, day_number): _day_record(market, BTC, day_number)}
    data = folder / "data.parquet"
    frame = pl.read_parquet(data).with_columns((pl.col("open") + 0.1).alias("open"))
    frame.write_parquet(data)
    candidate = pl.DataFrame(
        {
            "delay_minutes": [0],
            "account_sha256": ["synthetic"],
            "instrument": [BTC],
            "execute_ms": [int((START + timedelta(minutes=1)).timestamp() * 1000)],
            "source_fill_count": [1],
            "first_event_ms": [int(START.timestamp() * 1000)],
            "last_event_ms": [int(START.timestamp() * 1000)],
            "day_number": [day_number],
        }
    )
    with pytest.raises(ManifestBlocked, match="NATIVE_DAY_CHANGED_DURING_JOIN"):
        _join_instrument(market, BTC, candidate, pinned)


def test_sidecar_and_parquet_changes_invalidate_context(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    a = _run(source, market, tmp_path / "cache")
    sidecar = folder / "source.json"
    meta = json.loads(sidecar.read_text())
    meta["provider"] = "metadata-updated-test"
    sidecar.write_text(json.dumps(meta))
    b = _run(source, market, tmp_path / "cache")
    assert b["cache_status"] == "CACHE_CREATED"
    assert b["market_fingerprint_sha256"] != a["market_fingerprint_sha256"]
    data = folder / "data.parquet"
    data.write_bytes(b"corrupted data")
    c = _run(source, market, tmp_path / "cache")
    assert c["matched_batches"] == 0
    assert c["logical_sha256"] != a["logical_sha256"]


def test_mixed_optional_day_schema_and_midnight_prior_capacity(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    original = folder / "data.parquet"
    first = pl.read_parquet(original).with_columns(
        pl.lit(1).cast(pl.UInt32).alias("trade_count"),
        pl.lit(100).cast(pl.Float64).alias("quote_volume"),
        pl.col("timestamp").dt.cast_time_unit("ms"),
    )
    first.write_parquet(original)
    prior_meta = folder / "source.json"
    prev = json.loads(prior_meta.read_text())
    prev["sha256"] = sha256(original.read_bytes()).hexdigest()
    prior_meta.write_text(json.dumps(prev))
    next_folder = folder.parent / "day=21"
    next_folder.mkdir()
    second = (
        first.select("timestamp", "symbol", "open", "high", "low", "close", "volume")
        .with_columns(pl.col("timestamp") + pl.duration(days=1))
        .with_columns(pl.col("timestamp").dt.cast_time_unit("us"))
    )
    next_data = next_folder / "data.parquet"
    second.write_parquet(next_data)
    next_meta = dict(prev, sha256=sha256(next_data.read_bytes()).hexdigest())
    (next_folder / "source.json").write_text(json.dumps(next_meta))
    date0 = int(START.timestamp() * 1000) // DAY_MS
    data = pl.DataFrame(
        {
            "delay_minutes": [0, 0],
            "account_sha256": ["synthetic", "synthetic"],
            "instrument": [BTC, BTC],
            "execute_ms": [
                int((START + timedelta(days=1)).timestamp() * 1000),
                int((START + timedelta(days=1, minutes=1)).timestamp() * 1000),
            ],
            "source_fill_count": [1, 1],
            "first_event_ms": [int(START.timestamp() * 1000)] * 2,
            "last_event_ms": [int(START.timestamp() * 1000)] * 2,
            "day_number": [date0 + 1, date0 + 1],
        }
    )
    pinned = {
        (BTC, date0): _day_record(market, BTC, date0),
        (BTC, date0 + 1): _day_record(market, BTC, date0 + 1),
    }
    output = _join_instrument(market, BTC, data, pinned).sort("execute_ms")
    assert output["match_status"].to_list() == ["MATCHED_SCREEN_ONLY"] * 2
    assert output["prior_base_volume_screen_only"].to_list() == [1539.0, 100.0]


def test_bounded_market_day_scope_refuses_unverified_excess(tmp_path):
    source, market, folder = _native_fixture(tmp_path)
    with pytest.raises(ManifestInvalid, match="INVALID_NATIVE_DAY_BUDGET"):
        _run(source, market, tmp_path / "cache", max_market_days=0)
