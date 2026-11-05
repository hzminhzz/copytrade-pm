"""Pinned public Propr display snapshot -> native 3 physical WS, NO_TRADE evidence."""

from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

import copytrade_pm.pm_forward_journal as journal_module
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_propr_universe import (
    build_propr_public_socket_layout,
    snapshot_sha256,
    verify_propr_display_layout,
)
from copytrade_pm.pm_forward_public_trades import (
    capture_sharded_native_trades,
    load_public_market_shards,
    native_coin,
    plan_sharded_utc_buckets,
    validate_public_market_catalog,
)

CONFIG = (
    Path(__file__).resolve().parents[1] / "docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json"
)
FIXED = datetime(2026, 11, 5, 12, 4, 0, tzinfo=UTC)
BUYER = "0x" + "1" * 40
SELLER = "0x" + "2" * 40


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED if tz is not None else FIXED.replace(tzinfo=None)


def known(s: int) -> str:
    return (FIXED.replace(minute=0) + timedelta(seconds=s)).isoformat()


def _fixture_snapshot() -> dict:
    from copytrade_pm.pm_forward_propr_universe import TOP_MAJORS

    return {
        "schema": "propr_public_universe_browser_snapshot_v1",
        "retrieved_on_utc_date": "2026-10-30",
        "snapshot_market_count": 13,
        "category_counts": {
            "crypto": 9,
            "equities": 2,
            "indices": 1,
            "commodities": 1,
            "fx": 0,
        },
        "market_symbols": {
            "crypto": list(TOP_MAJORS) + ["DOGE"],
            "equities": ["COPPER", "AAPL"],
            "indices": ["SP500"],
            "commodities": ["COPPER"],
        },
        "not_proof_of_historical_availability": True,
        "not_proof_of_execution_or_order_acceptance": True,
    }


def test_small_snapshot_deduplicates_display_without_losing_dex(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(_fixture_snapshot()))
    layout = build_propr_public_socket_layout(path)
    assert layout["display_market_count"] == 13
    assert layout["native_market_count"] == 12
    assert layout["deduplicated_display_symbols"] == 1
    assert [len(g["instruments"]) for g in layout["physical_sockets"]] == [8, 1, 3]
    assert layout["source_snapshot_sha256"] == snapshot_sha256(path)
    assert layout["paper_admitted"] is False
    assert verify_propr_display_layout(path, layout)["native_market_count"] == 12
    changed = dict(layout)
    changed["physical_sockets"] = [dict(v) for v in layout["physical_sockets"]]
    changed["physical_sockets"][1] = {
        **changed["physical_sockets"][1],
        "instruments": ["hyperliquid/mainnet:perp:default/ADA"],
    }
    with pytest.raises(ValueError, match="DISPLAY_PARITY_FAILED"):
        verify_propr_display_layout(path, changed)
    original = _fixture_snapshot()
    original["category_counts"]["fx"] = 1
    path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="CATEGORY_DRIFT"):
        build_propr_public_socket_layout(path)


def test_propr_cli_requires_snapshot_and_parallel_connection_budget(tmp_path, monkeypatch, capsys):
    """Before any journal/WS call, enforce source proof and shared-IP guard."""
    import sys

    from copytrade_pm.pm_forward_public_trades import main

    args = [
        "copytrade-pm-public-trades",
        "--mode",
        "observe",
        "--registry",
        str(tmp_path / "not-created-registry.sqlite"),
        "--portfolio",
        "P1",
        "--market-file",
        str(CONFIG),
        "--state-root",
        str(tmp_path / "not-created-journal"),
    ]
    monkeypatch.setattr(sys, "argv", args + ["--parallel-shards", "3"])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "ack-shared-ip-connection-budget" in capsys.readouterr().err
    assert not (tmp_path / "not-created-journal").exists()

    monkeypatch.setattr(sys, "argv", args + ["--parallel-shards", "1"])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "--propr-snapshot is required" in capsys.readouterr().err
    assert not (tmp_path / "not-created-journal").exists()


def test_pinned_157_native_market_layout_matches_propr_categories():
    config = json.loads(CONFIG.read_text())
    layout = load_public_market_shards(CONFIG)
    assert config["schema"] == "paper_public_physical_sockets_v1"
    assert config["source_snapshot_sha256"] == (
        "1a6cd762634d4f05e88577be1a43a5cf2dede643bf724ab743cf7a278e20179b"
    )
    assert config["display_market_count"] == 158
    assert config["native_market_count"] == 157
    assert config["deduplicated_display_symbols"] == 1
    assert [len(group) for _, group in layout] == [8, 88, 61]
    assert [name for name, _ in layout] == [
        "core_crypto_majors",
        "other_crypto_perps",
        "xyz_equities_indices_commodities",
    ]
    assert sum(x.market == "mainnet:perp:default" for _, group in layout for x in group) == 96
    assert sum(x.market == "mainnet:perp:xyz" for _, group in layout for x in group) == 61
    native = [native_coin(inst) for _, group in layout for inst in group]
    assert len(set(native)) == 157
    assert "xyz:COPPER" in native
    assert "COPPER" not in native
    assert len(config["logical_reporting_groups"]) == 5
    assert sum(len(group["instruments"]) for group in config["logical_reporting_groups"]) == 40
    assert {m for g in config["logical_reporting_groups"] for m in g["instruments"]} <= {
        inst.key for _, group in layout for inst in group
    }
    assert config["propr_order_ids_attested"] is False
    assert config["paper_admitted"] is False


