"""End-to-end offline harness for observed first-known P1 -> PM04 -> PM03."""

from contextlib import closing
from datetime import datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
import sqlite3

from copytrade_pm.pm03_account import Instrument, digest
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from test_pm_forward_ccxt_market import ccxt_market

T = datetime.fromisoformat("2026-11-07T08:00:00+00:00")
BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
RAW_MARKET = ccxt_market()
ADDRESSES = {
    "S035": "0x" + "ab" * 20,
    "S051": "0x" + "cd" * 20,
    "S053": "0x" + "ef" * 20,
}


def registry(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,address TEXT NOT NULL)")
        db.execute("CREATE TABLE wallet_aliases(wallet_id INTEGER,alias TEXT,known_at TEXT)")
        for i, (alias, address) in enumerate(ADDRESSES.items(), 1):
            db.execute("INSERT INTO wallets VALUES (?,?)", (i, address))
            db.execute(
                "INSERT INTO wallet_aliases VALUES (?,?,?)",
                (i, {"S035": "S035-ENA", "S051": "S051-BTC", "S053": "S053-HYPE"}[alias],
                 "2026-11-01T00:00:00+00:00"),
            )
    return path


def at(seconds: int) -> str:
    return (T + timedelta(seconds=seconds)).isoformat()


def add_quote(journal: PaperJournal, at_seconds: int, *, size: int = 200) -> None:
    native = parse_ccxt_market(RAW_MARKET, first_known_at=at(1), expected=BTC)
    quote = parse_ccxt_book(
        native,
        {
            "symbol": RAW_MARKET["symbol"],
            "timestamp": int((T + timedelta(seconds=at_seconds)).timestamp() * 1000),
            "bids": [[100, size]],
            "asks": [[101, size]],
        },
        first_known_at=at(at_seconds + 1),
        max_age_seconds=20,
    )
    journal.append_market_quote(quote.payload())


def add_source(
    journal: PaperJournal, seq: int, seconds: int, positions: dict,
    *, account_id: str | None = None,
) -> None:
    book = {
        "schema": "paper_source_book_v1",
        "wallet_id": "S035",
        "account_id": account_id or sha256(ADDRESSES["S035"].encode()).hexdigest(),
        "snapshot_kind": "OFFICIAL_WS_PER_ACCOUNT_ALL_DEX_ONLY",
        "synthetic_fixture": False,
        "dex_census": ["mainnet:perp:default"],
        "observed_dexes": ["mainnet:perp:default"],
        "positions": positions,
        "source_event_at": at(seconds),
        "first_known_at": at(seconds + 1),
        "provider_raw_sha": digest(["source-frame", seq]),
        "source_equity": None,
    }
    book["snapshot_sha"] = digest(book)
    receipt = {
        "schema": "paper_first_known_source_v1",
        "source_id": "S035",
        "source_event_at": book["source_event_at"],
        "first_known_at": book["first_known_at"],
        "captured_at": at(seconds + 1),
        "payload_sha": book["snapshot_sha"],
        "source_book": book,
        "status": "BLOCKED_INCOMPLETE_WHOLE_WALLET",
    }
    journal.append_source_receipt("S035", seq, f"s035-{seq}", receipt)


