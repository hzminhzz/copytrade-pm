"""Adversarial PM-03 accounting, execution and replay tests (synthetic only)."""

from decimal import Decimal as D
import json

import pytest

from copytrade_pm.pm03_account import Account, Instrument, RiskState, Rulebook, digest
from copytrade_pm.pm03_execution import CostModel, MarketObservation, execute_targets
from copytrade_pm.pm03_risk import RiskEvidence, RiskPolicy, classify
from copytrade_pm.pm03_rules import propr_rulebook
from copytrade_pm.pm03_memory import Event
from copytrade_pm.pm03_run import ShadowRun

T = "2026-10-31T04:00:00+00:00"
NEXT = "2026-11-01T00:00:00+00:00"
BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
HIP = Instrument("hyperliquid", "mainnet:perp:xyz", "BTC")
SHA = digest("synthetic artifact")


def book(**kw):
    opts = {
        "program": "SYNTHETIC",
        "stage": "evaluation",
        "source": "synthetic-test",
        "observed_at": T,
        "version": "synthetic-v1",
        "timezone": "UTC",
        "initial_balance": D("10000"),
        "profit_target": D("1000"),
        "daily_loss": None,
        "daily_loss_rate": D("0.03"),
        "static_loss": D("600"),
        "trailing_loss": None,
        "confirmed": True,
        "permitted": (BTC, HIP),
        "max_gross_leverage": D("2"),
    }
    opts.update(kw)
    return Rulebook(**opts)


def quote(k=BTC, *, mark="100", volume="100", known=T, supported=True):
    return MarketObservation(k, T, known, D(mark), D(volume), supported=supported)


def cost():
    return CostModel(D("2"), D("4"), D("1"), D("4"), D("0.1"), 300, 1)


def event(event_id, kind, payload, *, at=T, fill_at=None):
    return Event(
        event_id,
        T,
        T,
        at,
        fill_at or at,
        kind,
        {"run_id": "s1", "rulebook_sha": book().sha, "input": payload},
        SHA,
    )


def test_official_rules_are_public_not_account_authorization():
    for program, stage, target, daily, static, trailing in (
        ("classic_1step", "evaluation", "1000", "0.03", "600", None),
        ("turbo_1step", "evaluation", "900", "0.03", "300", None),
        ("classic_2step", "step1", "500", "0.05", None, "800"),
        ("classic_2step", "step2", "1000", "0.05", None, "800"),
        ("classic_2step", "funded", None, "0.05", None, "800"),
    ):
        r = propr_rulebook(program, stage, D("10000"), observed_at=T)
        assert r.profit_target == (D(target) if target is not None else None)
        assert r.daily_loss_rate == D(daily)
        assert r.static_loss == (D(static) if static else None)
        assert r.trailing_loss == (D(trailing) if trailing else None)
        assert not r.confirmed and not r.account_terms_confirmed
        if trailing:
            assert r.trailing_cap == D("10000")
        a = Account.start(r, T)
        assert not a.evaluate(
            {"a": {BTC: D("1")}}, {BTC: D("100")}, trusted=True, market_known=True
        )["allowed"]


def test_daily_reset_ignores_floating_and_permanent_intraday_breach():
    a = Account.start(book(), T)
    a.simulate_fill(BTC, D("10"), D("100"), D("0"), accepted=True, allocated={"A": D("10")})
    a.mark({BTC: D("110")}, "2026-10-31T23:00:00+00:00")
    assert a.balance == D("10000") and a.equity == D("10100")
    a.mark({BTC: D("110")}, NEXT)
    assert a.daily_start_balance == D("10000")
    assert a.floor()[1]["daily"] == D("9700")
    a.mark({BTC: D("60")}, "2026-11-01T00:01:00+00:00")
    assert a.breached
    a.mark({BTC: D("200")}, "2026-11-01T00:02:00+00:00")
    assert a.breached and a.risk == RiskState.HALT
    with pytest.raises(ValueError, match="BREACH_PERSISTS"):
        a.manual_reset(authorization="signed", as_of="2026-11-01T00:03:00+00:00")


def test_realized_cash_cost_funding_and_pm_reconciliation():
    a = Account.start(book(), T)
    a.simulate_fill(BTC, D("10"), D("100"), D("1"), accepted=True, allocated={"A": D("10")})
    a.mark({BTC: D("110")}, "2026-10-31T04:01:00+00:00")
    assert a.balance == D("9999")
    assert a.unrealized_pnl == D("100")
    a.simulate_fill(BTC, D("-5"), D("105"), D("0.5"), accepted=True, allocated={"A": D("-5")})
    a.post_funding(D("-2"), {"A": D("-2")})
    a.mark({BTC: D("110")}, "2026-10-31T04:02:00+00:00")
    assert a.realized_pnl == D("25")
    assert a.balance == D("10021.5")
    assert a.equity == D("10071.5")
    a.verify()
    assert a.pm_equity_pnl()["A"] == D("71.5")
    restored = Account.from_snapshot(a.rulebook, a.snapshot())
    assert restored.snapshot() == a.snapshot()
    with pytest.raises(ValueError, match="MISMATCH"):
        Account.from_snapshot(book(static_loss=D("500")), a.snapshot())


