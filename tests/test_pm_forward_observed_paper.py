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
                (
                    i,
                    {"S035": "S035-ENA", "S051": "S051-BTC", "S053": "S053-HYPE"}[alias],
                    "2026-11-01T00:00:00+00:00",
                ),
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
    journal: PaperJournal,
    seq: int,
    seconds: int,
    positions: dict,
    *,
    account_id: str | None = None,
    observation_kind: str = "OBSERVED_STATE_CHANGE",
    position_transition_eligible: bool = True,
    leader_marks: dict[str, str] | None = None,
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
    if leader_marks is not None:
        book["source_marks"] = leader_marks
        book["source_mark_evidence"] = {
            key: {
                "mark": mark,
                "event_at": book["source_event_at"],
                "first_known_at": book["first_known_at"],
                "native_frame_sha": book["provider_raw_sha"],
                "basis": "OFFICIAL_POSITION_VALUE_DIV_ABS_NATIVE_QUANTITY",
            }
            for key, mark in leader_marks.items()
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
        "observation_kind": observation_kind,
        "position_transition_eligible": position_transition_eligible,
        "signal_eligible": False,
        "stream_epoch": "fixture-official-position-epoch",
    }
    journal.append_source_receipt("S035", seq, f"s035-{seq}", receipt)


def test_future_native_price_policy_rejects_unlinked_selfhashed_leader_mark(tmp_path):
    source = PaperJournal(tmp_path / "source")
    add_quote(source, 10)
    add_source(source, 1, 12, {BTC.key: "20"}, leader_marks={BTC.key: "120"})
    paper = ObservedP1Paper(
        source_db=source.path,
        state_root=tmp_path / "paper",
        run_id="future_unlinked_native_mark",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
        source_mark_age_seconds=600,  # explicit synthetic age; no live calibration
    )
    assert paper.step(at(14))["quantity_count"] == 0
    add_quote(source, 313)
    blocked = paper.step(at(314))
    assert "PAPER_NATIVE_PRICE_SOURCE_PROOF_INVALID" in str(blocked["execution_results"])
    assert blocked["quantity_count"] == 0
    assert not any(row["event"]["kind"] == "PM04_PAPER_EXECUTE" for row in paper.run.ledger.read())


def test_effect_fsync_then_lost_ack_restarts_without_duplicate_model_pnl(tmp_path, monkeypatch):
    """The append committed; a lost local acknowledgment must not invent T0 again."""
    import pytest

    observed = PaperJournal(tmp_path / "source")
    add_quote(observed, 10)
    registry_db = registry(tmp_path / "registry.sqlite")
    catalog = {RAW_MARKET["symbol"]: RAW_MARKET}
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "paper",
        run_id="crash_after_local_effect",
        catalog=catalog,
        registry_db=registry_db,
        started_at=at(0),
    )
    paper.step(at(12))
    add_source(observed, 1, 12, {BTC.key: "20"}, leader_marks={BTC.key: "120"})
    paper.step(at(14))
    assert paper.run.account.pm04_state["paper_execution"]["active"]["S035"]
    add_quote(observed, 313)
    original_append = paper.run.ledger.append

    def committed_then_ack_lost(event, *, expected_head=None):
        original_append(event, expected_head=expected_head)
        if event.kind == "PM04_PAPER_EXECUTE":
            raise RuntimeError("SYNTHETIC_CRASH_AFTER_DURABLE_COMMIT")
        return paper.run.ledger.read()[-1]["sha"]

    with monkeypatch.context() as scope:
        scope.setattr(paper.run.ledger, "append", committed_then_ack_lost)
        with pytest.raises(RuntimeError, match="DURABLE_COMMIT"):
            paper.step(at(314))
    rows_before = paper.run.ledger.read()
    effects_before = [
        item["event"] for item in rows_before if item["event"]["kind"] == "PM04_PAPER_EXECUTE"
    ]
    assert len(effects_before) == 1
    assert effects_before[0]["payload"]["input"]["decision_source_chain_sha"]
    assert effects_before[0]["payload"]["input"]["decision_source_first_known_at"] == at(13)
    assert effects_before[0]["payload"]["input"]["decision_cutoff"] == at(314)
    restarted = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "paper",
        run_id="crash_after_local_effect",
        catalog=catalog,
        registry_db=registry_db,
    )
    modeled = restarted.run.account.snapshot()
    assert restarted.run.account.pm04_state["paper_execution"]["history"]
    restarted.step(at(314))
    assert restarted.run.account.snapshot()["quantities"] == modeled["quantities"]
    effects_after = [
        item["event"]
        for item in restarted.run.ledger.read()
        if item["event"]["kind"] == "PM04_PAPER_EXECUTE"
    ]
    assert len(effects_after) == 1
    assert effects_after[0]["event_id"] == effects_before[0]["event_id"]
    assert restarted.last_seen["S035"] == 1


