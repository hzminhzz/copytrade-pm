"""FP shared canonical source -> physically isolated P1/P14 financial WALs.

Copies are receipt evidence only. The canonical public observer is never
mutated and does not create duplicate wallet subscriptions. A synthetic
PM04 signal requires a separate, explicitly fixture-only acceptance path.
"""

from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import sqlite3

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_fixture_worker import FixturePaperWorker
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_portfolios import P1, P14
from copytrade_pm.pm_forward_source_fanout import (
    fanout_frozen_source_receipts,
    fanout_one_portfolio_receipts,
)
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import sample_state
from test_pm_forward_journal import manifest
from test_pm_forward_pm04 import BTC, at, paper_signal, paper_tick, policy
from test_pm_forward_fill import _source_book
from test_pm_forward_admission import _alter

T = datetime.fromtimestamp(1793294400, UTC)


def test_continuous_parent_and_child_receipts_keep_exact_isolated_fanout(tmp_path):
    from copytrade_pm.pm_forward_source_stream import PersistentAccount

    source = source_five(tmp_path)
    # The same frozen parent alias owns distinct native account hashes.
    for n, address in enumerate(("0x" + f"{1:040x}", "0x" + f"{9:040x}"), 1):
        feed = PersistentAccount(
            journal=source,
            alias="S035" if n == 1 else "S035_sub_test",
            address=address,
            parent_alias="S035",
            dex_catalog=[None, {"name": "xyz"}],
            subaccounts=None,
            scope_sha="a" * 64,
        )
        frame = deepcopy(sample_state())
        frame["user"] = address
        feed.begin((T + timedelta(seconds=2 + n * 2)).isoformat())
        feed.observe(
            {"channel": "allDexsClearinghouseState", "data": frame},
            (T + timedelta(seconds=3 + n * 2)).isoformat(),
        )
    original = sha256(source.path.read_bytes()).hexdigest()
    p1, p14 = PaperJournal(tmp_path / "P1"), PaperJournal(tmp_path / "P14")
    first = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert first["all_destinations_reconciled"]
    assert p1.source_status("S035")["cursor"] == 3
    assert p14.source_status("S035")["head_sha"] == source.source_status("S035")["head_sha"]
    again = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert all(
        row["imported_new"] == 0
        for portfolio in again["portfolios"].values()
        for row in portfolio["source_cursors"].values()
    )
    for journal in (source, p1, p14):
        with closing(sqlite3.connect(journal.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM runs").fetchone() == (0,)
            assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
    assert sha256(source.path.read_bytes()).hexdigest() == original


def source_five(tmp_path):
    source = PaperJournal(tmp_path / "source")
    for index, alias in enumerate(P14.members, 1):
        addr = f"0x{index:040x}"
        frame = deepcopy(sample_state())
        frame["user"] = addr
        result = read_public_all_dex_scope(
            alias=alias,
            address=addr,
            frame={"channel": "allDexsClearinghouseState", "data": frame},
            dex_catalog=[None, {"name": "xyz"}],
            discovered_subaccounts=None,
            first_known_at=(T + timedelta(seconds=2)).isoformat(),
        )
        append_public_scope(source, alias=alias, seq=1, receipt=result)
    return source


def test_per_portfolio_relay_never_needs_other_financial_journal(tmp_path):
    source = source_five(tmp_path)
    p1 = PaperJournal(tmp_path / "P1")
    p14 = PaperJournal(tmp_path / "P14")
    first = fanout_one_portfolio_receipts(
        source_db=source.path,
        portfolio_id="P1",
        account_journal=p1,
    )
    assert first["schema"] == "paper_single_account_source_fanout_v1"
    assert first["unique_sources"] == 3
    assert first["other_portfolio_account_access_required"] is False
    assert first["result"]["status"] == "COPIED_EVIDENCE_ONLY"
    assert first["canonical_all_required_sources_observed"] is True
    assert p1.source_status("S035")["cursor"] == 1
    assert p14.source_status("S035")["cursor"] == 0
    assert first["paper_financial_events_committed"] == 0
    second = fanout_one_portfolio_receipts(
        source_db=source.path,
        portfolio_id="P14",
        account_journal=p14,
    )
    assert second["unique_sources"] == 5
    assert p14.source_status("S035")["cursor"] == 1
    assert p14.source_status("S064")["cursor"] == 1
    replay = fanout_one_portfolio_receipts(
        source_db=source.path,
        portfolio_id="P1",
        account_journal=PaperJournal(p1.root),
    )
    assert all(item["imported_new"] == 0 for item in replay["result"]["source_cursors"].values())
    assert replay["order_route"] == "NONE"
    assert replay["paper_observed"] is False
    with pytest.raises(ValueError, match="PAPER_SOURCE_FANOUT_FINANCIAL_SOURCE_ISOLATION_REQUIRED"):
        fanout_one_portfolio_receipts(
            source_db=source.path,
            portfolio_id="P1",
            account_journal=source,
        )
    with pytest.raises(ValueError, match="PAPER_SOURCE_FANOUT_PORTFOLIO_NOT_FROZEN"):
        fanout_one_portfolio_receipts(
            source_db=source.path,
            portfolio_id="unknown",
            account_journal=p1,
        )


def test_public_receipts_fanout_into_two_isolated_private_accounts_no_effect(tmp_path):
    source = source_five(tmp_path)
    original_sha = sha256(source.path.read_bytes()).hexdigest()
    p1 = PaperJournal(tmp_path / "P1")
    p14 = PaperJournal(tmp_path / "P14")
    result = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert result["schema"] == "paper_shared_source_isolated_account_fanout_v1"
    assert result["unique_sources"] == 5
    assert result["canonical_source_receipts"] == 5
    assert result["canonical_all_required_sources_observed"] is True
    assert result["all_destinations_reconciled"] is True
    assert result["portfolios"]["P1"]["all_source_aliases_observed"]
    assert result["portfolios"]["P14"]["all_source_aliases_observed"]
    assert result["portfolios"]["P1"]["source_cursors"].keys() == {
        "S035",
        "S051",
        "S053",
    }
    assert result["portfolios"]["P14"]["source_cursors"].keys() == {
        "S035",
        "S051",
        "S053",
        "S064",
        "Whale_0x5f94",
    }
    assert all(
        item["imported_new"] == 1
        for portfolio in result["portfolios"].values()
        for item in portfolio["source_cursors"].values()
    )
    assert p1.source_status("S035")["head_sha"] == source.source_status("S035")["head_sha"]
    assert p14.source_status("S035")["head_sha"] == source.source_status("S035")["head_sha"]
    assert p1.source_status("S064")["cursor"] == 0
    assert p14.source_status("S064")["cursor"] == 1
    assert result["paper_financial_events_committed"] == 0
    assert result["broker_orders"] == 0 and result["order_route"] == "NONE"
    assert result["paper_observed"] is False
    assert sha256(source.path.read_bytes()).hexdigest() == original_sha

    again = fanout_frozen_source_receipts(
        source_db=source.path,
        p1_journal=PaperJournal(p1.root),
        p14_journal=PaperJournal(p14.root),
    )
    assert again["all_destinations_reconciled"]
    assert all(
        item["imported_new"] == 0
        for portfolio in again["portfolios"].values()
        for item in portfolio["source_cursors"].values()
    )


def test_tampered_canonical_receipt_refused_before_financial_copy(tmp_path):
    source = source_five(tmp_path)
    p1 = PaperJournal(tmp_path / "P1")
    p14 = PaperJournal(tmp_path / "P14")
    with closing(sqlite3.connect(source.path)) as db:
        with db:
            db.execute(
                "UPDATE source_receipts SET chain_sha=? WHERE source_id='S035' AND seq=1",
                ("f" * 64,),
            )
    with pytest.raises(ValueError, match="PAPER_SOURCE_FANOUT_ORIGIN_CHAIN_INVALID"):
        fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert p1.source_status("S035")["cursor"] == 0
    assert p14.source_status("S035")["cursor"] == 0


def test_tampered_destination_prefix_isolated_from_other_financial_journal(tmp_path):
    source = source_five(tmp_path)
    p1 = PaperJournal(tmp_path / "P1")
    p14 = PaperJournal(tmp_path / "P14")
    fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    with closing(sqlite3.connect(p1.path)) as db:
        with db:
            db.execute(
                "UPDATE source_receipts SET chain_sha=? WHERE source_id='S035' AND seq=1",
                ("f" * 64,),
            )
    res = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert res["all_destinations_reconciled"] is False
    assert res["portfolios"]["P1"]["status"] == "BLOCKED_SOURCE_FANOUT"
    assert res["portfolios"]["P14"]["status"] == "COPIED_EVIDENCE_ONLY"
    assert res["portfolios"]["P14"]["source_cursors"]["S035"]["imported_new"] == 0
    assert res["paper_financial_events_committed"] == 0
    assert res["order_route"] == "NONE"


def test_one_destination_failure_does_not_undo_other_then_retry(tmp_path):
    source = source_five(tmp_path)
    p1 = PaperJournal(tmp_path / "P1")
    p14 = PaperJournal(tmp_path / "P14")
    original = p14.append_source_receipt

    def refuse(*_args, **_kwargs):
        raise ValueError("injected_disk_error")

    p14.append_source_receipt = refuse
    first = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert first["all_destinations_reconciled"] is False
    assert first["portfolios"]["P1"]["status"] == "COPIED_EVIDENCE_ONLY"
    assert first["portfolios"]["P14"]["status"] == "BLOCKED_SOURCE_FANOUT"
    assert p1.source_status("S035")["cursor"] == 1
    assert p14.source_status("S035")["cursor"] == 0
    p14.append_source_receipt = original

    after = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert after["all_destinations_reconciled"] is True
    assert after["portfolios"]["P1"]["source_cursors"]["S035"]["imported_new"] == 0
    assert after["portfolios"]["P14"]["source_cursors"]["S035"]["imported_new"] == 1
    assert after["paper_financial_events_committed"] == 0


def test_synthetic_effects_commit_in_separate_accounts_only_after_source_copy(tmp_path):
    source = PaperJournal(tmp_path / "source")
    synthetic = _alter(
        _source_book(),
        wallet_id="S035",
        source_event_at=at(60),
        first_known_at=at(60),
        source_equity="20000",
        positions={BTC.key: "2"},
        source_marks={BTC.key: "100"},
    )
    receipt = {
        "schema": "paper_first_known_source_v1",
        "source_id": "S035",
        "source_event_at": at(60),
        "first_known_at": at(60),
        "captured_at": at(60),
        "payload_sha": synthetic["snapshot_sha"],
    }
    source.append_source_receipt("S035", 1, "test_source", receipt)

    p1 = PaperJournal(tmp_path / "P1")
    p14 = PaperJournal(tmp_path / "P14")
    policies = {
        "P1": policy(P1.members, "3000"),
        "P14": policy(P14.members, "1600"),
    }
    workers = {}
    for name, portfolio, journal in (("P1", P1, p1), ("P14", P14, p14)):
        previous = manifest(name, name + "_account")
        sealed = replace(
            previous,
            portfolio_sha=portfolio.sha,
            policy_sha=digest(policies[name]),
            rulebook=replace(previous.rulebook, confirmed=True, permitted=(BTC,)),
        )
        workers[name] = FixturePaperWorker(journal, portfolio, sealed, policies[name])

    synced = fanout_frozen_source_receipts(source_db=source.path, p1_journal=p1, p14_journal=p14)
    assert synced["all_destinations_reconciled"] is True
    assert synced["canonical_all_required_sources_observed"] is False
    assert not synced["portfolios"]["P1"]["all_source_aliases_observed"]
    for name, journal, qty in (("P1", p1, "0.3"), ("P14", p14, "0.16")):
        event = paper_signal(name, 60, digest(policies[name]), synthetic, qty)
        event["source_ref"] = {
            "source_id": "S035",
            "sequence": 1,
            "receipt_sha": digest(receipt),
        }
        workers[name].campaign.record_source_decision(name, "signal", event)
        workers[name].campaign.record_event(
            name, "due", paper_tick(name, 360, digest(policies[name]))
        )
        snapshot = journal.restore(name)
        assert snapshot["source_cursors"] == {"S035": 1}
        assert snapshot["account"]["quantities"][BTC.key] == qty
        assert snapshot["account"]["cash"] != "10000"
        assert PaperJournal(journal.root).restore(name) == snapshot
    assert p1.restore("P1")["account"]["quantities"][BTC.key] == "0.3"
    assert p14.restore("P14")["account"]["quantities"][BTC.key] == "0.16"
    assert source.source_status("S035")["cursor"] == 1
    # The only positive simulated effects above are explicit SYNTHETIC fixtures,
    # never true public account observations or a qualified paper result.
