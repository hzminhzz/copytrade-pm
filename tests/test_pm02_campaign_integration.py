"""Synthetic integration fixtures for fixed OOS looks; never scientific evidence."""

from copy import deepcopy
from datetime import timedelta
import random

import pytest

from copytrade_pm.pm02_campaign import register_plan, read_plan
from copytrade_pm.pm02_outcomes import CLAIM_FIELDS, DIGEST_FIELDS, SCHEMA
from copytrade_pm.pm_manager import digest, rank, timestamp
from test_pm02_campaign import COHORT, NOW, windows
from test_pm_manager import replay


def setup(tmp_path):
    source = replay()
    source["rows"] = [{**r, "wallet": alias} for alias in COHORT for r in replay()["rows"][:3]]
    plan = read_plan(
        register_plan(
            tmp_path / "campaign",
            pm01_sha256=digest(source),
            aliases=COHORT,
            windows=windows(),
            clock_source=lambda: NOW,
        )
    )
    return source, plan


def outcomes(plan, index=0):
    window = plan["windows"][index]
    start = timestamp(window["start_at"])
    rng = random.Random(7701 + index)
    rows = []
    for day in range(30):
        for hour in (0, 6, 12, 18):
            event = start + timedelta(days=day, hours=hour)
            incremental = 2 + rng.uniform(-0.25, 0.25)
            for horizon in (5, 15, 60):
                rows.append(
                    {
                        "episode_id": f"fixture-{index}-{day}-{hour}-{horizon}",
                        "source_event_id": f"fixture-source-{index}-{day}-{hour}",
                        "event_at": event.isoformat(),
                        "known_at": (event + timedelta(seconds=10)).isoformat(),
                        "decision_at": (event + timedelta(minutes=1)).isoformat(),
                        "outcome_known_at": (event + timedelta(hours=2)).isoformat(),
                        "horizon_minutes": horizon,
                        "verified_first_known": True,
                        "oracle_hindsight": False,
                        "matched_control": True,
                        "independent_source_digest": "a" * 64,
                        "market_source_digest": "b" * 64,
                        "follower_net_r": incremental,
                        "control_net_r": 0.1,
                        "tail_loss_r": 0.1,
                        "turnover_r": 0.1,
                        "signed_exposures_r": {"hyperliquid/mainnet:perp:default/BTC": 0.1},
                        "whole_account_verified": True,
                        "outcome_schema": SCHEMA,
                        **{k: True for k in CLAIM_FIELDS},
                        **{k: "c" * 64 for k in DIGEST_FIELDS},
                        "selection_plan_sha256": plan["sha256"],
                        "source_net_r": 1.7,
                        "risk_unit_usd": 100,
                        "source_scale_factor": 0.01,
                    }
                )
    return rows


def decide(source, plan, rows, asof, previous=None):
    return rank(
        source,
        COHORT,
        asof,
        {COHORT[0]: rows},
        prospective_verified_head="f" * 64,
        campaign=plan,
        previous_report=previous,
    )


def test_fixed_look_preserves_horizon_trials_and_cannot_advance_twice(tmp_path):
    source, plan = setup(tmp_path)
    rows = outcomes(plan)
    asof = plan["windows"][0]["decision_at"]
    report = decide(source, plan, rows, asof)
    card = report["cards"][0]
    assert card["prospective"]["qualified"] is True
    assert card["prospective"]["n"] == 120
    assert all(s["n"] == 120 for s in card["prospective"]["horizon_scores"].values())
    assert card["lifecycle"]["state"] == "SHADOW"
    assert card["source_wallet_performance"]["source_net_r"] == 204
    again = decide(source, plan, rows, (timestamp(asof) + timedelta(minutes=1)).isoformat(), report)
    assert again["cards"][0]["lifecycle"]["state"] == "SHADOW"
    assert again["cards"][0]["lifecycle"]["transition_reason"] == "NO_NEW_OOS_WINDOW"


def test_campaign_requires_full_account_and_all_registered_horizons(tmp_path):
    source, plan = setup(tmp_path)
    rows = [r for r in outcomes(plan) if r["horizon_minutes"] == 15]
    report = decide(source, plan, rows, plan["windows"][0]["decision_at"])
    assert report["qualified_count"] == 0
    assert "ALL_PREDECLARED_HORIZONS_REQUIRED" in report["cards"][0]["prospective"]["reasons"]
    rows = outcomes(plan)
    for r in rows:
        r["whole_account_verified"] = False
    report = decide(source, plan, rows, plan["windows"][0]["decision_at"])
    assert report["qualified_count"] == 0
    assert (
        "INDEPENDENT_WHOLE_ACCOUNT_OUTCOME_REQUIRED" in report["cards"][0]["prospective"]["reasons"]
    )


