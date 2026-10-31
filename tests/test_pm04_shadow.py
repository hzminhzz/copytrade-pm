"""PM-04 public ShadowRun event contract: three independent research pods, no orders."""

from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import RiskState, digest
from copytrade_pm.pm03_memory import Event
from copytrade_pm.pm03_run import ShadowRun
from test_pm03_extended import BTC, T, book

SHA = digest("pm04 test source")
BTC_KEY = BTC.key
PODS = ("W028", "W042", "W030")


def at(seconds):
    return (datetime.fromisoformat(T) + timedelta(seconds=seconds)).isoformat()


def policy(**overrides):
    result = {
        "schema": "pm04_research_policy_v1",
        "version": "research-issue12-v1",
        "approval_reference": "research-only-issue-12",
        "pods": {
            p: {
                "budget_ref": f"approved-research-{p}",
                "daily_loss": "80",
                "max_drawdown": "180",
                "stress_loss": "200",
            }
            for p in PODS
        },
        "max_gross_notional": "1000",
        "max_instrument_fraction_equity": "0.50",
        "max_stress_loss": "800",
        "reserve": "10",
        "max_signal_age_seconds": 300,
        "broker_max_age_seconds": 300,
        "reconcile_tolerance": "0.001",
        "batch_seconds": 300,
        "execution_policy": "ASYMMETRIC",
        "broker_required": False,
    }
    result.update(overrides)
    return result


def event(i, kind, payload, seconds, *, source_seconds=None):
    known = seconds if source_seconds is None else source_seconds
    return Event(
        event_id=f"pm04-{i}",
        source_event_at=at(known),
        first_known_at=at(seconds),
        decision_at=at(seconds),
        hypothetical_fill_at=at(seconds + 2),
        kind=kind,
        payload={"run_id": "pm04-run", "rulebook_sha": book().sha, "input": payload},
        source_sha=SHA,
    )


