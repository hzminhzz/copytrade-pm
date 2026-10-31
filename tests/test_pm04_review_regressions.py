"""Independent PR #13 review regressions via the public ShadowRun event seam.

References GitHub issue comment 6540806432; synthetic only, never live orders.
"""

from decimal import Decimal as D

from copytrade_pm.pm03_account import RiskState
from copytrade_pm.pm03_run import ShadowRun
from test_pm03_extended import BTC
from test_pm04_shadow import BTC_KEY, SHA, at, event, make_run, signal, target, tick
from test_pm03_extended import T, book


def test_sequential_opposing_pod_reduces_consolidated_long_without_false_reversal(tmp_path):
    run = make_run(tmp_path, max_gross_notional="3000")
    signal(run, "one-long", [target("W028", 3)], 60)
    tick(run, "long-due", 360)
    assert run.account.quantities[BTC] == D("3")
    signal(run, "later-short", [target("W042", -2, first_known_seconds=420)], 420)
    tick(run, "short-due", 720)

    assert run.account.quantities[BTC] == D("1")
    assert run.account.pm_quantities["W028"][BTC] == D("3")
    assert run.account.pm_quantities["W042"][BTC] == D("-2")
    assert run.account.risk == RiskState.GREEN
    assert BTC_KEY not in run.account.pm04_state["batch_open"]
    run.account.verify()


