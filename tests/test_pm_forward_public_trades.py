"""Provisional public trade intake, PIT UTC buckets, quote as-of, and strict no-trade."""

import asyncio
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import sqlite3

import pytest

import copytrade_pm.pm_forward_journal as journal_module
from copytrade_pm.pm03_account import Instrument, digest
from copytrade_pm.pm_forward_batch import ForwardBatch
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_quote_execution import preview_top_level_paper_cost
from copytrade_pm.pm_forward_public_trades import (
    capture_bounded_native_trades,
    native_coin,
    normalize_native_trade,
    plan_latest_public_utc_bucket,
    registry_watched_addresses,
)
from test_pm_forward_batch import admission
from test_pm_forward_ccxt_tape import quotes
from test_pm_forward_ccxt_market import BTC, at

BUYER = "0x" + "1" * 40
SELLER = "0x" + "2" * 40
OUTSIDER = "0x" + "3" * 40
EPOCH = "e" * 32
BUCKET = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 4, 12, 4, tzinfo=tz or UTC)


def trade(tid, seconds, users=(BUYER, SELLER), sz="2"):
    return {
        "coin": "BTC",
        "px": "100",
        "sz": sz,
        "side": "B",
        "time": int((BUCKET + timedelta(seconds=seconds)).timestamp() * 1000),
        "tid": tid,
        "hash": "0x" + "f" * 64,
        "users": list(users),
    }


def known(seconds):
    return (BUCKET + timedelta(seconds=seconds)).isoformat()


def normalized(tid, seconds, users=(BUYER, SELLER), sz="2", *, known_seconds=None):
    return normalize_native_trade(
        trade(tid, seconds, users=users, sz=sz),
        instrument=BTC,
        watched={BUYER: "wallet:17", SELLER: "wallet:18"},
        first_known_at=known(known_seconds or seconds + 1),
        stream_epoch=EPOCH,
    )


def test_native_public_trade_buyer_seller_and_no_private_address_leak():
    rows = normalized(1, 40)
    assert native_coin(BTC) == "BTC"
    assert [r["signed_qty"] for r in rows] == ["2", "-2"]
    assert [r["wallet_key"] for r in rows] == ["wallet:17", "wallet:18"]
    assert rows[0]["event_key"] != rows[1]["event_key"]
    assert rows[0]["source_account_complete"] is False
    assert rows[0]["paper_admitted"] is False
    assert BUYER not in json.dumps(rows)
    assert SELLER not in json.dumps(rows)
    assert not any("address" in r for r in rows)
    assert native_coin(Instrument("hyperliquid", "mainnet:perp:xyz", "BRENTOIL")) == (
        "xyz:BRENTOIL"
    )


def test_unknown_trade_parts_and_future_clock_fail_closed():
    invalid = trade(2, 60)
    with pytest.raises(ValueError, match="FUTURE"):
        normalize_native_trade(
            invalid,
            instrument=BTC,
            watched={BUYER: "wallet:17"},
            first_known_at=known(59),
            stream_epoch=EPOCH,
        )
    with pytest.raises(ValueError, match="COIN_IDENTITY"):
        normalize_native_trade(
            {**invalid, "coin": "@SPOT"},
            instrument=BTC,
            watched={BUYER: "wallet:17"},
            first_known_at=known(70),
            stream_epoch=EPOCH,
        )
    with pytest.raises(ValueError, match="BUYER_SELLER"):
        normalize_native_trade(
            {**invalid, "users": []},
            instrument=BTC,
            watched={BUYER: "wallet:17"},
            first_known_at=known(70),
            stream_epoch=EPOCH,
        )
    result = normalize_native_trade(
        invalid,
        instrument=BTC,
        watched={OUTSIDER: "wallet:19"},
        first_known_at=known(70),
        stream_epoch=EPOCH,
    )
    assert result == []


