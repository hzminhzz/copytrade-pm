"""Fail-closed, offline-only ML4T cohort recovery regression tests."""

from __future__ import annotations

import json
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import sqlite3

import polars as pl
import pytest

from copytrade_pm.pm_ml4t_batch_recovery import (
    anchored_batches,
    batch_minute,
    effective_k,
    local_sources,
    roster,
    save_private,
)
from copytrade_pm.pm_offline_repository import native_instrument
from copytrade_pm.pm_shadow import VerifiedHyperliquidMinuteSource


def test_sqlite_roster_uses_address_not_filename_and_exclusions(tmp_path):
    db = tmp_path / "inventory.sqlite"
    with closing(sqlite3.connect(db)) as con:
        con.executescript("""
            CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY, address TEXT);
            CREATE TABLE cohort_memberships(wallet_id INTEGER, cohort_id TEXT);
            CREATE TABLE wallet_aliases(wallet_id INTEGER, namespace TEXT, alias TEXT, known_at TEXT);
            CREATE TABLE cohorts(cohort_id TEXT, version INTEGER, source_sha256 TEXT);
            CREATE TABLE propfirm_exclusions(wallet_id INTEGER, address TEXT);
        """)
        con.execute("INSERT INTO cohorts VALUES ('ml4t-strict-66',1,?)", ("a" * 64,))
        for num in range(66):
            address = f"0x{num + 1:040x}"
            con.execute("INSERT INTO wallets VALUES (?,?)", (num + 1, address))
            con.execute("INSERT INTO cohort_memberships VALUES (?, 'ml4t-strict-66')", (num + 1,))
            con.execute(
                "INSERT INTO wallet_aliases VALUES (?,'ml4t_strict',?,?)",
                (num + 1, f"M{num + 1:02d}", "2026-11-05T00:00:00+00:00"),
            )
        con.commit()
    identities, sha = roster(db)
    assert len(identities) == 66
    assert identities["0x" + "0" * 39 + "1"]["alias"] == "M01"
    assert sha == "a" * 64
    with closing(sqlite3.connect(db)) as con:
        con.execute("INSERT INTO propfirm_exclusions VALUES (1,?)", ("0x" + "0" * 39 + "1",))
        con.commit()
    with pytest.raises(ValueError, match="INVALID_SQLITE_COHORT_CARDINALITY"):
        roster(db)


def test_local_merge_stale_alias_and_conflicting_tid_fail_closed(tmp_path):
    address = "0x" + "a" * 40
    ident = {address: {"alias": "M52", "wallet_id": 5}}
    first = {
        "alias": "M15",
        "address": address,
        "equity": 20000,
        "fills": [
            {
                "user": address,
                "coin": "HYPE",
                "time": 1793000000000,
                "tid": 10,
                "px": "20",
                "sz": "1",
                "side": "B",
                "start_position": "0",
            }
        ],
    }
    for folder, value in (
        ("ml4t_100k_500k_fills_90d", first),
        ("wallet_fills_90d", dict(first, fills=[dict(first["fills"][0], px="21")])),
    ):
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "random_file_name.json").write_text(json.dumps(value))
    found, result = local_sources(tmp_path, ident)
    assert result["source_json_alias_drift_files"] == 2
    assert result["conflicting_source_tids"] == 1
    assert len(found[address]["events"]) == 1
    assert "CONFLICTING_SOURCE_TID" in found[address]["errors"]


def test_anchored_delay_collapses_events_and_never_uses_future_fills():
    rows = pl.DataFrame(
        [
            {"alias": "M01", "coin": "BTC", "time": 61_001, "size": 2.0},
            {"alias": "M01", "coin": "BTC", "time": 119_999, "size": -1.0},
            {"alias": "M01", "coin": "BTC", "time": 180_001, "size": 3.0},
        ]
    )
    d1 = anchored_batches(rows, 1)
    d5 = anchored_batches(rows, 5)
    assert d1.height == 2
    assert d1["execute_ms"].to_list() == [180_000, 300_000]
    assert d1["net_qty"].to_list() == [1.0, 3.0]
    assert d5.height == 1
    assert d5["net_qty"][0] == 4.0
    assert d5["execute_ms"][0] == 420_000


def test_equity_scale_and_bar_boundaries():
    assert effective_k(Decimal(1) / Decimal(3), Decimal(50000)) == (
        Decimal(1) / Decimal(3) * Decimal("0.2")
    )
    assert effective_k(Decimal(1) / Decimal(3), Decimal(10000)) == (
        Decimal(1) / Decimal(3) * Decimal("0.35")
    )
    with pytest.raises(ValueError):
        effective_k(Decimal("0.5"), Decimal(0))
    assert batch_minute(60_001, 2) == 240_000


def test_hip3_resolves_native_dex_store_not_fake_ticker_folder():
    instrument = native_instrument("xyz:GOLD")
    assert str(VerifiedHyperliquidMinuteSource._family(instrument)).endswith(
        "HYPERLIQUID_XYZ_PERP/symbol=GOLD"
    )
    assert str(VerifiedHyperliquidMinuteSource._family(native_instrument("io:ANTH"))).endswith(
        "HYPERLIQUID_IO_PERP/symbol=ANTH"
    )
    assert str(VerifiedHyperliquidMinuteSource._family(native_instrument("BTC"))).endswith(
        "HYPERLIQUID_BTC_PERP"
    )


def test_private_immutable_report(tmp_path):
    out = tmp_path / "report"
    p = save_private(out, {"schema": "no_trade", "network_api_calls": 0})
    assert p.stat().st_mode & 0o777 == 0o600
    assert out.stat().st_mode & 0o777 == 0o700
    assert save_private(out, {"schema": "no_trade", "network_api_calls": 0}) == p


def test_supplemental_public_source_requires_raw_sha_and_exact_row_parity(tmp_path):
    address = "0x" + "a" * 40
    alias = sha256(address.encode()).hexdigest()[:18]
    root = tmp_path / "generation"
    raw_root = root / "raw" / alias
    normal = root / "normalized"
    raw_root.mkdir(parents=True)
    normal.mkdir(parents=True)
    event = {
        "user": address,
        "coin": "BTC",
        "tid": 9,
        "time": 1793000000000,
        "px": "60000",
        "sz": "0.01",
        "side": "B",
    }
    data = json.dumps([event]).encode()
    digest = sha256(data).hexdigest()
    (raw_root / "page-000.json").write_bytes(data)
    (raw_root / "page-000.meta.json").write_text(json.dumps({"page_sha256": digest}))
    payload = {
        "alias": "M01",
        "address": address,
        "fills": [event],
        "source_page_shas": [digest],
        "historical_first_known_proven": False,
        "source": "OFFICIAL_HL_INFO_HISTORICAL_NOT_PIT",
        "equity": None,
    }
    normalized_file = normal / f"{alias}.json"
    normalized_file.write_text(json.dumps(payload))
    identities = {address: {"alias": "M01", "wallet_id": 1}}
    sources, summary = local_sources(tmp_path, identities, extra_source_dirs=(normal,))
    assert summary["wallets_with_fills"] == 1
    assert len(sources[address]["events"]) == 1

    (raw_root / "page-000.json").write_text("[]")
    with pytest.raises(ValueError, match="PUBLIC_GENERATION_PAGE_SHA_MISMATCH"):
        local_sources(tmp_path, identities, extra_source_dirs=(normal,))