def test_observed_forward_paper_entry_wait_300_close_and_restart(tmp_path):
    observed = PaperJournal(tmp_path / "public")
    catalog = {RAW_MARKET["symbol"]: RAW_MARKET}
    add_quote(observed, 10)
    consumer = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "isolated-private",
        run_id="p1_observed",
        catalog=catalog,
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    assert consumer.step(at(12))["quantity_count"] == 0

    add_source(observed, 1, 12, {BTC.key: "20"})
    first = consumer.step(at(14))
    assert first["source_results"]["S035"] == "RECORDED_PM04_SIGNAL"
    assert first["quantity_count"] == 0
    assert first["order_route"] == "NONE"
    assert consumer.run.account.pm04_state["batch_open"][BTC.key] == at(14)

    add_quote(observed, 295)
    before = consumer.step(at(296))
    assert before["quantity_count"] == 0
    add_quote(observed, 313)
    filled = consumer.step(at(314))
    assert filled["tick"] == "PAPER_TICK_COMMITTED"
    assert filled["quantity_count"] == 1
    assert filled["costs"] != "0"
    assert D(filled["positions"][BTC.key]) > 0
    assert D(filled["equity"]) < D("10000")
    journal_rows = consumer.run.ledger.read()
    assert any(row["event"]["kind"] == "PM04_TICK" for row in journal_rows)

    restarted = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "isolated-private",
        run_id="p1_observed",
        catalog=catalog,
        registry_db=tmp_path / "registry.sqlite",
    )
    assert restarted.run.account.snapshot() == consumer.run.account.snapshot()
    assert restarted.last_seen["S035"] == 1

    add_quote(observed, 319)
    add_source(observed, 2, 319, {})
    closed = restarted.step(at(322))
    assert closed["source_results"]["S035"] == "RECORDED_PM04_SIGNAL"
    assert closed["quantity_count"] == 0
    assert D(closed["realized_pnl"]) < 0
    assert D(closed["costs"]) > 0
    assert closed["real_broker_fills"] == 0
    assert closed["order_route"] == "NONE"
    assert closed["funding"] == "UNAVAILABLE_NOT_POSTED"
    assert restarted.run.restore()["account"] == restarted.run.account.snapshot()


def test_future_started_run_never_backfills_old_source(tmp_path):
    observed = PaperJournal(tmp_path / "public")
    add_quote(observed, 10)
    add_source(observed, 1, 12, {BTC.key: "20"})
    paper = ObservedP1Paper(
        source_db=observed.path, state_root=tmp_path / "private",
        run_id="forward_only", catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(13),
    )
    result = paper.step(at(14))
    assert result["source_results"]["S035"] == "PRE_START_UNMODELED"
    assert paper.run.account.quantities == {}


def test_partial_l2_paper_order_retries_remaining_on_next_fresh_tick(tmp_path):
    observed = PaperJournal(tmp_path / "public")
    catalog = {RAW_MARKET["symbol"]: RAW_MARKET}
    add_quote(observed, 10, size=3)
    paper = ObservedP1Paper(
        source_db=observed.path, state_root=tmp_path / "private",
        run_id="retry_partial", catalog=catalog,
        registry_db=registry(tmp_path / "registry.sqlite"), started_at=at(0),
    )
    add_source(observed, 1, 12, {BTC.key: "20"})
    assert paper.step(at(14))["quantity_count"] == 0

    add_quote(observed, 313, size=3)
    first = paper.step(at(314))
    first_qty = D(first["positions"][BTC.key])
    assert D("0") < first_qty <= D("0.3")
    assert paper.run.account.pm04_state["routed_targets"]["S035"][BTC.key] != str(first_qty)

    # Two polls must not spend the exact same displayed best-level depth twice.
    duplicate_book = paper.step(at(316))
    assert D(duplicate_book["positions"][BTC.key]) == first_qty
    assert paper.run.account.pm04_state["modeled_l2_consumed"][BTC.key]

    add_quote(observed, 319, size=3)
    next_fill = paper.step(at(321))
    final_qty = D(next_fill["positions"][BTC.key])
    assert final_qty > first_qty
    assert final_qty == D(paper.run.account.pm04_state["routed_targets"]["S035"][BTC.key])
    assert paper.run.restore()["account"] == paper.run.account.snapshot()


def test_registry_mismatched_selected_account_never_opens_a_paper_position(tmp_path):
    observed = PaperJournal(tmp_path / "public")
    add_quote(observed, 10)
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "private",
        run_id="identity_rejection",
        registry_db=registry(tmp_path / "registry.sqlite"),
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        started_at=at(0),
    )
    add_source(
        observed, 1, 12, {BTC.key: "20"},
        account_id=sha256(b"unknown-unselected-account").hexdigest(),
    )
    result = paper.step(at(14))
    assert result["source_results"]["S035"] == "BLOCKED_SELECTED_ACCOUNT_IDENTITY_MISMATCH"
    assert result["positions"] == {}
    assert paper.run.account.quantities == {}
