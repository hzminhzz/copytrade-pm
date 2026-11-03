"""PIT journal adapter regressions: no wallet/clock/coverage fabrication."""

from datetime import UTC, datetime, timedelta
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.trader_intelligence import (
    ObservationSnapshot,
    TraderIntelligence,
    WalletEvent,
    WalletIdentity,
)
from copytrade_pm.trader_intelligence_intake import (
    from_opportunity_journal,
    historical_fill_events,
    native_instrument,
)

NOW = datetime(2026, 10, 13, 10, tzinfo=UTC)
MARKET = "hyperliquid/mainnet:perp:default/BTC"
SHA = sha256(b"wallet1").hexdigest()


def roster(count=1, clusters=True):
    return tuple(
        WalletIdentity(
            f"wallet{i}",
            sha256(f"wallet{i}".encode()).hexdigest(),
            cluster=f"cluster{i}" if clusters else None,
        )
        for i in range(1, count + 1)
    )


def journal(path: Path, *, source_time=None, known_time=None, status="ACTIVE"):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE opportunity_state(ledger_id TEXT,last_seq INTEGER)")
        db.execute("INSERT INTO opportunity_state VALUES ('ledger',1)")
        db.execute(
            "CREATE TABLE opportunity_decisions("
            "opportunity_id TEXT,first_source_id TEXT,first_ledger_seq INTEGER,"
            "first_event_at TEXT,first_known_at TEXT,instrument_id TEXT,"
            "wallet_id TEXT,status TEXT,blocker TEXT,payload_json TEXT)"
        )
        db.execute(
            "CREATE TABLE opportunity_updates("
            "opportunity_id TEXT,ledger_seq INTEGER,known_at TEXT,status TEXT)"
        )
        db.execute("CREATE TABLE source_coverage_barriers(ledger_seq INTEGER,known_at TEXT)")
        source_time = source_time or (NOW - timedelta(minutes=2)).isoformat()
        known_time = known_time or (NOW - timedelta(minutes=1)).isoformat()
        data = {
            "first_source_id": "s1",
            "source_quantity_before": "0",
            "source_quantity_after": "2",
        }
        db.execute(
            "INSERT INTO opportunity_decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "o1",
                "s1",
                1,
                source_time,
                known_time,
                "hyperliquid:mainnet:perp:default:BTC",
                "wallet1",
                status,
                None,
                json.dumps(data),
            ),
        )
        db.commit()


def read(path, *, at=NOW, wallets=None, rows=50):
    return from_opportunity_journal(
        journal_db=path,
        decision_at=at.isoformat(),
        roster_id="roster-v1",
        roster_known_at=(NOW - timedelta(hours=1)).isoformat(),
        wallets=wallets or roster(),
        maximum_source_rows=rows,
    )


def test_journal_intake_does_not_infer_book_or_source_equity(tmp_path):
    p = tmp_path / "journal.db"
    journal(p)
    snapshot = read(p, wallets=roster(94))
    assert len(snapshot.wallets) == 94
    assert len(snapshot.events) == 1
    observed = snapshot.events[0]
    assert observed.origin == "PROSPECTIVE_OBSERVED"
    assert observed.first_known_at is not None
    assert observed.book_complete is None
    assert observed.source_equity_usd is None
    assert observed.strategy_style == "UNKNOWN"
    assert observed.transition == "OPEN"
    grade = TraderIntelligence().evaluate(snapshot, NOW.isoformat())[0]
    assert grade.grade == "C"
    assert "INCOMPLETE_OR_UNKNOWN_SOURCE_BOOK" in grade.reasons


def test_future_first_known_is_excluded_and_does_not_backdate(tmp_path):
    p = tmp_path / "journal.db"
    journal(p, known_time=(NOW + timedelta(minutes=1)).isoformat())
    assert read(p).events == ()
    assert len(read(p, at=NOW + timedelta(minutes=3)).events) == 1


