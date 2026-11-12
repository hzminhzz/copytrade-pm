"""Bounded two-DEX Reservoir research catalog tests; no S3 or live registry reads."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("pyarrow", reason="optional Reservoir research dependency")
pytest.importorskip("polars", reason="optional Reservoir research dependency")

from scripts import catalog_reservoir_six_portfolios as catalog  # noqa: E402
from scripts import pilot_reservoir_wallet_scoped as pilot  # noqa: E402


def fake_index() -> dict:
    return {
        "allowed_dexes": ["hyperliquid", "xyz"],
        "entries": [
            {
                "dex": "xyz",
                "day": "2026-11-11",
                "artifacts": [
                    {"kind": "fills", "path": "/tmp/private/path.parquet"},
                ],
            },
        ],
    }


def test_window_map_exact_31_day_two_dex_and_reuses_existing_pilot():
    mapping = catalog.window_sources()
    assert len(mapping) == 62
    assert {dex for dex, _ in mapping} == {"hyperliquid", "xyz"}
    assert mapping[("hyperliquid", "2026-11-11")] == pilot.OUTPUT
    assert mapping[("xyz", "2026-11-11")] != pilot.OUTPUT
    assert len({date for _, date in mapping}) == 31


def test_fails_closed_outside_two_dex_scope_and_dates():
    item = fake_index()
    with pytest.raises(ValueError, match="SOURCE_DEX_NOT_APPROVED"):
        catalog.scan_fills(item, "cash")
    with pytest.raises(ValueError, match="OUTSIDE_VERIFIED_DATE_WINDOW"):
        catalog.scan_fills(item, "xyz", date(2026, 10, 11), date(2026, 10, 12))
    with pytest.raises(ValueError, match="INCOMPLETE_REQUESTED_DATE_WINDOW"):
        catalog.scan_fills(item, "xyz", date(2026, 11, 10), date(2026, 11, 11))


def test_scan_checks_private_parquet_sha_before_return(monkeypatch, tmp_path: Path):
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq

    monkeypatch.setattr(catalog, "PRIVATE_RESEARCH_ROOT", tmp_path)
    path = tmp_path / "fills.parquet"
    pq.write_table(pa.table({"trade_id": [101]}), path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    source = {
        "allowed_dexes": ["hyperliquid", "xyz"],
        "entries": [
            {
                "dex": "xyz",
                "day": "2026-11-11",
                "artifacts": [
                    {
                        "kind": "fills",
                        "path": str(path),
                        "parquet_sha256": expected,
                    }
                ],
            }
        ],
    }
    assert (
        catalog.scan_fills(source, "xyz", date(2026, 11, 11), date(2026, 11, 11)).collect().height
        == 1
    )
    pq.write_table(pa.table({"trade_id": [999]}), path)
    with pytest.raises(ValueError, match="BACKTEST_SOURCE_SHA_MISMATCH"):
        catalog.scan_fills(source, "xyz", date(2026, 11, 11), date(2026, 11, 11))


def test_snapshot_reader_filters_global_main_vs_xyz(monkeypatch, tmp_path: Path):
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq

    monkeypatch.setattr(catalog, "PRIVATE_RESEARCH_ROOT", tmp_path)
    index = {"allowed_dexes": ["hyperliquid", "xyz"], "entries": []}
    cases = (
        ("hyperliquid", ["BTC", "xyz:TSLA"]),
        ("xyz", ["xyz:AAPL", "xyz:TSLA"]),
    )
    for dex, markets in cases:
        path = tmp_path / f"{dex}-snapshot.parquet"
        pq.write_table(pa.table({"market": markets}), path)
        index["entries"].append(
            {
                "dex": dex,
                "day": "2026-11-11",
                "artifacts": [
                    {
                        "kind": "position_snapshot",
                        "path": str(path),
                        "parquet_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                ],
            }
        )
    begin = end = date(2026, 11, 11)
    main = catalog.scan_snapshots(index, "hyperliquid", begin, end).collect()
    xyz = catalog.scan_snapshots(index, "xyz", begin, end).collect()
    assert main["market"].to_list() == ["BTC"]
    assert xyz["market"].to_list() == ["xyz:AAPL", "xyz:TSLA"]


def test_catalog_immutability(tmp_path: Path):
    index = {
        "scope": {"wallet_set_sha256": "e" * 64},
        "entries": [],
        "counts": {},
        "dates": ["2026-11-11"],
        "allowed_dexes": ["hyperliquid", "xyz"],
    }
    original = catalog.write_catalog(tmp_path, index)
    assert catalog.write_catalog(tmp_path, index) == original
    assert (tmp_path / "catalog.json").stat().st_mode & 0o777 == 0o600
    modified = {**index, "dates": ["2026-11-10"]}
    with pytest.raises(ValueError, match="CATALOG_DRIFT_VERSION_REQUIRED"):
        catalog.write_catalog(tmp_path, modified)


def test_source_key_allowlist_is_not_extended_by_caller(monkeypatch):
    with pytest.raises(ValueError, match="DEX_NOT_APPROVED"):
        pilot.source_keys("2026-11-11", dex="para", snapshot_scope="dex")
    with pytest.raises(ValueError, match="SNAPSHOT_SCOPE_NOT_APPROVED"):
        pilot.source_keys("2026-11-11", dex="xyz", snapshot_scope="global")

    observed_keys: list[str] = []

    def head(key: str):
        observed_keys.append(key)
        return {"key": key, "bytes": 10, "etag": "src-v1"}

    def listing(args):
        prefix = args[args.index("--prefix") + 1]
        assert "by_dex/xyz/snapshots/perp/" in prefix
        return {
            "Contents": [{"Key": prefix + "1216730000_1794355768609.parquet"}],
            "IsTruncated": False,
        }

    monkeypatch.setattr(pilot, "s3_head", head)
    monkeypatch.setattr(pilot, "aws_cli", listing)
    fill, snapshot = pilot.source_keys("2026-11-11", dex="xyz", snapshot_scope="dex")
    assert fill["key"].startswith("by_dex/xyz/fills/")
    assert snapshot["key"].startswith("by_dex/xyz/snapshots/")
    assert snapshot["block"] == 1216730000
    assert len(observed_keys) == 2
    assert all(key.startswith("by_dex/xyz/") for key in observed_keys)


def test_xyz_fill_validation_rejects_mismatched_dex():
    from tests.test_pilot_reservoir_wallet_scoped import arrow_rows, WALLETS

    original = arrow_rows()
    record = original.to_pylist()[0]
    record["dex"] = "xyz"
    import pyarrow as pa

    table = pa.Table.from_pylist([record], schema=original.schema)
    assert pilot.validate_fills(table, WALLETS, "2026-11-05", dex="xyz")["rows"] == 1
    with pytest.raises(ValueError, match="SOURCE_SCOPE_MISMATCH"):
        pilot.validate_fills(table, WALLETS, "2026-11-05", dex="hyperliquid")
