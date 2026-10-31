"""PM-04 Issue #12 acceptance matrix (18 adversarial behavior scenarios).

Black-box ShadowRun/CLI contracts only; invented data and zero live order paths.
"""

from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path

import pytest

from copytrade_pm.pm03_account import RiskState, digest
from copytrade_pm.pm03_cli import execute as cli_execute
from copytrade_pm.pm03_run import ShadowRun
from test_pm03_extended import BTC, T, book
from test_pm04_shadow import (
    BTC_KEY,
    SHA,
    at,
    engine,
    event,
    make_run,
    signal,
    target,
    tick,
)


def observation_event(run, name, kind, seconds, **extra):
    broker = {
        "schema": "pm04_broker_observation_v1",
        "evidence_id": name,
        "kind": kind,
        "event_at": at(seconds),
        "first_known_at": at(seconds),
        **extra,
    }
    return run.record(event(name, "PM04_BROKER", {"observation": broker}, seconds))


def reopen(root):
    return ShadowRun(
        root,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )


# 01: Same-instrument same-side pod signals net and preserve independent shares.
def test_01_same_side_netting_no_double_broker_quantity(tmp_path):
    r = make_run(tmp_path)
    signal(r, "same", [target("W028", 2), target("W042", 3)], 60)
    tick(r, "release", 360)
    assert r.account.quantities[BTC] == D("5")
    assert r.account.pm_quantities["W028"][BTC] == D("2")
    assert r.account.pm_quantities["W042"][BTC] == D("3")
    assert r.account.pm_equity_pnl().get("W028", D(0)) == D("0")


# 02: Opposing pods transfer virtual shares; net external fill only.
def test_02_opposite_side_netting_and_internal_cross_not_fill(tmp_path):
    r = make_run(tmp_path)
    signal(r, "hedged", [target("W028", 3), target("W042", -2)], 60)
    tick(r, "release", 360)
    assert r.account.quantities[BTC] == D("1")
    assert r.account.pm_quantities["W028"][BTC] == D("3")
    assert r.account.pm_quantities["W042"][BTC] == D("-2")
    assert r.account.pm04_state["internal_crosses"][0]["not_external_execution"]


# 03: Timer opens at first signal, never resets on second same-minute signal.
def test_03_nonresetting_300_second_batch_for_multiple_updates(tmp_path):
    r = make_run(tmp_path)
    signal(r, "first", [target("W028", 1)], 60)
    signal(r, "second", [target("W042", 1, first_known_seconds=120)], 120)
    assert r.account.pm04_state["batch_open"][BTC_KEY] == at(60)
    tick(r, "before", 359)
    assert r.account.quantities == {}
    tick(r, "due", 360)
    assert r.account.quantities[BTC] == D("2")


# 04: Asymmetric policy removes one pod's risk promptly but retains other.
def test_04_prompt_reduction_keeps_unrelated_pod_position(tmp_path):
    r = make_run(tmp_path)
    signal(r, "start", [target("W028", 2), target("W042", 2)], 60)
    tick(r, "due", 360)
    signal(r, "close-one", [target("W028", 0, 2, first_known_seconds=420)], 420)
    assert r.account.quantities[BTC] == D("2")
    assert r.account.pm_quantities["W042"][BTC] == D("2")


# 05: Same ticker on another exact market must never alias.
def test_05_market_namespace_collision_blocks_without_mutation(tmp_path):
    r = make_run(tmp_path)
    before = r.state()
    with pytest.raises(ValueError, match="UNSUPPORTED_INSTRUMENT"):
        signal(
            r,
            "wrong-dex",
            [target("W028", 1) | {"instrument": "hyperliquid/mainnet:perp:other/BTC"}],
            60,
        )
    assert r.state() == before


# 06: Reversals must first close; zero liquidity never manufactures a short.
def test_06_reversal_with_zero_liquidity_cannot_cross_through_flat(tmp_path):
    r = make_run(tmp_path)
    signal(r, "start", [target("W028", 2)], 60)
    tick(r, "due", 360)
    signal(r, "reverse", [target("W028", -2, 2, first_known_seconds=420)], 420, volume="0")
    assert r.account.quantities[BTC] == D("2")
    assert r.account.pm04_state["pending_reductions"][BTC_KEY] == "-2"
    assert r.account.pm_quantities["W028"][BTC] == D("2")