def test_restart_after_original_grace_expires_without_catchup_opening(tmp_path):
    observed = PaperJournal(tmp_path / "source")
    add_quote(observed, 10)
    reg = registry(tmp_path / "registry.sqlite")
    catalog = {RAW_MARKET["symbol"]: RAW_MARKET}
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "paper",
        run_id="no_late_catchup",
        catalog=catalog,
        registry_db=reg,
        started_at=at(0),
    )
    add_source(observed, 1, 12, {BTC.key: "20"})
    recorded = paper.step(at(14))
    due = recorded["execution_intents"]["S035"]["due_at"]
    assert due == at(313)
    restarted = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "paper",
        run_id="no_late_catchup",
        catalog=catalog,
        registry_db=reg,
    )
    add_quote(observed, 400)
    expired = restarted.step(at(401))
    assert expired["quantity_count"] == 0
    assert (
        len(
            [
                row
                for row in restarted.run.ledger.read()
                if row["event"]["kind"] == "PM04_PAPER_EXPIRE"
            ]
        )
        == 1
    )
    assert not any(
        row["event"]["kind"] == "PM04_PAPER_EXECUTE" for row in restarted.run.ledger.read()
    )
    again = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "paper",
        run_id="no_late_catchup",
        catalog=catalog,
        registry_db=reg,
    )
    again.step(at(402))
    assert not any(row["event"]["kind"] == "PM04_PAPER_EXECUTE" for row in again.run.ledger.read())


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
    assert first["source_results"]["S035"] == "RECORDED_PAPER_SOURCE"
    assert first["quantity_count"] == 0
    assert first["order_route"] == "NONE"
    assert first["execution_intents"]["S035"]["due_at"] == at(313)

    add_quote(observed, 295)
    before = consumer.step(at(296))
    assert before["quantity_count"] == 0
    add_quote(observed, 313)
    filled = consumer.step(at(314))
    assert filled["tick"] == "PAPER_MARK_COMMITTED"
    assert filled["quantity_count"] == 1
    assert filled["costs"] != "0"
    assert D(filled["positions"][BTC.key]) > 0
    assert D(filled["equity"]) < D("10000")
    journal_rows = consumer.run.ledger.read()
    assert any(row["event"]["kind"] == "PM04_PAPER_EXECUTE" for row in journal_rows)

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
    assert closed["source_results"]["S035"] == "RECORDED_PAPER_SOURCE"
    assert closed["quantity_count"] == 0
    assert D(closed["realized_pnl"]) < 0
    assert D(closed["costs"]) > 0
    assert closed["real_broker_fills"] == 0
    assert closed["order_route"] == "NONE"
    assert closed["funding"] == "UNAVAILABLE_NOT_POSTED"
    assert restarted.run.restore()["account"] == restarted.run.account.snapshot()


def test_due_paper_with_offsetting_held_pod_without_mark_waits_instead_of_crashing(tmp_path):
    """PM03 marks every pod leg even when aggregate net quantity is flat."""
    observed = PaperJournal(tmp_path / "source")
    add_quote(observed, 10)
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "private",
        run_id="offsetting_pod_marks",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(observed, 1, 12, {BTC.key: "20"})
    first = paper.step(at(14))
    pending = first["execution_intents"]["S035"]
    assert pending["status"] == "PENDING_5M"

    # Both pods hold ETH but aggregate exposure nets to zero. There is no ETH
    # minute quote. PM03 still requires its valuation mark before any entry.
    eth = Instrument("hyperliquid", "mainnet:perp:default", "ETH")
    account = paper.run.account
    account.pm_quantities.setdefault("S035", {})[eth] = D("1")
    account.pm_quantities.setdefault("S051", {})[eth] = D("-1")
    assert not account.quantities.get(eth)
    assert eth.key not in account.pm04_state["pod_targets"].get("S035", {})
    assert eth.key not in account.pm04_state["routed_targets"].get("S051", {})

    add_quote(observed, 312)
    with closing(sqlite3.connect(observed.path)) as source_conn:
        result = paper._execute_pending(source_conn, at(313))
    assert result["S035"] == "WAIT_MARKET_OR_TARGET:PAPER_QUOTE_MISSING:" + eth.key
    assert not any(row["event"]["kind"] == "PM04_PAPER_EXECUTE" for row in paper.run.ledger.read())
    after = paper.run.account.pm04_state["paper_execution"]["history"][pending["intent_id"]]
    assert after["status"] == "PENDING_5M"
    assert after["due_at"] == pending["due_at"]
    assert after["first_known_at"] == pending["first_known_at"]
    assert after["frozen_k"] == pending["frozen_k"]


