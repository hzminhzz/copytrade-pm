"""Follower economics: stop/gap, latency, missing marks and skill selection bias."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from copytrade_pm.trader_intelligence import (
    ObservationSnapshot,
    WalletIdentity,
    WalletEvent,
)
from copytrade_pm.trader_intelligence_research import (
    FollowerPolicy,
    MinuteBar,
    follower_replay,
    asof_skill,
)

AT = datetime(2026, 10, 13, 10, tzinfo=UTC)
MARKET = "hyperliquid/mainnet:perp:default/BTC"
SHA = sha256(b"wallet").hexdigest()


def snapshot():
    event = WalletEvent(
        event_id="source-fill",
        wallet="wallet",
        instrument=MARKET,
        event_at=AT.isoformat(),
        first_known_at=AT.isoformat(),
        origin="PROSPECTIVE_OBSERVED",
        position_before="0",
        position_after="1",
        book_complete=True,
        source_equity_usd="1000",
        strategy_style="DIRECTIONAL",
    )
    return ObservationSnapshot(
        "roster",
        (AT - timedelta(days=1)).isoformat(),
        (WalletIdentity("wallet", SHA, cluster="independent"),),
        (event,),
        "PROSPECTIVE_OBSERVED",
    )


def policy(exit_policy="FIXED_HORIZON"):
    return FollowerPolicy(
        300,
        (15,),
        "100",
        "5",
        "5",
        "2",
        "2",
        "2",
        "100",
        "0.01",
        "0",
        exit_policy=exit_policy,
    )


def bars(*, gap=False, stop=False):
    rows = []
    for minute in range(22):
        if gap and minute == 8:
            continue
        open_px, low = ("100", "100")
        if stop and minute == 6:
            low = "98"
        rows.append(
            MinuteBar(
                MARKET,
                (AT + timedelta(minutes=minute)).isoformat(),
                open_px,
                "100",
                low,
                "100",
                "10000",
            )
        )
    return tuple(rows)


def test_stop_proxy_loss_counted_not_dropped_from_skill():
    data = follower_replay(snapshot(), bars(stop=True), policy("STOP_OR_HORIZON"))
    assert len(data) == 1
    out = data[0]
    assert out.status == "STOP_PROXY_FILLED"
    assert out.hypothetical_entry_at == (AT + timedelta(minutes=5)).isoformat().replace(
        "+00:00", "Z"
    )
    assert out.outcome_known_at == (AT + timedelta(minutes=7)).isoformat().replace("+00:00", "Z")
    assert float(out.net_r) < -1
    skill = asof_skill(
        "wallet",
        MARKET,
        "LONG",
        "DIRECTIONAL",
        data,
        (AT + timedelta(hours=1)).isoformat(),
        prior_strength=2,
        tail_probability_z="1.96",
    )
    assert skill.sample_size == 1
    assert skill.effective_groups == 1
    assert float(skill.posterior_mean_r) < 0


def test_no_stop_policy_keeps_constant_horizon_and_different_sha():
    stop_data = follower_replay(snapshot(), bars(stop=True), policy("STOP_OR_HORIZON"))
    horizon_data = follower_replay(snapshot(), bars(stop=True), policy())
    assert policy().sha256 != policy("STOP_OR_HORIZON").sha256
    assert horizon_data[0].status == "OK"
    assert horizon_data[0].hypothetical_exit_at == (AT + timedelta(minutes=20)).isoformat().replace(
        "+00:00", "Z"
    )
    assert stop_data[0].net_r != horizon_data[0].net_r


def test_interior_market_gap_fails_closed():
    outcomes = follower_replay(snapshot(), bars(gap=True), policy())
    assert outcomes[0].status == "INTERIOR_MARKET_GAP"
    assert outcomes[0].net_r is None
    assert outcomes[0].outcome_known_at is None


def test_replay_idempotent_after_restart_and_bars_reordered():
    series = bars()
    a = follower_replay(snapshot(), series, policy())
    b = follower_replay(snapshot(), tuple(reversed(series)), policy())
    assert a[0].as_wire() == b[0].as_wire()


def test_future_outcome_cannot_raise_skill_at_earlier_cut():
    data = follower_replay(snapshot(), bars(stop=True), policy("STOP_OR_HORIZON"))
    before = asof_skill(
        "wallet",
        MARKET,
        "LONG",
        "DIRECTIONAL",
        data,
        (AT + timedelta(minutes=6)).isoformat(),
        prior_strength=2,
        tail_probability_z="1.96",
    )
    assert before.sample_size == 0 and before.posterior_mean_r is None