# 07: Accounting after a modeled partial fill, fees and funding remains exact.
def test_07_partial_fill_fees_funding_and_pod_pnl_reconcile(tmp_path):
    r = make_run(tmp_path)
    signal(r, "open", [target("W028", 5), target("W042", -2)], 60)
    row = engine(360, volume="1")
    row["costs"]["max_participation"] = "1"
    row["costs"]["fee_bps"] = "10"
    row["costs"]["full_spread_bps"] = "20"
    r.record(event("fill", "PM04_TICK", row, 360))
    r.record(
        event(
            "fund",
            "FUNDING",
            {
                "amount": "-0.3",
                "allocated": {"W028": "-0.2", "W042": "-0.1"},
            },
            370,
        )
    )
    r.account.verify()
    e = r.account.pm04_state["economics"]
    # After standalone PM-03 events, PM-04 cached economics must be refreshed.
    assert D(e["reconciliation_rounding_residual"]) == 0
    assert D(e["consolidated_account_pnl"]) == (
        r.account.equity - r.account.rulebook.initial_balance
    )
    assert sum(r.account.pm_equity_pnl().values(), D("0")) == (
        r.account.equity - r.account.rulebook.initial_balance
    )
    assert r.account.costs > D("0")


# 08: Every new attempt counts held gross + unresolved broker + still queued pod increases.
def test_08_pretrade_reserves_current_inflight_and_queued_increases(tmp_path):
    r = make_run(tmp_path, max_gross_notional="600")
    signal(r, "first", [target("W028", 3)], 60)
    tick(r, "release", 360)
    observation_event(
        r,
        "extorder",
        "ORDER_INTENT",
        370,
        order_id="ext1",
        instrument=BTC_KEY,
        quantity="2",
        provider_sequence=1,
    )
    signal(r, "queue", [target("W042", 2, first_known_seconds=400)], 400)
    # Held 300 + unresolved external 200 + queued 200 = 700 > cap 600.
    snap = r.account.pm04_state["exposure"]
    assert D(snap["total_conservative_gross"]) >= D("700")
    assert r.account.quantities[BTC] == D("3")
    assert r.account.risk in (RiskState.RED, RiskState.HALT)