def test_physical_sockets_fail_closed_on_missing_or_tampered_assets(tmp_path):
    config = json.loads(CONFIG.read_text())
    tmp = tmp_path / "layout.json"
    config["physical_sockets"][1]["instruments"].pop()
    tmp.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="NATIVE_MARKET_COUNT_DRIFT"):
        load_public_market_shards(tmp)
    config = json.loads(CONFIG.read_text())
    config["physical_sockets"][1]["instruments"].append(
        config["physical_sockets"][0]["instruments"][0]
    )
    tmp.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="DUPLICATE_MARKET"):
        load_public_market_shards(tmp)
    config = json.loads(CONFIG.read_text())
    config["propr_order_ids_attested"] = True
    tmp.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="PROVENANCE_REQUIRED"):
        load_public_market_shards(tmp)


def test_live_metadata_provider_must_verify_all_native_ids():
    layout = load_public_market_shards(CONFIG)
    instruments = tuple(inst for _, g in layout for inst in g)

    def catalog(request):
        dex = request.get("dex", "default")
        payload = {
            "universe": [
                {"name": native_coin(inst)}
                for inst in instruments
                if inst.market == "mainnet:perp:" + dex
            ]
        }
        raw = json.dumps(payload, sort_keys=True).encode()
        return payload, raw, sha256(raw).hexdigest()

    report = validate_public_market_catalog(instruments, info=catalog)
    assert report["markets_verified"] == 157
    assert sorted(row["markets"] for row in report["catalog_proofs"]) == [61, 96]

    def missing(request):
        payload, _, _ = catalog(request)
        if request.get("dex") == "xyz":
            payload["universe"] = [x for x in payload["universe"] if x["name"] != "xyz:GOLD"]
        raw = json.dumps(payload, sort_keys=True).encode()
        return payload, raw, sha256(raw).hexdigest()

    with pytest.raises(ValueError, match="MARKET_UNAVAILABLE:xyz:GOLD"):
        validate_public_market_catalog(instruments, info=missing)


class ThreePhysicalWS:
    def __init__(self) -> None:
        self.coins: list[str] = []
        self.frames: list[str] | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def send(self, message):
        self.coins.append(json.loads(message)["subscription"]["coin"])

    async def recv(self):
        if self.frames is None:
            base = int((FIXED.replace(minute=0) + timedelta(seconds=20)).timestamp() * 1000)

            def make_row(coin, tid):
                return {
                    "coin": coin,
                    "time": base,
                    "tid": tid,
                    "px": "100",
                    "sz": "2",
                    "side": "B",
                    "hash": "0x" + "f" * 64,
                    "users": [BUYER, SELLER],
                }

            self.frames = [
                json.dumps(
                    {
                        "channel": "trades",
                        "data": [make_row(c, i + 1) for i, c in enumerate(self.coins)],
                    }
                ),
                json.dumps(
                    {
                        "channel": "trades",
                        "data": [make_row(c, i + 1000) for i, c in enumerate(self.coins)],
                    }
                ),
            ]
        return self.frames.pop(0)


def test_three_physical_sockets_capture_each_157_market_buy_and_sell(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    layout = load_public_market_shards(CONFIG)
    universe = tuple(inst for _, group in layout for inst in group)
    journal = PaperJournal(tmp_path / "private")
    report = asyncio.run(
        capture_sharded_native_trades(
            instruments=universe,
            configured_shards=layout,
            watched={BUYER: "wallet:17", SELLER: "wallet:18"},
            journal=journal,
            duration_seconds=5,
            max_frames=2,
            max_parallel_shards=3,
            connect=lambda *_a, **_kw: ThreePhysicalWS(),
            now=lambda: known(240),
        )
    )
    assert report["shard_count"] == 3
    assert report["market_count"] == 157
    assert report["max_markets_per_shard"] == 88
    assert report["baseline_markets"] == 157
    assert report["all_markets_baselined"] is True
    assert report["new_wallet_receipts"] == 314
    assert report["matched_wallet_sides"] == 314
    assert report["financial_events_committed"] == 0
    assert report["paper_admitted"] is False
    for inst in universe:
        assert report["market_stats"][inst.key]["status"] == "ACTIVE_AFTER_BASELINE"
        assert journal.audit_public_wallet_trade_tape("wallet:17", inst.key)["receipts"] == 1
        assert journal.audit_public_wallet_trade_tape("wallet:18", inst.key)["receipts"] == 1
    # Execute the same sealed-data read contract on the entire native universe.
    plan = plan_sharded_utc_buckets(
        instruments=universe,
        configured_shards=layout,
        wallet_keys=("wallet:17", "wallet:18"),
        journal=journal,
        as_of=known(301),
    )
    assert plan["market_count"] == 157
    assert plan["shard_count"] == 3
    assert plan["result_count"] == 314
    assert plan["financial_events_committed"] == 0
    assert all(x["paper_executed"] is False for x in plan["buckets"])
    assert all(x["bucket_status"].startswith("BLOCKED") for x in plan["buckets"])
    with closing(sqlite3.connect(journal.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM public_wallet_trade_receipts").fetchone()[0] == 314
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
