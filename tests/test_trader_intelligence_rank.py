"""Research-only specialized wallet ranking; no A/B or automatic orders."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from copytrade_pm.trader_intelligence import (
    ObservationSnapshot,
    TraderIntelligence,
    WalletEvent,
    WalletIdentity,
)
from copytrade_pm.trader_intelligence_research import (
    FollowerEpisode,
    rank_research_opportunities,
)

NOW = datetime(2026, 10, 13, 10, tzinfo=UTC)
BTC = "hyperliquid/mainnet:perp:default/BTC"
ETH = "hyperliquid/mainnet:perp:default/ETH"
SHA = sha256(b"policy").hexdigest()


def sample():
    wallets = tuple(
        WalletIdentity(name, sha256(name.encode()).hexdigest(), cluster=cluster)
        for name, cluster in (
            ("A", "parent-clone"),
            ("B", "parent-clone"),
            ("C", "independent"),
            ("D", "eth-specialist"),
        )
    )
    events = tuple(
        WalletEvent(
            event_id=f"trade-{wallet}",
            wallet=wallet,
            instrument=market,
            event_at=(NOW - timedelta(minutes=3)).isoformat(),
            first_known_at=(NOW - timedelta(minutes=2)).isoformat(),
            origin="PROSPECTIVE_OBSERVED",
            position_before="0",
            position_after="1",
            book_complete=True,
            source_equity_usd="10000",
            strategy_style="DIRECTIONAL",
        )
        for wallet, market in (("A", BTC), ("B", BTC), ("C", BTC), ("D", ETH))
    )
    return ObservationSnapshot(
        "research-roster",
        (NOW - timedelta(days=3)).isoformat(),
        wallets,
        events,
        "PROSPECTIVE_OBSERVED",
    )


def label(wallet, market, value, *, future=False):
    completed = NOW + timedelta(hours=1) if future else NOW - timedelta(hours=10)
    return FollowerEpisode(
        episode_id=f"matured-{wallet}-{market}",
        wallet=wallet,
        instrument=market,
        direction="LONG",
        strategy_style="DIRECTIONAL",
        cluster_id="parent-clone" if wallet in ("A", "B") else wallet,
        origin="PROSPECTIVE_OBSERVED",
        observation_at=(completed - timedelta(minutes=20)).isoformat(),
        first_known_at=(completed - timedelta(minutes=20)).isoformat(),
        hypothetical_entry_at=(completed - timedelta(minutes=15)).isoformat(),
        hypothetical_exit_at=completed.isoformat(),
        outcome_known_at=completed.isoformat(),
        horizon_minutes=15,
        net_r=str(value),
        gross_r=str(value),
        cost_r="0",
        source_pnl_usd="5000",
        status="OK",
        group_id=f"{wallet}-episode",
        policy_sha256=SHA,
    )


def test_wallet_instrument_specialization_and_clone_aware_rank():
    snap = sample()
    assessments = TraderIntelligence().evaluate(snap, NOW.isoformat())
    labels = (
        label("A", BTC, "3"),
        label("B", BTC, "-2"),
        label("C", BTC, "0.1"),
        label("D", ETH, "3"),
    )
    rows = rank_research_opportunities(
        assessments,
        snap,
        labels,
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    by_market = {x.instrument: x for x in rows}
    assert len(rows) == 2
    assert by_market[ETH].rank == 1
    assert by_market[BTC].rank == 2
    assert by_market[BTC].independent_scored_clusters == 2
    assert by_market[BTC].matured_episode_groups == 2
    assert all(x.watch_grade == "C" for x in rows)
    assert all(x.cluster_conservative_lcb_r is not None for x in rows)


def test_future_label_never_improves_earlier_rank():
    snap = sample()
    engine = TraderIntelligence()
    scores = engine.evaluate(snap, NOW.isoformat())
    mature = (label("A", BTC, "1"),)
    future = (label("B", BTC, "1000", future=True),)
    baseline = rank_research_opportunities(
        scores,
        snap,
        mature,
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    extended = rank_research_opportunities(
        scores,
        snap,
        mature + future,
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    assert baseline == extended


def test_unsupported_positive_grade_rejected_even_with_positive_label():
    snap = sample()
    assessments = TraderIntelligence().evaluate(snap, NOW.isoformat())
    with pytest.raises(ValueError, match="RESEARCH_RANK_CANNOT_PROMOTE_GRADE"):
        rank_research_opportunities(
            (replace(assessments[0], grade="A", research_r="1"),),
            snap,
            (label("A", BTC, "1000"),),
            decision_at=NOW.isoformat(),
            prior_strength=3,
            tail_probability_z="1.96",
        )


def test_unknown_cluster_not_counted_as_independent_rank_evidence():
    snap = sample()
    wallets = tuple(
        replace(w, cluster=None, parent=None) if w.alias == "D" else w for w in snap.wallets
    )
    no_independence = replace(snap, wallets=wallets)
    rows = rank_research_opportunities(
        TraderIntelligence().evaluate(no_independence, NOW.isoformat()),
        no_independence,
        (label("D", ETH, "4"),),
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    eth = next(x for x in rows if x.instrument == ETH)
    assert eth.rank is None
    assert eth.independent_scored_clusters is None
    assert "INDEPENDENCE_UNVERIFIED" in eth.reasons


def test_parent_identity_overrides_distinct_cluster_labels():
    snap = sample()
    wallets = tuple(
        replace(w, parent="shared-parent", cluster=f"independent-{w.alias}")
        if w.alias in ("A", "B")
        else w
        for w in snap.wallets
    )
    related = replace(snap, wallets=wallets)
    rows = rank_research_opportunities(
        TraderIntelligence().evaluate(related, NOW.isoformat()),
        related,
        (label("A", BTC, "3"), label("B", BTC, "-2"), label("C", BTC, "0.1")),
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    btc = next(x for x in rows if x.instrument == BTC)
    assert btc.independent_scored_clusters == 2
    assert btc.evidence_class == "UNATTESTED_DIAGNOSTIC_ONLY"
    assert "UNATTESTED_REPLAY_NOT_FOLLOWER_PROOF" in btc.reasons


def test_forged_early_maturity_does_not_use_later_first_receipt():
    snap = sample()
    assessment = TraderIntelligence().evaluate(snap, NOW.isoformat())
    forged = replace(
        label("A", BTC, "20"),
        first_known_at=(NOW + timedelta(minutes=1)).isoformat(),
    )
    rows = rank_research_opportunities(
        assessment,
        snap,
        (forged,),
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    btc = next(x for x in rows if x.instrument == BTC)
    assert btc.rank is None
    assert btc.matured_episode_groups is None


def test_cross_horizon_or_cost_policy_not_pooled_as_one_skill():
    snap = sample()
    assessment = TraderIntelligence().evaluate(snap, NOW.isoformat())
    first = label("A", BTC, "2")
    second = replace(
        label("C", BTC, "3"),
        episode_id="different-policy-episode",
        policy_sha256="a" * 64,
    )
    rows = rank_research_opportunities(
        assessment,
        snap,
        (first, second),
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    btc = next(x for x in rows if x.instrument == BTC)
    assert btc.rank is None
    assert "INCOMPARABLE_LABEL_POLICY_OR_HORIZON" in btc.reasons


def test_matured_failed_episode_not_dropped_to_inflate_rank():
    snap = sample()
    assessment = TraderIntelligence().evaluate(snap, NOW.isoformat())
    failed = replace(
        label("C", BTC, "100"),
        episode_id="failed-exit",
        net_r=None,
        gross_r=None,
        cost_r=None,
        status="INTERIOR_MARKET_GAP",
        hypothetical_exit_at=None,
        outcome_known_at=None,
    )
    rows = rank_research_opportunities(
        assessment,
        snap,
        (label("A", BTC, "2"), failed),
        decision_at=NOW.isoformat(),
        prior_strength=3,
        tail_probability_z="1.96",
    )
    btc = next(x for x in rows if x.instrument == BTC)
    assert btc.rank is None
    assert "UNRESOLVED_MATURED_FOLLOWER_EPISODE" in btc.reasons


def test_conflicting_duplicate_episode_refused_not_selected_optimistically():
    snap = sample()
    initial = label("A", BTC, "1")
    with pytest.raises(ValueError, match="CONFLICTING_FOLLOWER_EPISODE"):
        rank_research_opportunities(
            TraderIntelligence().evaluate(snap, NOW.isoformat()),
            snap,
            (initial, replace(initial, net_r="100", gross_r="100")),
            decision_at=NOW.isoformat(),
            prior_strength=3,
            tail_probability_z="1.96",
        )
