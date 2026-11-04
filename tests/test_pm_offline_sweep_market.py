"""Exact native 1m market matching and prior-bar capacity tests."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid
from copytrade_pm.pm_offline_market import match_native_open
from copytrade_pm.pm_shadow import VerifiedHyperliquidMinuteSource

pl = pytest.importorskip("polars")
T = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
BTC = "hyperliquid:mainnet:perp:default:BTC"
HIP = "hyperliquid:mainnet:perp:xyz:BTC"


def fixture(root, instrument=BTC, *, invalid=False, duplicate=False, wrong_dex=False):
    relative = VerifiedHyperliquidMinuteSource._family(instrument)
    folder = root / relative / "year=2026/month=10/day=20"
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(3):
        rows.append(
            {
                "timestamp": T + timedelta(minutes=i),
                "symbol": "BTC",
                "open": float(100 + i),
                "high": float(102 + i),
                "low": float(99 + i),
                "close": float(101 + i),
                "volume": float(10 + i),
            }
        )
    if invalid:
        rows[0]["low"] = 200.0
    if duplicate:
        rows[-1]["timestamp"] = rows[1]["timestamp"]
    parquet = folder / "data.parquet"
    pl.DataFrame(rows).write_parquet(parquet)
    (folder / "source.json").write_text(
        json.dumps(
            {
                "sha256": sha256(parquet.read_bytes()).hexdigest(),
                "exchange": "hyperliquid_futures",
                "source_type": "trades",
                "source_symbol": "wrong:BTC"
                if wrong_dex
                else ("BTC" if instrument == BTC else "xyz:BTC"),
            }
        )
    )
    return folder


def candidate(when=T + timedelta(minutes=1), instrument=BTC):
    dex = instrument.split(":")[3]
    return {
        "account": "W001",
        "dex": dex,
        "instrument": instrument,
        "symbol": "BTC",
        "execute_open_at": when.isoformat(),
        "event_id": "one",
    }


def test_exact_open_and_only_prior_volume_is_capacity(tmp_path):
    fixture(tmp_path)
    a = match_native_open(events=[candidate()], market_root=tmp_path, engine="streaming")
    b = match_native_open(events=[candidate()], market_root=tmp_path, engine="in-memory")
    assert a["sha256"] == b["sha256"]
    item = a["matched"][0]
    assert item["price_open_float_screen_only"] == 101.0
    assert item["prior_bar_volume_base"] == 10.0
    assert item["same_bar_volume_ex_post_diagnostic"] == 11.0
    assert item["execution_certified"] is False
    assert "NOT_L2" in item["capacity_basis"]


def test_missing_prior_completed_bar_blocks(tmp_path):
    fixture(tmp_path)
    with pytest.raises(ManifestBlocked, match="MISSING_EXACT_OR_PRIOR_1M_BAR"):
        match_native_open(events=[candidate(T)], market_root=tmp_path)


def test_wrong_dex_and_corrupt_source_sha_block(tmp_path):
    fixture(tmp_path, HIP, wrong_dex=True)
    with pytest.raises(ManifestBlocked, match="WRONG_NATIVE_DEX_OR_SYMBOL"):
        match_native_open(events=[candidate(instrument=HIP)], market_root=tmp_path)
    folder = fixture(tmp_path)
    with (folder / "data.parquet").open("ab") as writer:
        writer.write(b"corruption")
    with pytest.raises(ManifestBlocked, match="NATIVE_SOURCE_SHA_MISMATCH"):
        match_native_open(events=[candidate()], market_root=tmp_path)


def test_invalid_ohlc_or_duplicate_minute_blocks(tmp_path):
    fixture(tmp_path, invalid=True)
    with pytest.raises(ManifestBlocked, match="INVALID_NATIVE_OHLCV"):
        match_native_open(events=[candidate()], market_root=tmp_path)
    fixture(tmp_path, duplicate=True)
    with pytest.raises(ManifestBlocked, match="DUPLICATE_NATIVE_MARKET_MINUTE"):
        match_native_open(events=[candidate()], market_root=tmp_path)


def test_quote_volume_cannot_be_passed_as_base_volume(tmp_path):
    folder = fixture(tmp_path)
    sidecar = folder / "source.json"
    metadata = json.loads(sidecar.read_text())
    metadata["volume_unit"] = "quote"
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ManifestBlocked, match="UNSUPPORTED_VOLUME_UNIT"):
        match_native_open(events=[candidate()], market_root=tmp_path)


def test_wrong_namespace_and_nonminute_clock_block(tmp_path):
    fixture(tmp_path)
    event = candidate()
    event["dex"] = "xyz"
    with pytest.raises(ManifestInvalid, match="EXECUTION_NAMESPACE_MISMATCH"):
        match_native_open(events=[event], market_root=tmp_path)
    with pytest.raises(ManifestInvalid, match="NON_MINUTE_EXECUTION_OPEN"):
        match_native_open(events=[candidate(T + timedelta(seconds=1))], market_root=tmp_path)
