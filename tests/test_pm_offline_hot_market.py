"""Native Hyperliquid full-week Polars -> private read-only numeric mmap cache."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import subprocess
import sys

import pytest

from copytrade_pm.pm_offline_hot_market import WEEK_BARS, open_verified_hot_week
from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid
from copytrade_pm.pm_shadow import VerifiedHyperliquidMinuteSource

pl = pytest.importorskip("polars")
np = pytest.importorskip("numpy")

START = datetime(2026, 10, 19, tzinfo=UTC)
MARKET = "hyperliquid:mainnet:perp:default:BTC"


def _sample_lake(root):
    for offset in range(7):
        day = START + timedelta(days=offset)
        folder = (
            root
            / VerifiedHyperliquidMinuteSource._family(MARKET)
            / f"year={day.year:04d}/month={day.month:02d}/day={day.day:02d}"
        )
        folder.mkdir(parents=True, exist_ok=True)
        bars = pl.DataFrame(
            {
                "timestamp": pl.datetime_range(
                    day,
                    day + timedelta(minutes=1439),
                    interval="1m",
                    eager=True,
                    time_zone="UTC",
                ),
                "symbol": ["BTC"] * 1440,
                "open": [float(100 + offset)] * 1440,
                "high": [float(101 + offset)] * 1440,
                "low": [float(99 + offset)] * 1440,
                "close": [float(100 + offset)] * 1440,
                "volume": [float(50 + offset)] * 1440,
            }
        )
        data = folder / "data.parquet"
        bars.write_parquet(data)
        (folder / "source.json").write_text(
            json.dumps(
                {
                    "exchange": "hyperliquid_futures",
                    "source_symbol": "BTC",
                    "source_type": "trades",
                    "sha256": sha256(data.read_bytes()).hexdigest(),
                    "bars": 1440,
                }
            )
        )
    return root


def _open(market, cache):
    return open_verified_hot_week(
        market_root=market,
        cache_root=cache,
        instrument=MARKET,
        week_start=START,
    )


def test_exact_week_readonly_mmap_and_restart_same_bytes(tmp_path):
    market = _sample_lake(tmp_path / "market")
    cache = tmp_path / "owner-private-cache"
    with _open(market, cache) as first:
        assert first.cache_status == "CACHE_CREATED"
        assert first.rows.shape == (WEEK_BARS,)
        assert first.rows.flags.writeable is False
        assert first.sample(START)["open_float_screen_only"] == 100.0
        assert first.sample(START + timedelta(days=3))["open_float_screen_only"] == 103.0
        assert first.sample(START + timedelta(minutes=1))["volume_base_screen_only"] == 50.0
        assert first.prior_volume(START) is None
        assert first.prior_volume(START + timedelta(minutes=1)) == 50.0
        assert first.sample(START - timedelta(minutes=1)) is None
        assert first.sample(START + timedelta(days=7)) is None
        with pytest.raises(ValueError):
            first.rows["open_float_screen_only"][0] = 5.0
        recorded = sha256(first.content_path.read_bytes()).hexdigest()
        path = first.content_path
    with _open(market, cache) as second:
        assert second.cache_status == "CACHE_HIT"
        assert second.content_path == path
        assert sha256(second.content_path.read_bytes()).hexdigest() == recorded
    assert (cache.stat().st_mode & 0o077) == 0
    assert (path.stat().st_mode & 0o077) == 0


def test_source_change_only_rebuilds_new_week_cache_identity(tmp_path):
    market = _sample_lake(tmp_path / "market")
    cache = tmp_path / "private"
    with _open(market, cache) as before:
        old_path = before.content_path
        old_sha = sha256(old_path.read_bytes()).hexdigest()
    middle = market / VerifiedHyperliquidMinuteSource._family(MARKET) / "year=2026/month=10/day=22"
    data = middle / "data.parquet"
    frame = pl.read_parquet(data).with_columns((pl.col("open") + 0.1).alias("open"))
    frame.write_parquet(data)
    meta_path = middle / "source.json"
    meta = json.loads(meta_path.read_text())
    meta["sha256"] = sha256(data.read_bytes()).hexdigest()
    meta_path.write_text(json.dumps(meta))
    with _open(market, cache) as new:
        assert new.cache_status == "CACHE_CREATED"
        assert new.content_path != old_path
        assert sha256(new.content_path.read_bytes()).hexdigest() != old_sha
        assert new.sample(START + timedelta(days=3))["open_float_screen_only"] == 103.1
    assert old_path.is_file()
    with _open(market, cache) as warmed:
        assert warmed.cache_status == "CACHE_HIT"


def test_missing_day_corrupt_sha_and_bad_week_clock_are_blocked(tmp_path):
    market = _sample_lake(tmp_path / "market")
    cache = tmp_path / "private"
    folder = market / VerifiedHyperliquidMinuteSource._family(MARKET) / "year=2026/month=10/day=24"
    data = folder / "data.parquet"
    data.write_bytes(b"corrupt")
    with pytest.raises(ManifestBlocked, match="HOT_NATIVE_SOURCE_SHA_MISMATCH"):
        _open(market, cache)
    data.unlink()
    with pytest.raises(ManifestBlocked, match="INCOMPLETE_HOT_NATIVE_WEEK"):
        _open(market, cache)
    with pytest.raises(ManifestInvalid, match="HOT_WEEK_MUST_START_MONDAY_UTC"):
        open_verified_hot_week(
            market_root=market,
            cache_root=cache,
            instrument=MARKET,
            week_start=START + timedelta(days=1),
        )


def test_separate_process_can_map_same_readonly_sealed_week(tmp_path):
    market = _sample_lake(tmp_path / "market")
    cache = tmp_path / "private"
    with _open(market, cache):
        pass
    code = """from pathlib import Path
from datetime import datetime,timezone
from copytrade_pm.pm_offline_hot_market import open_verified_hot_week
import sys
with open_verified_hot_week(
    market_root=Path(sys.argv[1]),
    cache_root=Path(sys.argv[2]),
    instrument='hyperliquid:mainnet:perp:default:BTC',
    week_start=datetime(2026,10,19,tzinfo=timezone.utc),
) as hot:
    assert not hot.rows.flags.writeable
    assert hot.cache_status == 'CACHE_HIT'
    assert hot.sample(datetime(2026,10,20,tzinfo=timezone.utc))['open_float_screen_only']==101.0
print('READ_ONLY_PROCESS_VERIFIED')
"""
    cmd = [sys.executable, "-c", code, str(market), str(cache)]
    run = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=40)
    assert "READ_ONLY_PROCESS_VERIFIED" in run.stdout
