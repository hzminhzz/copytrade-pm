"""Offline, deterministic checks for the major-four fill-turnover portfolio screen."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import phase7_major4_portfolio_screen as screen


def sample_wallet(alias: str, address: str, *, weights: dict, source: str = "wallet_fills_90d"):
    return {
        "alias": alias,
        "address": address,
        "recommendation": "CANDIDATE_UNVERIFIED",
        "gross_turnover_by_coin_fraction": weights,
        "observation_days": 60,
        "last_fill_age_days_at_cutoff": 2.0,
        "main_perp_fill_fraction": 1.0,
        "fills_per_observation_day": 20.0,
        "opening_positions": True,
        "source": source,
    }


def test_major4_rejects_other_coins_and_separates_weight_from_return() -> None:
    a = sample_wallet(
        "A",
        "0x" + "a" * 40,
        weights={"BTC": 0.4, "ETH": 0.2, "SOL": 0.2, "HYPE": 0.1, "xyz:BTC": 0.1},
    )
    b = sample_wallet(
        "B",
        "0x" + "b" * 40,
        weights={"BTC": 0.3, "ETH": 0.3, "SOL": 0.1, "HYPE": 0.2, "xyz:BTC": 0.1},
    )
    c = sample_wallet(
        "C",
        "0x" + "c" * 40,
        weights={"BTC": 0.2, "ETH": 0.2, "SOL": 0.3, "HYPE": 0.2, "BTC/USDT": 0.1},
    )
    out = screen.composition((a, b, c))
    assert out["ninety_day_equal_wallet_turnover_fractions"]["BTC"] == pytest.approx(0.3)
    assert out["ninety_day_four_major_share"] == pytest.approx(0.9)
    assert out["actual_follower_pnl"] is None
    assert out["source_equity_faithful"] is False
    assert out["complete_source_account_books"] == 0
    assert out["portfolio_drawdown"] is None


def test_duplicate_source_addresses_fail_closed() -> None:
    a = sample_wallet("A", "0x" + "1" * 40, weights={"BTC": 1})
    b = sample_wallet("B", "0x" + "1" * 40, weights={"HYPE": 1})
    c = sample_wallet("C", "0x" + "3" * 40, weights={"SOL": 1})
    with pytest.raises(ValueError, match="NON_UNIQUE_SOURCE_WALLETS"):
        screen.composition((a, b, c))


def test_exact_market_threshold_and_trial_count() -> None:
    rows = [
        sample_wallet(
            f"Z{i}",
            f"0x{i:040x}",
            weights={"BTC": 0.4, "ETH": 0.2, "SOL": 0.2, "HYPE": 0.2},
        )
        for i in range(3)
    ]
    checked, eligible, top = screen.evaluate_combinations(rows)
    assert checked == {"3": 1}
    assert len(eligible) == 1
    assert len(top) == 1


def test_registry_is_exact_address_authority(tmp_path: Path) -> None:
    file = tmp_path / "private-registry.sqlite"
    with closing(sqlite3.connect(file)) as db:
        db.executescript(
            """
            CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,address TEXT);
            CREATE TABLE cohort_memberships(wallet_id INTEGER,cohort_id TEXT);
            CREATE TABLE exclusions(wallet_id INTEGER);
            CREATE TABLE snapshot_meta(key TEXT,value TEXT);
            """
        )
        db.execute("INSERT INTO snapshot_meta VALUES (?,?)", ("manifest_sha256", "a" * 64))
        db.execute("INSERT INTO snapshot_meta VALUES (?,?)", ("observed_at", "2026-11-04"))
        for i in range(158):
            db.execute("INSERT INTO wallets VALUES (?,?)", (i + 1, f"0x{i:040x}"))
            cohort = "research-108" if i < 108 else "nansen-20" if i < 128 else "hyperx-30"
            db.execute("INSERT INTO cohort_memberships VALUES (?,?)", (i + 1, cohort))
        db.execute("INSERT INTO exclusions VALUES (?)", (158,))
        db.commit()
    present, denied, meta = screen.registry_addresses(file)
    assert len(present) == 158
    assert f"0x{157:040x}" in denied
    assert meta["registry_manifest_sha256"] == "a" * 64


def test_load_recent_reconciles_raw_and_csv_and_detects_source_drift(tmp_path: Path) -> None:
    a = "0x" + "a" * 40
    b = "0x" + "b" * 40
    first = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)
    last = int(datetime(2026, 10, 15, tzinfo=UTC).timestamp() * 1000)
    raw = sample_wallet("A", a, weights={"BTC": 0.5, "ETH": 0.5}, source="wallet_fills_90d")
    csv = sample_wallet("B", b, weights={"SOL": 0.5, "HYPE": 0.5}, source="phase5_new50_csv")
    folder = tmp_path / "data/wallet_fills_90d"
    folder.mkdir(parents=True)
    (folder / "a.json").write_text(
        json.dumps(
            {
                "address": a,
                "fills": [
                    {"time": first, "coin": "BTC", "px": "2", "sz": "1"},
                    {"time": last, "coin": "ETH", "px": "1", "sz": "2"},
                ],
            }
        )
    )
    (tmp_path / "docs").mkdir()
    with gzip.open(
        tmp_path / "docs/PHASE5_NEW50_ALL_FILLS_CONSOLIDATED_20261104.csv.gz", "wt"
    ) as output:
        output.write("address,coin,price,size,datetime_utc\n")
        output.write(f"{b},SOL,1,2,2026-09-01 00:00:00\n")
        output.write(f"{b},HYPE,1,2,2026-10-15 00:00:00\n")
    sha_map = {
        "wallet_fills_90d/a.json": sha256((folder / "a.json").read_bytes()).hexdigest(),
        "docs/PHASE5_NEW50_ALL_FILLS_CONSOLIDATED_20261104.csv.gz": sha256(
            (tmp_path / "docs/PHASE5_NEW50_ALL_FILLS_CONSOLIDATED_20261104.csv.gz").read_bytes()
        ).hexdigest(),
    }
    recent, audits = screen.load_recent([raw, csv], tmp_path, expected_source_sha=sha_map)
    bad_sha = {**sha_map, "wallet_fills_90d/a.json": "0" * 64}
    with pytest.raises(ValueError, match="FROZEN_RAW_SOURCE_SHA_MISMATCH"):
        screen.load_recent([raw, csv], tmp_path, expected_source_sha=bad_sha)
    assert audits["direct_raw_address_count"] == 1
    assert recent["A"]["first60"]["fractions"]["BTC"] == 1
    assert recent["B"]["last30"]["fractions"]["HYPE"] == 1
    bad = {**raw, "gross_turnover_by_coin_fraction": {"BTC": 0.1, "ETH": 0.9}}
    with pytest.raises(ValueError, match="SOURCE_UNIVERSE_RECONSTRUCTION_DRIFT"):
        screen.load_recent([bad, csv], tmp_path)


def test_selected_experiment_slots_are_three_four_five() -> None:
    assert {len(x) for x in screen.EXPERIMENTS.values()} == {3, 4, 5}
    for members in screen.EXPERIMENTS.values():
        assert len(set(members)) == len(members)
