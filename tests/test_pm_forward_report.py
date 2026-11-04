"""FP-13 truthful read-only synthetic economics and funding coverage reports."""

from decimal import Decimal as D
from hashlib import sha256

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_report import build_report
from test_pm_forward_pm04 import _setup, paper_signal, paper_tick


def test_two_portfolio_report_reconciles_account_and_no_alpha(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    for name, qty in (("P1", "0.3"), ("P14", "0.16")):
        event = paper_signal(name, 60, digest(policies[name]), book, qty)
        event["source_ref"] = {
            "source_id": "S035",
            "sequence": 1,
            "receipt_sha": digest(receipt),
        }
        campaign.record_source_decision(name, "signal", event)
        campaign.record_event(name, "due", paper_tick(name, 360, digest(policies[name])))
    sha_before = sha256(journal.path.read_bytes()).hexdigest()
    result = build_report(journal.path, ("P1", "P14"), as_of="2026-11-04T04:08:00+00:00")
    assert sha256(journal.path.read_bytes()).hexdigest() == sha_before
    assert result["matched_p1_p14"].startswith("NOT_QUALIFIED")
    assert not result["alpha_claim"] and not result["challenge_pass_probability_claim"]
    first, second = result["runs"]
    assert first["evidence_class"] == second["evidence_class"] == "FORWARD_PAPER_SIMULATED_v1"
    assert not first["paper_observed"] and not second["scientifically_qualified"]
    assert first["modeled_external_fill_count"] == 1
    assert second["modeled_external_fill_count"] == 1
    assert D(first["financial_state"]["fees"]) > 0
    assert D(first["financial_state"]["gross_notional"]) > 0
    assert (
        first["financial_state"]["signed_positions"]
        != second["financial_state"]["signed_positions"]
    )
    assert first["coverage"]["actual_source_coverage"] == "UNKNOWN"
    for row in (first, second):
        values = row["financial_state"]
        assert D(row["net_modeled_pnl"]) == D(values["equity"]) - D(row["initial_equity"])
        assert D(values["balance"]) + D(values["unrealized_pnl"]) == D(values["equity"])
        assert row["cost_sensitivity_2x"] == "NOT_COMPUTED"
        assert row["timeline"][0]["equity"] == "10000"
        assert row["coverage"]["source_cursors"] == {"S035": 1}


def test_report_refuses_future_event_from_past_asof(tmp_path) -> None:
    journal, campaign, policies, _, _ = _setup(tmp_path)
    campaign.record_event("P1", "tick", paper_tick("P1", 10, digest(policies["P1"])))
    with pytest.raises(ValueError, match="PAPER_REPORT_ASOF_PRECEDES_COMMITTED_STATE"):
        build_report(journal.path, ("P1",), as_of="2026-11-04T04:00:05+00:00")
    with pytest.raises(ValueError, match="PAPER_REPORT_RUNS_REQUIRED_UNIQUE"):
        build_report(journal.path, ("P1", "P1"), as_of="2026-11-04T04:01:00+00:00")
