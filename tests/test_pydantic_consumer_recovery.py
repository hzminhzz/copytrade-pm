"""Independent existing ledger owners survive lost ACKs; no shared finance."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import multiprocessing
import os

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm03_memory import Event
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_forward_source_fanout import fanout_one_portfolio_receipts
from test_pm_forward_admission import _alter
from test_pm_forward_fill import _decision
from test_pm_forward_journal import manifest
from test_pm_forward_observed_paper import BTC, RAW_MARKET, add_quote, add_source, at, registry


def _child(action):
    process = multiprocessing.get_context("fork").Process(target=action)
    process.start()
    process.join(15)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail("crash child timed out")
    assert process.exitcode == 42


@pytest.mark.parametrize("cut", ["before_commit", "after_commit"])
def test_sql_effect_and_cursor_crash_before_other_destination_import(tmp_path, cut):
    source = PaperJournal(tmp_path / "source")
    decision = _decision()
    decision["source_book"] = _alter(decision["source_book"], wallet_id="S035")
    book = decision["source_book"]
    receipt = {
        "schema": "paper_first_known_source_v1",
        "source_id": "S035",
        "source_event_at": book["source_event_at"],
        "first_known_at": book["first_known_at"],
        "captured_at": book["first_known_at"],
        "payload_sha": book["snapshot_sha"],
    }
    source.append_source_receipt("S035", 1, "original-source-event", receipt)
    source_before = source.source_status("S035")
    decision["source_ref"] = {"source_id": "S035", "sequence": 1, "receipt_sha": digest(receipt)}
    journals = {name: PaperJournal(tmp_path / name) for name in ("P1", "P14")}
    for name, journal in journals.items():
        row = manifest(name, name + "_account")
        journal.register(
            replace(row, rulebook=replace(row.rulebook, confirmed=True, permitted=(BTC,)))
        )
    a, b = journals.values()
    fanout_one_portfolio_receipts(source_db=source.path, portfolio_id="P1", account_journal=a)
    b_before = b.restore("P14")
    assert b.source_status("S035")["cursor"] == 0

    class CrashingJournal(PaperJournal):
        @contextmanager
        def _writer(self):
            with super()._writer() as db:

                class Connection:
                    def __getattr__(self, key):
                        return getattr(db, key)

                    def execute(self, sql, *args):
                        if sql == "COMMIT" and cut == "before_commit":
                            os._exit(42)
                        result = db.execute(sql, *args)
                        if sql == "COMMIT" and cut == "after_commit":
                            os._exit(42)
                        return result

                yield Connection()

    _child(lambda: CrashingJournal(a.root).consume_source_effect("P1", "effect-1", decision))
    a = PaperJournal(a.root)
    recovered = a.restore("P1")
    assert recovered["cursor"] == (1 if cut == "after_commit" else 0)
    assert recovered["source_cursors"] == ({"S035": 1} if cut == "after_commit" else {})
    assert b.restore("P14") == b_before
    assert b.source_status("S035")["cursor"] == 0
    committed = a.consume_source_effect("P1", "effect-1", decision)
    assert a.consume_source_effect("P1", "effect-1", decision) == committed
    assert committed["account"]["quantities"] == {BTC.key: "1"}
    assert Decimal(committed["account"]["costs"]) > 0
    if cut == "after_commit":
        assert committed == recovered
    conflicting = deepcopy(decision)
    conflicting["proposed"]["PM_A"][BTC.key] = "0.5"
    with pytest.raises(ValueError, match="CONFLICTING_PAPER_EVENT"):
        a.consume_source_effect("P1", "effect-1", conflicting)
    fanout_one_portfolio_receipts(source_db=source.path, portfolio_id="P14", account_journal=b)
    b_result = b.consume_source_effect("P14", "effect-1", conflicting)
    assert b_result["account"]["quantities"] == {BTC.key: "0.5"}
    assert b_result["source_cursors"] == {"S035": 1}
    assert a.restore("P1") == committed
    assert b.source_status("S035")["head_sha"] == source_before["head_sha"]
    assert source.source_status("S035") == source_before
    a.append("P1", "local-halt", {"kind": "HALT", "event_at": decision["hypothetical_fill_at"]})
    assert a.restore("P1")["account"]["risk"] == "HALT"
    assert b.restore("P14") == b_result


@pytest.mark.parametrize("event_kind", ["PM04_PAPER_SOURCE", "PM04_PAPER_EXECUTE"])
def test_v4_commit_before_ack_restores_cursor_intent_and_finance_once(tmp_path, event_kind):
    source = PaperJournal(tmp_path / "source")
    registry_path = registry(tmp_path / "registry.sqlite")
    add_quote(source, 10)

    def reopen(name, *, new=False):
        kwargs = {"started_at": at(0)} if new else {}
        return ObservedP1Paper(
            source_db=source.path,
            state_root=tmp_path / name,
            run_id=name,
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
            registry_db=registry_path,
            **kwargs,
        )

    a, b = reopen("a", new=True), reopen("b", new=True)
    add_source(source, 1, 12, {BTC.key: "20"})
    source_before = source.source_status("S035")
    if event_kind == "PM04_PAPER_EXECUTE":
        a.step(at(14))
        b.step(at(14))
        add_quote(source, 313)
    b_before = b.run.account.snapshot()

    def crash():
        original = a.run.ledger.append

        def append(event, **kwargs):
            result = original(event, **kwargs)
            if event.kind == event_kind:
                os._exit(42)
            return result

        a.run.ledger.append = append
        a.step(at(14) if event_kind == "PM04_PAPER_SOURCE" else at(314))

    _child(crash)
    a = reopen("a")
    assert a.last_seen["S035"] == 1
    assert b.run.account.snapshot() == b_before
    committed = next(
        row["event"] for row in a.run.ledger.read() if row["event"]["kind"] == event_kind
    )
    state_before_retry = a.run.account.snapshot()
    a.run.record(Event(**committed))
    assert a.run.account.snapshot() == state_before_retry
    conflicting = deepcopy(committed)
    conflicting["payload"]["source_seq"] = 999
    with pytest.raises(ValueError, match="CONFLICTING_EVENT_REVISION"):
        a.run.record(Event(**conflicting))
    if event_kind == "PM04_PAPER_SOURCE":
        assert a.run.account.quantities == {}
        assert b.last_seen["S035"] == 0
        a.step(at(14))
        b.step(at(14))
        add_quote(source, 313)
    a.step(at(314))
    b.step(at(314))
    for paper in (a, b):
        assert paper.last_seen["S035"] == 1
        assert paper.run.account.quantities[BTC] > 0
        assert paper.run.account.costs > 0
        events = [row["event"] for row in paper.run.ledger.read()]
        assert sum(e["kind"] == "PM04_PAPER_SOURCE" for e in events) == 1
        assert sum(e["kind"] == "PM04_PAPER_EXECUTE" for e in events) == 1
        once = paper.run.account.snapshot()
        paper.step(at(315))
        assert paper.run.account.cash == Decimal(once["cash"])
        assert paper.run.account.costs == Decimal(once["costs"])
        assert (
            reopen(paper.run.manifest["run_id"]).run.account.snapshot()
            == paper.run.account.snapshot()
        )
    a_id = next(
        r["event"]["event_id"]
        for r in a.run.ledger.read()
        if r["event"]["kind"] == "PM04_PAPER_EXECUTE"
    )
    b_id = next(
        r["event"]["event_id"]
        for r in b.run.ledger.read()
        if r["event"]["kind"] == "PM04_PAPER_EXECUTE"
    )
    assert a_id != b_id
    assert source.source_status("S035") == source_before


def test_v4_consumer_offline_past_admission_does_not_backdate_source(tmp_path):
    source = PaperJournal(tmp_path / "source")
    add_quote(source, 10)
    paper = ObservedP1Paper(
        source_db=source.path,
        state_root=tmp_path / "private",
        run_id="late",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(source, 1, 12, {BTC.key: "20"})
    add_quote(source, 313)
    result = paper.step(at(314))
    assert result["quantity_count"] == 0
    assert paper.run.account.costs == 0
    assert not any(row["event"]["kind"] == "PM04_PAPER_SOURCE" for row in paper.run.ledger.read())