def test_lifecycle_is_asof_and_source_gap_cannot_count_as_entry(tmp_path):
    p = tmp_path / "journal.db"
    journal(p)
    before = read(p)
    with closing(sqlite3.connect(p)) as db, db:
        db.execute(
            "INSERT INTO opportunity_updates VALUES (?,?,?,?)",
            ("o1", 2, (NOW + timedelta(minutes=3)).isoformat(), "INVALIDATED"),
        )
        db.execute(
            "INSERT INTO source_coverage_barriers VALUES (?,?)",
            (1, (NOW + timedelta(minutes=5)).isoformat()),
        )
        db.commit()
    assert read(p).sha256 == before.sha256
    after = read(p, at=NOW + timedelta(minutes=8))
    assert after.events[0].verified_position_transition is False
    assert TraderIntelligence().evaluate(after, (NOW + timedelta(minutes=8)).isoformat()) == ()


def test_full_journal_coalesced_add_is_new_asof_event_not_backdated(tmp_path):
    p = tmp_path / "journal.db"
    journal(p)
    before = read(p)
    after_time = NOW + timedelta(minutes=3)
    with closing(sqlite3.connect(p)) as db, db:
        db.execute("DROP TABLE opportunity_updates")
        db.execute(
            "CREATE TABLE opportunity_updates("
            "source_id TEXT,opportunity_id TEXT,ledger_seq INTEGER,"
            "event_at TEXT,known_at TEXT,status TEXT,payload_json TEXT)"
        )
        db.execute(
            "INSERT INTO opportunity_updates VALUES (?,?,?,?,?,?,?)",
            (
                "s2",
                "o1",
                2,
                (NOW + timedelta(minutes=1)).isoformat(),
                after_time.isoformat(),
                "UPDATED",
                json.dumps({"before": "2", "after": "3"}),
            ),
        )
    assert read(p).sha256 == before.sha256
    later = read(p, at=after_time)
    assert len(later.events) == 2
    assert later.events[1].transition == "ADD"
    assert later.events[1].position_before == "2"
    assert later.events[1].position_after == "3"
    assert later.events[1].first_known_at == after_time.isoformat()
    assert later.events[1].source_equity_usd is None


def test_full_source_window_must_be_fetched(tmp_path):
    p = tmp_path / "journal.db"
    journal(p)
    with closing(sqlite3.connect(p)) as db, db:
        db.execute(
            "INSERT INTO opportunity_decisions SELECT "
            "'o2','s2',2,first_event_at,first_known_at,instrument_id,"
            "wallet_id,status,blocker,"
            "REPLACE(payload_json,'s1','s2') FROM opportunity_decisions LIMIT 1"
        )
        db.commit()
    with pytest.raises(ValueError, match="INCOMPLETE_JOURNAL_SOURCE_WINDOW"):
        read(p, rows=1)


def test_historical_vendor_fill_has_no_first_known_and_explicit_dex():
    events = historical_fill_events(
        wallet="wallet1",
        raw_fill_rows=(
            {
                "coin": "BTC",
                "side": "B",
                "sz": "2",
                "start_position": "0",
                "px": "100",
                "tid": 42,
                "time": 1790841600000,
            },
        ),
        instrument_map={"BTC": MARKET},
        source_page_sha256=SHA,
    )
    assert events[0].first_known_at is None
    assert events[0].origin == "HISTORICAL_PROXY"
    assert events[0].book_complete is None
    assert events[0].transition == "OPEN"
    with pytest.raises(ValueError, match="UNKNOWN_SOURCE_INSTRUMENT_MAP"):
        historical_fill_events(
            wallet="wallet1",
            raw_fill_rows=(
                {
                    "coin": "BTC",
                    "side": "B",
                    "sz": "2",
                    "start_position": "0",
                    "px": "100",
                    "tid": 42,
                    "time": 1790841600000,
                },
            ),
            instrument_map={},
            source_page_sha256=SHA,
        )


