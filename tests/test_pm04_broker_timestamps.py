"""Independent PR #13 source-clock reconciliation regressions (review #6540960265).

Public ShadowRun PM04_BROKER events; completely synthetic and offline.
"""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import RiskState
from test_pm04_acceptance import observation_event, reopen
from test_pm04_shadow import BTC_KEY, at, make_run, signal, target, tick


def test_late_received_pre_cancel_position_snapshot_cannot_resolve_order_race(tmp_path):
    run = make_run(tmp_path, broker_required=True)
    observation_event(
        run,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(run, "cancel", "CANCEL", 20, order_id="O1", provider_sequence=2)
    observation_event(
        run,
        "late-old-position",
        "POSITION_SNAPSHOT",
        30,
        event_at=at(15),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(
        run,
        "balance",
        "BALANCE_SNAPSHOT",
        31,
        balance="10000",
        equity="10000",
    )
    observation_event(run, "fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    broker = run.account.pm04_state["broker"]

    assert "CANCEL_FILL_RACE_UNRESOLVED" in broker["discrepancies"]
    assert not broker["ready"]
    assert run.account.risk == RiskState.HALT
    tick(run, "mark-and-reserve", 33)
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 300
    assert reopen(tmp_path).state() == run.state()


def test_fresh_post_cancel_provider_snapshot_resolves_reservation_but_not_halt(tmp_path):
    run = make_run(tmp_path, broker_required=True)
    observation_event(
        run,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(run, "cancel", "CANCEL", 20, order_id="O1", provider_sequence=2)
    observation_event(
        run,
        "fresh-position",
        "POSITION_SNAPSHOT",
        30,
        event_at=at(21),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(
        run,
        "fresh-balance",
        "BALANCE_SNAPSHOT",
        31,
        balance="10000",
        equity="10000",
    )
    observation_event(run, "fresh-fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    broker = run.account.pm04_state["broker"]

    assert broker["discrepancies"] == []
    assert broker["ready"]
    assert run.account.risk == RiskState.HALT  # No implicit risk reset.
    tick(run, "mark-and-release", 33)
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 0
    assert run.account.quantities == {}
    assert reopen(tmp_path).state() == run.state()


def test_complete_post_cancel_snapshot_expires_and_re_reserves_uncertain_order(tmp_path):
    run = make_run(tmp_path, broker_required=True, broker_max_age_seconds=300)
    observation_event(
        run,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(run, "cancel", "CANCEL", 20, order_id="O1", provider_sequence=2)
    observation_event(
        run,
        "fresh-position",
        "POSITION_SNAPSHOT",
        30,
        event_at=at(21),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(
        run,
        "balance",
        "BALANCE_SNAPSHOT",
        31,
        balance="10000",
        equity="10000",
    )
    observation_event(run, "fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    assert run.account.pm04_state["broker"]["ready"]
    tick(run, "fresh-mark", 33)
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 0

    tick(run, "source-expired", 400)
    assert not run.account.pm04_state["broker"]["ready"]
    assert "STALE_POSITION_SNAPSHOT" in run.account.pm04_state["broker"]["discrepancies"]
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 300
    assert run.account.risk == RiskState.HALT
    assert reopen(tmp_path).state() == run.state()


def test_crash_after_commit_replays_pre_cancel_snapshot_as_unresolved(tmp_path, monkeypatch):
    run = make_run(tmp_path, broker_required=True)
    observation_event(
        run,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(run, "cancel", "CANCEL", 20, order_id="O1", provider_sequence=2)
    original = run.ledger.append

    def append_then_crash(sealed, *, expected_head):
        original(sealed, expected_head=expected_head)
        raise RuntimeError("SYNTHETIC_CRASH_AFTER_BROKER_COMMIT")

    monkeypatch.setattr(run.ledger, "append", append_then_crash)
    with pytest.raises(RuntimeError, match="CRASH_AFTER_BROKER_COMMIT"):
        observation_event(
            run,
            "late-old-position",
            "POSITION_SNAPSHOT",
            30,
            event_at=at(15),
            complete=True,
            positions={BTC_KEY: "0"},
        )
    # The event is already journaled, but the in-memory account has not committed.
    assert run.account.pm04_state["broker"]["position_snapshot"] is None
    restored = reopen(tmp_path)
    assert restored.account.pm04_state["broker"]["position_snapshot"]["event_at"] == at(15)
    observation_event(
        restored,
        "balance",
        "BALANCE_SNAPSHOT",
        31,
        balance="10000",
        equity="10000",
    )
    observation_event(restored, "fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    tick(restored, "mark-and-reserve", 33)
    assert not restored.account.pm04_state["broker"]["ready"]
    assert "CANCEL_FILL_RACE_UNRESOLVED" in restored.account.pm04_state["broker"]["discrepancies"]
    assert D(restored.account.pm04_state["exposure"]["pending_inflight_gross"]) == 300
    assert reopen(tmp_path).state() == restored.state()


def test_late_pre_reconnect_provider_position_cannot_clear_reconnect_gap(tmp_path):
    run = make_run(tmp_path, broker_required=True)
    observation_event(run, "reconnect", "RECONNECT", 20)
    observation_event(
        run,
        "pre-reconnect-position",
        "POSITION_SNAPSHOT",
        30,
        event_at=at(15),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(
        run,
        "balance",
        "BALANCE_SNAPSHOT",
        31,
        balance="10000",
        equity="10000",
    )
    observation_event(run, "fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    broker = run.account.pm04_state["broker"]
    assert "RECONNECT_POSITION_UNRESOLVED" in broker["discrepancies"]
    assert not broker["ready"]
    assert reopen(tmp_path).state() == run.state()


def test_reconnect_re_reserves_pre_reconnect_canceled_order_until_fresh_position(tmp_path):
    run = make_run(tmp_path, broker_required=True)
    observation_event(
        run,
        "intent",
        "ORDER_INTENT",
        10,
        order_id="O1",
        instrument=BTC_KEY,
        quantity="3",
        provider_sequence=1,
    )
    observation_event(run, "cancel", "CANCEL", 20, order_id="O1", provider_sequence=2)
    observation_event(
        run,
        "pre-reconnect-position",
        "POSITION_SNAPSHOT",
        30,
        event_at=at(21),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(run, "balance", "BALANCE_SNAPSHOT", 31, balance="10000", equity="10000")
    observation_event(run, "fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    tick(run, "pre-reconnect-mark", 33)
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 0

    observation_event(run, "reconnect", "RECONNECT", 40)
    tick(run, "after-reconnect", 41)
    assert not run.account.pm04_state["broker"]["ready"]
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 300

    observation_event(
        run,
        "post-reconnect-position",
        "POSITION_SNAPSHOT",
        45,
        event_at=at(42),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    tick(run, "post-reconnect-mark", 46)
    assert D(run.account.pm04_state["exposure"]["pending_inflight_gross"]) == 0
    assert not run.account.pm04_state["broker"]["ready"]  # Balance/fee still pre-reconnect.
    assert reopen(tmp_path).state() == run.state()


def test_fresh_post_reconnect_source_snapshot_restores_broker_readiness(tmp_path):
    run = make_run(tmp_path, broker_required=True)
    observation_event(run, "reconnect", "RECONNECT", 20)
    observation_event(
        run,
        "late-old-position",
        "POSITION_SNAPSHOT",
        30,
        event_at=at(15),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(
        run,
        "balance",
        "BALANCE_SNAPSHOT",
        31,
        balance="10000",
        equity="10000",
    )
    observation_event(run, "fees", "FEES_FUNDING", 32, fee_total="0", funding_total="0")
    assert not run.account.pm04_state["broker"]["ready"]

    observation_event(
        run,
        "post-reconnect-position",
        "POSITION_SNAPSHOT",
        35,
        event_at=at(33),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    assert run.account.pm04_state["broker"]["discrepancies"] == []
    assert run.account.pm04_state["broker"]["ready"]
    assert run.account.risk == RiskState.GREEN
    assert reopen(tmp_path).state() == run.state()


def test_recent_receipts_do_not_refresh_342_second_old_provider_snapshots(tmp_path):
    run = make_run(tmp_path, broker_required=True, broker_max_age_seconds=300)
    observation_event(
        run,
        "old-position",
        "POSITION_SNAPSHOT",
        350,
        event_at=at(10),
        complete=True,
        positions={BTC_KEY: "0"},
    )
    observation_event(
        run,
        "old-balance",
        "BALANCE_SNAPSHOT",
        351,
        event_at=at(10),
        balance="10000",
        equity="10000",
    )
    observation_event(
        run,
        "old-fees",
        "FEES_FUNDING",
        352,
        event_at=at(10),
        fee_total="0",
        funding_total="0",
    )

    broker = run.account.pm04_state["broker"]
    assert sorted(broker["discrepancies"]) == [
        "STALE_BALANCE_SNAPSHOT",
        "STALE_FEES_FUNDING_SNAPSHOT",
        "STALE_POSITION_SNAPSHOT",
    ]
    assert broker["ready"] is False
    assert run.account.risk == RiskState.HALT
    assert run.account.quantities == {}
    signal(run, "blocked-new-risk", [target("W028", 2, first_known_seconds=400)], 400)
    tick(run, "blocked-new-risk-due", 700)
    assert run.account.quantities == {}  # Stale provider state never authorizes fills.
    assert run.account.risk == RiskState.HALT
    assert reopen(tmp_path).state() == run.state()
