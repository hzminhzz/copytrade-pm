"""Fault injection, no-silent-risk and security regression suite for PM-03."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import Account, RiskState
from copytrade_pm.pm03_attribution import IntendedVirtualBooks, explain_economics
from copytrade_pm.pm03_execution import execute_targets
from copytrade_pm.pm03_memory import Ledger
from copytrade_pm.pm03_run import ShadowRun
from test_pm03_extended import T, BTC, HIP, SHA, book, cost, quote, event, synthetic_run
from test_pm03_scenarios import steps
from copytrade_pm.pm03_stress import compare_policies


def test_cash_attribution_exact_under_netting_fees_and_pm_hedges():
    a = Account.start(book(), T)
    a.internal_cross(BTC, "long", "short", D("2"), D("100"))
    a.simulate_fill(BTC, D("1"), D("100.01"), D("0.03"), accepted=True, allocated={"long": D("1")})
    a.mark({BTC: D("110")}, "2026-10-31T04:05:00+00:00")
    a.verify()
    intent = IntendedVirtualBooks()
    intent.mark_and_target({"long": {BTC: D("3")}, "short": {BTC: D("-2")}}, {BTC: D("100")})
    intent.mark_and_target({"long": {BTC: D("3")}, "short": {BTC: D("-2")}}, {BTC: D("110")})
    economic = explain_economics(a, intent, D("0.01"))
    assert economic["source_wallet_pnl"] is None
    assert D(economic["consolidated_account_pnl"]) == (
        D(economic["virtual_intended_pm_pnl"])
        + D(economic["central_overlay_pnl"])
        - D(economic["external_fees"])
        - D(economic["execution_price_drag"])
        + D(economic["funding"])
    )
    assert D(economic["reconciliation_rounding_residual"]) == 0


def test_rejected_reductions_remain_open_not_assumed_flat():
    a = Account.start(book(), T)
    a.simulate_fill(BTC, D("2"), D("100"), D("0"), accepted=True, allocated={"A": D("2")})
    a.risk = RiskState.RED
    report = execute_targets(
        a,
        {"A": {BTC: D("0")}},
        {BTC: quote(volume="0")},
        cost(),
        decision_at=T,
        hypothetical_fill_at="2026-10-31T04:00:01+00:00",
        permitted=True,
    )
    assert a.quantities[BTC] == D("2")
    assert report["remaining"][BTC.key] == "-2"
    assert "NO_EXECUTION_CAPACITY:" + BTC.key in report["rejections"]
    assert a.risk == RiskState.RED


def test_futures_instrument_namespaces_not_interchangeable():
    a = Account.start(book(), T)
    a.simulate_fill(BTC, D("2"), D("100"), D("0"), accepted=True, allocated={"A": D("2")})
    a.simulate_fill(HIP, D("-2"), D("100"), D("0"), accepted=True, allocated={"B": D("-2")})
    assert a.quantities[BTC] == D("2") and a.quantities[HIP] == D("-2")
    assert a.external_targets(a.pm_quantities) == {BTC: D("2"), HIP: D("-2")}
    assert a.gross() == D("400")


def test_process_crash_after_fsynced_append_restores_same_state(tmp_path, monkeypatch):
    run = synthetic_run(tmp_path)
    prior = run.state()
    real_append = run.ledger.append

    def crash_after_append(e, **kw):
        real_append(e, **kw)
        raise RuntimeError("SIMULATED_PROCESS_CRASH")

    monkeypatch.setattr(run.ledger, "append", crash_after_append)
    with pytest.raises(RuntimeError, match="SIMULATED_PROCESS_CRASH"):
        run.record(event("failure1", "HALT", {"reason": "risk-incident"}))
    assert run.state() == prior
    restored = synthetic_run(tmp_path)
    assert restored.account.risk == RiskState.HALT
    assert restored.last_event_id == "failure1"
    assert restored.account.halt_reason == "risk-incident"
    with pytest.raises(ValueError, match="CONCURRENT_LEDGER_ADVANCE"):
        restored.ledger.append(
            event("late", "HALT", {"reason": "second"}),
            expected_head="0" * 64,
        )


def test_duplicate_after_crash_never_applies_fill_twice(tmp_path):
    run = synthetic_run(tmp_path)
    ev = event("f1", "FUNDING", {"amount": "2.5", "allocated": {"A": "2.5"}})
    first = run.record(ev)
    assert first["account"]["balance"] == "10002.5"
    restored = synthetic_run(tmp_path)
    assert restored.record(ev) == first
    assert restored.account.funding == D("2.5")
    assert len(restored.ledger.read()) == 1


def test_unknown_account_state_persists_after_restart_and_is_not_flat(tmp_path):
    r = synthetic_run(tmp_path)
    r.record(event("u1", "MARK", {"state_known": False, "prices": {}}))
    assert r.account.risk == RiskState.HALT
    assert r.account.halt_reason == "UNKNOWN_ACCOUNT_OBSERVATION"
    restart = synthetic_run(tmp_path)
    assert restart.account.risk == RiskState.HALT
    with pytest.raises(ValueError, match="MISSING_MANUAL"):
        restart.record(event("u2", "MANUAL_RESET", {"reason": "silent"}))


def test_old_observation_cannot_move_back_in_time():
    a = Account.start(book(), T)
    a.mark({}, "2026-10-31T05:00:00+00:00")
    with pytest.raises(ValueError, match="BACKDATED_MARK"):
        a.mark({}, T)


def test_malformed_ledger_tail_and_conflict_not_repaired(tmp_path):
    ledger = Ledger(tmp_path / "run")
    ledger.append(event("x1", "HALT", {"reason": "alert"}))
    with ledger.events_path.open("ab") as f:
        f.write(b'{"partial":')
    with pytest.raises(ValueError, match="TRUNCATED_EVENT"):
        ledger.read()
    with pytest.raises(ValueError, match="TRUNCATED_EVENT"):
        ledger.append(event("x2", "HALT", {"reason": "retry"}))


def test_prospective_research_flag_cannot_promote_to_fill(tmp_path):
    r = ShadowRun(
        tmp_path,
        run_id="s1",
        rulebook=book(),
        started_at=T,
        mode="PROSPECTIVE_OBSERVED",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    payload = {
        "proposed": {"A": {BTC.key: "1"}},
        "observations": [
            {
                "instrument": BTC.key,
                "event_at": T,
                "first_known_at": T,
                "mark": "100",
                "volume_base": "100",
                "quality": "SYNTHETIC",
                "supported": True,
            }
        ],
        "shocks": [{BTC.key: "-0.01"}],
        "evidence": {
            "trusted": True,
            "account_state_known": True,
            "market_state_known": True,
            "market_coverage_valid": True,
            "pending_unknown_orders": False,
            "input_status": "PROSPECTIVE_OBSERVED",
            "pm02_qualified": True,
        },
        "costs": {
            "fee_bps": "2",
            "full_spread_bps": "4",
            "slippage_bps": "1",
            "impact_bps_at_full_participation": "4",
            "max_participation": "0.1",
            "max_age_seconds": 300,
            "latency_seconds": 1,
        },
    }
    ev = event("d1", "DECISION", payload, fill_at="2026-10-31T04:00:01+00:00")
    r.record(ev)
    assert r.account.quantities == {}
    assert r.account.cash == D("10000")


def test_corr_stress_and_hindsight_remain_synthetic():
    result = compare_policies(
        rulebook=book(),
        started_at=T,
        steps=steps(),
        cost_model=cost(),
        historical_scores={"A": D("100"), "B": D("-50")},
    )
    for name, report in result["comparison"].items():
        economic = report["economic_attribution"]
        assert economic is not None
        assert economic["not_follower_execution_qualification"]
        assert economic["source_wallet_pnl"] is None
        assert D(economic["reconciliation_rounding_residual"]) == 0
        assert len(report["equity"]) == 3
    assert result["label"] == "RESEARCH_SYNTHETIC_NOT_VALIDATED_PASS_PROBABILITY"


def test_late_funding_requires_explicit_utc_reset_and_audited_balance(tmp_path):
    run = synthetic_run(tmp_path)
    late = event(
        "overnight_funding",
        "FUNDING",
        {"amount": "-3", "allocated": {"A": "-3"}},
        at="2026-11-01T00:00:03+00:00",
    )
    with pytest.raises(ValueError, match="MISSING_DAILY_RESET_MARK"):
        run.record(late)
    assert run.ledger.read() == []
    run.record(
        event(
            "reset_mark",
            "MARK",
            {"state_known": True, "prices": {}},
            at="2026-11-01T00:00:01+00:00",
        )
    )
    state = run.record(late)
    assert state["account"]["daily_key"] == "2026-11-01"
    assert run.account.balance == D("9997")
    assert run.account.daily_start_balance == D("10000")
    assert synthetic_run(tmp_path).state() == state


def test_reset_only_explicit_event_and_restart_roundtrip(tmp_path):
    run = synthetic_run(tmp_path)
    run.record(event("h1", "HALT", {"reason": "stale-quote"}))
    state = run.record(
        event(
            "signed-reset",
            "MANUAL_RESET",
            {"operator_id": "unit-test-operator", "authorization_reference": "synthetic-signoff"},
            at="2026-10-31T04:00:04+00:00",
        )
    )
    assert state["account"]["risk"] == "GREEN"
    assert len(run.ledger.read()) == 2
    assert run.ledger.read()[-1]["event"]["payload"]["tool_trace"]["action"] == (
        "pm03.shadow.manual_reset"
    )
    assert synthetic_run(tmp_path).state() == state


def test_intraday_trailing_hwm_floor_caps_then_permanent_breach():
    a = Account.start(
        book(static_loss=None, trailing_loss=D("800"), trailing_cap=D("10000")),
        T,
    )
    a.simulate_fill(BTC, D("10"), D("100"), D("0"), accepted=True, allocated={"A": D("10")})
    a.mark({BTC: D("150")}, "2026-10-31T04:00:30+00:00")
    assert a.floor()[1]["trailing"] == D("9700")
    a.mark({BTC: D("180")}, "2026-10-31T04:00:40+00:00")
    assert a.high_water == D("10800")
    assert a.floor()[1]["trailing"] == D("10000")
    a.mark({BTC: D("90")}, "2026-10-31T04:00:50+00:00")
    assert a.breached and a.risk == RiskState.HALT
    a.mark({BTC: D("220")}, "2026-10-31T04:01:00+00:00")
    assert a.risk == RiskState.HALT and a.breached


def test_halt_mid_batch_does_not_rewrite_requested_unfilled_as_executed():
    a = Account.start(book(static_loss=D("1")), T)
    very_expensive = type(cost())(D("1000"), D("0"), D("0"), D("0"), D("1"), 300, 1)
    report = execute_targets(
        a,
        {"A": {BTC: D("1"), HIP: D("1")}},
        {BTC: quote(mark="100", volume="10"), HIP: quote(HIP, mark="50", volume="10")},
        very_expensive,
        decision_at=T,
        hypothetical_fill_at="2026-10-31T04:00:01+00:00",
        permitted=True,
    )
    assert report["status"] == "HALT_DURING_HYPOTHETICAL_EXECUTION"
    assert len(report["fills"]) == 1
    assert BTC in a.quantities
    assert HIP not in a.quantities
    assert report["unprocessed_instruments"] == [HIP.key]
    assert a.breached and a.risk == RiskState.HALT
    a.verify()


def test_secret_field_refused_before_persistent_ledger_write(tmp_path):
    ledger = Ledger(tmp_path / "private-run")
    secret = event("secret", "HALT", {"nested": {"api_key": "do-not-persist"}})
    with pytest.raises(ValueError, match="SENSITIVE_FIELD_IN_RESEARCH_LEDGER"):
        ledger.append(secret)
    assert ledger.read() == []


def test_external_fee_cannot_be_assigned_to_opposing_internal_cross_leg():
    a = Account.start(book(), T)
    with pytest.raises(ValueError, match="EXTERNAL_FILL_MIXED_SIGN_ALLOCATION"):
        a.simulate_fill(
            BTC, D("1"), D("100"), D("0.2"), accepted=True, allocated={"A": D("2"), "B": D("-1")}
        )
    assert a.quantities == {} and a.costs == 0 and not a.pm_quantities
    a.internal_cross(BTC, "A", "B", D("1"), D("100"))
    a.simulate_fill(BTC, D("1"), D("100"), D("0.2"), accepted=True, allocated={"A": D("1")})
    assert a.pm_costs["A"] == D("0.2")
    assert a.pm_costs["B"] == 0
    a.verify()


def test_offsetting_pod_targets_require_separate_hedge_break_loss_assumption():
    from copytrade_pm.pm03_risk import RiskEvidence, RiskPolicy, classify

    a = Account.start(book(), T)
    pms = {"A": {BTC: D("3")}, "B": {BTC: D("-2")}}
    missing = RiskEvidence(True, True, True, True, False, "RESEARCH_SYNTHETIC", False)
    rejected = classify(a, pms, {BTC: D("100")}, ({BTC: D("-0.1")},), missing, RiskPolicy())
    assert "MISSING_HEDGE_BREAK_STRESS" in rejected["reason_codes"]
    assert not rejected["approved_new_risk"]
    b = Account.start(book(), T)
    observed = RiskEvidence(
        True, True, True, True, False, "RESEARCH_SYNTHETIC", False, hedge_break_loss=D("25")
    )
    allowed = classify(b, pms, {BTC: D("100")}, ({BTC: D("-0.1")},), observed, RiskPolicy())
    assert allowed["approved_new_risk"]
    assert allowed["worst_stress_loss"] == "35.0"
