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
    capture_sharded_native_trades,
    load_public_market_allowlist,
    native_coin,
    normalize_native_trade,
    plan_latest_public_utc_bucket,
    plan_sharded_utc_buckets,
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


def test_shard_fanout_preserves_all_markets_and_reports_each_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    instruments = tuple(
        Instrument("hyperliquid", "mainnet:perp:default", f"C{i}") for i in range(11)
    )

    class MultiMarketFakeWS:
        def __init__(self):
            self.coins = []
            self.frames = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def send(self, raw):
            self.coins.append(json.loads(raw)["subscription"]["coin"])

        async def recv(self):
            if self.frames is None:
                self.frames = [
                    json.dumps({"channel": "trades", "data": [{**trade(1, 10), "coin": c}]})
                    for c in self.coins
                ] + [
                    json.dumps({"channel": "trades", "data": [{**trade(2, 20), "coin": c}]})
                    for c in self.coins
                ]
            if self.frames:
                return self.frames.pop(0)
            await asyncio.sleep(1)

    journal = PaperJournal(tmp_path / "private")
    result = asyncio.run(
        capture_sharded_native_trades(
            instruments=instruments,
            watched={BUYER: "wallet:17"},
            journal=journal,
            duration_seconds=0.5,
            max_frames=30,
            max_parallel_shards=2,
            connect=lambda *_args, **_kwargs: MultiMarketFakeWS(),
            now=lambda: known(240),
        )
    )
    assert result["status"] == "PROVISIONAL_OBSERVATION_ONLY"
    assert result["market_count"] == 11
    assert result["shard_count"] == 2
    assert result["baseline_markets"] == 11
    assert result["new_wallet_receipts"] == 11
    assert result["all_markets_baselined"] is True
    assert result["coverage_complete"] is False
    assert result["paper_admitted"] is False
    assert result["financial_events_committed"] == 0
    assert len(result["market_stats"]) == 11
    plan = plan_sharded_utc_buckets(
        instruments=instruments,
        wallet_keys=("wallet:17",),
        journal=journal,
        as_of=known(301),
    )
    assert plan["market_count"] == 11
    assert plan["shard_count"] == 2
    assert plan["result_count"] == 11
    assert plan["financial_events_committed"] == 0
    for instrument in instruments:
        assert result["market_stats"][instrument.key]["active_messages"] == 1
        assert journal.audit_public_wallet_trade_tape("wallet:17", instrument.key)["receipts"] == 1


def test_inactive_market_is_not_mislabeled_as_covered(tmp_path):
    eth = Instrument("hyperliquid", "mainnet:perp:default", "ETH")
    ws = FakeWS([json.dumps({"channel": "trades", "data": [trade(1, 10)]})])
    journal = PaperJournal(tmp_path / "private")
    result = asyncio.run(
        capture_bounded_native_trades(
            instruments=(BTC, eth),
            watched={BUYER: "wallet:17"},
            journal=journal,
            duration_seconds=0.5,
            max_frames=1,
            connect=lambda *_args, **_kwargs: ws,
            now=lambda: known(240),
        )
    )
    assert result["baseline_markets"] == 1
    assert result["all_markets_baselined"] is False
    assert result["market_stats"][BTC.key]["status"] == "BASELINE_ONLY"
    assert result["market_stats"][eth.key]["status"] == "NO_MARKET_FRAMES"
    assert result["coverage_complete"] is False
    assert result["paper_admitted"] is False


def test_market_allowlist_sha_and_bounded_shards(tmp_path):
    market = tmp_path / "markets.json"
    data = {
        "schema": "paper_public_market_allowlist_v1",
        "instruments": [BTC.key, "hyperliquid/mainnet:perp:default/ETH"],
    }
    market.write_text(json.dumps(data))
    assert [x.key for x in load_public_market_allowlist(market)] == data["instruments"]
    market.write_text(json.dumps({**data, "instruments": data["instruments"] * 2}))
    with pytest.raises(ValueError, match="DUPLICATE"):
        load_public_market_allowlist(market)
    market.write_text(json.dumps({**data, "instruments": ["hyperliquid/mainnet:perp:default/@1"]}))
    with pytest.raises(ValueError, match="INVALID_NATIVE_COIN"):
        load_public_market_allowlist(market)
    market.write_text(
        json.dumps(
            {
                **data,
                "instruments": [f"hyperliquid/mainnet:perp:default/T{i}" for i in range(129)],
            }
        )
    )
    with pytest.raises(ValueError, match="LIMIT"):
        load_public_market_allowlist(market)


