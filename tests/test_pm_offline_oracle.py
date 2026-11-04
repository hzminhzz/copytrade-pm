"""Actual historical fill normalization is oracle-only and deterministic."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from copytrade_pm.pm_offline_oracle import (
    _batches,
    compile_real_historical_oracle,
    load_real_oracle_batches,
)

pytest.importorskip("polars")

from test_pm_offline_repository import _fixture


T = datetime(2026, 10, 20, tzinfo=UTC)


def study(source, market, cache, engine="streaming"):
    return compile_real_historical_oracle(
        source,
        cache,
        start="2026-10-20T00:00:00+00:00",
        end="2026-10-21T00:00:00+00:00",
        engine=engine,
    )


def test_five_delays_real_source_clock_screen_only_and_cache_parity(tmp_path):
    source, market, _ = _fixture(tmp_path)
    original = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(original.read_text())
    extra = dict(doc["fills"][0])
    extra["tid"] = 79
    extra["time"] = int((T + timedelta(seconds=30)).timestamp() * 1000)
    doc["fills"].append(extra)
    original.write_text(json.dumps(doc))
    a = study(source, market, tmp_path / "cache-a", "streaming")
    b = study(source, market, tmp_path / "cache-b", "in-memory")
    warm = study(source, market, tmp_path / "cache-a", "in-memory")
    assert a["status"] == "HISTORICAL_ORACLE_BATCH_SCREEN_ONLY"
    assert a["clock_basis"] == "HISTORICAL_ORACLE"
    assert a["batch_parquet_sha256"] == b["batch_parquet_sha256"]
    assert a["logical_sha256"] == b["logical_sha256"]
    assert a["logical_sha256"] == warm["logical_sha256"]
    assert a["cache_status"] == "CACHE_CREATED"
    assert warm["cache_status"] == "CACHE_HIT"
    assert warm["source_cache_status"] == "CACHE_HIT"
    tape, digest = load_real_oracle_batches(
        tmp_path / "cache-a",
        start="2026-10-20T00:00:00+00:00",
        end="2026-10-21T00:00:00+00:00",
        source_sha256=a["source_collection_sha256"],
    )
    assert tape.height == 15
    assert digest == a["batch_parquet_sha256"]
    assert len(a["per_delay"]) == 5
    assert all(item["eligible_fills"] == 4 for item in a["per_delay"])
    assert all(item["batches"] == 3 for item in a["per_delay"])
    assert all(item["merged_orders"] == 1 for item in a["per_delay"])
    assert a["contractual_pass_or_breach"] == "UNKNOWN"
    assert a["first_known_receipts_verified"] is False
    assert a["account_equity_pit_verified"] is False


def test_right_censor_does_not_promote_late_fills(tmp_path):
    source, market, _ = _fixture(tmp_path)
    original = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(original.read_text())
    doc["fills"][0]["time"] = int((T + timedelta(hours=23, minutes=56)).timestamp() * 1000)
    original.write_text(json.dumps(doc))
    result = study(source, market, tmp_path / "cache")
    zero = next(item for item in result["per_delay"] if item["delay_minutes"] == 0)
    ten = next(item for item in result["per_delay"] if item["delay_minutes"] == 10)
    assert zero["eligible_fills"] == 3
    assert ten["eligible_fills"] == 2
    assert ten["right_censored_fills"] == 1


def test_source_change_invalidates_cached_lineage(tmp_path):
    source, market, _ = _fixture(tmp_path)
    first = study(source, market, tmp_path / "cache")
    f = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(f.read_text())
    doc["fills"][0]["time"] += 30_000
    f.write_text(json.dumps(doc))
    second = study(source, market, tmp_path / "cache")
    assert second["cache_status"] == "CACHE_CREATED"
    assert first["source_collection_sha256"] != second["source_collection_sha256"]


def test_large_streaming_vs_in_memory_parquet_byte_parity():
    from io import BytesIO

    import polars as pl

    count = 12000
    frame = pl.DataFrame(
        {
            "account_sha256": [str(i % 23) for i in range(count)],
            "instrument": [
                "hyperliquid:mainnet:perp:default:BTC"
                if i % 2
                else "hyperliquid:mainnet:perp:default:ETH"
                for i in range(count)
            ],
            "source_ms": [int(T.timestamp() * 1000) + i * 500 for i in range(count)],
            "event_id": [str(i) for i in range(count)],
        }
    )
    stop = int((T + timedelta(days=1)).timestamp() * 1000)
    a = _batches(frame, end_ms=stop, engine="streaming")
    b = _batches(frame, end_ms=stop, engine="in-memory")
    assert a.equals(b)
    assert a.n_chunks() == b.n_chunks() == 1
    contents = []
    for output in (a, b):
        stream = BytesIO()
        output.write_parquet(stream, compression="zstd", statistics=False)
        contents.append(stream.getvalue())
    assert contents[0] == contents[1]


def test_duplicate_wallet_across_source_cohorts_rejected(tmp_path):
    source, market, _ = _fixture(tmp_path)
    original = source / "wallet_fills_90d" / "one.json"
    other = source / "broader_active_inventory_fills_90d" / "one.json"
    payload = json.loads(other.read_text())
    payload["address"] = json.loads(original.read_text())["address"]
    payload["fills"][0]["tid"] = 999
    other.write_text(json.dumps(payload))
    from copytrade_pm.pm_offline_manifest import ManifestBlocked

    with pytest.raises(ManifestBlocked, match="DUPLICATE_SOURCE_ACCOUNT_FILES"):
        study(source, market, tmp_path / "cache")


@pytest.mark.parametrize("payload", ['{"address":', '{"address":null,"fills":[]}'])
def test_malformed_source_file_blocks_with_typed_provenance(tmp_path, payload):
    from copytrade_pm.pm_offline_manifest import ManifestBlocked

    source, market, _ = _fixture(tmp_path)
    (source / "wallet_fills_90d" / "one.json").write_text(payload)
    with pytest.raises(ManifestBlocked, match="MALFORMED_SOURCE_JSON|INVALID_SOURCE_FILE_SCHEMA"):
        study(source, market, tmp_path / "cache")


def test_unsafe_clock_not_accepted(tmp_path):
    source, market, _ = _fixture(tmp_path)
    from copytrade_pm.pm_offline_manifest import ManifestInvalid

    with pytest.raises(ManifestInvalid, match="NAIVE_WINDOW_CLOCK"):
        compile_real_historical_oracle(
            source,
            tmp_path / "cache",
            start="2026-10-20T00:00:00",
            end="2026-10-21T00:00:00+00:00",
        )
