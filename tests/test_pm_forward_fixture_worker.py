"""End-to-end test-only paper fixture worker and no-trade missing-book gate."""

from dataclasses import replace
from decimal import Decimal

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_fixture_worker import FixturePaperWorker
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_portfolios import P1, P14
from test_pm_forward_admission import _alter
from test_pm_forward_fill import BTC, _source_book
from test_pm_forward_journal import manifest
from test_pm_forward_pm04 import at, engine, market_contract, policy


def create_worker(tmp_path, portfolio=P1, *, journal=None):
    journal = journal or PaperJournal(tmp_path / "paper")
    frozen_policy = policy(portfolio.members, "3000" if portfolio.name == "P1" else "1600")
    m = manifest(portfolio.name, f"{portfolio.name}_virtual")
    sealed = replace(
        m,
        portfolio_sha=portfolio.sha,
        policy_sha=digest(frozen_policy),
        rulebook=replace(m.rulebook, confirmed=True, permitted=(BTC,)),
    )
    return journal, FixturePaperWorker(journal, portfolio, sealed, frozen_policy)


def whole_book(alias, *, qty="0"):
    return _alter(
        _source_book(),
        wallet_id=alias,
        account_id=f"fixture_{alias}",
        source_event_at=at(60),
        first_known_at=at(60),
        positions={BTC.key: qty} if Decimal(qty) else {},
        source_equity="20000",
    )


def drive(worker, second):
    inputs = engine(second)
    return worker.drive(
        decision_at=at(second),
        hypothetical_fill_at=at(second + 2),
        observations=inputs["observations"],
        shocks=inputs["shocks"],
        evidence=inputs["evidence"],
        costs=inputs["costs"],
        market_contracts={BTC.key: market_contract(second, inputs["costs"])},
    )


def test_missing_book_blocks_every_position_then_replays_from_wal(tmp_path) -> None:
    journal, worker = create_worker(tmp_path)
    first = worker.record_source_book(
        "S035", 1, "s035-1", whole_book("S035", qty="2"), captured_at=at(60)
    )
    assert first["cursor"] == 1
    not_ready = drive(worker, 60)
    assert not_ready["status"] == "BLOCKED"
    assert set(not_ready["missing_wallets"]) == {"S051", "S053"}
    assert journal.restore("P1")["account"]["quantities"] == {}
    assert journal.restore("P1")["cursor"] == 1
    for alias in ("S051", "S053"):
        worker.record_source_book(alias, 1, f"{alias}-1", whole_book(alias), captured_at=at(60))
    before_due = drive(worker, 60)
    assert before_due["status"] == "SYNTHETIC_EVENT_COMMITTED"
    assert before_due["state"]["account"]["quantities"] == {}
    assert before_due["state"]["source_cursors"] == {"S035": 1, "S051": 1, "S053": 1}
    journal_after = journal.restore("P1")
    assert journal_after["account"]["pm04"]["batch_open"][BTC.key] == at(60)
    # New process reconstructs available books from persisted source receipts,
    # never from volatile memory or guessed zero-position state.
    _, restarted = create_worker(tmp_path, journal=PaperJournal(journal.root))
    due = drive(restarted, 360)
    assert Decimal(due["state"]["account"]["quantities"][BTC.key]) == Decimal("0.3")
    assert due["state"]["source_cursors"] == {"S035": 1, "S051": 1, "S053": 1}
    replay = PaperJournal(journal.root).restore("P1")
    assert replay["account"] == due["state"]["account"]


def test_shared_p1_p14_source_does_not_override_p14_missing_leg(tmp_path) -> None:
    journal, p1 = create_worker(tmp_path)
    _, p14 = create_worker(tmp_path, P14, journal=journal)
    for alias in ("S035", "S051", "S053"):
        book = whole_book(alias, qty="2" if alias == "S035" else "0")
        p1.record_source_book(alias, 1, f"r-{alias}", book, captured_at=at(60))
    assert drive(p1, 60)["status"] == "SYNTHETIC_EVENT_COMMITTED"
    assert drive(p14, 60)["status"] == "BLOCKED"
    assert journal.restore("P14")["source_cursors"] == {}
    assert journal.restore("P14")["account"]["quantities"] == {}
    # Once the two additional synthetic whole books are provided, both
    # portfolios trade on the same source but have independent PM-03 books.
    for alias in ("S064", "Whale_0x5f94"):
        p14.record_source_book(alias, 1, f"r-{alias}", whole_book(alias), captured_at=at(60))
    assert drive(p14, 60)["status"] == "SYNTHETIC_EVENT_COMMITTED"
    p1_due = drive(p1, 360)
    p14_due = drive(p14, 360)
    assert Decimal(p1_due["state"]["account"]["quantities"][BTC.key]) == Decimal("0.3")
    assert Decimal(p14_due["state"]["account"]["quantities"][BTC.key]) == Decimal("0.16")
    assert p1_due["state"]["account"]["cash"] != p14_due["state"]["account"]["cash"]
    assert p1_due["state"]["source_cursors"] == {
        "S035": 1,
        "S051": 1,
        "S053": 1,
    }
    assert p14_due["state"]["source_cursors"] == {
        "S035": 1,
        "S051": 1,
        "S053": 1,
        "S064": 1,
        "Whale_0x5f94": 1,
    }
    assert journal.source_status("S035")["cursor"] == 1