def test_suspended_long_reduces_to_flat_without_unapproved_net_short(tmp_path):
    run = make_run(tmp_path, max_gross_notional="2000")
    signal(run, "hedged", [target("W028", 3), target("W042", -2)], 60)
    tick(run, "due", 360)
    assert run.account.quantities[BTC] == D("1")
    tick(run, "loss", 420, mark="60")

    assert run.account.pm04_state["pod_stats"]["W028"]["state"] == "SUSPENDED"
    assert run.account.quantities[BTC] == D("0")
    assert run.account.pm_quantities["W028"][BTC] == D("2")
    assert run.account.pm_quantities["W042"][BTC] == D("-2")
    assert run.account.pm04_state["pending_pod_reductions"]["W028"][BTC_KEY] == "-2"
    assert run.account.pm04_state["pending_reversals"][BTC_KEY]["blocked_new_net"] == "-2"
    assert run.account.pm04_state["pending_reductions"] == {}
    assert run.account.risk != RiskState.HALT
    tick(run, "next", 480, mark="60")
    assert run.account.quantities[BTC] == D("0")
    assert run.account.pm_quantities["W028"][BTC] == D("2")
    assert run.account.pm04_state["pending_pod_reductions"]["W028"][BTC_KEY] == "-2"

    recovered = ShadowRun(
        tmp_path,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    assert recovered.state() == run.state()
    recovered.account.verify()


def test_suspension_exit_is_partial_then_flat_never_fabricated_when_capacity_is_zero(
    tmp_path,
):
    run = make_run(tmp_path, max_gross_notional="2000")
    signal(run, "hedged", [target("W028", 3), target("W042", -2)], 60)
    tick(run, "due", 360)

    tick(run, "no-liquidity", 420, mark="60", volume="0")
    assert run.account.quantities[BTC] == D("1")
    assert run.account.pm_quantities["W028"][BTC] == D("3")
    assert run.account.pm04_state["pending_reductions"][BTC_KEY] == "-1"
    assert run.account.pm04_state["pending_pod_reductions"]["W028"][BTC_KEY] == "-3"
    tick(run, "still-no-liquidity", 480, mark="60", volume="0")
    assert run.account.quantities[BTC] == D("1")

    tick(run, "partial", 540, mark="60", volume="0.5")
    assert run.account.quantities[BTC] == D("0.5")
    assert run.account.pm_quantities["W028"][BTC] == D("2.5")
    assert run.account.pm04_state["pending_reductions"][BTC_KEY] == "-0.5"
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

    tick(restored, "flat", 600, mark="60", volume="0.5")
    assert restored.account.quantities[BTC] == D("0")
    assert restored.account.pm_quantities["W028"][BTC] == D("2")
    assert restored.account.pm_quantities["W042"][BTC] == D("-2")
    assert restored.account.pm04_state["pending_reductions"] == {}
    assert D(restored.account.pm04_state["pending_pod_reductions"]["W028"][BTC_KEY]) == -2
    assert restored.account.pm04_state["pending_reversals"][BTC_KEY]["at"] == at(420)
    tick(restored, "no-automatic-short", 660, mark="60")
    assert restored.account.quantities[BTC] == D("0")
    restored.account.verify()


def test_later_opposing_pod_would_reverse_net_and_is_staged_only_to_flat(tmp_path):
    run = make_run(tmp_path, max_gross_notional="3000")
    signal(run, "long", [target("W028", 3)], 60)
    tick(run, "due", 360)
    signal(run, "oversized-short", [target("W042", -5, first_known_seconds=420)], 420)
    tick(run, "release", 720)
    assert run.account.quantities[BTC] == D("0")
    assert run.account.pm_quantities["W028"][BTC] == D("3")
    assert run.account.pm_quantities["W042"][BTC] == D("-3")
    assert run.account.pm04_state["pending_reversals"][BTC_KEY]["blocked_new_net"] == "-2"
    tick(run, "unapproved-remainder", 780)
    assert run.account.quantities[BTC] == D("0")
    assert run.account.pm04_state["pending_reversals"][BTC_KEY]["at"] == at(720)
    run.account.verify()


def test_latched_halt_retains_unfilled_suspended_pod_exit_and_allows_only_net_close(tmp_path):
    run = make_run(tmp_path, max_gross_notional="2000")
    signal(run, "hedged", [target("W028", 3), target("W042", -2)], 60)
    tick(run, "due", 360)
    tick(run, "loss-no-liquidity", 420, mark="60", volume="0")
    run.record(event("operator-halt", "HALT", {"reason": "synthetic manual stop"}, 440))

    assert run.account.risk == RiskState.HALT
    assert run.account.quantities[BTC] == D("1")
    assert run.account.pm04_state["pending_reductions"][BTC_KEY] == "-1"
    assert run.account.pm04_state["pending_pod_reductions"]["W028"][BTC_KEY] == "-3"
    tick(run, "halt-close", 480, mark="60", volume="1000")
    assert run.account.risk == RiskState.HALT
    assert run.account.quantities[BTC] == D("0")
    assert run.account.pm_quantities["W028"][BTC] == D("2")
    assert run.account.pm_quantities["W042"][BTC] == D("-2")
    assert run.account.pm04_state["pending_pod_reductions"]["W028"][BTC_KEY] == "-2"
    tick(run, "halt-no-reopen", 540, mark="60", volume="1000")
    assert run.account.quantities[BTC] == D("0")
    assert run.account.risk == RiskState.HALT
    reopened = ShadowRun(
        tmp_path,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    assert reopened.state() == run.state()
    reopened.account.verify()


def test_simultaneous_opposite_pod_reductions_use_internal_cross_not_fake_broker_fill(
    tmp_path,
):
    run = make_run(tmp_path, max_gross_notional="2000")
    signal(run, "hedged", [target("W028", 3), target("W042", -2)], 60)
    tick(run, "due", 360)
    assert run.account.quantities[BTC] == D("1")
    signal(
        run,
        "rebalance",
        [
            target("W028", 2, 2, first_known_seconds=420),
            target("W042", -1, 2, first_known_seconds=420),
        ],
        420,
    )
    assert run.account.quantities[BTC] == D("1")
    assert run.account.pm_quantities["W028"][BTC] == D("2")
    assert run.account.pm_quantities["W042"][BTC] == D("-1")
    assert run.account.pm04_state["internal_crosses"][-1]["not_external_execution"]
    assert run.account.pm04_state["pending_reductions"] == {}
    run.account.verify()