def test_exact_user_top40_layout_and_current_catalog_guard(tmp_path):
    from hashlib import sha256
    from pathlib import Path

    from copytrade_pm.pm_forward_public_trades import (
        load_public_market_shards,
        validate_public_market_catalog,
    )

    path = (
        Path(__file__).resolve().parents[1] / "docs/FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json"
    )
    layout = load_public_market_shards(path)
    names = [
        "core_crypto_majors",
        "liquid_altcoins",
        "commodities_indices",
        "defi_l1_infrastructure",
        "precious_metals_alts",
    ]
    assert [name for name, _ in layout] == names
    assert [len(group) for _, group in layout] == [8] * 5
    coins = [[native_coin(inst) for inst in group] for _, group in layout]
    assert coins == [
        ["HYPE", "NEAR", "ZEC", "BTC", "ETH", "XMR", "SOL", "ENA"],
        ["LIT", "PONS", "TRX", "UNI", "JUP", "CASHCAT", "VVV", "ZRO"],
        ["xyz:CL", "xyz:BRENTOIL", "xyz:XYZ100", "PUMP", "CRV", "ONDO", "xyz:SP500", "BNB"],
        ["MORPHO", "LINK", "SUI", "kPEPE", "USELESS", "XRP", "MET", "STRK"],
        ["AAVE", "xyz:GOLD", "ARB", "DASH", "XPL", "PAXG", "INJ", "xyz:SILVER"],
    ]
    selected = tuple(inst for _, group in layout for inst in group)
    assert len(set(inst.key for inst in selected)) == 40

    def fake_catalog(req):
        dex = req.get("dex", "default")
        universe = [
            {"name": native_coin(inst)} for inst in selected if inst.market.endswith(":" + dex)
        ]
        payload = {"universe": universe}
        raw = json.dumps(payload).encode()
        return payload, raw, sha256(raw).hexdigest()

    accepted = validate_public_market_catalog(selected, info=fake_catalog)
    assert accepted["markets_verified"] == 40
    assert accepted["status"] == "ALL_MARKETS_PRESENT_AT_PREFLIGHT"

    def missing_catalog(req):
        payload, _, _ = fake_catalog(req)
        if req.get("dex") == "xyz":
            payload["universe"] = [row for row in payload["universe"] if row["name"] != "xyz:SP500"]
        raw = json.dumps(payload).encode()
        return payload, raw, sha256(raw).hexdigest()

    with pytest.raises(ValueError, match="MARKET_UNAVAILABLE:xyz:SP500"):
        validate_public_market_catalog(selected, info=missing_catalog)

    data = json.loads(path.read_text())
    duplicate = tmp_path / "duplicates.json"
    data["shards"][4]["instruments"][0] = data["shards"][0]["instruments"][0]
    duplicate.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="DUPLICATE_MARKET"):
        load_public_market_shards(duplicate)
    data = json.loads(path.read_text())
    data["shards"][1]["instruments"].pop()
    duplicate.write_text(json.dumps(data))
    group_short = load_public_market_shards(duplicate)
    assert len(group_short[1][1]) == 7
    # A malformed 9-market shard must not be repartitioned silently.
    data["shards"][1]["instruments"].extend(
        [data["shards"][0]["instruments"][0], data["shards"][0]["instruments"][1]]
    )
    duplicate.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="SHARD_SIZE"):
        load_public_market_shards(duplicate)


def test_five_shard_wallet_buy_sell_captured_for_all_40_and_no_paper_execution(
    tmp_path, monkeypatch
):
    """Deterministic end-to-end positive trade-match test, NOT live follower PnL."""
    from pathlib import Path

    from copytrade_pm.pm_forward_public_trades import load_public_market_shards

    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    layout = load_public_market_shards(
        Path(__file__).resolve().parents[1] / "docs/FORWARD-PAPER-MARKET-TOP40-SHARDS-20261105.json"
    )
    selected = tuple(inst for _, shard in layout for inst in shard)

    class AllCoinsWS:
        def __init__(self):
            self.coins = []
            self.messages = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def send(self, raw):
            self.coins.append(json.loads(raw)["subscription"]["coin"])

        async def recv(self):
            if self.messages is None:
                # One uncertain baseline followed by one first-known trade per coin.
                self.messages = [
                    json.dumps(
                        {
                            "channel": "trades",
                            "data": [{**trade(1, 10), "coin": c} for c in self.coins],
                        }
                    ),
                    json.dumps(
                        {
                            "channel": "trades",
                            "data": [{**trade(2, 20), "coin": c} for c in self.coins],
                        }
                    ),
                ]
            return self.messages.pop(0)

    journal = PaperJournal(tmp_path / "private")
    result = asyncio.run(
        capture_sharded_native_trades(
            instruments=selected,
            configured_shards=layout,
            watched={BUYER: "wallet:17", SELLER: "wallet:18"},
            journal=journal,
            duration_seconds=5,
            max_frames=2,
            max_parallel_shards=5,
            connect=lambda *_args, **_kwargs: AllCoinsWS(),
            now=lambda: known(240),
        )
    )
    assert result["market_count"] == 40
    assert result["shard_count"] == 5
    assert [s["shard_name"] for s in result["shard_reports"]] == [name for name, _ in layout]
    assert [len(s["instruments"]) for s in result["shard_reports"]] == [8] * 5
    assert result["all_markets_baselined"] is True
    assert result["new_wallet_receipts"] == 80
    assert result["matched_wallet_sides"] == 80
    expected_layout_sha = digest([[name, [inst.key for inst in shard]] for name, shard in layout])
    assert result["shard_layout_sha"] == expected_layout_sha
    assert result["financial_events_committed"] == 0
    assert result["paper_admitted"] is False
    for inst in selected:
        assert journal.audit_public_wallet_trade_tape("wallet:17", inst.key)["receipts"] == 1
        assert journal.audit_public_wallet_trade_tape("wallet:18", inst.key)["receipts"] == 1
        assert result["market_stats"][inst.key]["status"] == "ACTIVE_AFTER_BASELINE"
    plan = plan_sharded_utc_buckets(
        instruments=selected,
        configured_shards=layout,
        wallet_keys=("wallet:17", "wallet:18"),
        journal=journal,
        as_of=known(301),
    )
    assert plan["shard_names"] == [name for name, _ in layout]
    assert plan["shard_layout_sha"] == expected_layout_sha
    assert plan["result_count"] == 80
    assert plan["financial_events_committed"] == 0
    assert all(b["bucket_status"].startswith("BLOCKED") for b in plan["buckets"])
    net = {b["wallet_key"]: set() for b in plan["buckets"]}
    for b in plan["buckets"]:
        net[b["wallet_key"]].add(b["observed_net_delta"])
    assert net == {"wallet:17": {"2"}, "wallet:18": {"-2"}}
    with closing(sqlite3.connect(journal.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


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
