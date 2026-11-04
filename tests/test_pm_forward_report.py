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
    compared = result["matched_model_comparison"]
    assert compared["status"] == "SYNTHETIC_MATCHED_OUTPUT_ONLY_NO_PROSPECTIVE_COVERAGE"
    assert compared["model_event_clocks_aligned"] is True
    assert D(compared["model_event_return_dispersion_bps"]) >= 0
    assert compared["real_tracking_error"] == "NOT_ESTIMABLE_WITHOUT_MATCHED_PROSPECTIVE_PAPER"
    assert not compared["paper_observed"] and not compared["scientifically_qualified"]
    assert compared["p14_minus_p1_model_pnl"] == str(
        D(result["runs"][1]["net_modeled_pnl"]) - D(result["runs"][0]["net_modeled_pnl"])
    )
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


def test_opt_in_2x_3x_cost_stress_replays_same_sealed_events_readonly(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    event = paper_signal("P1", 60, digest(policies["P1"]), book, "0.3")
    event["source_ref"] = {
        "source_id": "S035",
        "sequence": 1,
        "receipt_sha": digest(receipt),
    }
    campaign.record_source_decision("P1", "signal", event)
    campaign.record_event("P1", "due", paper_tick("P1", 360, digest(policies["P1"])))
    before = sha256(journal.path.read_bytes()).hexdigest()
    report = build_report(
        journal.path,
        ("P1",),
        as_of="2026-11-04T04:08:00+00:00",
        cost_stress=True,
    )
    assert sha256(journal.path.read_bytes()).hexdigest() == before
    row = report["runs"][0]
    higher = row["cost_sensitivity_2x"]
    highest = row["cost_sensitivity_3x"]
    assert report["cost_sensitivity_status"] == "SYNTHETIC_REPLAY_ONLY_NO_ALPHA"
    assert higher["status"] == highest["status"] == "SYNTHETIC_COST_STRESS_REPLAY_ONLY"
    assert higher["multiplier"] == 2
    assert highest["multiplier"] == 3
    assert D(row["net_modeled_pnl"]) >= D(higher["net_modeled_pnl"])
    assert D(higher["net_modeled_pnl"]) >= D(highest["net_modeled_pnl"])
    assert D(highest["total_fees"]) >= D(higher["total_fees"])
    assert not higher["paper_observed"] and not highest["scientifically_qualified"]
    assert report["alpha_claim"] is False


def test_matched_model_cost_scenarios_remain_unqualified(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    for run_id, qty in (("P1", "0.3"), ("P14", "0.16")):
        event = paper_signal(run_id, 60, digest(policies[run_id]), book, qty)
        event["source_ref"] = {"source_id": "S035", "sequence": 1, "receipt_sha": digest(receipt)}
        campaign.record_source_decision(run_id, "signal", event)
        campaign.record_event(run_id, "due", paper_tick(run_id, 360, digest(policies[run_id])))
    report = build_report(
        journal.path,
        ("P14", "P1"),
        as_of="2026-11-04T04:08:00+00:00",
        cost_stress=True,
    )
    compared = report["matched_model_comparison"]
    assert compared["status"].startswith("SYNTHETIC_MATCHED")
    for factor in ("2x", "3x"):
        assert compared["scenario_p14_minus_p1_model_pnl"][factor] != "NOT_COMPUTED"
        p14 = next(x for x in report["runs"] if x["run_id"] == "P14")
        p1 = next(x for x in report["runs"] if x["run_id"] == "P1")
        expected = D(p14[f"cost_sensitivity_{factor}"]["net_modeled_pnl"]) - D(
            p1[f"cost_sensitivity_{factor}"]["net_modeled_pnl"]
        )
        assert D(compared["scenario_p14_minus_p1_model_pnl"][factor]) == expected
    assert compared["real_tracking_error"].startswith("NOT_ESTIMABLE")


def test_unaligned_model_timelines_do_not_fabricate_tracking_error(tmp_path) -> None:
    journal, campaign, policies, _, _ = _setup(tmp_path)
    campaign.record_event("P1", "tick", paper_tick("P1", 10, digest(policies["P1"])))
    report = build_report(journal.path, ("P1", "P14"), as_of="2026-11-04T04:01:00+00:00")
    compared = report["matched_model_comparison"]
    assert compared["model_event_clocks_aligned"] is False
    assert compared["model_event_return_dispersion_bps"] is None
    assert compared["real_tracking_error"].startswith("NOT_ESTIMABLE")


def test_report_refuses_future_event_from_past_asof(tmp_path) -> None:
    journal, campaign, policies, _, _ = _setup(tmp_path)
    campaign.record_event("P1", "tick", paper_tick("P1", 10, digest(policies["P1"])))
    with pytest.raises(ValueError, match="PAPER_REPORT_ASOF_PRECEDES_COMMITTED_STATE"):
        build_report(journal.path, ("P1",), as_of="2026-11-04T04:00:05+00:00")
    with pytest.raises(ValueError, match="PAPER_REPORT_RUNS_REQUIRED_UNIQUE"):
        build_report(journal.path, ("P1", "P1"), as_of="2026-11-04T04:01:00+00:00")
