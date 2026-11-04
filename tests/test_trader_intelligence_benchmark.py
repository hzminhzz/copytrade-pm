"""Matched follower-control benchmark is descriptive until independent PIT holdout."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from copytrade_pm.trader_intelligence import (
    ObservationSnapshot,
    WalletIdentity,
    WalletEvent,
)
from copytrade_pm.trader_intelligence_research import (
    CandidateCut,
    FollowerEpisode,
    MatchedMarketControl,
    matched_benchmark,
)

NOW = datetime(2026, 10, 13, 10, tzinfo=UTC)
MARKET = "hyperliquid/mainnet:perp:default/BTC"
SHA = sha256(b"evidence").hexdigest()


def example(*, all_clones=False):
    wallets = tuple(
        WalletIdentity(
            f"W{i}",
            sha256(f"W{i}".encode()).hexdigest(),
            cluster="same-parent" if all_clones else f"indep{i}",
        )
        for i in range(3)
    )
    changes = tuple(
        WalletEvent(
            event_id=f"e{i}",
            wallet=f"W{i}",
            instrument=MARKET,
            event_at=NOW.isoformat(),
            first_known_at=NOW.isoformat(),
            origin="PROSPECTIVE_OBSERVED",
            position_before="0",
            position_after="1",
            book_complete=True,
            source_equity_usd="10000",
            strategy_style="DIRECTIONAL",
        )
        for i in range(3)
    )
    snapshot = ObservationSnapshot(
        "R1",
        (NOW - timedelta(days=1)).isoformat(),
        wallets,
        changes,
        "PROSPECTIVE_OBSERVED",
    )
    episode = FollowerEpisode(
        episode_id=SHA,
        wallet="W0",
        instrument=MARKET,
        direction="LONG",
        strategy_style="DIRECTIONAL",
        cluster_id="indep0",
        origin="PROSPECTIVE_OBSERVED",
        observation_at=NOW.isoformat(),
        first_known_at=NOW.isoformat(),
        hypothetical_entry_at=(NOW + timedelta(minutes=5)).isoformat(),
        hypothetical_exit_at=(NOW + timedelta(minutes=20)).isoformat(),
        outcome_known_at=(NOW + timedelta(minutes=20)).isoformat(),
        horizon_minutes=15,
        net_r="-0.5",
        gross_r="-0.4",
        cost_r="0.1",
        source_pnl_usd="200",
        status="OK",
        group_id="g0",
        policy_sha256=SHA,
    )
    cut = CandidateCut(
        (NOW + timedelta(minutes=3)).isoformat(),
        snapshot,
        MARKET,
        "LONG",
        SHA,
        roster_is_point_in_time=False,
    )
    market = MatchedMarketControl(
        candidate_episode_id=SHA,
        policy_sha256=SHA,
        control_net_r="-0.1",
        source_sha256=SHA,
        outcome_known_at=(NOW + timedelta(minutes=20)).isoformat(),
        instrument=MARKET,
        direction="LONG",
        decision_at=cut.decision_at,
        entry_at=episode.hypothetical_entry_at,
        exit_at=episode.hypothetical_exit_at,
        horizon_minutes=episode.horizon_minutes,
        modeled_cost_r=episode.cost_r,
    )
    return cut, episode, market


def test_matched_follower_net_r_worse_than_market_but_not_qualified():
    cut, episode, control = example()
    report = matched_benchmark(
        (cut,),
        (episode,),
        prior_strength=5,
        tail_probability_z="1.96",
        market_controls={SHA: control},
    )
    assert report.qualification == "NOT_QUALIFIED"
    assert report.schema == "ti_matched_benchmark_v2"
    assert len(report.rows) == 5
    equal_addresses = report.rows[0]
    independent = report.rows[1]
    assert equal_addresses.selected == 1
    assert independent.selected == 1
    assert float(independent.net_r_mean) == -0.5
    assert float(independent.net_r_vs_market_control) == pytest.approx(-0.4)
    assert independent.missing_controls == 0
    assert report.as_wire()["qualification"] == "NOT_QUALIFIED"


def test_unverified_cluster_does_not_increase_independent_votes():
    cut, episode, control = example(all_clones=True)
    report = matched_benchmark(
        (cut,),
        (episode,),
        prior_strength=5,
        tail_probability_z="1.96",
        market_controls={SHA: control},
    )
    assert report.rows[0].selected == 1
    assert report.rows[1].selected == 0


def test_misbound_outcome_cannot_be_used_for_another_market_or_direction():
    cut, episode, control = example()
    with pytest.raises(ValueError, match="CONTROL_OR_OUTCOME_CANDIDATE_MISMATCH"):
        matched_benchmark(
            (cut,),
            (replace(episode, direction="SHORT"),),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={SHA: control},
        )


def test_conflicting_duplicate_episode_never_silently_overwrites_economics():
    cut, episode, control = example()
    with pytest.raises(ValueError, match="CONFLICTING_BENCHMARK_EPISODE"):
        matched_benchmark(
            (cut,),
            (episode, replace(episode, net_r="99")),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={SHA: control},
        )


def test_outcome_must_belong_to_cut_roster_and_be_known_by_decision():
    cut, episode, control = example()
    for bad in (
        replace(episode, wallet="NOT_MONITORED"),
        replace(episode, first_known_at=(NOW + timedelta(minutes=4)).isoformat()),
    ):
        with pytest.raises(ValueError, match="CONTROL_OR_OUTCOME_CANDIDATE_MISMATCH"):
            matched_benchmark(
                (cut,),
                (bad,),
                prior_strength=5,
                tail_probability_z="1.96",
                market_controls={SHA: control},
            )


def test_control_identity_and_maturity_must_match_selected_episode():
    cut, episode, control = example()
    with pytest.raises(ValueError, match="CONTROL_EPISODE_IDENTITY_MISMATCH"):
        matched_benchmark(
            (cut,),
            (episode,),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={SHA: replace(control, candidate_episode_id="wrong")},
        )
    with pytest.raises(ValueError, match="INVALID_CONTROL_CLOCK_ORDER"):
        matched_benchmark(
            (cut,),
            (episode,),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={
                SHA: replace(control, outcome_known_at=(NOW + timedelta(minutes=6)).isoformat())
            },
        )


def test_missing_follower_economics_are_counted_not_dropped_as_wins():
    cut, episode, control = example()
    report = matched_benchmark(
        (cut,),
        (replace(episode, net_r=None),),
        prior_strength=5,
        tail_probability_z="1.96",
        market_controls={SHA: control},
    )
    assert all(row.selected == 0 and row.missing_outcomes == 1 for row in report.rows)
    assert all(row.net_r_mean is None for row in report.rows)


@pytest.mark.parametrize(
    "changed",
    [
        {"instrument": "hyperliquid/mainnet:perp:default/ETH"},
        {"direction": "SHORT"},
        {"horizon_minutes": 60},
        {"modeled_cost_r": "0"},
        {"entry_at": (NOW + timedelta(minutes=6)).isoformat()},
        {"exit_at": (NOW + timedelta(minutes=19)).isoformat()},
        {"decision_at": (NOW + timedelta(minutes=2)).isoformat()},
    ],
)
def test_market_control_must_match_all_economic_dimensions(changed):
    cut, episode, control = example()
    with pytest.raises(ValueError, match="CONTROL_INSTRUMENT_CLOCK_HORIZON_OR_COST_MISMATCH"):
        matched_benchmark(
            (cut,),
            (episode,),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={SHA: replace(control, **changed)},
        )


def test_repeated_candidate_cannot_inflate_evaluation_denominator():
    cut, episode, control = example()
    with pytest.raises(ValueError, match="REUSED_BENCHMARK_CANDIDATE"):
        matched_benchmark(
            (cut, cut),
            (episode,),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={SHA: control},
        )


def test_policy_mismatch_fail_closed_and_missing_controls_nullable():
    cut, episode, control = example()
    with pytest.raises(ValueError, match="CONTROL_EXECUTION_POLICY_MISMATCH"):
        matched_benchmark(
            (cut,),
            (episode,),
            prior_strength=5,
            tail_probability_z="1.96",
            market_controls={SHA: replace(control, policy_sha256="0" * 64)},
        )
    report = matched_benchmark(
        (cut,),
        (episode,),
        prior_strength=5,
        tail_probability_z="1.96",
    )
    assert report.rows[0].selected == 1
    assert report.rows[0].net_r_vs_market_control is None
    assert report.rows[0].missing_controls == 1