def test_future_started_run_never_backfills_old_source(tmp_path):
    observed = PaperJournal(tmp_path / "public")
    add_quote(observed, 10)
    add_source(observed, 1, 12, {BTC.key: "20"})
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "private",
        run_id="forward_only",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(13),
    )
    result = paper.step(at(14))
    assert result["source_results"]["S035"] == "PRE_START_UNMODELED"
    assert paper.run.account.quantities == {}


def test_post_start_baseline_is_never_a_new_risk_signal(tmp_path):
    source = PaperJournal(tmp_path / "observations")
    add_quote(source, 10)
    paper = ObservedP1Paper(
        source_db=source.path,
        state_root=tmp_path / "isolated",
        run_id="position_only",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(
        source,
        1,
        12,
        {BTC.key: "20"},
        observation_kind="BASELINE",
        position_transition_eligible=False,
    )
    blocked = paper.step(at(14))
    assert blocked["source_results"]["S035"] == "BLOCKED_SOURCE_NOT_PROSPECTIVE_POSITION_TRANSITION"
    assert blocked["quantity_count"] == 0
    assert blocked["execution_intents"] == {}
    # A later verified continuous position increase may initiate T+300.
    add_source(source, 2, 20, {BTC.key: "25"})
    accepted = paper.step(at(22))
    assert accepted["source_results"]["S035"] == "RECORDED_PAPER_SOURCE"
    assert accepted["execution_intents"]["S035"]["due_at"] == at(321)
    assert accepted["quantity_count"] == 0


def test_unverified_position_change_cannot_forge_t300(tmp_path):
    source = PaperJournal(tmp_path / "observations")
    add_quote(source, 10)
    paper = ObservedP1Paper(
        source_db=source.path,
        state_root=tmp_path / "isolated",
        run_id="not_prospective",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(
        source,
        1,
        12,
        {BTC.key: "20"},
        observation_kind="OBSERVED_STATE_CHANGE",
        position_transition_eligible=False,
    )
    result = paper.step(at(15))
    assert result["source_results"]["S035"] == "BLOCKED_SOURCE_NOT_PROSPECTIVE_POSITION_TRANSITION"
    assert not result["execution_intents"]
    assert paper.run.account.quantities == {}


def test_unpriceable_book_rejects_once_without_residual_chasing(tmp_path):
    observed = PaperJournal(tmp_path / "public")
    catalog = {RAW_MARKET["symbol"]: RAW_MARKET}
    add_quote(observed, 10, size=3)
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "private",
        run_id="unpriceable",
        catalog=catalog,
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(observed, 1, 12, {BTC.key: "20"})
    assert paper.step(at(14))["quantity_count"] == 0

    # The single displayed level cannot price the full market quantity.
    add_quote(observed, 313, size=0.3)
    first = paper.step(at(314))
    assert first["positions"] == {}
    intent = first["execution_intents"]["S035"]
    assert intent["status"] == "REJECTED"
    attempt = first["execution_outcomes"][intent["intent_id"]][BTC.key]
    assert attempt["status"] == "UNPRICEABLE_MARKET_ORDER"
    assert D(attempt["required_quantity"]) == D("0.564")

    add_quote(observed, 319, size=200)
    after = paper.step(at(321))
    assert after["positions"] == {}
    assert after["execution_intents"]["S035"]["status"] == "REJECTED"
    assert (
        len([r for r in paper.run.ledger.read() if r["event"]["kind"] == "PM04_PAPER_EXECUTE"]) == 1
    )
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
        observed,
        1,
        12,
        {BTC.key: "20"},
        account_id=sha256(b"unknown-unselected-account").hexdigest(),
    )
    result = paper.step(at(14))
    assert result["source_results"]["S035"] == "BLOCKED_SELECTED_ACCOUNT_IDENTITY_MISMATCH"
    assert result["positions"] == {}
    assert paper.run.account.quantities == {}