def test_scoped_utc_planner_is_durable_restart_safe_and_nonfinancial(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    journal = PaperJournal(tmp_path / "private")
    journal.append_public_wallet_trades(normalized(1, 40))
    window = plan_latest_public_utc_bucket(
        journal=journal,
        instruments=(BTC,),
        wallet_keys=("wallet:17", "wallet:18"),
        as_of=known(304),
    )
    assert window["window_start_at"] == known(0)
    assert window["due_at"] == known(300)
    assert window["result_count"] == 2
    assert all(x["bucket_status"].startswith("BLOCKED") for x in window["buckets"])
    assert all(x["paper_executed"] is False for x in window["buckets"])
    assert window["financial_events_committed"] == 0
    restored = PaperJournal(tmp_path / "private")
    again = plan_latest_public_utc_bucket(
        journal=restored,
        instruments=(BTC,),
        wallet_keys=("wallet:17", "wallet:18"),
        as_of=known(305),
    )
    assert again["result_count"] == 2
    future_delay = plan_latest_public_utc_bucket(
        journal=restored,
        instruments=(BTC,),
        wallet_keys=("wallet:17",),
        as_of=known(606),
        timing_policy="UTC_BUCKET_PLUS_5M",
    )
    assert future_delay["due_at"] == known(600)
    assert future_delay["buckets"][0]["observed_net_delta"] == "2"


def test_sqlite_first_known_idempotent_and_utc_net_with_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    journal = PaperJournal(tmp_path / "private")
    first = normalized(1, 40, sz="2")
    trim = normalized(2, 80, users=(SELLER, BUYER), sz="1")
    assert journal.append_public_wallet_trades(first)["new_receipts"] == 2
    assert journal.append_public_wallet_trades(trim)["new_receipts"] == 2
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)["receipts"] == 2
    repeated = [{**row, "first_known_at": known(250), "stream_epoch": "f" * 32} for row in first]
    assert journal.append_public_wallet_trades(repeated)["duplicates"] == 2
    with closing(sqlite3.connect(journal.path)) as db:
        receipt = json.loads(
            db.execute(
                "SELECT payload FROM public_wallet_trade_receipts "
                "WHERE wallet_key='wallet:17' ORDER BY seq LIMIT 1"
            ).fetchone()[0]
        )
    assert receipt["first_known_at"] == first[0]["first_known_at"]
    assert BUYER not in json.dumps(receipt)
    due = journal.observed_utc_net_delta(
        "wallet:17",
        BTC.key,
        bucket_start_at=known(0),
        as_of=known(301),
    )
    assert due["event_count"] == 2
    assert due["net_position_delta"] == "1"
    assert due["gross_observed_turnover"] == "3"
    assert not due["paper_admitted"]
    assert journal.persist_observed_utc_bucket(due)["status"].startswith("BLOCKED")
    assert journal.persist_observed_utc_bucket(due)["bucket_key"]
    roundtrip = normalized(3, 100, users=(SELLER, BUYER), sz="1")
    journal.append_public_wallet_trades(roundtrip)
    # Existing sealed bucket cannot be silently rewritten with new data.
    changed = journal.observed_utc_net_delta(
        "wallet:17",
        BTC.key,
        bucket_start_at=known(0),
        as_of=known(302),
    )
    assert changed["net_position_delta"] == "0"
    with pytest.raises(ValueError, match="CORRECTION"):
        journal.persist_observed_utc_bucket(changed)


def test_late_durability_refused_and_chain_tamper_detected(tmp_path, monkeypatch):
    journal = PaperJournal(tmp_path / "private")
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    row = normalized(5, 29)[0]
    journal.append_public_wallet_trades([row])
    first = journal.observed_utc_net_delta(
        "wallet:17",
        BTC.key,
        bucket_start_at=known(0),
        as_of=known(301),
    )
    assert first["net_position_delta"] == "2"
    monkeypatch.setattr(
        journal_module, "datetime", datetime
    )  # real commit is far after bucket close
    row2 = normalized(6, 33)[0]
    journal.append_public_wallet_trades([row2])
    second = journal.observed_utc_net_delta(
        "wallet:17",
        BTC.key,
        bucket_start_at=known(0),
        as_of="2026-11-06T12:00:00+00:00",
    )
    assert second["net_position_delta"] == "2"
    assert second["late_event_count"] == 1
    with closing(sqlite3.connect(journal.path)) as db, db:
        db.execute(
            "UPDATE public_wallet_trade_receipts SET payload=? "
            "WHERE wallet_key='wallet:17' AND seq=1",
            ('{"signed_qty":"999"}',),
        )
    with pytest.raises(ValueError, match="PUBLIC_WALLET_TRADE"):
        journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)