def test_hyperliquid_public_fill_schema_keeps_vendor_time_retrospective():
    rows = (
        {
            "coin": "BTC",
            "side": "B",
            "sz": "2",
            "startPosition": "0",
            "px": "100",
            "tid": 99,
            "time": 1790841600000,
        },
    )
    events = historical_fill_events(
        wallet="wallet1",
        raw_fill_rows=rows,
        instrument_map={"BTC": MARKET},
        source_page_sha256=SHA,
        source_schema="HYPERLIQUID_PUBLIC",
    )
    assert events[0].position_after == "2"
    assert events[0].first_known_at is None
    assert events[0].source_equity_usd is None
    with pytest.raises(ValueError, match="UNKNOWN_SOURCE_FILL_SCHEMA"):
        historical_fill_events(
            wallet="wallet1",
            raw_fill_rows=rows,
            instrument_map={"BTC": MARKET},
            source_page_sha256=SHA,
            source_schema="AUTO_GUESS",
        )


def test_future_events_do_not_modify_prior_assessment_hash():
    e1 = WalletEvent(
        event_id="one",
        wallet="wallet1",
        instrument=MARKET,
        event_at=(NOW - timedelta(minutes=2)).isoformat(),
        first_known_at=(NOW - timedelta(minutes=1)).isoformat(),
        origin="PROSPECTIVE_OBSERVED",
        position_before="0",
        position_after="1",
        book_complete=True,
        source_equity_usd="1000",
        strategy_style="DIRECTIONAL",
    )
    e2 = WalletEvent(
        event_id="two",
        wallet="wallet1",
        instrument=MARKET,
        event_at=(NOW + timedelta(minutes=1)).isoformat(),
        first_known_at=(NOW + timedelta(minutes=2)).isoformat(),
        origin="PROSPECTIVE_OBSERVED",
        position_before="1",
        position_after="2",
        book_complete=True,
        source_equity_usd="1000",
        strategy_style="DIRECTIONAL",
    )
    base = ObservationSnapshot(
        "roster",
        (NOW - timedelta(hours=1)).isoformat(),
        roster(),
        (e1,),
        "PROSPECTIVE_OBSERVED",
    )
    with_future = ObservationSnapshot(
        "roster",
        (NOW - timedelta(hours=1)).isoformat(),
        roster(),
        (e1, e2),
        "PROSPECTIVE_OBSERVED",
    )
    engine = TraderIntelligence()
    original = engine.evaluate(base, NOW.isoformat())[0]
    new = engine.evaluate(with_future, NOW.isoformat())[0]
    assert original.candidate_id == new.candidate_id
    assert original.input_sha256 == new.input_sha256
    assert original.as_wire() == new.as_wire()


def test_unknown_independence_must_remain_null():
    one = WalletEvent(
        event_id="unknown",
        wallet="wallet1",
        instrument=MARKET,
        event_at=(NOW - timedelta(minutes=2)).isoformat(),
        first_known_at=(NOW - timedelta(minutes=1)).isoformat(),
        origin="PROSPECTIVE_OBSERVED",
        position_before="0",
        position_after="1",
        book_complete=True,
        source_equity_usd="1000",
        strategy_style="DIRECTIONAL",
    )
    snap = ObservationSnapshot(
        "roster",
        (NOW - timedelta(hours=1)).isoformat(),
        roster(clusters=False),
        (one,),
        "PROSPECTIVE_OBSERVED",
    )
    a = TraderIntelligence().evaluate(snap, NOW.isoformat())[0]
    assert a.independent_clusters is None
    assert "INDEPENDENCE_UNVERIFIED" in a.reasons


def test_market_mapping_requires_explicit_namespace():
    assert native_instrument("hyperliquid:mainnet:perp:default:BTC") == MARKET
    with pytest.raises(ValueError):
        native_instrument("hyperliquid:mainnet:perp:BTC")