# 09: Independently approved pod stress budgets reject excessive *new* risk pre-fill.
def test_09_pod_pretrade_stress_budget_prevents_oversized_new_trade(tmp_path):
    from test_pm04_shadow import policy

    p = policy(max_gross_notional="2000")
    p["pods"]["W028"]["stress_loss"] = "5"
    r = ShadowRun(
        tmp_path,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    r.record(event("cfg", "PM04_CONFIG", {"policy": p}, 0))
    signal(r, "oversize", [target("W028", 3)], 60)
    tick(r, "due", 360)
    assert r.account.quantities == {}
    assert r.account.pm04_state["pod_stats"]["W028"]["state"] == "REDUCED"
    assert (
        "PRETRADE_POD_STRESS_BUDGET_REJECT" in r.account.pm04_state["pod_rejections"][0]["reasons"]
    )
    assert r.account.risk == RiskState.GREEN  # Independent pod veto, not account HALT.


# 10: A mark gap must cause autonomous reduction attempt even without another signal.
def test_10_gap_over_cap_zero_liquidity_latches_reduction_request(tmp_path):
    r = make_run(tmp_path, max_gross_notional="500")
    signal(r, "initial", [target("W028", 4)], 60)
    tick(r, "due", 360)
    tick(r, "gap", 420, mark="200", volume="0")
    s = r.account.pm04_state
    assert r.account.quantities[BTC] == D("4")
    assert D(s["pending_reductions"][BTC_KEY]) < D("0")
    assert s["risk_breaches"]
    assert r.account.risk in (RiskState.RED, RiskState.HALT)
    assert reopen(tmp_path).state() == r.state()


# 11: Drawdown suspension is per pod, not one shared pod kill-switch.
def test_11_pod_daily_loss_suspends_only_losing_pod(tmp_path):
    r = make_run(tmp_path, max_gross_notional="2000")
    signal(r, "hedged", [target("W028", 3), target("W042", -2)], 60)
    tick(r, "due", 360)
    tick(r, "loss", 420, mark="60")
    s = r.account.pm04_state["pod_stats"]
    assert s["W028"]["state"] == "SUSPENDED"
    assert s["W042"]["state"] not in ("SUSPENDED", "REDUCED")


# 12: Global HALT wins even against a later pod restoration attempt.
def test_12_account_halt_overrides_all_pods_and_restoration(tmp_path):
    r = make_run(tmp_path)
    r.record(event("halt", "HALT", {"reason": "operator"}, 10))
    with pytest.raises(ValueError, match="ACCOUNT_STOP"):
        r.record(
            event(
                "restore",
                "PM04_RESTORE",
                {
                    "pod": "W028",
                    "authorization_reference": "synthetic-control",
                },
                12,
            )
        )
    signal(r, "risk", [target("W042", 2)], 60)
    tick(r, "due", 360)
    assert r.account.risk == RiskState.HALT
    assert r.account.quantities == {}


# 13: Duplicate same-ID fill is idempotent and conflicting revision is rejected.
def test_13_duplicate_fill_and_conflicting_revision(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(
        r,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="2",
        provider_sequence=1,
    )
    row = {
        "schema": "pm04_broker_observation_v1",
        "evidence_id": "fill",
        "kind": "FILL",
        "order_id": "O1",
        "event_at": at(20),
        "first_known_at": at(20),
        "provider_sequence": 3,
        "cumulative_filled": "1",
    }
    r.record(event("fill", "PM04_BROKER", {"observation": row}, 20))
    before = r.account.pm04_state["broker"]["orders"]["O1"].copy()
    r.record(event("dup", "PM04_BROKER", {"observation": row}, 21))
    assert r.account.pm04_state["broker"]["orders"]["O1"] == before
    with pytest.raises(ValueError, match="CONFLICTING"):
        r.record(
            event(
                "revision", "PM04_BROKER", {"observation": row | {"cumulative_filled": "1.5"}}, 22
            )
        )


# 14: Out-of-order cumulative broker fills must only advance the max; never invent cash.
def test_14_out_of_order_fill_sequence_keeps_max_cumulative_only(tmp_path):
    r = make_run(tmp_path)
    observation_event(
        r,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="4",
        provider_sequence=1,
    )
    observation_event(
        r, "fill3", "PARTIAL_FILL", 30, order_id="O1", provider_sequence=7, cumulative_filled="3"
    )
    observation_event(
        r, "fill2", "PARTIAL_FILL", 31, order_id="O1", provider_sequence=4, cumulative_filled="2"
    )
    assert r.account.pm04_state["broker"]["orders"]["O1"]["cumulative_filled"] == "3"
    assert r.account.quantities == {}
    assert r.account.cash == r.account.rulebook.initial_balance


# 15: Cancel-then-fill leaves unresolved race, never implies flat.
def test_15_cancel_then_fill_race_requires_later_account_snapshot(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(
        r,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(r, "cancel", "CANCEL", 20, order_id="O1", provider_sequence=3)
    observation_event(
        r, "fill", "FILL", 30, order_id="O1", provider_sequence=2, cumulative_filled="1"
    )
    broker = r.account.pm04_state["broker"]
    assert broker["orders"]["O1"]["status"] == "CANCELED_PARTIAL"
    assert "CANCEL_FILL_RACE_UNRESOLVED" in broker["discrepancies"]
    assert r.account.quantities == {}


# 16: Stale/missing balance and reconnect gaps refuse any synthetic fresh-risk claim.
def test_16_missing_balance_or_reconnect_gap_denies_broker_ready(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(
        r, "positions", "POSITION_SNAPSHOT", 10, complete=True, positions={BTC_KEY: "0"}
    )
    assert not r.account.pm04_state["broker"]["ready"]
    assert "MISSING_BALANCE_SNAPSHOT" in r.account.pm04_state["broker"]["discrepancies"]
    observation_event(r, "reconnect", "RECONNECT", 20)
    assert "RECONNECT_POSITION_UNRESOLVED" in r.account.pm04_state["broker"]["discrepancies"]
    assert not r.account.pm04_state["broker"]["ready"]


# 17: Restart/crash recovery is hash identical with outstanding exposure and halt.
def test_17_restart_recovers_halt_pending_orders_and_sha(tmp_path):
    r = make_run(tmp_path, max_gross_notional="500")
    signal(r, "open", [target("W028", 4)], 60)
    tick(r, "due", 360)
    observation_event(
        r,
        "intent",
        "ORDER_INTENT",
        370,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="2",
        provider_sequence=1,
    )
    tick(r, "gap", 420, mark="200", volume="0")
    before = deepcopy(r.state())
    head = r.ledger.read()[-1]["sha"]
    recovered = reopen(tmp_path)
    assert recovered.state() == before
    assert recovered.ledger.read()[-1]["sha"] == head
    assert recovered.account.quantities[BTC] == D("4")
    assert recovered.account.risk in (RiskState.RED, RiskState.HALT)


# 18: Replaying an unchanged input through 3 policies yields deterministic SHA.
def test_18_identical_input_three_policy_comparison_and_replay(tmp_path):
    from test_pm04_compare import _spec

    spec = _spec()
    first = cli_execute(spec, tmp_path)
    second = cli_execute(spec, tmp_path)
    assert first == second
    assert Path(first["path"]).exists()
    assert first["sha"] == digest(
        __import__("json").loads(Path(first["path"]).read_text(encoding="utf-8"))
    )
    assert set(
        __import__("json").loads(Path(first["path"]).read_text(encoding="utf-8"))["comparison"]
    ) == {"immediate", "batched", "asymmetric"}