def test_internal_cross_partial_liquidity_and_unfillable_reduction():
    a = Account.start(book(), T)
    inputs = {"A": {BTC: D("3")}, "B": {BTC: D("-2")}}
    result = execute_targets(
        a,
        inputs,
        {BTC: quote(volume="5")},
        cost(),
        decision_at=T,
        hypothetical_fill_at="2026-10-31T04:00:02+00:00",
        permitted=True,
    )
    assert result["status"] == "PARTIAL"
    assert D(result["fills"][0]["quantity"]) == D("0.5")
    assert result["remaining"][BTC.key] == "0.5"
    assert sum((D(x["quantity"]) for x in result["internal_crosses"]), D("0")) == D("2")
    assert a.quantities[BTC] == D("0.5")
    a.verify()
    before = a.snapshot()
    no_cap = execute_targets(
        a,
        {"A": {}, "B": {}},
        {BTC: quote(volume="0")},
        cost(),
        decision_at="2026-10-31T04:00:03+00:00",
        hypothetical_fill_at="2026-10-31T04:00:04+00:00",
        permitted=True,
    )
    assert no_cap["rejections"] and a.quantities[BTC] == D("0.5")
    assert a.snapshot() != before  # mark timestamp changes, not actual filled quantity


def test_unknown_quote_stale_and_future_knowledge_fail_closed():
    a = Account.start(book(), T)
    res = execute_targets(
        a,
        {"A": {BTC: D("1")}},
        {},
        cost(),
        decision_at=T,
        hypothetical_fill_at="2026-10-31T04:00:01+00:00",
        permitted=True,
    )
    assert res["status"] == "BLOCKED" and a.quantities == {}
    a = Account.start(book(), T)
    with pytest.raises(ValueError, match="POINT_IN_TIME"):
        execute_targets(
            a,
            {"A": {BTC: D("1")}},
            {BTC: quote(known="2026-10-31T04:02:00+00:00")},
            cost(),
            decision_at=T,
            hypothetical_fill_at="2026-10-31T04:00:01+00:00",
            permitted=True,
        )


def test_risk_states_and_unknown_nonpromotion():
    q = {BTC: D("100")}
    proposal = {"A": {BTC: D("10")}}
    evidence = RiskEvidence(True, True, True, True, False, "RESEARCH_SYNTHETIC", False)
    for shock, expected in [
        ("-0.03", RiskState.GREEN),
        ("-0.075", RiskState.YELLOW),
        ("-0.125", RiskState.ORANGE),
        ("-0.20", RiskState.RED),
        ("-0.26", RiskState.HALT),
    ]:
        a = Account.start(book(), T)
        decision = classify(a, proposal, q, ({BTC: D(shock)},), evidence, RiskPolicy())
        assert a.risk == expected
        if expected in (RiskState.RED, RiskState.HALT):
            assert not decision["approved_new_risk"]
    a = Account.start(book(), T)
    bad = RiskEvidence(True, False, True, False, True, "PROSPECTIVE_OBSERVED", False)
    decision = classify(a, proposal, q, ({BTC: D("-0.05")},), bad, RiskPolicy())
    assert not decision["approved_new_risk"]
    assert decision["approved"] == {}


def synthetic_run(path):
    return ShadowRun(
        path,
        run_id="s1",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )


def test_replay_latched_halt_crash_restart_checkpoint_and_revisions(tmp_path):
    run = synthetic_run(tmp_path)
    halting = event("e1", "HALT", {"reason": "stale-source"})
    state = run.record(halting)
    assert state["account"]["risk"] == "HALT"
    cp = run.checkpoint()
    again = synthetic_run(tmp_path)
    assert again.state() == state
    assert again.verify_checkpoint(cp) == state
    assert again.record(halting) == state
    assert len(again.ledger.read()) == 1
    with pytest.raises(ValueError, match="CONFLICTING"):
        again.record(event("e1", "HALT", {"reason": "rewritten"}))
    with pytest.raises(ValueError, match="CROSS_RUN"):
        again.record(
            Event(
                "e2",
                T,
                T,
                T,
                T,
                "MARK",
                {
                    "run_id": "other",
                    "rulebook_sha": book().sha,
                    "input": {"state_known": True, "prices": {}},
                },
                SHA,
            )
        )
    with pytest.raises(ValueError, match="IMMUTABLE"):
        ShadowRun(
            tmp_path,
            run_id="s1",
            rulebook=book(static_loss=D("400")),
            started_at=T,
            mode="RESEARCH_SYNTHETIC",
            pm01_sha=SHA,
            pm02_sha=SHA,
            market_manifest_sha=SHA,
        )
    row = json.loads((tmp_path / "s1" / f"{cp}.checkpoint.json").read_text())
    row["payload"]["state"]["account"]["risk"] = "GREEN"
    (tmp_path / "s1" / f"{cp}.checkpoint.json").write_text(json.dumps(row))
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        again.verify_checkpoint(cp)


def test_replay_decision_partial_fill_recovered_as_same_hash(tmp_path):
    run = synthetic_run(tmp_path)
    payload = {
        "proposed": {"A": {BTC.key: "3"}, "B": {BTC.key: "-2"}},
        "observations": [
            {
                "instrument": BTC.key,
                "event_at": T,
                "first_known_at": T,
                "mark": "100",
                "volume_base": "10",
                "quality": "OHLCV_1M_PROXY",
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
            "input_status": "RESEARCH_SYNTHETIC",
            "pm02_qualified": False,
            "hedge_break_loss": "5",
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
    first = run.record(event("d1", "DECISION", payload, fill_at="2026-10-31T04:00:01+00:00"))
    assert first["account"]["quantities"][BTC.key] == "1"
    assert first["account"]["pm_quantities"]["A"][BTC.key] == "3"
    second = synthetic_run(tmp_path)
    assert second.state() == first
    assert run.checkpoint() == second.checkpoint()
