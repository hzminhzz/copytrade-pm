"""Deterministic exploratory historical episode-account parity and honesty checks."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from copytrade_pm.pm_historical_combos import (
    START,
    Episode,
    _batched_actions,
    _run_combo,
    _source_episodes,
    _verified_interval,
)
from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_shadow import MarketDataBlocked, MinuteBar


def sample_event(when, coin, before, after, tid=1, price="100"):
    return (when, tid, coin, D(before), D(after), D(after) - D(before), D(price))


def ep(wallet="W028", coin="BTC", start=None, exit_at=None, quantity="2"):
    start = start or START + timedelta(minutes=1, seconds=5)
    exit_at = exit_at or start + timedelta(minutes=20)
    return Episode(
        wallet,
        coin,
        (
            sample_event(start, coin, "0", quantity, 1),
            sample_event(exit_at, coin, quantity, "0", 2),
        ),
    )


class FixedMarket:
    def __init__(self, bad=None, price="100"):
        self.bad = bad
        self.price = D(price)
        self.calls = []

    def get(self, instrument, when):
        self.calls.append((instrument, when))
        if when == self.bad:
            raise MarketDataBlocked("MISSING_EXACT_1M_BAR")
        return MinuteBar(when, self.price, D("10000000"), "f" * 64)


def test_source_only_explicit_flat_to_flat_and_gap_is_not_zero():
    t = START + timedelta(minutes=1)
    fills = [
        sample_event(t, "BTC", "5", "6", 1),  # left censored
        sample_event(t + timedelta(minutes=1), "BTC", "6", "0", 2),
        sample_event(t + timedelta(minutes=2), "BTC", "0", "2", 3),
        sample_event(t + timedelta(minutes=3), "BTC", "2", "0", 4),
        sample_event(t + timedelta(minutes=4), "ETH", "0", "2", 1),
        sample_event(t + timedelta(minutes=5), "ETH", "9", "0", 2),  # gap
    ]
    episodes, counts = _source_episodes("W028", fills)
    assert len(episodes) == 1
    assert episodes[0].coin == "BTC"
    assert episodes[0].start == t + timedelta(minutes=2)
    assert counts["left_censored_observation_rows"] >= 1
    assert counts["source_chain_breaks"] == 1


def test_batch_waits_five_minutes_since_first_source_event_and_scales_fixed():
    start = START + timedelta(seconds=5)
    opening = Episode(
        "W028",
        "BTC",
        (
            sample_event(start, "BTC", "0", "2", 1),
            sample_event(start + timedelta(minutes=2), "BTC", "2", "3", 2),
            sample_event(start + timedelta(minutes=8), "BTC", "3", "0", 3),
        ),
    )
    eps = {"W028": [opening], "W042": [], "W030": []}
    actions = _batched_actions(
        eps, ("W028", "W042", "W030"), {"W028": D("0.5"), "W042": None, "W030": None}
    )
    assert len(actions) == 2
    assert actions[0][0] == START + timedelta(minutes=6)
    inst = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
    assert actions[0][1]["W028"][inst] == D("1.5")
    assert actions[1][1]["W028"] == {}


def test_market_interval_missing_minute_excludes_entire_episode():
    episode = ep()
    expected = START + timedelta(minutes=12)
    ok, reason, count = _verified_interval(episode, FixedMarket(bad=expected))
    assert ok is False
    assert reason == "MISSING_EXACT_1M_BAR"
    assert count > 0


def test_shared_account_costs_and_internal_netting_are_real_ledger_operations():
    market = FixedMarket()
    start = START + timedelta(minutes=1, seconds=5)
    stop = start + timedelta(minutes=20)
    epis = {
        "W028": [ep("W028", "BTC", start, stop, "2")],
        "W042": [
            Episode(
                "W042",
                "BTC",
                (
                    sample_event(start, "BTC", "0", "-2", 1),
                    sample_event(stop, "BTC", "-2", "0", 2),
                ),
            )
        ],
        "W030": [ep("W030", "ETH", start, stop, "1")],
    }
    scales = {k: D("1") for k in epis}
    result = _run_combo("A", ("W028", "W042", "W030"), epis, scales, market)
    assert result["status"] == "CONDITIONAL_EPISODE_REPLAY_FULL_Q3"
    assert D(result["pnl_usd"]) < 0
    assert result["counters"]["internal_crosses"] >= 1
    assert result["counters"]["hypothetical_net_orders"] == 2  # ETH entry/exit only
    assert D(result["per_wallet_pnl_usd"]["W028"]) == 0
    assert D(result["per_wallet_pnl_usd"]["W042"]) == 0
    assert result["stage_passed"] is False
    assert result["breached_floor"] is False


def test_any_missing_active_minute_stops_metrics_not_zero_fills():
    open_at = START + timedelta(minutes=1, seconds=5)
    bad = START + timedelta(minutes=9)
    eps = {"W028": [ep("W028", "BTC", open_at)]}
    result = _run_combo("single", ("W028",), eps, {"W028": D("1")}, FixedMarket(bad))
    assert result["status"] == "PARTIAL_CONDITIONAL_REPLAY"
    assert result["stop_reason"].startswith("MISSING_ACTIVE_OR_TARGET_MARK")
    assert result["observed_through"] == bad.isoformat()


def test_capacity_policy_uses_prior_complete_minute_not_future_bar_volume():
    """An order at 00:07 cannot know 00:07's finished quote volume."""
    opening = START + timedelta(minutes=1, seconds=5)
    entry_at = START + timedelta(minutes=7)
    previous_at = entry_at - timedelta(minutes=1)

    class AsymmetricMinuteVolume(FixedMarket):
        def get(self, instrument, when):
            current = super().get(instrument, when)
            volume = D("0") if when == previous_at else D("10000000")
            return MinuteBar(when, current.open, volume, current.source_sha256)

    obs = {"W028": [ep(wallet="W028", start=opening, quantity="0.06")]}
    result = _run_combo(
        "capacity-PIT",
        ("W028",),
        obs,
        {"W028": D("1")},
        AsymmetricMinuteVolume(),
        capacity_enforced=True,
    )
    assert result["counters"]["capacity_blocked_orders"] == 1
    assert result["counters"].get("hypothetical_net_orders", 0) == 0
    assert result["pnl_usd"] == "0"
    assert result["stop_reason"] is None


def test_positions_unknown_without_episodes_not_marked_flat():
    result = _run_combo(
        "B",
        ("W044", "CA-005", "W031"),
        {"W044": [], "CA-005": [], "W031": []},
        {"W044": None, "CA-005": None, "W031": None},
        FixedMarket(),
    )
    assert result["status"] == "NO_THREE_WALLET_OBSERVABLE_INPUT"
    assert result["pnl_usd"] is None
