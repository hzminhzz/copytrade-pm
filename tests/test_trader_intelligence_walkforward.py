"""Read-only walk-forward matched-economics falsification contracts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from copytrade_pm.trader_intelligence import ObservationSnapshot, WalletEvent, WalletIdentity
from copytrade_pm.trader_intelligence_research import (
    CandidateCut,
    FollowerEpisode,
    MatchedMarketControl,
)
from copytrade_pm.trader_intelligence_walkforward import (
    WalkForwardFold,
    walkforward_diagnostic,
)

START = datetime(2026, 11, 5, tzinfo=UTC)
MARKET = "hyperliquid/mainnet:perp:default/BTC"
SHA = sha256(b"policy").hexdigest()


def fixtures(days=6):
    wallets = tuple(
        WalletIdentity(f"W{i}", sha256(f"W{i}".encode()).hexdigest(), cluster=f"independent-{i}")
        for i in range(3)
    )
    cuts, labels, controls = [], [], {}
    for day in range(days):
        now = START + timedelta(days=day)
        events = tuple(
            WalletEvent(
                event_id=f"{day}-{i}",
                wallet=f"W{i}",
                instrument=MARKET,
                event_at=now.isoformat(),
                first_known_at=now.isoformat(),
                origin="PROSPECTIVE_OBSERVED",
                position_before="0",
                position_after="1",
                book_complete=True,
                source_equity_usd="1000",
                strategy_style="DIRECTIONAL",
            )
            for i in range(3)
        )
        snap = ObservationSnapshot(
            "registered",
            (START - timedelta(days=2)).isoformat(),
            wallets,
            events,
            "PROSPECTIVE_OBSERVED",
        )
        episode_id = sha256(f"episode-{day}".encode()).hexdigest()
        cuts.append(
            CandidateCut(
                (now + timedelta(minutes=1)).isoformat(),
                snap,
                MARKET,
                "LONG",
                episode_id,
                roster_is_point_in_time=True,
            )
        )
        labels.append(
            FollowerEpisode(
                episode_id=episode_id,
                wallet="W0",
                instrument=MARKET,
                direction="LONG",
                strategy_style="DIRECTIONAL",
                cluster_id="independent-0",
                origin="PROSPECTIVE_OBSERVED",
                observation_at=now.isoformat(),
                first_known_at=now.isoformat(),
                hypothetical_entry_at=(now + timedelta(minutes=6)).isoformat(),
                hypothetical_exit_at=(now + timedelta(minutes=21)).isoformat(),
                outcome_known_at=(now + timedelta(minutes=21)).isoformat(),
                horizon_minutes=15,
                net_r="-0.5",
                gross_r="-0.4",
                cost_r="0.1",
                source_pnl_usd=None,
                status="OK",
                group_id=f"group-{day}",
                policy_sha256=SHA,
            )
        )
        controls[episode_id] = MatchedMarketControl(
            candidate_episode_id=episode_id,
            policy_sha256=SHA,
            control_net_r="-0.1",
            source_sha256=SHA,
            outcome_known_at=(now + timedelta(minutes=21)).isoformat(),
        )
    return cuts, labels, controls


def fold(days=6):
    return WalkForwardFold(
        START.isoformat(),
        (START + timedelta(days=days)).isoformat(),
    )


def run(cuts, labels, controls, folds=None):
    return walkforward_diagnostic(
        cuts,
        labels,
        (fold(),) if folds is None else folds,
        plan_sha256=SHA,
        market_controls=controls,
        prior_strength=5,
        tail_probability_z="1.96",
        bootstrap_repetitions=200,
    )


def test_frozen_same_universe_matched_negative_economics_with_block_uncertainty():
    cuts, labels, controls = fixtures()
    result = run(cuts, labels, controls)
    incumbent = result.folds[0].policies[0]
    assert incumbent.evaluated == 6
    assert incumbent.selected == 6
    assert incumbent.matched == 6
    assert float(incumbent.paired_mean_r) == pytest.approx(-0.4)
    assert float(incumbent.day_block_lcb_r) == pytest.approx(-0.4)
    assert incumbent.day_count == 6
    assert result.qualification == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert result == run(cuts, labels, controls)


def test_missing_control_preserved_and_confidence_unavailable():
    cuts, labels, controls = fixtures()
    del controls[labels[0].episode_id]
    report = run(cuts, labels, controls)
    row = report.folds[0].policies[0]
    assert row.missing_controls == 1
    assert row.matched == 5
    assert row.day_block_lcb_r is None


def test_duplicate_candidate_and_invalid_embargo_rejected():
    cuts, labels, controls = fixtures()
    with pytest.raises(ValueError, match="REUSED_CANDIDATE_EPISODE"):
        run(cuts + [cuts[0]], labels, controls)
    split = (
        WalkForwardFold(START.isoformat(), (START + timedelta(days=2)).isoformat()),
        WalkForwardFold(
            (START + timedelta(days=2)).isoformat(),
            (START + timedelta(days=6)).isoformat(),
        ),
    )
    with pytest.raises(ValueError, match="OVERLAPPING_OR_UNEMBARGOED_FOLDS"):
        run(cuts, labels, controls, split)


def test_outside_declared_future_fold_is_not_silently_removed():
    cuts, labels, controls = fixtures()
    with pytest.raises(ValueError, match="CANDIDATE_OUTSIDE_DECLARED_FOLDS"):
        run(cuts, labels, controls, (fold(4),))


def test_control_identity_mismatch_fail_closed():
    cuts, labels, controls = fixtures()
    controls[labels[0].episode_id] = replace(
        controls[labels[0].episode_id], candidate_episode_id="wrong"
    )
    with pytest.raises(ValueError, match="CONTROL_EPISODE_IDENTITY_MISMATCH"):
        run(cuts, labels, controls)


def test_missing_follower_is_counted_not_hidden_in_fold():
    cuts, labels, controls = fixtures()
    labels[0] = replace(labels[0], net_r=None)
    report = run(cuts, labels, controls)
    assert report.folds[0].policies[0].missing_outcomes == 1
    assert report.folds[0].policies[0].selected == 5
