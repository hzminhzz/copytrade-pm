"""Adversarial PIT and nonactivation gates for the Track C 16-portfolio replay."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from scripts.track_c_pit_replay import risk_k, summarize_outcomes, track_c_abstention


def _july_record():
    return {
        "max_observed_gross_usd": "10000",
        "last_observed_at": "2026-08-04T23:59:00+00:00",
    }


def test_pit_risk_calibration_uses_only_pre_cutoff_gross_and_per_pod_budget():
    r = _july_record()
    assert risk_k(r, D("200"), cutoff="2026-08-05T00:00:00+00:00") == D("0.100000000000")
    assert risk_k(r, D("120"), cutoff="2026-08-05T00:00:00+00:00") == D("0.060000000000")
    assert risk_k(
        {**r, "max_observed_gross_usd": "100"}, D("200"), cutoff="2026-08-05T00:00:00+00:00"
    ) == D("1.000000000000")


@pytest.mark.parametrize(
    ("record", "budget", "error"),
    [
        (
            {**_july_record(), "last_observed_at": "2026-08-05T00:00:00+00:00"},
            D("200"),
            "PIT_LOOKAHEAD_PREWINDOW_OBSERVATION",
        ),
        (
            {**_july_record(), "last_observed_at": "2026-08-06T00:00:00+00:00"},
            D("200"),
            "PIT_LOOKAHEAD_PREWINDOW_OBSERVATION",
        ),
        ({**_july_record(), "max_observed_gross_usd": "0"}, D("200"), "INVALID_PIT_TRAINING_GROSS"),
        (
            {**_july_record(), "max_observed_gross_usd": "NaN"},
            D("200"),
            "INVALID_PIT_TRAINING_GROSS",
        ),
        (_july_record(), D("0"), "INVALID_POD_BUDGET"),
    ],
)
def test_pit_refuses_future_rows_or_nonfinite_inputs(record, budget, error):
    with pytest.raises(ValueError, match=error):
        risk_k(record, budget, cutoff="2026-08-05T00:00:00+00:00")


def test_track_c_evaluator_abstains_with_historical_episode_data_not_pm03_finance():
    receipt = track_c_abstention(
        portfolio_id="P1",
        portfolio_sha="a" * 64,
        pod="S051",
        address_sha="b" * 64,
        current=D("0.043"),
        candidate=D("0.008839923570"),
        pod_budget=D("200"),
        as_of="2026-11-10T11:00:00+00:00",
        source_sha="c" * 64,
        calibration_sha="d" * 64,
        last_training_observed="2026-08-04T23:00:00+00:00",
    )
    assert receipt["decision"] == "INSUFFICIENT_EVIDENCE"
    assert "NO_PM03_FINANCIAL_REPORT" in receipt["reason_codes"]
    assert "RETROSPECTIVE_PORTFOLIO_SELECTION" in receipt["reason_codes"]
    assert "PM03_ACCOUNT_SNAPSHOT_REQUIRED" in receipt["reason_codes"]
    assert receipt["candidate_is_still_hypothetical"]
    assert not receipt["trade_authorized"]
    assert not receipt["release_eligible"]


def test_track_c_evaluator_does_not_authorize_increase_even_with_sample():
    receipt = track_c_abstention(
        portfolio_id="E8",
        portfolio_sha="a" * 64,
        pod="S051",
        address_sha="b" * 64,
        current=D("0.001"),
        candidate=D("0.008839923570"),
        pod_budget=D("120"),
        as_of="2026-11-10T11:00:00+00:00",
        source_sha="c" * 64,
        calibration_sha="d" * 64,
        last_training_observed="2026-08-04T23:00:00+00:00",
    )
    assert receipt["decision"] == "INSUFFICIENT_EVIDENCE"
    assert "INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED" in receipt["reason_codes"]
    assert not receipt["trade_authorized"]


def test_historical_episode_blockers_are_never_counted_as_zero_pnl():
    pl = pytest.importorskip("polars")
    rows = pl.DataFrame(
        [
            {
                "account": "x",
                "scenario": "BASE",
                "t0": 100,
                "estimated_net_pnl": 5.0,
                "outcome": "ESTIMATED_HISTORICAL_FOLLOWER_PROXY",
            },
            {
                "account": "x",
                "scenario": "BASE",
                "t0": 200,
                "estimated_net_pnl": None,
                "outcome": "UNPRICEABLE_CAPACITY",
            },
            {
                "account": "x",
                "scenario": "ADVERSE",
                "t0": 100,
                "estimated_net_pnl": -2.0,
                "outcome": "ESTIMATED_HISTORICAL_FOLLOWER_PROXY",
            },
            {
                "account": "y",
                "scenario": "BASE",
                "t0": 100,
                "estimated_net_pnl": None,
                "outcome": "MISSING_NATIVE_DAY",
            },
        ]
    )
    result = summarize_outcomes(rows, end_ms=5000)
    assert result["x"]["BASE"]["completed_episode_net_usd"] == 5.0
    assert result["x"]["BASE"]["priced_complete_episodes"] == 1
    assert result["x"]["BASE"]["blocked_reasons"] == {"UNPRICEABLE_CAPACITY": 1}
    assert result["x"]["ADVERSE"]["completed_episode_net_usd"] == -2.0
    assert result["y"]["BASE"]["completed_episode_net_usd"] is None
