"""Native Phase 6B exact-minute and immutable-source verification tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json

import pytest

from copytrade_pm.pm_phase6b import fingerprint
from copytrade_pm.pm_phase6b_minute import audit_one_day, expected_minutes

pl = pytest.importorskip("polars", reason="Phase 6B Parquet tests require market extra")


def _date_root(root: Path) -> Path:
    p = root / "crypto_futures_ohlcv_1m_HYPERLIQUID_BTC_PERP" / "year=2026"
    return p / "month=08" / "day=05"


def _fixture(root: Path) -> Path:
    directory = _date_root(root)
    directory.mkdir(parents=True)
    frame = pl.DataFrame(
        {
            "timestamp": [
                datetime(2026, 8, 5, 0, tzinfo=UTC),
                datetime(2026, 8, 5, 0, 1, tzinfo=UTC),
            ],
            "symbol": ["BTC", "BTC"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [1.0, 1.0],
        }
    )
    frame.write_parquet(directory / "data.parquet")
    (directory / "source.json").write_text(
        json.dumps(
            {
                "exchange": "hyperliquid_futures",
                "source_symbol": "BTC",
                "source_type": "trades",
                "sha256": fingerprint(directory / "data.parquet"),
            }
        )
    )
    return directory


def test_full_day_sha_and_minute_count(tmp_path: Path):
    _fixture(tmp_path)
    result = audit_one_day(
        tmp_path,
        "BTC",
        "2026-08-05",
        start=datetime(2026, 8, 5, tzinfo=UTC),
        end=datetime(2026, 8, 5, 0, 2, tzinfo=UTC),
    )
    assert result["status"] == "EXACT_MINUTE_SHA_VERIFIED"
    assert result["verified_minutes"] == 2
    assert result["missing_minutes"] == 0


def test_missing_minute_is_not_filled(tmp_path: Path):
    _fixture(tmp_path)
    result = audit_one_day(
        tmp_path,
        "BTC",
        "2026-08-05",
        start=datetime(2026, 8, 5, tzinfo=UTC),
        end=datetime(2026, 8, 5, 0, 3, tzinfo=UTC),
    )
    assert result["status"] == "PARTIAL_EXACT_MINUTE_SHA_VERIFIED"
    assert result["missing_minutes"] == 1


def test_mutated_market_parquet_is_rejected(tmp_path: Path):
    directory = _fixture(tmp_path)
    (directory / "data.parquet").write_bytes((directory / "data.parquet").read_bytes() + b"x")
    result = audit_one_day(
        tmp_path,
        "BTC",
        "2026-08-05",
        start=datetime(2026, 8, 5, tzinfo=UTC),
        end=datetime(2026, 8, 5, 0, 2, tzinfo=UTC),
    )
    assert result["status"] == "SHA256_MISMATCH"
    assert result["verified_minutes"] == 0


def test_market_identity_is_required(tmp_path: Path):
    directory = _fixture(tmp_path)
    meta = directory / "source.json"
    doc = json.loads(meta.read_text())
    doc["source_symbol"] = "ETH"
    meta.write_text(json.dumps(doc))
    result = audit_one_day(
        tmp_path,
        "BTC",
        "2026-08-05",
        start=datetime(2026, 8, 5, tzinfo=UTC),
        end=datetime(2026, 8, 5, 0, 2, tzinfo=UTC),
    )
    assert result["status"] == "INVALID_SOURCE_IDENTITY"


def test_missing_days_fail_closed(tmp_path: Path):
    result = audit_one_day(
        tmp_path,
        "BTC",
        "2026-08-05",
        start=datetime(2026, 8, 5, tzinfo=UTC),
        end=datetime(2026, 8, 5, 0, 2, tzinfo=UTC),
    )
    assert result["status"] == "MISSING_MARKET_DAY"


def test_expected_minutes_respect_cutoff():
    start = datetime(2026, 8, 5, 4, 30, tzinfo=UTC)
    end = start + timedelta(minutes=5)
    values = expected_minutes("2026-08-05", start, end)
    assert len(values) == 5
    assert min(values) == start
    assert max(values) == end - timedelta(minutes=1)
