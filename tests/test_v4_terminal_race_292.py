"""Adversarial V4 terminal attempt source-head race, issue #292."""

from contextlib import closing
from decimal import Decimal as D
import sqlite3

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_vike_market_catalog import NativePaperContract
from copytrade_pm import pm_forward_observed_paper as paper_module
from test_pm_forward_observed_paper import BTC, at, registry
from test_pm_vike_paper_integration import official_observer, official_frame, price


def test_new_gap_after_initial_read_during_sizing_cancels_terminal_attempt(
    tmp_path,
    monkeypatch,
):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    official = official_observer(source)
    official.observe(official_frame(12, 20), at(13))
    contract = NativePaperContract(
        instrument=BTC,
        amount_step=D("0.001"),
        minimum_notional=D("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    paper = ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=tmp_path / "finance",
        registry_db=registry(tmp_path / "registry.sqlite"),
        run_id="source_head_interleave",
        catalog={},
        native_contracts={BTC.key: contract},
        started_at=at(0),
    )
    initial = paper.step(at(14))
    intent_id = initial["execution_intents"]["S035"]["intent_id"]
    assert initial["execution_intents"]["S035"]["due_at"] == at(313)
    price(prices, 312)
    original = paper_module.target_from_fixed_k
    fired = False

    def interleave(*args, **kwargs):
        nonlocal fired
        assert not fired, "unexpected duplicate sizing attempt"
        fired = True
        # Real journal writer can proceed while paper is computing.
        official.gap(at(312), "TEST_INTERLEAVED_GAP")
        with closing(sqlite3.connect(source.path, timeout=0.3)) as db:
            busy, log, checkpointed = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            assert not busy and log >= checkpointed
        return original(*args, **kwargs)

    monkeypatch.setattr(paper_module, "target_from_fixed_k", interleave)
    result = paper.step(at(313))
    assert fired
    assert result["quantity_count"] == 0
    assert result["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert (
        paper.run.account.pm04_state["paper_execution"]["history"][intent_id]["status"]
        == "CANCELED_SOURCE_GAP"
    )
    assert result["real_broker_fills"] == 0
    assert result["order_route"] == "NONE"
