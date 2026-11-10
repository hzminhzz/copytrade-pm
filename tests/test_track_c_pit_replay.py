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


def _supplement(tmp_path):
    import json
    from datetime import UTC, datetime, timedelta
    from hashlib import sha256

    from scripts.track_c_pit_replay import load_supplemental_july

    address = "0x" + "a" * 40
    key = sha256(address.encode()).hexdigest()
    stamps = [
        (datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=day, hours=hour)).isoformat()
        for day in range(7)
        for hour in range(4)
    ]
    hours = [
        {"ts": t, "gross_usd": 10000 if i == 27 else 5000, "positions": 1}
        for i, t in enumerate(stamps)
    ]
    receipt = {
        "schema": "vike_precalibration_hourly_receipt_v1",
        "wallet_alias": "ACT04",
        "wallet_address": address,
        "source": "Vike Hyperliquid positions historic 1h via connector",
        "start": "2026-07-01T00:00:00Z",
        "end_exclusive": "2026-08-05T00:00:00Z",
        "complete_pages": True,
        "failed_validation": False,
        "invalid": 0,
        "duplicates": 0,
        "total_position_rows": 28,
        "total_observed_hours": 28,
        "pages": [{"position_rows": 28, "remaining": False}],
        "max_observed_gross_usd": 10000,
        "hours": hours,
    }
    policy = {
        "wallets": {},
        "training_start": "2026-07-01T00:00:00+00:00",
        "training_end": "2026-08-05T00:00:00+00:00",
    }
    target = tmp_path / "trackc-july-ACT04-hourly.json"
    target.write_text(json.dumps(receipt))
    return load_supplemental_july, receipt, target, policy, {"p": {"ACT04": key}}, key


def test_supplemental_vendor_history_is_frozen_before_cutoff(tmp_path):
    loader, receipt, target, policy, identity, key = _supplement(tmp_path)
    merged, provenance = loader(root=tmp_path, policy=policy, account_hashes=identity)
    assert merged[key]["max_observed_gross_usd"] == "10000"
    assert merged[key]["observation_days"] == 7
    assert provenance["ACT04"]["status"] == "PREWINDOW_COMPLETE_PAGE_PROXY_ONLY"
    assert provenance["ACT04"]["file_sha256"]
    assert len(policy["wallets"]) == 0  # original source remains immutable


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"complete_pages": False}, "SUPPLEMENTAL_PAGINATION_OR_VALIDATION_INCOMPLETE"),
        ({"max_observed_gross_usd": 500}, "SUPPLEMENTAL_MAX_GROSS_MISMATCH"),
        ({"wallet_alias": "ACT09"}, "SUPPLEMENTAL_WALLET_OR_ORIGINAL_K_IDENTITY_MISMATCH"),
        ({"total_position_rows": 20}, "SUPPLEMENTAL_PAGINATION_OR_VALIDATION_INCOMPLETE"),
        ({"invalid": 1}, "SUPPLEMENTAL_PAGINATION_OR_VALIDATION_INCOMPLETE"),
    ],
)
def test_supplemental_refuses_truncated_or_tampered(tmp_path, mutation, reason):
    import json

    loader, receipt, target, policy, identity, _ = _supplement(tmp_path)
    target.write_text(json.dumps({**receipt, **mutation}))
    with pytest.raises(ValueError, match=reason):
        loader(root=tmp_path, policy=policy, account_hashes=identity)


def test_supplemental_refuses_future_snapshot_or_original_k_overwrite(tmp_path):
    import json

    loader, receipt, target, policy, identity, key = _supplement(tmp_path)
    receipt["hours"][-1]["ts"] = "2026-08-06T00:56:00+00:00"
    target.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="SUPPLEMENTAL_FUTURE_OR_OUTSIDE_WINDOW"):
        loader(root=tmp_path, policy=policy, account_hashes=identity)
    receipt["hours"][-1]["ts"] = "2026-07-07T03:00:00+00:00"
    target.write_text(json.dumps(receipt))
    policy["wallets"][key] = {"k": "0.2"}
    with pytest.raises(ValueError, match="SUPPLEMENTAL_WALLET_OR_ORIGINAL_K_IDENTITY_MISMATCH"):
        loader(root=tmp_path, policy=policy, account_hashes=identity)


def test_supplemental_intrahour_rows_use_conservative_gross(tmp_path):
    import json

    loader, receipt, target, policy, identity, key = _supplement(tmp_path)
    receipt["hours"].append({"ts": "2026-07-07T03:30:00+00:00", "gross_usd": 4000, "positions": 1})
    receipt["total_position_rows"] = 29
    receipt["total_observed_hours"] = 29
    receipt["pages"][0]["position_rows"] = 29
    target.write_text(json.dumps(receipt))
    merged, evidence = loader(root=tmp_path, policy=policy, account_hashes=identity)
    assert evidence["ACT04"]["max_observed_gross_usd"] == "10000"
    assert evidence["ACT04"]["conservative_hourly_gross_usd"] == "14000"
    assert merged[key]["max_observed_gross_usd"] == "14000"


def test_missing_july_rows_stay_unqualified(tmp_path):
    import json

    loader, receipt, target, policy, identity, key = _supplement(tmp_path)
    receipt.update(
        hours=[],
        total_position_rows=0,
        total_observed_hours=0,
        max_observed_gross_usd=0,
        pages=[{"position_rows": 0, "remaining": False}],
    )
    target.write_text(json.dumps(receipt))
    merged, evidence = loader(root=tmp_path, policy=policy, account_hashes=identity)
    assert key not in merged
    assert evidence["ACT04"]["status"] == "NO_ELIGIBLE_PREWINDOW_POSITION_OBSERVATIONS"


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
