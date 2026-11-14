"""269-wallet Reservoir cohort and source-metadata reuse tests. No live S3."""

from datetime import date
import json
from pathlib import Path

import pytest

pytest.importorskip("pyarrow", reason="optional Reservoir research dependency")
pytest.importorskip("polars", reason="optional Reservoir research dependency")

from scripts import backfill_reservoir_six_from_july as backfill  # noqa: E402
from scripts import catalog_reservoir_six_portfolios as catalog  # noqa: E402
from scripts import pilot_reservoir_wallet_scoped as pilot  # noqa: E402


def test_monitored_window_covers_full_requested_range_and_preserves_old():
    latest = backfill.windows("monitored_plus_six")
    assert len(latest) == 20
    assert latest[0][1] == date(2026, 7, 1)
    assert latest[-1][2] == date(2026, 11, 11)
    assert sum((b - a).days + 1 for _, a, b in latest) == 134
    assert latest == catalog.monitored_windows()
    assert len(backfill.windows("sealed_six")) == 15


def test_monitored_roots_do_not_overwrite_narrower_source():
    token = backfill.windows("monitored_plus_six")[0][0]
    narrow = backfill.root_for(token, "hyperliquid", "sealed_six")
    broad = backfill.root_for(token, "hyperliquid", "monitored_plus_six")
    assert narrow != broad
    assert "reservoir-monitored-plus-six" in str(broad)
    assert backfill.root_for(token, "xyz", "monitored_plus_six") != broad
    with pytest.raises(ValueError, match="THIRD_DEX_NOT_ALLOWED"):
        backfill.root_for(token, "cash", "monitored_plus_six")


def test_catalog_new_scope_has_exact_268_dex_days():
    roots = catalog.window_sources("monitored_plus_six")
    assert len(roots) == 268
    assert ("hyperliquid", "2026-07-01") in roots
    assert ("xyz", "2026-11-11") in roots
    assert pilot.OUTPUT not in set(roots.values())
    assert all("reservoir-monitored-plus-six" in str(root) for root in roots.values())


def test_preflight_reuses_old_exact_parquet_metadata_without_any_s3(monkeypatch, tmp_path: Path):
    day = "2026-07-01"
    old = tmp_path / "old"
    old.mkdir()
    narrow = {
        "wallet_set_sha256": "a" * 64,
        "portfolio_versions": {"A": {"version": 2}},
    }
    broad = {
        **narrow,
        "cohort": "monitored_plus_six",
        "wallet_set_sha256": "b" * 64,
        "wallet_count": 269,
    }
    fill = {
        "type": "fills",
        "key": f"by_dex/xyz/fills/perp/all/date={day}/fills.parquet",
        "etag": "test-etag",
        "bytes": 1000,
        "column_budget": {
            "selected_columns": list(pilot.CORE),
            "projected_compressed_bytes": 700,
        },
    }
    anchor = {
        "type": "position_snapshot",
        "key": f"by_dex/xyz/snapshots/perp/date={day}/1_1782864000000.parquet",
        "etag": "test-etag",
        "bytes": 200,
        "column_budget": {
            "selected_columns": list(pilot.SNAP_FIELDS),
            "projected_compressed_bytes": 90,
        },
    }
    (old / "preflight.json").write_text(
        json.dumps(
            {
                "scope": narrow,
                "dex": "xyz",
                "days": [day],
                "objects": [fill, anchor],
            }
        )
    )
    monkeypatch.setattr(
        backfill,
        "scope_from_registry",
        lambda cohort: (["0x" + f"{i:040x}" for i in range(269)], broad),
    )
    monkeypatch.setattr(
        backfill,
        "registry_scope",
        lambda: (["0x" + f"{i:040x}" for i in range(14)], narrow),
    )
    monkeypatch.setattr(
        backfill,
        "sealed_window_sources",
        lambda: {("xyz", day): old},
    )

    def forbid_s3(*_args, **_kwargs):
        raise AssertionError("Unexpected AWS S3 request while reusing metadata")

    monkeypatch.setattr(backfill, "remote_connection", forbid_s3)
    monkeypatch.setattr(backfill, "source_keys", forbid_s3)
    destination = tmp_path / "new"
    result = backfill.cached_metadata_preflight(
        date(2026, 7, 1),
        date(2026, 7, 1),
        destination,
        "xyz",
        790,
    )
    assert result["metadata_objects_reused"] == 2
    assert result["wallet_count"] == 269
    saved = json.loads((destination / "preflight.json").read_text())
    assert saved["scope"]["cohort"] == "monitored_plus_six"
    assert saved["scope"]["wallet_set_sha256"] == "b" * 64
    assert saved["total_projected_compressed_bytes"] == 790
    with pytest.raises(FileExistsError):
        backfill.cached_metadata_preflight(
            date(2026, 7, 1),
            date(2026, 7, 1),
            destination,
            "xyz",
            790,
        )


def test_duckdb_parameterized_one_scan_supports_269_wallets(monkeypatch, tmp_path):
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq

    from tests.test_pilot_reservoir_wallet_scoped import arrow_rows

    prototype = arrow_rows()
    rows = []
    for wid, trade in ((1, 101), (999, 999)):
        record = prototype.to_pylist()[0]
        record["wallet"] = "0x" + f"{wid:040x}"
        record["trade_id"] = trade
        rows.append(record)
    source = pa.Table.from_pylist(rows, schema=prototype.schema)
    source = source.rename_columns(
        [
            "address" if c == "wallet" else "timestamp" if c == "exchange_ts" else c
            for c in source.column_names
        ]
    )
    raw = tmp_path / "raw.parquet"
    pq.write_table(source, raw)
    monkeypatch.setattr(pilot, "S3_PREFIX", str(tmp_path))
    wallets = ["0x" + f"{i:040x}" for i in range(1, 270)]
    with duckdb.connect() as con:
        returned = pilot.fetch_fills(con, "raw.parquet", wallets, "2026-07-01")
    assert returned.num_rows == 1
    assert returned.column("trade_id").to_pylist() == [101]


def test_new_cohort_requires_full_explicit_date_coverage(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "scope_from_registry",
        lambda _cohort: (
            ["0x" + f"{i:040x}" for i in range(269)],
            {"wallet_set_sha256": "b" * 64, "portfolio_versions": {}},
        ),
    )
    monkeypatch.setattr(
        catalog,
        "window_sources",
        lambda _c: {
            ("xyz", "2026-07-01"): Path("/tmp/no-data"),
        },
    )
    with pytest.raises(ValueError, match="WINDOW_COVERAGE_INCOMPLETE"):
        catalog.build_index("monitored_plus_six")
