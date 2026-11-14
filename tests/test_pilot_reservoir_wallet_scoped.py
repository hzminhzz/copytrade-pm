"""Adversarial unit tests; synthetic wallets only. Never access live S3."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
import sqlite3

import pytest

# Standalone Reservoir research uses the separate quant-lab Arrow/DuckDB venv.
# Core/market CI environments intentionally do not install these optional deps.
pa = pytest.importorskip("pyarrow", reason="optional Reservoir research dependency")
pytest.importorskip("polars", reason="optional Reservoir research dependency")

from scripts import pilot_reservoir_wallet_scoped as pilot  # noqa: E402


DAY = "2026-11-05"
WALLETS = {"0x" + "a" * 40, "0x" + "b" * 40}


def arrow_rows():
    return pa.Table.from_pylist(
        [
            {
                "wallet": "0x" + "a" * 40,
                "exchange_ts": datetime(2026, 11, 5, 2, tzinfo=UTC),
                "coin": "BTC",
                "dex": "hyperliquid",
                "side": "buy",
                "size": Decimal("1.0000000000"),
                "start_position": Decimal("0.0000000000"),
                "trade_id": 101,
                "direction": "Open Long",
                "is_liquidation": False,
            }
        ],
        schema=pa.schema(
            [
                ("wallet", pa.string()),
                ("exchange_ts", pa.timestamp("ms", tz="UTC")),
                ("coin", pa.string()),
                ("dex", pa.string()),
                ("side", pa.string()),
                ("size", pa.decimal128(20, 10)),
                ("start_position", pa.decimal128(20, 10)),
                ("trade_id", pa.uint64()),
                ("direction", pa.string()),
                ("is_liquidation", pa.bool_()),
            ]
        ),
    )


def test_lossless_source_validation_and_no_alias_leak():
    table = arrow_rows()
    result = pilot.validate_fills(table, WALLETS, DAY)
    assert result["rows"] == 1
    assert result["unique_wallet_trade_ids"] == 1
    assert not any(w in json.dumps(result) for w in WALLETS)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("wallet", "0x" + "f" * 40, "SOURCE_SCOPE_MISMATCH"),
        ("dex", "xyz", "SOURCE_SCOPE_MISMATCH"),
        ("side", "hold", "SOURCE_DIRECTION_OR_MARKET_INVALID"),
        ("size", Decimal("0.0000000000"), "SOURCE_NONPOSITIVE_SIZE"),
        ("exchange_ts", datetime(2026, 11, 4, tzinfo=UTC), "SOURCE_TIMESTAMP_DAY_MISMATCH"),
        ("trade_id", None, "SOURCE_MISSING_TRADE_ID"),
    ],
)
def test_source_fails_closed_on_scope_or_schema(field, value, reason):
    src = arrow_rows()
    out = src.to_pylist()[0]
    out[field] = value
    invalid = pa.Table.from_pylist([out], schema=src.schema)
    with pytest.raises(ValueError, match=reason):
        pilot.validate_fills(invalid, WALLETS, DAY)


def test_rejects_duplicate_trade_id_for_wallet():
    src = arrow_rows()
    duplicated = pa.concat_tables([src, src])
    with pytest.raises(ValueError, match="SOURCE_DUPLICATE_TRADE_ID"):
        pilot.validate_fills(duplicated, WALLETS, DAY)


def test_private_immutable_publish_and_tamper(tmp_path):
    folder = tmp_path / "fills" / "day=2026-11-05"
    table = arrow_rows()
    receipt = pilot.publish_table(
        folder, table, "etag", "scopehash", "f/path.parquet", DAY, {"rows": 1}
    )
    assert (folder / "data.parquet").stat().st_mode & 0o777 == 0o600
    assert receipt["rows"] == 1
    assert pilot.verify_artifact(folder, "etag", "scopehash")["sha256"] == receipt["sha256"]
    with pytest.raises(ValueError, match="SCOPE_DRIFT"):
        pilot.verify_artifact(folder, "etag2", "scopehash")
    with pytest.raises(ValueError, match="SOURCE_VERSION_OR_SCOPE_DRIFT"):
        pilot.publish_table(folder, table, "etag2", "scopehash2", "f/path.parquet", DAY, {})


def test_incomplete_pair_is_blocked(tmp_path):
    folder = tmp_path / "day=2026-11-05"
    folder.mkdir()
    (folder / "data.parquet").write_bytes(b"partial")
    with pytest.raises(ValueError, match="BLOCKED_INCOMPLETE"):
        pilot.verify_artifact(folder, "etag", "scope")


def test_date_window_is_bounded():
    start = date(2026, 11, 5)
    assert len(pilot.date_window(start, start + timedelta(days=6))) == 7
    with pytest.raises(ValueError):
        pilot.date_window(start, start + timedelta(days=7))
    with pytest.raises(ValueError):
        pilot.date_window(date(2026, 11, 13), date(2026, 11, 13))


def test_selected_sealed_roster_and_missing_seal(tmp_path):
    db = tmp_path / "registry.sqlite"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY, address TEXT);
        CREATE TABLE portfolio_seals(
          portfolio_id TEXT, version INTEGER, selection_known_at TEXT,
          definition_sha256 TEXT
        );
        CREATE TABLE portfolio_memberships(
          portfolio_id TEXT, version INTEGER, member_alias TEXT, wallet_id INTEGER
        );
    """)
    for i in range(14):
        c.execute(
            "INSERT INTO wallets VALUES (?,?)",
            (i + 1, "0x" + f"{i + 1:040x}"),
        )
    members = [1, 2, 3, 3, 4, 5, 5, 6, 7, 8, 9, 10, 10, 11, 12, 12, 13, 14]
    for j, name in enumerate(pilot.SELECTED_PORTFOLIOS):
        c.execute(
            "INSERT INTO portfolio_seals VALUES (?,?,?,?)",
            (name, 2, "2026-11-07T01:08:46Z", "a" * 64),
        )
        for k, member in enumerate(members[j * 3 : (j + 1) * 3]):
            c.execute(
                "INSERT INTO portfolio_memberships VALUES (?,?,?,?)",
                (name, 2, f"M{k}", member),
            )
    c.commit()
    addresses, scope = pilot.registry_scope(db)
    assert len(addresses) == 14
    assert scope["member_records"] == 18
    assert scope["study_class"] == "RETROSPECTIVE_FIXED_COHORT_NOT_PIT_SELECTION"
    c.execute(
        "DELETE FROM portfolio_seals WHERE portfolio_id=?",
        (pilot.SELECTED_PORTFOLIOS[-1],),
    )
    c.commit()
    c.close()
    with pytest.raises(ValueError, match="MISSING_SELECTED_SEALED_MEMBERS"):
        pilot.registry_scope(db)


