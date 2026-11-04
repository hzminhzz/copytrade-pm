"""Final Phase6B evidence is fail-closed on mismatched generations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copytrade_pm.pm_phase6b import WALLETS, fingerprint
from copytrade_pm.pm_phase6b_finish import verify_evidence


def _file(folder: Path, stem: str, value: dict) -> Path:
    p = folder / (stem + ".json")
    p.write_text(json.dumps(value, sort_keys=True))
    return p


def _fixture_files(tmp_path: Path) -> dict[str, Path]:
    phase5 = _file(tmp_path, "phase5", {"portfolios": [{} for _ in range(5)]})
    scopes = {
        x: ({"SPOT": 4} if x == "ACT08" else {})
        for x in set().union(*(set(v) for v in WALLETS.values()))
    }
    source = _file(
        tmp_path,
        "source",
        {
            "wallets": {
                x: {
                    "source_file_sha256": "a" * 64,
                    "full_account_book_qualified": False,
                    "source_position": {
                        "excluded_nonperp_fills_by_scope": scopes[x],
                        "excluded_nonperp_collateral_reconciled": False,
                    },
                }
                for x in scopes
            },
            "market_day_inventory": {"BTC": {}},
        },
    )
    minute = _file(
        tmp_path,
        "minute",
        {
            "original_coverage_sha256": fingerprint(source),
            "instruments": {
                "BTC": {
                    "verified_minutes": 10,
                    "expected_minutes": 20,
                    "missing_or_invalid_minutes": 10,
                }
            },
        },
    )
    activity = _file(
        tmp_path,
        "activity",
        {
            "source_coverage_sha256": fingerprint(source),
            "native_minute_sha256": fingerprint(minute),
            "phase5_sha256": fingerprint(phase5),
            "wallets": {
                alias: {
                    "excluded_nonperp_fills_by_scope": scope,
                    "excluded_nonperp_collateral_reconciled": False,
                }
                for alias, scope in scopes.items()
            },
            "total_observed_exposure_minutes": 100,
            "total_unverified_exposure_minutes": 25,
        },
    )
    history = _file(
        tmp_path,
        "history",
        {
            "frozen_phase5_sha256": fingerprint(phase5),
            "portfolio_total_equity_reconciled": False,
            "historical_first_known_verified": False,
            "wallets": {
                "N01": {"history": {"allTime": {"maximum_gap_hours": 168}}},
            },
            "completed_at": "2026-11-04T06:00:00+00:00",
        },
    )
    sample = {
        "actionable": False,
        "actual_follower_pnl_usd": None,
        "actual_challenge_first_passage": None,
        "PM03_actual_supervisor_unknown_source_gate": {
            "approved_new_risk": False,
            "PM03_state": "RED",
        },
        "S1_frozen_one_hour_held_leg_diagnostic": {"verified_prior_held_legs": 0},
        "S6_missing_feed_response_model": {"would_block_new_risk": True},
    }
    stress = _file(
        tmp_path,
        "stress",
        {
            "source_file_audit_sha256": fingerprint(source),
            "native_market_audit_sha256": fingerprint(minute),
            "account_challenge_curve": None,
            "daily_snapshots": [sample for _ in range(540)],
            "portfolio_summary": {},
            "S8_30_day_temporal_sensitivity": {},
        },
    )
    blocked = _file(
        tmp_path,
        "blocked",
        {
            "source_coverage_sha256": fingerprint(source),
            "minute_coverage_sha256": fingerprint(minute),
            "scenario_rows": 180,
            "attempted_stresses": 0,
        },
    )
    return dict(
        phase5=phase5,
        source=source,
        minute=minute,
        activity=activity,
        historical_equity=history,
        stress=stress,
        blocked=blocked,
    )


def test_complete_research_does_not_claim_scientific_equity(tmp_path: Path):
    result = verify_evidence(**_fixture_files(tmp_path))
    assert result["research_engineering"] == "COMPLETE"
    assert result["scientific_qualification"] == "NOT_ESTABLISHED"
    assert result["account_challenge_first_passage"] is None
    assert result["conditional_stress_daily_snapshots"] == 540
    assert result["blocked_account_scenarios"] == 180
    assert result["trading_authorization"] is False


def test_cross_generation_sha_mismatch_blocks_final_signoff(tmp_path: Path):
    paths = _fixture_files(tmp_path)
    contents = json.loads(paths["minute"].read_text())
    contents["original_coverage_sha256"] = "0" * 64
    paths["minute"].write_text(json.dumps(contents))
    with pytest.raises(ValueError, match="PHASE6B_EVIDENCE_INCOMPLETE_OR_CONFLICT"):
        verify_evidence(**paths)


def test_spot_exclusion_reconciliation_mismatch_blocks_signoff(tmp_path: Path):
    paths = _fixture_files(tmp_path)
    activity = json.loads(paths["activity"].read_text())
    activity["wallets"]["ACT08"]["excluded_nonperp_fills_by_scope"]["SPOT"] = 3
    paths["activity"].write_text(json.dumps(activity))
    with pytest.raises(ValueError, match="nonperp_fill_scope_accounting_consistent"):
        verify_evidence(**paths)


def test_unverified_action_is_a_signoff_failure(tmp_path: Path):
    paths = _fixture_files(tmp_path)
    source = json.loads(paths["stress"].read_text())
    source["daily_snapshots"][0]["PM03_actual_supervisor_unknown_source_gate"][
        "approved_new_risk"
    ] = True
    paths["stress"].write_text(json.dumps(source))
    with pytest.raises(ValueError, match="all_540_model_states_nonactionable"):
        verify_evidence(**paths)
