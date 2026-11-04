"""Atomic per-account source cursor and modeled effect regression (FP-02/06)."""

from contextlib import closing
from dataclasses import replace
import sqlite3

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from test_pm_forward_fill import BTC, _decision
from test_pm_forward_journal import T, manifest


def _prepared(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    campaign = PaperCampaign(journal=journal)
    for name in ("p1", "p14"):
        row = manifest(name, name + "_account")
        rules = replace(row.rulebook, confirmed=True, permitted=(BTC,))
        campaign.register(replace(row, rulebook=rules))
    decision = _decision()
    source = decision["source_book"]
    receipt = {
        "schema": "paper_first_known_source_v1",
        "source_id": source["wallet_id"],
        "source_event_at": T,
        "first_known_at": T,
        "captured_at": T,
        "payload_sha": source["snapshot_sha"],
    }
    journal.append_source_receipt(source["wallet_id"], 1, "receipt_1", receipt)
    decision["source_ref"] = {
        "source_id": source["wallet_id"],
        "sequence": 1,
        "receipt_sha": digest(receipt),
    }
    return journal, campaign, decision


def test_atomic_shared_source_receipt_two_account_effects_and_retry(tmp_path):
    journal, campaign, decision = _prepared(tmp_path)
    first = campaign.record_source_decision("p1", "d_1", decision)
    second = campaign.record_source_decision("p14", "d_1", decision)
    assert first["cursor"] == second["cursor"] == 1
    assert first["source_cursors"] == second["source_cursors"] == {"fixture_wallet": 1}
    assert first["account"]["quantities"][BTC.key] == "1"
    assert journal.restore("p14")["account"] == second["account"]
    assert campaign.record_source_decision("p1", "d_1", decision) == first
    with pytest.raises(ValueError, match="SOURCE_ALREADY_CONSUMED|CONFLICTING_PAPER_EVENT"):
        campaign.record_source_decision("p1", "other_decision", decision)
    assert journal.restore("p1")["cursor"] == 1
    assert journal.restore("p14")["cursor"] == 1


def test_source_gap_and_spoofed_receipt_do_not_advance_account(tmp_path):
    journal, campaign, decision = _prepared(tmp_path)
    event = dict(decision)
    event["source_ref"] = {**decision["source_ref"], "sequence": 2}
    with pytest.raises(ValueError, match="SOURCE_RECEIPT_NOT_PRESENT|SOURCE_RUN_SEQUENCE_GAP"):
        campaign.record_source_decision("p1", "out_of_order", event)
    assert journal.restore("p1")["cursor"] == 0
    forged = dict(decision)
    forged["source_ref"] = {**decision["source_ref"], "receipt_sha": "a" * 64}
    with pytest.raises(ValueError, match="SOURCE_RECEIPT_SHA_MISMATCH"):
        campaign.record_source_decision("p1", "forged", forged)
    assert journal.restore("p1")["account"]["quantities"] == {}


def test_transaction_abort_never_skips_cursor_or_financial_effect(tmp_path):
    journal, campaign, decision = _prepared(tmp_path)
    with closing(sqlite3.connect(journal.path)) as db:
        with db:
            db.execute(
                "CREATE TRIGGER stop_before_cursor BEFORE INSERT ON account_source_cursors "
                "BEGIN SELECT RAISE(ABORT, 'injected transaction failure'); END"
            )
    with pytest.raises(sqlite3.IntegrityError, match="injected transaction failure"):
        campaign.record_source_decision("p1", "d_1", decision)
    state = journal.restore("p1")
    assert state["cursor"] == 0
    assert state["source_cursors"] == {}
    assert state["account"]["quantities"] == {}
    with closing(sqlite3.connect(journal.path)) as db:
        with db:
            db.execute("DROP TRIGGER stop_before_cursor")
    recovered = campaign.record_source_decision("p1", "d_1", decision)
    assert recovered["source_cursors"] == {"fixture_wallet": 1}
    assert recovered["cursor"] == 1


def test_tampered_consumption_is_detected_on_replay(tmp_path):
    journal, campaign, decision = _prepared(tmp_path)
    campaign.record_source_decision("p1", "d_1", decision)
    with closing(sqlite3.connect(journal.path)) as db:
        with db:
            db.execute("UPDATE account_source_cursors SET seq=9 WHERE run_id='p1'")
    with pytest.raises(ValueError, match="SOURCE_CURSOR_REPLAY_DIVERGENCE"):
        journal.restore("p1")


def test_direct_append_cannot_bypass_atomic_source_consumption(tmp_path):
    journal, _, decision = _prepared(tmp_path)
    with pytest.raises(ValueError, match="SOURCE_REF_REQUIRES_ATOMIC_CONSUME"):
        journal.append("p1", "bypass", decision)
    assert journal.restore("p1")["cursor"] == 0
