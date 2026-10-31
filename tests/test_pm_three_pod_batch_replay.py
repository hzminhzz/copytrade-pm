"""Research-only three-pod execution-policy and loss-floor regression tests."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from copytrade_pm.pm_quarter_fill_audit import START
from copytrade_pm.pm_shadow import MarketDataBlocked, MinuteBar
from copytrade_pm.pm_three_pod_batch_replay import (
    PODS,
    Signal,
    _risk_is_reducing,
    minute_after,
    replay_policy,
    target_quantities,
)


D = Decimal
INST = "hyperliquid:mainnet:perp:default:BTC"
ALT = "hyperliquid:mainnet:perp:default:ETH"


def tick(n: int):
    return START + timedelta(minutes=n)


def signal(n: int, pod: str, proportion: str, *, symbol: str = INST) -> Signal:
    observed = tick(n)
    return Signal(
        observed,
        observed - timedelta(seconds=30),
        pod,
        symbol,
        1,
        D(proportion) / D("100"),
    )


class Market:
    def __init__(
        self,
        *,
        px: dict[int, str] | None = None,
        gap=(),
        volume="10000000",
        minute_volume: dict[int, str] | None = None,
    ):
        self.prices = px or {}
        self.gaps = set(gap)
        self.volume = D(volume)
        self.minute_volume = minute_volume or {}
        self.reads = []

    def get(self, instrument, when):
        self.reads.append((instrument, when))
        if when in self.gaps:
            raise MarketDataBlocked("MISSING_EXACT_1M_BAR")
        minute = int((when - START) / timedelta(minutes=1))
        return MinuteBar(
            when,
            D(self.prices.get(minute, "100")),
            D(self.minute_volume.get(minute, self.volume)),
            "a" * 64,
        )


def simulate(
    events,
    policy,
    market=None,
    *,
    end=32,
    notional="1000",
    cap="4000",
    global_cap="12000",
    singlecap="7000",
):
    return replay_policy(
        events,
        market or Market(),
        policy=policy,
        per_episode_notional=D(notional),
        per_pod_cap=D(cap),
        global_gross_cap=D(global_cap),
        single_instrument_cap=D(singlecap),
        end_at=tick(end),
    )


def test_selects_exact_three_pods_and_never_executes_before_source_time():
    assert PODS == ("W028", "W042", "W030")
    assert minute_after(tick(0)) == tick(1)
    assert minute_after(tick(0) + timedelta(seconds=30)) == tick(1)
    with pytest.raises(ValueError, match="INVALID_HINDSIGHT_SOURCE_EVENT"):
        Signal(tick(0), tick(0), PODS[0], INST, 1, D("0.01"))
    with pytest.raises(ValueError, match="INVALID_HINDSIGHT_SOURCE_EVENT"):
        Signal(tick(1), tick(0), "SOME_WALLET", INST, 1, D("0.01"))


def test_equal_pod_target_nets_opposing_signals_before_one_order():
    marks = {INST: D("100")}
    states = {
        ("W028", INST): D("0.01"),
        ("W042", INST): D("-0.01"),
        ("W030", INST): D("0.01"),
    }
    result = target_quantities(
        states,
        marks,
        per_episode_notional=D("1000"),
        per_pod_cap=D("1000"),
        global_gross_cap=D("3000"),
        single_instrument_cap=D("2500"),
    )
    assert result[INST] == D("10")
    del states[("W030", INST)]
    assert (
        target_quantities(
            states,
            marks,
            per_episode_notional=D("1000"),
            per_pod_cap=D("1000"),
            global_gross_cap=D("3000"),
            single_instrument_cap=D("2500"),
        )
        == {}
    )


def test_global_and_pod_caps_include_all_open_instruments():
    states = {
        ("W028", INST): D("0.04"),
        ("W028", ALT): D("0.04"),
        ("W042", INST): D("0.04"),
        ("W030", ALT): D("0.04"),
    }
    result = target_quantities(
        states,
        {INST: D("100"), ALT: D("100")},
        per_episode_notional=D("1000"),
        per_pod_cap=D("2000"),
        global_gross_cap=D("3000"),
        single_instrument_cap=D("2000"),
    )
    assert sum(abs(q * D("100")) for q in result.values()) <= 3000
    with pytest.raises(ValueError, match="INVALID_PORTFOLIO_CAPS"):
        target_quantities(
            {},
            {},
            per_episode_notional=D("3000"),
            per_pod_cap=D("2000"),
            global_gross_cap=D("3000"),
            single_instrument_cap=D("2000"),
        )


def test_five_minute_batch_reduces_orders_and_cancels_short_lived_signal():
    # All three source updates are known only at their respective minute opens.
    events = [
        signal(1, "W028", "1"),
        signal(2, "W042", "-1"),
        signal(3, "W030", "1"),
        signal(16, "W028", "0"),
        signal(16, "W042", "0"),
        signal(16, "W030", "0"),
    ]
    m1, m2 = Market(), Market()
    immediate = simulate(events, "IMMEDIATE", m1)
    batch = simulate(events, "BATCH_5M", m2)
    assert immediate["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert batch["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert immediate["hypothetical_market_order_count"] > batch["hypothetical_market_order_count"]
    assert batch["first_execution_at"] == tick(6).isoformat()
    assert immediate["first_execution_at"] == tick(1).isoformat()
    assert batch["modeled_turnover_usdc"] != immediate["modeled_turnover_usdc"]


def test_asymmetry_closes_risk_at_earliest_open_and_delays_new_risk():
    events = [
        signal(1, "W028", "1"),
        signal(12, "W028", "0"),
    ]
    symmetric = simulate(events, "BATCH_5M")
    asymmetric = simulate(events, "ASYMMETRIC_5M")
    assert symmetric["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert asymmetric["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert symmetric["last_execution_at"] == tick(17).isoformat()
    assert asymmetric["last_execution_at"] == tick(12).isoformat()
    assert asymmetric["event_counts"]["immediate_risk_reduction"] == 1
    assert _risk_is_reducing(D("1"), D("0"))
    assert _risk_is_reducing(D("1"), D("-1"))
    assert not _risk_is_reducing(D("0"), D("1"))


def test_fixed_delay_is_different_from_source_observed_batch():
    events = [
        signal(1, "W028", "1"),
        signal(2, "W028", "2"),
        signal(12, "W028", "0"),
    ]
    delayed = simulate(events, "FIXED_5M")
    batch = simulate(events, "BATCH_5M")
    assert delayed["status"] == batch["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert delayed["hypothetical_market_order_count"] > batch["hypothetical_market_order_count"]


def test_sampled_daily_loss_is_account_level_absorbing_barrier():
    price = {n: "80" for n in range(4, 30)}
    market = Market(px=price)
    events = [signal(1, "W028", "1"), signal(20, "W028", "0")]
    row = simulate(
        events,
        "IMMEDIATE",
        market,
        notional="50000",
        cap="50000",
        global_cap="50000",
        singlecap="50000",
    )
    assert row["status"] == "SAMPLED_CHALLENGE_LOSS_FLOOR_TOUCH"
    assert row["pass_probability"] is None
    assert row["broker_executed"] is False
    assert D(row["sampled_max_daily_loss_usdc"]) > D("3000")


def test_active_missing_minute_does_not_become_flat_or_zero_pnl():
    events = [signal(1, "W028", "1"), signal(20, "W028", "0")]
    row = simulate(events, "IMMEDIATE", Market(gap={tick(5)}))
    assert row["status"] == "BLOCKED_ACTIVE_MARKET_DATA"
    assert row["data_blocker"] == "MISSING_EXACT_1M_BAR"


def test_capacity_rejects_new_risk_and_does_not_make_up_fills():
    events = [signal(1, "W028", "1"), signal(20, "W028", "0")]
    row = simulate(events, "IMMEDIATE", Market(volume="1"))
    assert row["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert row["hypothetical_market_order_count"] == 0
    assert row["event_counts"]["skipped_new_risk_liquidity"] >= 1


def test_illiquid_exit_is_partially_filled_and_retried_not_instant():
    events = [signal(1, "W028", "1"), signal(10, "W028", "0")]
    volume = {9: "2000", 10: "2000", 11: "20000"}
    row = simulate(events, "IMMEDIATE", Market(minute_volume=volume), end=25)
    assert row["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert row["event_counts"]["partial_exit_rebalance_orders"] >= 1
    assert row["hypothetical_market_order_count"] >= 3
    assert row["last_execution_at"] == tick(12).isoformat()
    assert row["unresolved_risk_reduction_instruments"] == 0


def test_uses_completed_previous_minute_volume_not_future_t_volume():
    events = [signal(1, "W028", "1"), signal(12, "W028", "0")]
    m = Market(minute_volume={0: "0", 1: "10000000", 11: "10000000"})
    result = simulate(events, "IMMEDIATE", m, end=24)
    assert result["hypothetical_market_order_count"] == 0
    assert result["event_counts"]["skipped_new_risk_liquidity"] >= 1
    assert result["execution_volume_uses_only_previously_completed_minute"] is True


def test_marked_risk_cap_excess_forces_deleveraging_without_source_signal():
    # New exposure is capped at execution, but a subsequent adverse/profit
    # mark can increase gross. The PM must not wait for another wallet fill.
    events = [signal(1, "W028", "1"), signal(19, "W028", "0")]
    m = Market(px={i: "200" for i in range(4, 28)})
    row = simulate(
        events,
        "IMMEDIATE",
        m,
        end=31,
        notional="1000",
        cap="1500",
        global_cap="1500",
        singlecap="1000",
    )
    assert row["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    assert row["event_counts"]["forced_marked_gross_risk_reductions"] > 0
    assert row["max_observed_gross_usdc"] != "0"


def test_end_timestamp_and_sorted_source_are_strictly_enforced():
    event = signal(1, "W028", "1")
    with pytest.raises(ValueError, match="INVALID_EVALUATION_INTERVAL"):
        replay_policy(
            [event],
            Market(),
            policy="IMMEDIATE",
            per_episode_notional=D(100),
            per_pod_cap=D(500),
            global_gross_cap=D(1500),
            single_instrument_cap=D(500),
            end_at=START,
        )
    with pytest.raises(ValueError, match="NONMONOTONIC_SOURCE_ARRIVAL"):
        simulate([signal(2, "W028", "0"), event], "IMMEDIATE")
