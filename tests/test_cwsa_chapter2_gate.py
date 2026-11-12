"""Adversarial Chapter 2 acceptance gates: service health cannot imply finance health."""

import sqlite3
from contextlib import closing
import pytest
from copytrade_pm.pm03_account import digest

from copytrade_pm.pm_cwsa_chapter2_gate import (
    GateCheck,
    decide,
    assess_financial_runtime,
    assess_portfolio_roster,
    EXPECTED_PORTFOLIOS,
    EXPECTED_WALLETS,
    _verified_finance_scan,
)


def test_finance_scan_signed_receipt_tampering_is_rejected():
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute(
            "CREATE TABLE chapter2_finance_scan(owner TEXT,checkpoint_ms INTEGER,outcome_id TEXT,receipt_sha TEXT)"
        )
        owner, checkpoint, outcome_id = "W028", 1794470500000, "a" * 64
        receipt = digest(["chapter2_finance_scan_v1", owner, checkpoint, outcome_id])
        db.execute(
            "INSERT INTO chapter2_finance_scan VALUES(?,?,?,?)",
            (owner, checkpoint, outcome_id, receipt),
        )
        assert _verified_finance_scan(db, "A") == (1, checkpoint)
        db.execute("UPDATE chapter2_finance_scan SET receipt_sha=?", ("f" * 64,))
        with pytest.raises(ValueError, match="CHAPTER2_FINANCE_SCAN_TAMPERED"):
            _verified_finance_scan(db, "A")


def test_gate_has_three_distinct_verdicts():
    ok = GateCheck("identity", "PASS", "pinned seals match")
    blocked = GateCheck("mandates", "BLOCKED_EVIDENCE", "no independent signing key")
    broken = GateCheck("journal", "FAIL", "tampered chain")
    assert decide("postdeploy", [ok])["verdict"] == "PASS"
    assert decide("postdeploy", [ok, blocked])["verdict"] == "BLOCKED_EVIDENCE"
    assert decide("postdeploy", [ok, blocked, broken])["verdict"] == "FAIL"


def test_live_service_with_dead_financial_consumer_never_passes():
    result = assess_financial_runtime(
        service_active=True,
        signed_portfolios={"A"},
        finance_scans={"A": {"last_checkpoint_ms": 0}},
        source_changes={"A": 1794470500000},
        journal_cursors={"A": 0},
        latest_source_checkpoint_ms=1794470800000,
    )
    assert result.state == "FAIL"
    assert "CONSUMER" in result.detail


def test_provisional_six_empty_journals_are_not_financially_active():
    result = assess_financial_runtime(
        service_active=True,
        signed_portfolios=set(),
        finance_scans={},
        source_changes={},
        journal_cursors={pid: 0 for pid in EXPECTED_PORTFOLIOS},
        latest_source_checkpoint_ms=1794470800000,
    )
    assert result.state == "BLOCKED_EVIDENCE"
    assert "NO_SIGNED" in result.detail


def test_no_eligible_trades_does_not_invent_execution():
    result = assess_financial_runtime(
        service_active=True,
        signed_portfolios={"A"},
        finance_scans={"A": {"last_checkpoint_ms": 1794470500000}},
        source_changes={},
        journal_cursors={"A": 0},
        latest_source_checkpoint_ms=1794470800000,
    )
    assert result.state == "BLOCKED_EVIDENCE"
    assert "NO_ELIGIBLE" in result.detail


def test_six_identity_contract_rejects_other_wallet_or_portfolio():
    expected = {pid: set(m) for pid, m in EXPECTED_PORTFOLIOS.items()}
    assert assess_portfolio_roster(expected).state == "PASS"
    wrong = {k: set(v) for k, v in expected.items()}
    wrong["A"].add("UNKNOWN_WALLET")
    assert assess_portfolio_roster(wrong).state == "FAIL"
    assert len(EXPECTED_WALLETS) == 14


def test_baseline_financial_cursor_does_not_prove_a_fill():
    result = assess_financial_runtime(
        service_active=True,
        signed_portfolios={"A"},
        finance_scans={"A": {"last_checkpoint_ms": 1794470500000}},
        source_changes={"A": 1794470500000},
        journal_cursors={"A": 3},
        latest_source_checkpoint_ms=1794470800000,
    )
    assert result.state == "BLOCKED_EVIDENCE"
    assert "NO_PROVEN_MODELED_FINANCIAL_EFFECT" in result.detail


def test_all_signed_and_consumed_events_pass_financial_proof():
    result = assess_financial_runtime(
        service_active=True,
        signed_portfolios={"A"},
        finance_scans={"A": {"last_checkpoint_ms": 1794470500000}},
        source_changes={"A": 1794470500000},
        journal_cursors={"A": 4},
        latest_source_checkpoint_ms=1794470800000,
        modeled_effects={"A": 1},
    )
    assert result.state == "PASS"