def test_no_future_look_no_late_revision_and_no_overlapping_samples(tmp_path):
    source, plan = setup(tmp_path)
    rows = outcomes(plan)
    assert decide(source, plan, rows, NOW.isoformat())["qualified_count"] == 0
    asof = plan["windows"][0]["decision_at"]
    report = decide(source, plan, rows, asof)
    late = deepcopy(rows[0])
    late["episode_id"] = "late"
    late["outcome_known_at"] = (timestamp(asof) + timedelta(minutes=1)).isoformat()
    later = decide(
        source, plan, rows + [late], (timestamp(asof) + timedelta(minutes=2)).isoformat()
    )
    assert later["cards"][0]["prospective"] == report["cards"][0]["prospective"]
    duplicate = deepcopy(rows[0])
    duplicate["episode_id"] = "new-id-same-source-horizon"
    with pytest.raises(ValueError, match="DUPLICATE_OR_MISSING_SOURCE_HORIZON"):
        decide(source, plan, rows + [duplicate], asof)
    duplicate["source_event_id"] = "another-source"
    overlap = decide(source, plan, rows + [duplicate], asof)
    assert overlap["qualified_count"] == 0
    assert (
        "OVERLAPPING_OUTCOME_WINDOWS"
        in overlap["cards"][0]["prospective"]["horizon_scores"]["5"]["reasons"]
    )


def test_new_windows_advance_with_native_exposure_risk_history(tmp_path):
    source, plan = setup(tmp_path)
    previous = None
    rows = []
    for index, state in enumerate(("SHADOW", "INCUBATION", "ACTIVE", "CORE")):
        rows.extend(outcomes(plan, index))
        previous = decide(source, plan, rows, plan["windows"][index]["decision_at"], previous)
        card = previous["cards"][0]
        assert card["lifecycle"]["state"] == state
        assert card["lifecycle"]["evaluated_oos_windows"] == [
            f"oos-{i + 1}" for i in range(index + 1)
        ]
    assert previous["five_seats"][0]["wallet"] == COHORT[0]
    assert previous["research_risk_allocated_r"] <= 0.2


def test_missing_evidence_never_counts_as_falsification(tmp_path):
    source, plan = setup(tmp_path)
    previous = None
    for index in range(4):
        previous = decide(source, plan, [], plan["windows"][index]["decision_at"], previous)
    card = previous["cards"][0]
    assert card["lifecycle"]["statistical_failures"] == 0
    assert card["lifecycle"]["state"] == "CANDIDATE"
    assert previous["qualified_count"] == 0


def test_post_look_revision_cannot_poison_a_fixed_asof_decision(tmp_path):
    source, plan = setup(tmp_path)
    rows = outcomes(plan)
    cutoff = plan["windows"][0]["decision_at"]
    expected = decide(source, plan, rows, cutoff)
    revision = {
        **rows[0],
        "follower_net_r": 999,
        "outcome_known_at": (timestamp(cutoff) + timedelta(minutes=1)).isoformat(),
    }
    actual = decide(
        source, plan, rows + [revision], (timestamp(cutoff) + timedelta(minutes=2)).isoformat()
    )
    assert actual["cards"][0]["prospective"] == expected["cards"][0]["prospective"]


def test_retired_manager_cannot_requalify_and_missing_data_is_distinct(tmp_path):
    source, plan = setup(tmp_path)
    previous = None
    rows = []
    for index in range(4):
        current = outcomes(plan, index)
        if index < 3:
            for row in current:
                row["follower_net_r"] -= 4
        rows.extend(current)
        previous = decide(source, plan, rows, plan["windows"][index]["decision_at"], previous)
    assert previous["cards"][0]["lifecycle"]["state"] == "RETIRED"
    assert previous["qualified_count"] == 0
    assert previous["cards"][0]["lifecycle"]["statistical_failures"] == 3


def test_overlapping_prior_risk_history_cannot_be_used_for_allocation(tmp_path):
    source, plan = setup(tmp_path)
    rows = outcomes(plan) + outcomes(plan, 1)
    original = next(r for r in rows if r["horizon_minutes"] == 15)
    rows.append({**original, "episode_id": "old-overlap", "source_event_id": "old-other-source"})
    report = decide(source, plan, rows, plan["windows"][1]["decision_at"])
    assert report["qualified_count"] == 0
    assert "OVERLAPPING_RISK_HISTORY" in report["cards"][0]["prospective"]["reasons"]