def test_utc_batch_policy_does_not_change_existing_rolling_contract():
    rolling = ForwardBatch(Decimal("1000"))
    assert rolling.ingest(admission(), first_known_at=known(263))["due_at"] == known(563)
    aligned = ForwardBatch(Decimal("1000"), timing_policy="UTC_BUCKET_CLOSE")
    assert aligned.ingest(admission(), first_known_at=known(263))["due_at"] == known(300)
    assert aligned.ingest(admission(), first_known_at=known(299))["due_at"] == known(300)
    with pytest.raises(ValueError, match="BUCKET_CLOSED"):
        aligned.ingest(admission(), first_known_at=known(300))
    delayed = ForwardBatch(Decimal("1000"), timing_policy="UTC_BUCKET_PLUS_5M")
    assert delayed.ingest(admission(), first_known_at=known(263))["due_at"] == known(600)
    with pytest.raises(ValueError, match="TIMING_POLICY"):
        ForwardBatch(Decimal("1000"), timing_policy="INSTANT")


def test_quote_after_deadline_only_and_no_paper_fill(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    earlier, later = quotes()
    journal.append_market_quote(earlier)
    journal.append_market_quote(later)
    found = journal.first_eligible_quote_after(
        BTC.key,
        due_at=at(4),
        checked_at=at(5),
    )
    assert found["status"] == "QUOTE_OBSERVED_SCENARIO_ONLY"
    assert found["quote_sha"] == digest(later)
    assert found["actual_observed_at"] == at(5)
    assert found["executed"] is False
    assert (
        journal.first_eligible_quote_after(
            BTC.key,
            due_at=at(6),
            checked_at=at(7),
        )["status"]
        == "BLOCKED_NO_POST_DEADLINE_QUOTE"
    )
    assert (
        journal.first_eligible_quote_after(
            BTC.key,
            due_at=at(6),
            checked_at=at(5),
        )["status"]
        == "WAIT"
    )


def test_best_level_fill_is_costed_but_not_a_financial_paper_execution():
    first, _ = quotes()
    priced = preview_top_level_paper_cost(
        first,
        signed_qty=Decimal("0.3"),
        fee_bps=Decimal("3"),
        adverse_bps=Decimal("2"),
    )
    assert priced["status"] == "SCENARIO_ONLY_PRICE_ESTIMATE"
    assert Decimal(priced["best_level"]) == Decimal(first["best_ask"])
    assert Decimal(priced["half_spread_cost"]) > 0
    assert Decimal(priced["taker_fee"]) > 0
    assert priced["paper_executed"] is False
    too_big = preview_top_level_paper_cost(
        first,
        signed_qty=Decimal(first["ask_size"]) + Decimal("1"),
        fee_bps=Decimal("3"),
    )
    assert too_big["status"] == "BLOCKED_UNPROVEN_DEPTH"
    with pytest.raises(ValueError, match="QUOTE_COST"):
        preview_top_level_paper_cost(first, signed_qty=Decimal("1"), fee_bps=Decimal("-1"))


def test_atomic_multi_wallet_conflict_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    journal = PaperJournal(tmp_path / "private")
    first = normalized(1, 40)
    bad = {**first[0], "signed_qty": "6"}
    with pytest.raises(ValueError, match="BATCH_CONFLICT"):
        journal.append_public_wallet_trades([first[0], bad])
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)["receipts"] == 0
    journal.append_public_wallet_trades(first)
    with pytest.raises(ValueError, match="CONFLICTING_REPLAY"):
        journal.append_public_wallet_trades([bad])
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)["receipts"] == 1


class FakeWS:
    def __init__(self, messages):
        self.messages = list(messages)
        self.subscriptions = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def send(self, raw):
        self.subscriptions.append(json.loads(raw))

    async def recv(self):
        return self.messages.pop(0)


