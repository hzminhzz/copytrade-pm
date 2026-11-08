"""Ranking is fail-closed when cost stress, coverage, or risk stops invalidate it."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "scripts"))
from research_t5_rank_audit_20261108 import _score_record  # noqa: E402


def _row(mult:int, net:str|None, status:str="COMPLETED_NATIVE_SELECTED_EPISODE_SCREEN")->dict:
    return {
        "wallet":"REG42",
        "cost_multiplier":mult,
        "status":status,
        "net_usd_screen_only":net,
        "selected_episode_replay_completed":net is not None,
        "native_selected_fill_fraction":0.95,
        "orders":60,
        "unverified_execution":False,
        "last_local_source_fill_at":"2026-11-06T23:00:00+00:00",
    }


def _receipts(first:dict,second:dict,third:dict):
    return {
        "native_all":{"results":[first]},
        "native":{"results":[first,second,third]},
        "vike_inferred":{"results":[]},
    }


def test_complete_cost_stress_can_rank_but_never_scientifically_qualifies() -> None:
    r=_score_record("REG42",_receipts(_row(1,"101"),_row(2,"80"),_row(3,"60")))
    assert r["sim_net_1x"]==101
    assert r["worst_cost_net"]==60
    assert r["numerical_subset_screen_pass"] is True


def test_risk_stop_is_not_highest_rank_even_with_positive_closed_pnl() -> None:
    r=_score_record("REG42",_receipts(
        _row(1,"150","STOPPED_BY_POD_RISK"),
        _row(2,"140","STOPPED_BY_POD_RISK"),
        _row(3,"130","STOPPED_BY_POD_RISK"),
    ))
    assert r["sim_net_1x"]==150
    assert r["risk_stopped_any_scenario"] is True
    assert r["worst_cost_net"] is None
    assert r["numerical_subset_screen_pass"] is False


def test_missing_market_mark_cannot_invent_any_qualified_follower_profit() -> None:
    blocked=_row(2,None,"MISSING_SHA_VERIFIED_MARK_OR_PRIOR_VOLUME")
    blocked["partial_net_at_block_usd"]="1000.0"
    r=_score_record("REG42",_receipts(_row(1,"100"),blocked,_row(3,"50")))
    assert r["worst_cost_net"] is None
    assert r["sim_net_2x"] is None
    assert r["numerical_subset_screen_pass"] is False
