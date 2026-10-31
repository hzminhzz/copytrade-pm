"""PM-04 acceptance supplements: fault injection, pod independence and source integrity."""

from copy import deepcopy
from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import RiskState
from copytrade_pm.pm03_run import ShadowRun
from test_pm03_extended import BTC, T, book
from test_pm04_shadow import BTC_KEY, SHA, at, engine, event, policy, signal, target, tick
from test_pm04_acceptance import make_run, observation_event, reopen


def test_crash_after_immutable_append_recovers_exact_shadow_state(tmp_path, monkeypatch):
    r = make_run(tmp_path)
    before = deepcopy(r.account.snapshot())
    original = r.ledger.append

    def append_then_die(sealed, *, expected_head):
        original(sealed, expected_head=expected_head)
        raise RuntimeError("SYNTHETIC_CRASH_AFTER_COMMIT")

    monkeypatch.setattr(r.ledger, "append", append_then_die)
    with pytest.raises(RuntimeError, match="CRASH_AFTER_COMMIT"):
        signal(r, "queued", [target("W028", 3)], 60)
    assert r.account.snapshot() == before
    recovered = reopen(tmp_path)
    assert recovered.state()["last_processed_event"] == "pm04-queued"
    assert recovered.account.pm04_state["batch_open"][BTC_KEY] == at(60)
    tick(recovered, "fill", 360)
    assert recovered.account.quantities[BTC] == D("3")
    recovered.verify_checkpoint(recovered.checkpoint())


def test_new_pod_stress_veto_keeps_other_pod_authorized(tmp_path):
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
    r.record(event("config", "PM04_CONFIG", {"policy": p}, 0))
    signal(r, "two-pods", [target("W028", 3), target("W042", 2)], 60)
    tick(r, "release", 360)
    assert r.account.pm04_state["pod_stats"]["W028"]["state"] == "REDUCED"
    assert r.account.pm04_state["pod_stats"]["W042"]["state"] == "ACTIVE"
    assert r.account.quantities[BTC] == D("2")
    assert r.account.pm_quantities["W042"][BTC] == D("2")
    assert r.account.risk == RiskState.GREEN


def test_instrument_concentration_veto_below_total_gross_cap(tmp_path):
    r = make_run(tmp_path, max_gross_notional="5000", max_instrument_fraction_equity="0.01")
    signal(r, "large-instrument", [target("W028", 3)], 60)
    tick(r, "due", 360)
    assert r.account.quantities == {}
    assert "PRETRADE_CONCENTRATION_REJECT" in r.account.risk_reasons


def test_account_floor_headroom_overrides_large_approved_pod_budget(tmp_path):
    p = policy(max_gross_notional="5000", max_stress_loss="10000")
    p["pods"]["W028"]["stress_loss"] = "400"
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
    r.record(event("config", "PM04_CONFIG", {"policy": p}, 0))
    signal(r, "risk", [target("W028", 3)], 60)
    tick(r, "due", 360, shocks=[{BTC_KEY: "-0.99"}, {BTC_KEY: "0.99"}])
    assert r.account.quantities == {}
    assert "PRETRADE_CONTRACTUAL_HEADROOM_REJECT" in r.account.risk_reasons


def test_broker_position_balance_fee_synthetic_snapshots_are_not_fills(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(
        r, "position", "POSITION_SNAPSHOT", 10, complete=True, positions={BTC_KEY: "0"}
    )
    observation_event(r, "balance", "BALANCE_SNAPSHOT", 11, balance="10000", equity="10000")
    observation_event(r, "fee", "FEES_FUNDING", 12, fee_total="0", funding_total="0")
    snap = deepcopy(r.account.snapshot())
    assert r.account.pm04_state["broker"]["ready"]
    assert r.account.quantities == {}
    assert r.account.cash == r.account.rulebook.initial_balance
    assert snap["pm04"]["broker"]["ready"]
    # The externally supplied read-only reconciliation cannot itself execute.
    assert snap["quantities"] == {}


def test_stale_broker_balance_disables_new_risk_even_if_position_still_matches(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(
        r, "position", "POSITION_SNAPSHOT", 10, complete=True, positions={BTC_KEY: "0"}
    )
    observation_event(r, "balance", "BALANCE_SNAPSHOT", 11, balance="10000", equity="10000")
    observation_event(r, "fee", "FEES_FUNDING", 12, fee_total="0", funding_total="0")
    tick(r, "late", 500)
    assert "STALE_BALANCE_SNAPSHOT" in r.account.pm04_state["broker"]["discrepancies"]
    assert not r.account.pm04_state["broker"]["ready"]


def test_partial_cancel_reserves_inflight_until_later_complete_snapshot(tmp_path):
    r = make_run(tmp_path)
    observation_event(
        r,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="5",
        provider_sequence=1,
    )
    observation_event(
        r, "partial", "PARTIAL_FILL", 20, order_id="O1", cumulative_filled="2", provider_sequence=2
    )
    observation_event(r, "cancel", "CANCEL", 30, order_id="O1", provider_sequence=3)
    tick(r, "mark", 31)
    assert D(r.account.pm04_state["exposure"]["pending_inflight_gross"]) == D("300")
    observation_event(
        r, "position", "POSITION_SNAPSHOT", 40, complete=True, positions={BTC_KEY: "0"}
    )
    assert D(r.account.pm04_state["exposure"]["pending_inflight_gross"]) == D("0")
    assert r.account.cash == r.account.rulebook.initial_balance


def test_funding_loss_pod_suspension_requests_unfilled_exit_without_broker_fill(tmp_path):
    r = make_run(tmp_path)
    signal(r, "open", [target("W028", 2)], 60)
    tick(r, "due", 360)
    r.record(
        event(
            "fund-loss",
            "FUNDING",
            {
                "amount": "-90",
                "allocated": {"W028": "-90"},
            },
            370,
        )
    )
    assert r.account.pm04_state["pod_stats"]["W028"]["state"] == "SUSPENDED"
    assert D(r.account.pm04_state["pending_reductions"][BTC_KEY]) < 0
    assert r.account.quantities[BTC] == D("2")
    assert reopen(tmp_path).state() == r.state()


def test_new_challenge_stage_halts_until_pm04_budgets_reauthorized(tmp_path):
    r = make_run(tmp_path, max_gross_notional="5000")
    signal(r, "open", [target("W028", 3)], 60)
    tick(r, "due", 360)
    tick(r, "profit", 420, mark="450")
    assert r.account.stage_passed
    next_book = book(stage="evaluation2", version="synthetic-stage2")
    r.record(event("stage", "STAGE", {"next_rulebook": next_book.to_dict()}, 430))
    assert r.account.rulebook.sha == next_book.sha
    assert r.account.risk == RiskState.HALT
    assert "PM04_POLICY_RULEBOOK_CHANGED_REAUTH_REQUIRED" in r.account.risk_reasons


def test_unknown_quote_or_account_durably_halts_even_without_executable_order(tmp_path):
    r = make_run(tmp_path)
    signal(r, "long", [target("W028", 1)], 60)
    tick(r, "due", 360)
    row = engine(420)
    row["observations"] = []
    r.record(event("missing", "PM04_TICK", row, 420))
    assert r.account.risk == RiskState.HALT
    assert r.account.quantities[BTC] == D("1")
    assert r.account.pm04_state["blocked_observations"]
    assert reopen(tmp_path).state() == r.state()