def make_run(tmp_path, **kwargs):
    run = ShadowRun(
        tmp_path,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    run.record(event("config", "PM04_CONFIG", {"policy": policy(**kwargs)}, 0))
    return run


def observation(seconds, *, mark="100", volume="1000", instrument=BTC_KEY):
    return {
        "instrument": instrument,
        "event_at": at(seconds),
        "first_known_at": at(seconds),
        "mark": mark,
        "volume_base": volume,
        "quality": "SYNTHETIC",
        "supported": True,
    }


def engine(seconds, *, mark="100", volume="1000", shocks=None):
    return {
        "observations": [observation(seconds, mark=mark, volume=volume)],
        "shocks": shocks if shocks is not None else [{BTC_KEY: "-0.05"}, {BTC_KEY: "0.05"}],
        "evidence": {
            "trusted": True,
            "account_state_known": True,
            "market_state_known": True,
            "market_coverage_valid": True,
            "pending_unknown_orders": False,
            "input_status": "RESEARCH_SYNTHETIC",
            "pm02_qualified": False,
            "hedge_break_loss": "10",
        },
        "costs": {
            "fee_bps": "0",
            "full_spread_bps": "0",
            "slippage_bps": "0",
            "impact_bps_at_full_participation": "0",
            "max_participation": "1",
            "max_age_seconds": 300,
            "latency_seconds": 1,
        },
    }


def target(pod, qty, rev=1, *, first_known_seconds=60):
    return {
        "pod": pod,
        "instrument": BTC_KEY,
        "quantity": str(qty),
        "revision": rev,
        "source_event_at": at(first_known_seconds),
        "first_known_at": at(first_known_seconds),
        "source_sha": SHA,
        "budget_ref": f"approved-research-{pod}",
    }


def signal(run, i, targets, seconds, **kwargs):
    payload = {**engine(seconds, **kwargs), "targets": targets}
    return run.record(event(i, "PM04_SIGNAL", payload, seconds))


def tick(run, i, seconds, **kwargs):
    return run.record(event(i, "PM04_TICK", engine(seconds, **kwargs), seconds))


def test_two_longs_batch_once_and_decreases_do_not_wait(tmp_path):
    run = make_run(tmp_path)
    signal(run, "first", [target("W028", 3), target("W042", 2)], 60)
    assert run.account.quantities == {}
    assert run.state()["account"]["pm04"]["batch_open"][BTC_KEY] == at(60)
    tick(run, "not-yet", 359)
    assert run.account.quantities == {}
    tick(run, "due", 360)
    assert run.account.quantities[BTC] == D("5")
    assert run.account.pm_quantities["W028"][BTC] == D("3")
    assert run.account.pm_quantities["W042"][BTC] == D("2")
    signal(run, "reduce", [target("W028", 0, 2, first_known_seconds=420)], 420)
    assert run.account.quantities[BTC] == D("2")
    assert run.account.pm_quantities["W042"][BTC] == D("2")
    assert run.verify_checkpoint(run.checkpoint()) == run.state()


def test_opposing_pods_internal_cross_and_exact_namespace(tmp_path):
    run = make_run(tmp_path)
    signal(run, "opposite", [target("W028", 3), target("W042", -2)], 60)
    tick(run, "due", 360)
    assert run.account.quantities[BTC] == D("1")
    assert run.account.pm_quantities["W028"][BTC] == D("3")
    assert run.account.pm_quantities["W042"][BTC] == D("-2")
    assert D(run.account.snapshot()["pm04"]["economics"]["reconciliation_rounding_residual"]) == 0
    with pytest.raises(ValueError, match="UNSUPPORTED_INSTRUMENT|INVALID_INSTRUMENT"):
        signal(
            run,
            "badmarket",
            [
                target("W030", 1, first_known_seconds=400)
                | {"instrument": "hyperliquid/mainnet:perp:another/BTC"}
            ],
            400,
        )


def test_gross_gap_zero_exit_liquidity_preserves_position_and_recovery(tmp_path):
    run = make_run(tmp_path, max_gross_notional="500")
    signal(run, "long", [target("W028", 4)], 60)
    tick(run, "due", 360)
    assert run.account.quantities[BTC] == D("4")
    # A gap can exceed a cap; it is not instantly and fictionally liquidated.
    signal(
        run, "close", [target("W028", 0, 2, first_known_seconds=420)], 420, mark="200", volume="0"
    )
    assert run.account.quantities[BTC] == D("4")
    s = run.state()["account"]
    assert s["risk"] in ("RED", "HALT")
    assert s["pm04"]["pending_reductions"][BTC_KEY] != "0"
    assert s["pm04"]["risk_breaches"]
    restored = ShadowRun(
        tmp_path,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    assert restored.state() == run.state()


def test_independent_pod_daily_loss_suspends_only_loser(tmp_path):
    run = make_run(tmp_path, max_gross_notional="2000")
    signal(run, "long", [target("W028", 3), target("W042", -2)], 60)
    tick(run, "due", 360)
    # W028 loses on downside. W042's short PnL is positive.
    tick(run, "loss", 420, mark="60")
    pods = run.state()["account"]["pm04"]["pod_stats"]
    assert pods["W028"]["state"] == "SUSPENDED"
    assert pods["W042"]["state"] != "SUSPENDED"
    assert run.account.risk != RiskState.HALT


def test_broker_duplicate_race_unknown_order_and_snapshot_mismatch(tmp_path):
    run = make_run(tmp_path, broker_required=True)
    base = {
        "schema": "pm04_broker_observation_v1",
        "evidence_id": "intent1",
        "kind": "ORDER_INTENT",
        "order_id": "ex1",
        "instrument": BTC_KEY,
        "quantity": "2",
        "event_at": at(10),
        "first_known_at": at(20),
        "provider_sequence": 1,
    }
    run.record(event("broker1", "PM04_BROKER", {"observation": base}, 20))
    snap = run.state()["account"]["pm04"]["broker"]
    run.record(event("dup", "PM04_BROKER", {"observation": base}, 21))
    assert run.state()["account"]["pm04"]["broker"] == snap
    cancel = base | {
        "evidence_id": "cancel",
        "kind": "CANCEL",
        "event_at": at(25),
        "first_known_at": at(30),
        "provider_sequence": 3,
    }
    fill = base | {
        "evidence_id": "fill",
        "kind": "FILL",
        "cumulative_filled": "1",
        "event_at": at(27),
        "first_known_at": at(31),
        "provider_sequence": 2,
    }
    run.record(event("cancel", "PM04_BROKER", {"observation": cancel}, 30))
    run.record(event("fill", "PM04_BROKER", {"observation": fill}, 31))
    assert run.state()["account"]["pm04"]["broker"]["orders"]["ex1"]["cumulative_filled"] == "1"
    with pytest.raises(ValueError, match="CONFLICTING|REVISION"):
        run.record(event("conflict", "PM04_BROKER", {"observation": fill | {"quantity": "3"}}, 32))
    # Unknown independently reported account position must stop further increases.
    run.record(
        event(
            "foreign",
            "PM04_BROKER",
            {
                "observation": {
                    "schema": "pm04_broker_observation_v1",
                    "evidence_id": "snapshot",
                    "kind": "POSITION_SNAPSHOT",
                    "event_at": at(35),
                    "first_known_at": at(36),
                    "positions": {BTC_KEY: "5"},
                    "complete": True,
                }
            },
            36,
        )
    )
    assert "POSITION_MISMATCH" in run.state()["account"]["pm04"]["broker"]["discrepancies"]
    assert run.account.risk in (RiskState.RED, RiskState.HALT)


def test_hard_pretrade_reject_increase_and_preserve_real_holdings(tmp_path):
    run = make_run(tmp_path, max_gross_notional="200")
    signal(run, "large", [target("W028", 3)], 60)
    tick(run, "due", 360)
    assert run.account.quantities == {}
    assert run.account.risk == RiskState.RED
    assert "PRETRADE_GROSS_REJECT" in run.account.risk_reasons


def test_account_halt_blocks_all_new_pod_risk(tmp_path):
    run = make_run(tmp_path)
    run.record(event("halt", "HALT", {"reason": "operator shadow stop"}, 10))
    signal(run, "after-halt", [target("W028", 2, first_known_seconds=60)], 60)
    tick(run, "due", 360)
    assert run.account.quantities == {}
    assert run.account.risk == RiskState.HALT


def test_stale_and_wrong_provenance_fail_closed(tmp_path):
    run = make_run(tmp_path)
    with pytest.raises(ValueError, match="STALE|FUTURE|SOURCE|CAUSAL"):
        signal(run, "stale", [target("W028", 1, first_known_seconds=60)], 600)
    with pytest.raises(ValueError, match="BUDGET_REF"):
        signal(
            run,
            "budget",
            [target("W028", 1, first_known_seconds=65) | {"budget_ref": "unknown"}],
            65,
        )
    assert run.account.quantities == {}
