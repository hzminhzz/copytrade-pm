"""Synthetic partial-episode follower replay: causal bookkeeping and censoring."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm_quarter_fill_audit import EconomicFill, START, END
from copytrade_pm.pm_quarter_episode_replay import (
    Episode,
    closed_episodes,
    replay_episode,
    wallet_episodes,
)
from copytrade_pm.pm_shadow import MarketDataBlocked, MinuteBar


def fill(minute: int, tid: int, before: str, delta: str, coin="BTC"):
    at = START + timedelta(hours=10, minutes=minute)
    prev, change = D(before), D(delta)
    return EconomicFill(
        at,
        tid,
        coin,
        prev,
        prev + change,
        change,
        D("100"),
        D("0"),
        D("0.05"),
        "USDC",
        "Open Long" if change > 0 else "Close Long",
    )


class Price:
    def __init__(self, *, missing=(), volume="100000"):
        self.missing = set(missing)
        self.volume = D(volume)
        self.requested = []

    def get(self, instrument, at):
        self.requested.append((instrument, at))
        if at in self.missing:
            raise MarketDataBlocked("MISSING_EXACT_1M_BAR")
        return MinuteBar(at, D("100"), self.volume, "a" * 64)


def test_flat_to_flat_episodes_without_inventing_initial_position():
    # First old segment starts nonflat, so it must not be counted. Once
    # directly flat, next episode can be reconstructed.
    old = fill(-50, 1, "5", "-5")
    entry = fill(0, 2, "0", "1")
    close = fill(10, 3, "1", "-1")
    after = fill(20, 4, "0", "2")
    rows, stats = closed_episodes("W001", [old, entry, close, after])
    assert len(rows) == 1
    assert rows[0].rows == (entry, close)
    assert stats["valid_flat_to_flat_episodes_in_quarter"] == 1
    assert stats["censored_open_segments_at_source_cutoff"] == 1


def test_recovered_source_gap_censors_partial_episode():
    rows, stats = closed_episodes(
        "W001",
        [
            fill(0, 1, "0", "1"),
            fill(1, 2, "4", "-4"),  # a missing source transition
            fill(2, 3, "0", "1"),
            fill(3, 4, "1", "-1"),
        ],
    )
    assert stats["position_chain_gaps"] == 1
    assert len(rows) == 1
    assert rows[0].rows[0].trade_id == 3


def test_flip_through_zero_is_rejected():
    rows, stats = closed_episodes(
        "W001",
        [
            fill(0, 1, "0", "2"),
            fill(1, 2, "2", "-3"),
            fill(2, 3, "-1", "1"),
        ],
    )
    assert not rows
    assert stats["unsupported_flip_or_restart"] == 1


def test_episode_replay_uses_future_execution_minutes_and_costs():
    episode = Episode("W001", "BTC", (fill(0, 1, "0", "1"), fill(10, 2, "1", "-1")))
    market = Price()
    result = replay_episode(episode, market, 5)
    assert result["status"] == "HINDSIGHT_EPISODE_SIMULATED_ONLY"
    assert D(result["hypothetical_net_pnl_usdc"]) < 0
    assert D(result["incremental_vs_long_control_usdc"]) == 0
    assert D(result["max_live_gross_episode_notional_usdc"]) <= D(100)
    assert result["copyability_qualified"] is False
    assert {when for _, when in market.requested} == {
        START + timedelta(hours=10, minutes=5),
        START + timedelta(hours=10, minutes=15),
    }


def test_execution_cost_and_liquidity_blockers_are_not_zero_returns():
    episode = Episode("W001", "BTC", (fill(0, 1, "0", "1"), fill(10, 2, "1", "-1")))
    missing = START + timedelta(hours=10, minutes=5)
    result = replay_episode(episode, Price(missing={missing}), 5)
    assert result["status"] == "BLOCKED_MARKET_DATA"
    assert "hypothetical_net_pnl_usdc" not in result
    outcome = replay_episode(episode, Price(volume="0"), 5)
    assert outcome["status"] == "BLOCKED_INSTRUMENT_MINUTE_PARTICIPATION"
    assert "hypothetical_net_pnl_usdc" not in outcome


def test_opaque_coin_and_post_quarter_close_fail_closed():
    episode = Episode(
        "W001",
        "#ID",
        (
            fill(0, 1, "0", "1", "#ID"),
            fill(10, 2, "1", "-1", "#ID"),
        ),
    )
    result = replay_episode(episode, Price(), 5)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXCHANGE_INSTRUMENT"
    finish_at = END - timedelta(minutes=1)
    first = EconomicFill(finish_at, 1, "BTC", D(0), D(1), D(1), D(100), D(0), D(0), "USDC", "Open")
    exit_ = EconomicFill(
        finish_at + timedelta(seconds=10),
        2,
        "BTC",
        D(1),
        D(0),
        D(-1),
        D(100),
        D(0),
        D(0),
        "USDC",
        "Close",
    )
    finish = Episode("W001", "BTC", (first, exit_))
    assert replay_episode(finish, Price(), 5)["status"] == ("BLOCKED_ACTION_AFTER_QUARTER_END")


def test_same_minute_entry_exit_does_not_create_fake_pnl():
    episode = Episode(
        "W001",
        "BTC",
        (
            fill(0, 1, "0", "1"),
            fill(0, 2, "1", "-1"),
        ),
    )
    result = replay_episode(episode, Price(), 5)
    assert result["status"] == "BLOCKED_NO_EXECUTABLE_ENTRY"


def test_unanchored_or_out_of_window_source_rejected():
    episode = Episode("W001", "BTC", (fill(0, 1, "10", "-10"),))
    with pytest.raises(ValueError, match="UNANCHORED"):
        replay_episode(episode, Price(), 5)
    with pytest.raises(ValueError, match="INVALID_HISTORICAL_EPISODE_POLICY"):
        replay_episode(Episode("W001", "BTC", (fill(0, 1, "0", "1"),)), Price(), 30)


def test_paired_same_episode_comparator_excludes_different_coverage():
    episode = Episode("W001", "BTC", (fill(0, 1, "0", "1"), fill(10, 2, "1", "-1")))
    result = wallet_episodes("W001", [episode], Counter(), Price())
    paired = result["paired_same_episodes_all_5_15_60m"]
    assert paired["count"] == 1
    assert all(
        D(paired["by_lag"][str(delay)]["sum_incremental_vs_long_control_usdc"]) == 0
        for delay in (5, 15, 60)
    )
    missing60 = START + timedelta(hours=11)
    result = wallet_episodes("W001", [episode], Counter(), Price(missing={missing60}))
    assert result["by_lag"]["5"]["completed_observable_flat_to_flat_episodes"] == 1
    assert result["by_lag"]["60"]["completed_observable_flat_to_flat_episodes"] == 0
    assert result["paired_same_episodes_all_5_15_60m"]["count"] == 0


def test_time_order_and_same_ms_tids_not_arbitrarily_resorted():
    a = fill(1, 99, "0", "1")
    b = fill(1, 1, "1", "1")
    c = fill(2, 55, "2", "-2")
    episodes, _ = closed_episodes("W001", [a, b, c])
    assert episodes[0].rows == (a, b, c)
    with pytest.raises(ValueError, match="NONCHRONOLOGICAL"):
        closed_episodes("W001", [c, a, b])
