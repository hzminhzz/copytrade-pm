"""Adversarial recovery tests for Phase 6B source and conditional stress contracts.

No network, historical data reads or broker authority.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from copytrade_pm.pm_phase6b import (
    WALLETS,
    inspect_fill_chain,
    locate_phase4_wallet,
    normalize_phase4_wallet,
)
from copytrade_pm.pm_phase6b_activity import SourceStep, active_intervals
from copytrade_pm.pm_phase6b_portfolio_history import _equity_points, inspect_portfolio
from copytrade_pm.pm_phase6b_snapshot_stress import (
    _hour_hold_diagnostic,
    _portfolio_observation,
    _temporal_stability,
    _verify_consumed_native_shas,
    frozen_scalar_policy,
    sources_asof,
)

ADDR = "0x" + "3" * 40
TIME = datetime(2026, 9, 9, 16, 30, tzinfo=UTC)


def make_frozen_phase5():
    ids = {
        "A_base": "Ensemble_A_Pure_New50_1x",
        "A_active": "Ensemble_A_Pure_New50_Active_1.5x",
        "B_base": "Ensemble_B_CrossCohort_Hybrid_1x",
        "B_active": "Ensemble_B_CrossCohort_Hybrid_Active_1.6x",
    }
    return {
        "portfolios": [
            {
                "portfolio_id": identifier,
                "members": [
                    {
                        "member_alias": alias,
                        "original_weight_percent": str(weight),
                        "original_effective_k": str(D(str(weight)) * D("0.01")),
                    }
                    for alias, weight in WALLETS[key].items()
                ],
            }
            for key, identifier in ids.items()
        ]
    }


def test_frozen_scalar_scale_and_controls():
    multipliers = frozen_scalar_policy(make_frozen_phase5())
    assert multipliers["A_base"]["H21"] == D("0.025")
    assert multipliers["A_active"]["H21"] == D("0.035")
    assert multipliers["C_equal"]["H21"] == D(1) / D(30)
    assert abs(sum(multipliers["C_equal"].values()) - D("0.1")) < D("1e-25")
    assert multipliers["D_equal"]["ACT08"] == D(1) / D(30)


def test_frozen_weights_reject_hidden_composition_mutation():
    frozen = make_frozen_phase5()
    frozen["portfolios"][0]["members"][0]["original_weight_percent"] = "26"
    with pytest.raises(ValueError, match="PHASE6B_FROZEN_WEIGHTS_MISMATCH"):
        frozen_scalar_policy(frozen)


def test_phase4_compatibility_preserves_original_trade_ids(tmp_path: Path):
    root = tmp_path / "legacy"
    root.mkdir()
    payload = {
        "address": ADDR,
        "total_fills_90d": 2,
        "hl_fills_count": 1,
        "hx_fills_count": 1,
        "fills": [
            {
                "coin": "ETH",
                "side": "B",
                "sz": "2",
                "px": "100",
                "startPosition": "0.0",
                "tid": 90,
                "time": 1790076476512,
            },
            {
                "coin": "ETH",
                "side": "A",
                "sz": "2",
                "px": "101",
                "start_position": "2",
                "tid": 91,
                "time": 1790076477521,
                "user": ADDR,
            },
        ],
    }
    p = root / "saved_original.json"
    p.write_text(json.dumps(payload))
    assert locate_phase4_wallet(root, ADDR) == p
    rows = normalize_phase4_wallet(payload, ADDR)
    assert [r["tid"] for r in rows] == [90, 91]
    assert [r["start_position"] for r in rows] == ["0.0", "2"]
    assert inspect_fill_chain(rows, ADDR)["counts"].get("UNKNOWN_PRE_ANCHOR_POSITION", 0) == 0


def test_phase4_wrong_owner_and_conflicting_positions_rejected():
    base = {
        "address": ADDR,
        "total_fills_90d": 1,
        "hl_fills_count": 1,
        "hx_fills_count": 0,
        "fills": [
            {
                "coin": "BTC",
                "side": "B",
                "sz": "1",
                "px": "100",
                "startPosition": "0",
                "tid": 9,
                "time": 1790076476512,
            }
        ],
    }
    with pytest.raises(ValueError, match="PHASE4_FILL_DIFFERENT_OWNER"):
        normalize_phase4_wallet(
            {
                **base,
                "fills": [{**base["fills"][0], "user": "0x" + "4" * 40}],
            },
            ADDR,
        )
    with pytest.raises(ValueError, match="PHASE4_MISSING_OR_AMBIGUOUS_START_POSITION"):
        normalize_phase4_wallet(
            {
                **base,
                "fills": [{**base["fills"][0], "start_position": "0"}],
            },
            ADDR,
        )


def test_source_asof_never_uses_event_inside_delay_window():
    steps = [
        SourceStep(TIME - timedelta(minutes=7), "1", "BTC", D("0"), D("2"), D("100")),
        SourceStep(TIME - timedelta(minutes=3), "2", "BTC", D("2"), D("0"), D("100")),
        SourceStep(TIME - timedelta(minutes=7), "3", "ETH", D("0"), D("1"), D("101")),
    ]
    book, unseen = sources_asof(steps, TIME)
    assert book == {"BTC": D("2"), "ETH": D("1")}
    assert unseen == 0
    book2, unseen2 = sources_asof(steps, TIME - timedelta(minutes=5))
    assert book2 == {}
    assert unseen2 == 2


def test_position_chain_break_does_not_erase_diagnostic():
    steps = [
        SourceStep(TIME - timedelta(minutes=60), "1", "BTC", D("0"), D("2"), D("100")),
        SourceStep(TIME - timedelta(minutes=30), "2", "BTC", D("9"), D("10"), D("99")),
    ]
    intervals, gaps = active_intervals(steps)
    assert gaps == {"BTC": 1}
    assert all(x[2] > x[1] for x in intervals)


class DummyMarket:
    def get(self, native: str, timestamp: datetime):
        assert native.startswith("hyperliquid:mainnet:perp:default:")
        return SimpleNamespace(
            open=D("100") if timestamp < TIME else D("110"),
            source_sha256="a" * 64,
        )


def test_s1_s6_s7_return_conditional_stress_not_account_pnl():
    market = DummyMarket()
    positions = {"N01": {"BTC": D("2")}, "N07": {"BTC": D("-1")}}
    k = {"N01": D("0.1"), "N07": D("0.1")}
    s1 = _hour_hold_diagnostic(k, positions, market, TIME, {})
    assert D(s1["model_pnl_usd_on_priced_prior_holdings"]) == D("1")
    assert s1["complete_follower_account_economics"] is False
    snap = _portfolio_observation(
        "custom", k, positions, {"N01": 0, "N07": 0}, market, TIME, {}, positions
    )
    assert D(snap["priced_gross_notional_usd"]) == D("11")
    assert D(snap["known_leg_instantaneous_model_losses_usd"]["S3_crash_30pct"]) == D("3.3")
    assert snap["S6_missing_feed_response_model"]["flatten_executed"] is None
    assert D(snap["S7_leave_one_out_model"]["N01"]["net_30pct_crash_model_loss_usd"]) == 0
    assert D(snap["S7_leave_one_out_model"]["N07"]["net_30pct_crash_model_loss_usd"]) == D("6.6")
    unknown = _portfolio_observation(
        "custom", k, positions, {"N01": 1, "N07": 0}, market, TIME, {}, positions
    )
    assert unknown["S6_missing_feed_response_model"]["would_block_new_risk"]
    assert unknown["actual_challenge_first_passage"] is None


def test_market_sha_bound_to_frozen_independent_audit():
    audit = {
        "instruments": {
            "BTC": {
                "days": [
                    {"day": "2026-09-09", "sha256": "a" * 64},
                ]
            }
        }
    }
    label = "hyperliquid:mainnet:perp:default:BTC@2026-09-09"
    _verify_consumed_native_shas({label: "a" * 64}, audit, {})
    with pytest.raises(ValueError, match="NATIVE_MARKET_SHA_DRIFT_VS_FROZEN_AUDIT"):
        _verify_consumed_native_shas({label: "b" * 64}, audit, {})


def test_sparse_official_history_not_reconciled_or_first_known():
    a = int((TIME - timedelta(days=7)).timestamp() * 1000)
    b = int(TIME.timestamp() * 1000)
    metadata = _equity_points({"accountValueHistory": [[a, "200"], [b, "220"]]})
    assert metadata["maximum_gap_hours"] == 168
    assert metadata["point_in_time_first_known_verified"] is False
    assert metadata["reconciled_all_dex_funding_and_collateral"] is False
    invalid = inspect_portfolio([["allTime", {}], ["perpAllTime", {}]])
    assert invalid["allTime"]["status"] == "INVALID_PROVIDER_HISTORY"


def test_three_temporal_slices_do_not_mint_sharpe():
    from copytrade_pm.pm_phase6b import START

    samples = [
        {
            "portfolio": "p",
            "snapshot_at": (START + timedelta(days=d, hours=12)).isoformat(),
            "priced_observed_leg_count": 1,
            "source_missing_market_leg_count": 0,
            "known_leg_instantaneous_model_losses_usd": {"S3_crash_30pct": "25"},
        }
        for d in range(90)
    ]
    splits = _temporal_stability(samples, ["p"])["p"]
    assert [x["n_fixed_snapshots"] for x in splits] == [30, 30, 30]
    assert all(x["realized_pnl"] is None for x in splits)
