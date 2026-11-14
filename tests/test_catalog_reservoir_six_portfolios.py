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


def test_window_map_exact_134_day_two_dex_and_reuses_existing_pilot():
    mapping = catalog.window_sources()
    assert len(mapping) == 268
    assert {dex for dex, _ in mapping} == {"hyperliquid", "xyz"}
    assert mapping[("hyperliquid", "2026-11-11")] == pilot.OUTPUT
    assert mapping[("xyz", "2026-11-11")] != pilot.OUTPUT
    assert len({date for _, date in mapping}) == 134
    assert ("hyperliquid", "2026-07-01") in mapping
    assert ("xyz", "2026-07-01") in mapping
    assert ("xyz", "2026-06-30") not in mapping
    assert len(catalog.historical_windows()) == 15
    assert catalog.historical_windows()[-1][2] == date(2026, 10, 11)


def test_fails_closed_outside_two_dex_scope_and_dates():
    item = fake_index()
    with pytest.raises(ValueError, match="SOURCE_DEX_NOT_APPROVED"):
        catalog.scan_fills(item, "cash")
    with pytest.raises(ValueError, match="OUTSIDE_VERIFIED_DATE_WINDOW"):
        catalog.scan_fills(item, "xyz", date(2026, 6, 30), date(2026, 7, 1))
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


def frozen_offline_fixture(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """One UTC day for two DEXes, preserving the same pinned source structure."""
    import hashlib
    import json

    import pyarrow as pa
    import pyarrow.parquet as pq

    monkeypatch.setattr(catalog, "START", date(2026, 7, 1))
    monkeypatch.setattr(catalog, "END", date(2026, 7, 1))
    monkeypatch.setattr(catalog, "PRIVATE_RESEARCH_ROOT", tmp_path)
    roots = {(dex, "2026-07-01"): tmp_path / dex for dex in ("hyperliquid", "xyz")}
    monkeypatch.setattr(catalog, "window_sources", lambda cohort: roots)
    monkeypatch.setattr(
        catalog,
        "scope_from_registry",
        lambda _cohort: (_ for _ in ()).throw(
            AssertionError("Offline status consulted live registry")
        ),
    )
    scope = {
        "cohort": "monitored_plus_six",
        "wallet_count": 269,
        "wallet_set_sha256": "a" * 64,
    }
    entries = []
    for dex in ("hyperliquid", "xyz"):
        root = roots[(dex, "2026-07-01")]
        objects = []
        artifacts = []
        for kind in ("fills", "position_snapshot"):
            folder = root / kind / "day=2026-07-01"
            folder.mkdir(parents=True)
            file_path = folder / "data.parquet"
            pq.write_table(pa.table({"value": [1]}), file_path)
            sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
            key = f"by_dex/{dex}/{kind}/date=2026-07-01/test.parquet"
            record = {
                "type": kind,
                "key": key,
                "etag": "etag-pinned",
                "bytes": 200,
                "block": 123,
                "state_ts_ms": 1782864000000,
            }
            objects.append(record)
            (folder / "provenance.json").write_text(
                json.dumps(
                    {
                        "source_etag": record["etag"],
                        "wallet_set_sha256": scope["wallet_set_sha256"],
                        "source_key": key,
                        "sha256": sha,
                        "rows": 1,
                    }
                )
            )
            artifacts.append(
                {
                    "kind": kind,
                    "path": str(file_path),
                    "parquet_sha256": sha,
                    "rows_staged": 1,
                    "rows_within_scope": 1,
                    "source_key": key,
                    "source_etag": record["etag"],
                    "source_object_bytes": record["bytes"],
                    "source_state_block": record["block"] if kind == "position_snapshot" else None,
                    "source_state_ts_ms": (
                        record["state_ts_ms"] if kind == "position_snapshot" else None
                    ),
                }
            )
        preflight_path = root / "preflight.json"
        preflight_path.write_text(
            json.dumps(
                {
                    "scope": scope,
                    "dex": dex,
                    "snapshot_scope": "dex",
                    "days": ["2026-07-01"],
                    "objects": objects,
                }
            )
        )
        entries.append(
            {
                "day": "2026-07-01",
                "dex": dex,
                "preflight_sha256": hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
                "artifacts": artifacts,
            }
        )
    folder = tmp_path / "catalog"
    folder.mkdir()
    saved = {
        "schema": "reservoir_two_dex_catalog_v3",
        "cohort": "monitored_plus_six",
        "start": "2026-07-01",
        "end": "2026-07-01",
        "dates": ["2026-07-01"],
        "allowed_dexes": ["hyperliquid", "xyz"],
        "scope": scope,
        "source_status": "HISTORICAL_SELECTED_WALLET_STAGED_ONLY",
        "historical_first_known": False,
        "scientifically_qualified": False,
        "paper_admitted": False,
        "trading_authorized": False,
        "entries": entries,
        "counts": {
            dex: {
                "fills": 1,
                "snapshot_position_rows": 1,
                "verified_dates": 1,
            }
            for dex in ("hyperliquid", "xyz")
        },
    }
    (folder / "catalog.json").write_text(json.dumps(saved))
    return folder, roots[("xyz", "2026-07-01")] / "fills" / "day=2026-07-01" / "data.parquet"


def test_offline_status_verifies_completion_without_aws_or_live_registry(
    monkeypatch, tmp_path: Path
):
    folder, _ = frozen_offline_fixture(monkeypatch, tmp_path)
    receipt = catalog.verify_frozen_catalog(folder)
    assert receipt["status"] == "HISTORICAL_SOURCE_COMPLETE_VERIFIED_OFFLINE"
    assert receipt["artifacts_verified"] == 4
    assert receipt["counts"]["xyz"]["fills"] == 1
    assert receipt["aws_login_required"] is False
    assert receipt["scientifically_qualified"] is False


def test_offline_status_rejects_mutated_artifact(monkeypatch, tmp_path: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    folder, path = frozen_offline_fixture(monkeypatch, tmp_path)
    pq.write_table(pa.table({"value": [9999]}), path)
    with pytest.raises(ValueError, match="BLOCKED_STAGED_SHA_MISMATCH"):
        catalog.verify_frozen_catalog(folder)


def test_offline_status_rejects_false_catalog_aggregate(monkeypatch, tmp_path: Path):
    import json

    folder, _ = frozen_offline_fixture(monkeypatch, tmp_path)
    catalog_path = folder / "catalog.json"
    saved = json.loads(catalog_path.read_text())
    saved["counts"]["xyz"]["fills"] = 9
    catalog_path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="FROZEN_CATALOG_AGGREGATE_MISMATCH"):
        catalog.verify_frozen_catalog(folder)


def test_offline_status_rejects_unknown_or_missing_cohort(monkeypatch, tmp_path: Path):
    folder, _ = frozen_offline_fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="OFFLINE_STATUS_ONLY_FOR_MONITORED_COHORT"):
        catalog.verify_frozen_catalog(folder, "sealed_six")
    (folder / "catalog.json").unlink()
    with pytest.raises(ValueError, match="MISSING_OR_SYMLINKED_EVIDENCE"):
        catalog.verify_frozen_catalog(folder)


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
