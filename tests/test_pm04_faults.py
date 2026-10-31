"""Additional PM-04 fault/recovery and invalid-source integration cases."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import RiskState, digest
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
from test_pm04_acceptance import observation_event, reopen


def test_cancel_after_complete_snapshot_releases_only_verified_remaining(tmp_path):
    r = make_run(tmp_path)
    observation_event(
        r,
        "int",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(r, "can", "CANCEL", 20, order_id="O1", provider_sequence=2)
    assert r.account.pm04_state["exposure"]["pending_inflight_gross"] == "0"
    # A later fully observed account position proves no additional broker fill.
    observation_event(r, "pos", "POSITION_SNAPSHOT", 30, complete=True, positions={BTC_KEY: "0"})
    assert "CANCEL_FILL_RACE_UNRESOLVED" not in r.account.pm04_state["broker"]["discrepancies"]
    assert r.account.pm04_state["exposure"]["pending_inflight_gross"] == "0"


def test_older_provider_snapshot_cannot_override_newer_reconciliation(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(r, "fresh", "POSITION_SNAPSHOT", 40, complete=True, positions={BTC_KEY: "0"})
    old = {
        "schema": "pm04_broker_observation_v1",
        "evidence_id": "late-old",
        "kind": "POSITION_SNAPSHOT",
        "event_at": at(20),
        "first_known_at": at(50),
        "positions": {BTC_KEY: "99"},
        "complete": True,
    }
    r.record(event("old", "PM04_BROKER", {"observation": old}, 50))
    snap = r.account.pm04_state["broker"]["position_snapshot"]
    assert snap["positions"][BTC_KEY] == "0"
    assert "POSITION_MISMATCH" not in r.account.pm04_state["broker"]["discrepancies"]


def test_unknown_external_order_halts_and_never_fabricates_position(tmp_path):
    r = make_run(tmp_path)
    observation_event(r, "unknown", "ACK", 10, order_id="not-ours", provider_sequence=1)
    assert r.account.risk == RiskState.HALT
    assert r.account.quantities == {}
    assert r.account.cash == r.account.rulebook.initial_balance
    assert "UNKNOWN_ORDER" in r.account.pm04_state["broker"]["discrepancies"]


def test_broker_funding_mismatch_halts_account_without_booked_funding(tmp_path):
    r = make_run(tmp_path, broker_required=True)
    observation_event(r, "bad-funding", "FEES_FUNDING", 10, fee_total="0", funding_total="100")
    assert "FEES_FUNDING_MISMATCH" in r.account.pm04_state["broker"]["discrepancies"]
    assert r.account.risk == RiskState.HALT
    assert r.account.funding == D("0")


def test_stale_market_observation_persists_halt_without_repricing(tmp_path):
    r = make_run(tmp_path)
    signal(r, "entry", [target("W028", 2)], 60)
    tick(r, "release", 360)
    before = r.account.quantities[BTC]
    stale = engine(360, mark="1")
    r.record(event("stale", "PM04_TICK", stale, 720))
    assert r.account.quantities[BTC] == before
    assert r.account.marks[BTC] == D("100")
    assert r.account.risk == RiskState.HALT
    assert reopen(tmp_path).state() == r.state()


def test_late_batch_does_not_execute_stale_pod_signal_or_erase_prior_evidence(tmp_path):
    r = make_run(tmp_path)
    signal(r, "entry", [target("W028", 3)], 60)
    tick(r, "late-batch", 361)
    assert r.account.quantities == {}
    assert r.account.pm04_state["batch_open"] == {}
    assert r.account.pm04_state["expired_targets"]
    assert reopen(tmp_path).state() == r.state()


def test_pod_stress_veto_latches_and_explicit_restore_does_not_change_account(tmp_path):
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
    assert r.account.pm04_state["pod_stats"]["W028"]["state"] == "REDUCED"
    tick(r, "quiet", 420)
    assert r.account.pm04_state["pod_stats"]["W028"]["state"] == "REDUCED"
    before = r.account.snapshot()["cash"]
    r.record(
        event(
            "restore",
            "PM04_RESTORE",
            {
                "pod": "W028",
                "authorization_reference": "synthetic signed operator reference",
            },
            430,
        )
    )
    assert r.account.snapshot()["cash"] == before
    assert r.account.pm04_state["pod_stats"]["W028"]["state"] == "RESTORED"


def test_immutable_ledger_tail_corruption_halts_read_only_restore(tmp_path):
    r = make_run(tmp_path)
    signal(r, "entry", [target("W028", 3)], 60)
    ledger_path = tmp_path / "pm04-run" / "events.jsonl"
    original = ledger_path.read_bytes()
    ledger_path.write_bytes(original[:-1])
    with pytest.raises(ValueError, match="TRUNCATED|CORRUPT"):
        reopen(tmp_path)
    # Tests own tmp_path only; restore synthetic test fixture to confirm recovery.
    ledger_path.write_bytes(original)
    assert reopen(tmp_path).state() == r.state()


def test_copytrade_pr_compare_cache_never_masks_missing_immutable_event_ledger(tmp_path):
    from test_pm04_compare import _spec
    from copytrade_pm.pm04_compare import compare_pm04_policies

    spec = _spec()
    report = compare_pm04_policies(spec, tmp_path)
    assert report["report_sha"] == digest({k: v for k, v in report.items() if k != "report_sha"})
    ledger = tmp_path / "runs" / "pm04-compare-immediate" / "events.jsonl"
    ledger.unlink()
    with pytest.raises(ValueError, match="MISSING|REPLAY|EVIDENCE|LEDGER"):
        compare_pm04_policies(spec, tmp_path)
