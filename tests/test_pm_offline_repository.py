"""Read-only local repository inventory; never creates source book or equity."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid
from copytrade_pm.pm_offline_repository import (
    GROUPS,
    inspect_repository,
    native_instrument,
)


START = datetime(2026, 10, 20, tzinfo=UTC)
ADDRESS = ["0x" + char * 40 for char in ("a", "b", "c")]


def _fixture(tmp_path, *, missing_last_group=False):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    market = tmp_path / "market"
    market.mkdir(mode=0o700)
    for i, group in enumerate(GROUPS):
        folder = source / group
        folder.mkdir()
        if missing_last_group and i == 2:
            continue
        when = START + timedelta(minutes=i)
        payload = {
            "label": f"P{i}",
            "address": ADDRESS[i],
            "equity": 1000 + i,
            "fills": [
                {
                    "coin": "BTC",
                    "tid": i + 1,
                    "time": int(when.timestamp() * 1000),
                    "sz": "1",
                    "px": "100",
                    "side": "B",
                    "startPosition": "0",
                }
            ],
        }
        (folder / "one.json").write_text(json.dumps(payload))
    folder = market / "crypto_futures_ohlcv_1m_HYPERLIQUID_BTC_PERP" / "year=2026/month=10/day=20"
    folder.mkdir(parents=True, mode=0o700)
    content = b"synthetic parquet marker"
    (folder / "data.parquet").write_bytes(content)
    (folder / "source.json").write_text(
        json.dumps(
            {
                "exchange": "hyperliquid_futures",
                "source_symbol": "BTC",
                "source_type": "trades",
                "sha256": sha256(content).hexdigest(),
                "bars": 1440,
            }
        )
    )
    return source, market, folder


def audit(source, market, **kwargs):
    return inspect_repository(
        source,
        market,
        start="2026-10-20T00:00:00+00:00",
        end="2026-10-21T00:00:00+00:00",
        **kwargs,
    )


def test_source_and_native_metadata_aggregate_only(tmp_path):
    source, market, _ = _fixture(tmp_path)
    result = audit(source, market, verify_market_sha=True)
    assert result["source_rows_all_time"] == 3
    assert result["source_rows_in_window_valid_unique"] == 3
    assert result["source_account_count"] == 3
    assert result["instruments_with_every_complete_native_day"] == 1
    assert result["market_claimed_bar_rows"] == 1440
    assert result["independent_first_known_receipt_count"] == 0
    assert result["equity_snapshots_with_asof"] == 0
    assert result["contractual_follower_pnl"].startswith("BLOCKED_")
    assert all(address not in json.dumps(result) for address in ADDRESS)
    assert (
        result["source_collection_sha256"]
        == audit(source, market, verify_market_sha=True)["source_collection_sha256"]
    )


def test_corrupt_native_bytes_never_report_verified(tmp_path):
    source, market, folder = _fixture(tmp_path)
    (folder / "data.parquet").write_bytes(b"tampered")
    result = audit(source, market, verify_market_sha=True)
    assert result["market_status_instrument_days"]["NATIVE_PARQUET_SHA_MISMATCH"] == 1
    assert result["instruments_with_every_complete_native_day"] == 0


def test_missing_group_blocks_no_implicit_flat_or_inferred_equity(tmp_path):
    source, market, _ = _fixture(tmp_path, missing_last_group=True)
    with pytest.raises(ManifestBlocked, match="EMPTY_SOURCE_GROUP"):
        audit(source, market)


def test_wrong_instrument_dex_and_clock_refused(tmp_path):
    with pytest.raises(ManifestInvalid, match="UNSUPPORTED_SOURCE_INSTRUMENT"):
        native_instrument("unknown:BTC")
    source, market, _ = _fixture(tmp_path)
    with pytest.raises(ManifestInvalid, match="NAIVE_WINDOW_CLOCK"):
        inspect_repository(
            source,
            market,
            start="2026-10-20T00:00:00",
            end="2026-10-21T00:00:00+00:00",
        )
    with pytest.raises(ManifestInvalid, match="INVALID_AUDIT_WINDOW"):
        inspect_repository(
            source,
            market,
            start="2026-10-20T00:00:00+00:00",
            end="2026-10-20T00:00:00+00:00",
        )


def test_duplicate_source_tid_not_double_counted(tmp_path):
    source, market, _ = _fixture(tmp_path)
    f = source / GROUPS[0] / "one.json"
    payload = json.loads(f.read_text())
    payload["fills"].append(dict(payload["fills"][0]))
    f.write_text(json.dumps(payload))
    result = audit(source, market)
    assert result["source_duplicate_tid_count"] == 1
    assert result["source_rows_all_time"] == 4
    assert result["source_rows_in_window_valid_unique"] == 3


def test_beyond_window_is_explicit_not_clean_coverage(tmp_path):
    source, market, _ = _fixture(tmp_path)
    f = source / GROUPS[0] / "one.json"
    payload = json.loads(f.read_text())
    payload["fills"][0]["time"] = int((START - timedelta(days=1)).timestamp() * 1000)
    f.write_text(json.dumps(payload))
    result = audit(source, market)
    assert result["source_error_counts"]["OUTSIDE_FROZEN_WINDOW"] == 1
    assert result["source_rows_in_window_valid_unique"] == 2
