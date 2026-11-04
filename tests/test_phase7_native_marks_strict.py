"""Phase 7: native OHLCV mark coverage survives mixed schemas, never bad days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

pytest.importorskip("polars")

import polars as pl
import scripts.phase7_native_exposure as exposure
from scripts.phase7_native_exposure import START_MS


def _write_day(root, date: datetime, *, enriched: bool = False, rows: int = 1440):
    folder = (
        root
        / "crypto_futures_ohlcv_1m_HYPERLIQUID_CHIP_PERP"
        / f"year={date.year:04d}/month={date.month:02d}/day={date.day:02d}"
    )
    folder.mkdir(parents=True)
    columns = {
        "timestamp": pl.Series(
            "timestamp",
            [date + timedelta(minutes=i) for i in range(rows)],
            dtype=pl.Datetime("us" if enriched else "ms", "UTC"),
        ),
        "symbol": ["CHIP"] * rows,
        "open": [100.0] * rows,
        "high": [101.0] * rows,
        "low": [99.0] * rows,
        "close": [100.0] * rows,
        "volume": [2.0] * rows,
    }
    if enriched:
        columns["source"] = ["enriched"] * rows
        columns["observations"] = [1] * rows
    data = folder / "data.parquet"
    pl.DataFrame(columns).write_parquet(data)
    sidecar = folder / "source.json"
    sidecar.write_text(
        json.dumps(
            {
                "exchange": "hyperliquid_futures",
                "source_symbol": "CHIP",
                "source_type": "trades",
                "bars": rows,
                "sha256": sha256(data.read_bytes()).hexdigest(),
            }
        )
    )
    return data, sidecar


def test_mixed_seven_and_nine_column_native_days_remain_covered(monkeypatch, tmp_path):
    monkeypatch.setattr(exposure, "MARKET", tmp_path)
    day = datetime(2026, 8, 5, tzinfo=UTC)
    _write_day(tmp_path, day)
    _write_day(tmp_path, day + timedelta(days=1), enriched=True)
    frame, audit = exposure.native_marks_with_audit("CHIP", START_MS, START_MS + 2 * 86_400_000)
    assert frame.height == 2880
    assert frame["ms"].n_unique() == 2880
    assert frame["ms"].min() == START_MS
    assert frame["ms"].max() == START_MS + 2 * 86_400_000 - 60_000
    assert audit["day_statuses"] == {"VERIFIED_NATIVE_DAY": 2}
    assert len(audit["source_day_fingerprint_sha256"]) == 64


def test_incomplete_day_is_not_counted_even_when_sidecar_has_matching_sha(monkeypatch, tmp_path):
    monkeypatch.setattr(exposure, "MARKET", tmp_path)
    day = datetime(2026, 8, 5, tzinfo=UTC)
    _write_day(tmp_path, day, rows=1439)
    frame, audit = exposure.native_marks_with_audit("CHIP", START_MS, START_MS + 86_400_000)
    assert frame is None
    assert audit["day_statuses"] == {"PARTIAL_NATIVE_DAY": 1}
    assert audit["verified_bar_count"] == 0


def test_corrupted_parquet_sha_blocks_day_without_zero_filling(monkeypatch, tmp_path):
    monkeypatch.setattr(exposure, "MARKET", tmp_path)
    day = datetime(2026, 8, 5, tzinfo=UTC)
    data, _ = _write_day(tmp_path, day)
    data.write_bytes(data.read_bytes() + b"corruption")
    frame, audit = exposure.native_marks_with_audit("CHIP", START_MS, START_MS + 86_400_000)
    assert frame is None
    assert audit["day_statuses"] == {"NATIVE_SOURCE_SHA_MISMATCH": 1}


def test_missing_day_and_verified_day_preserve_unknown_interval(monkeypatch, tmp_path):
    monkeypatch.setattr(exposure, "MARKET", tmp_path)
    day = datetime(2026, 8, 5, tzinfo=UTC)
    _write_day(tmp_path, day)
    frame, audit = exposure.native_marks_with_audit("CHIP", START_MS, START_MS + 2 * 86_400_000)
    assert frame.height == 1440
    assert audit["requested_days"] == 2
    assert audit["day_statuses"] == {
        "MISSING_NATIVE_MARKET_DAY": 1,
        "VERIFIED_NATIVE_DAY": 1,
    }


def test_wrong_symbol_sidecar_and_bad_window_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(exposure, "MARKET", tmp_path)
    day = datetime(2026, 8, 5, tzinfo=UTC)
    _, sidecar = _write_day(tmp_path, day)
    meta = json.loads(sidecar.read_text())
    meta["source_symbol"] = "UNRELATED"
    sidecar.write_text(json.dumps(meta))
    frame, audit = exposure.native_marks_with_audit("CHIP", START_MS, START_MS + 86_400_000)
    assert frame is None
    assert audit["day_statuses"] == {"WRONG_NATIVE_DEX_OR_SYMBOL": 1}
    with pytest.raises(Exception, match="INVALID_NATIVE_MARK_WINDOW"):
        exposure.native_marks_with_audit("CHIP", START_MS, START_MS)