def test_production_monitored_plus_six_scope_freezes_269_and_preserves_five(
    tmp_path,
):
    db = tmp_path / "roster.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,address TEXT);
        CREATE TABLE portfolio_seals(
          portfolio_id TEXT,version INTEGER,selection_known_at TEXT,
          definition_sha256 TEXT
        );
        CREATE TABLE portfolio_memberships(
          portfolio_id TEXT,version INTEGER,member_alias TEXT,wallet_id INTEGER
        );
        CREATE TABLE monitoring(
          wallet_id INTEGER,configured INTEGER,subscribed INTEGER,known_at TEXT
        );
        CREATE TABLE snapshot_meta(key TEXT PRIMARY KEY,value TEXT);
    """)
    for i in range(269):
        conn.execute("INSERT INTO wallets VALUES(?,?)", (i + 1, "0x" + f"{i + 1:040x}"))
    for i in range(264):
        conn.execute(
            "INSERT INTO monitoring VALUES(?,?,?,?)",
            (i + 1, 1, 1, "2026-11-04T09:36:57Z"),
        )
    # Nine source-selection wallets are monitored; five are outside.
    members = [1, 2, 3, 4, 5, 6, 7, 8, 9, 265, 266, 267, 268, 269]
    edges = members[:12] + [
        members[12],
        members[13],
        members[0],
        members[1],
        members[2],
        members[3],
    ]
    for j, name in enumerate(pilot.SELECTED_PORTFOLIOS):
        conn.execute(
            "INSERT INTO portfolio_seals VALUES(?,?,?,?)",
            (name, 2, "2026-11-07T00:00:00Z", "b" * 64),
        )
        for k, wid in enumerate(edges[j * 3 : (j + 1) * 3]):
            conn.execute(
                "INSERT INTO portfolio_memberships VALUES(?,?,?,?)",
                (name, 2, f"S{k}", wid),
            )
    conn.executemany(
        "INSERT INTO snapshot_meta VALUES (?,?)",
        [
            ("manifest_sha256", "c" * 64),
            ("observed_at", "2026-11-04T09:36:57Z"),
        ],
    )
    conn.commit()
    conn.close()
    selection, selected_scope = pilot.scope_from_registry("sealed_six", db)
    assert len(selection) == 14
    enlarged, scope = pilot.scope_from_registry("monitored_plus_six", db)
    assert len(enlarged) == 269
    assert set(selection).issubset(enlarged)
    assert scope["production_monitored_count"] == 264
    assert scope["selected_outside_monitored"] == 5
    assert scope["wallet_set_sha256"] != selected_scope["wallet_set_sha256"]
    assert scope["study_class"] == "RETROSPECTIVE_FIXED_MONITORED_PLUS_SIX_NOT_PIT"


def test_preflight_respects_projected_budget_and_never_fetches_wallet_data(tmp_path, monkeypatch):
    class DummyConn:
        def close(self):
            pass

    monkeypatch.setattr(
        pilot,
        "registry_scope",
        lambda path=pilot.REGISTRY: (
            ["0x" + f"{i:040x}" for i in range(14)],
            {
                "wallet_count": 14,
                "wallet_set_sha256": "d" * 64,
                "portfolio_versions": {},
            },
        ),
    )
    monkeypatch.setattr(pilot, "remote_connection", DummyConn)
    monkeypatch.setattr(
        pilot,
        "source_keys",
        lambda day: (
            {
                "key": f"by_dex/hyperliquid/fills/perp/all/date={day}/fills.parquet",
                "bytes": 500,
                "etag": "e",
                "type": "fills",
            },
            {
                "key": f"global/snapshots/perp/all/date={day}/1_1770249600000.parquet",
                "bytes": 60,
                "etag": "e",
                "type": "position_snapshot",
                "block": 1,
                "state_ts_ms": 1770249600000,
            },
        ),
    )
    monkeypatch.setattr(
        pilot,
        "column_budget",
        lambda con, key, fields: {
            "projected_compressed_bytes": 100,
            "selected_columns": list(fields),
            "source_columns": 28,
            "row_groups": 2,
            "address_or_user_stats_row_groups": 0,
        },
    )
    with pytest.raises(ValueError, match="COST_CAP_ESTIMATE_EXCEEDED"):
        pilot.preflight(date(2026, 11, 5), date(2026, 11, 5), tmp_path, 199)
    assert not (tmp_path / "preflight.json").exists()
    ok = pilot.preflight(date(2026, 11, 5), date(2026, 11, 5), tmp_path, 200)
    assert ok["object_count"] == 2
    assert ok["total_projected_compressed_MB"] == 0.0
    assert (tmp_path / "preflight.json").is_file()