def test_bounded_ws_baselines_first_batch_and_persists_provisional(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    frames = [
        json.dumps({"channel": "subscriptionResponse", "data": {}}),
        json.dumps({"channel": "trades", "data": [trade(1, 10), trade(4, 11)]}),
        json.dumps({"channel": "trades", "data": [trade(2, 20)]}),
    ]
    ws = FakeWS(frames)
    journal = PaperJournal(tmp_path / "private")
    report = asyncio.run(
        capture_bounded_native_trades(
            instruments=(BTC,),
            watched={BUYER: "wallet:17"},
            journal=journal,
            connect=lambda *_args, **_kwargs: ws,
            now=lambda: known(240),
            max_frames=3,
        )
    )
    assert ws.subscriptions == [
        {"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}},
    ]
    assert report["baseline_markets"] == 1
    assert report["new_wallet_receipts"] == 1
    assert report["paper_admitted"] is False
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)["receipts"] == 1
    assert (
        journal.observed_utc_net_delta(
            "wallet:17",
            BTC.key,
            bucket_start_at=known(0),
            as_of=known(301),
        )["gap_count"]
        >= 1
    )


def test_registry_only_sealed_resolves_and_exclusions_fail_closed(tmp_path):
    registry = tmp_path / "registry.sqlite3"
    conn = sqlite3.connect(registry)
    conn.executescript("""
        CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,venue TEXT,network TEXT,address TEXT);
        CREATE TABLE portfolio_versions(
            portfolio_id TEXT,version INTEGER,status TEXT,source_doc TEXT,
            sizing_contract TEXT,PRIMARY KEY(portfolio_id,version)
        );
        CREATE TABLE portfolio_memberships(
            portfolio_id TEXT,version INTEGER,member_alias TEXT,wallet_id INTEGER
        );
        CREATE TABLE portfolio_seals(
            portfolio_id TEXT,version INTEGER,definition_sha256 TEXT,
            doc_sha256 TEXT,source_revision TEXT,selection_known_at TEXT
        );
        CREATE TABLE exclusions(wallet_id INTEGER,reason TEXT);
    """)
    conn.execute("INSERT INTO wallets VALUES (1,'hyperliquid','mainnet',?)", (BUYER,))
    conn.execute(
        "INSERT INTO portfolio_versions VALUES ('test/E6',1,'FROZEN','src.md','whole_book')"
    )
    conn.execute("INSERT INTO portfolio_memberships VALUES ('test/E6',1,'W1',1)")
    params = {
        "schema": "wallet_portfolio_definition_v1",
        "portfolio_id": "test/E6",
        "aliases": ["W1"],
        "source_commit": "sha",
        "source_doc_sha256": "a" * 64,
        "selection_known_at": known(0),
        "status": "FROZEN",
        "sizing_contract": "whole_book",
        "source_identity_proven": False,
        "order_route": "NONE",
    }
    conn.execute(
        "INSERT INTO portfolio_seals VALUES (?,?,?,?,?,?)",
        ("test/E6", 1, digest(params), "a" * 64, "sha", known(0)),
    )
    conn.commit()
    conn.close()
    assert registry_watched_addresses(registry, ("test/E6",), as_of=known(301)) == {
        BUYER: "wallet:1"
    }
    with closing(sqlite3.connect(registry)) as db, db:
        db.execute("INSERT INTO exclusions VALUES (1,'BLOCKED')")
    with pytest.raises(ValueError, match="EXCLUDED"):
        registry_watched_addresses(registry, ("test/E6",), as_of=known(301))


def test_public_wallet_receipts_survive_verified_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    journal = PaperJournal(tmp_path / "private")
    journal.append_public_wallet_trades(normalized(1, 30))
    journal.append_public_trade_gap(
        instrument=BTC.key,
        stream_epoch=EPOCH,
        observed_at=known(33),
        reason="DISCONNECT",
    )
    original = journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)
    journal.backup(tmp_path / "backup")
    copied = PaperJournal(tmp_path / "backup").audit_public_wallet_trade_tape("wallet:17", BTC.key)
    assert original == copied
    assert original["source_complete"] is False
