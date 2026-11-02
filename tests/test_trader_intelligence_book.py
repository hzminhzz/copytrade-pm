"""Whole-book PIT specialization and clone-resistance regressions."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from dataclasses import replace

import pytest

from copytrade_pm.trader_intelligence import (
    ObservationSnapshot,
    Calibration,
    TraderIntelligence,
    WalletEvent,
    WalletIdentity,
)
from copytrade_pm.trader_intelligence_book import CoherentBook, enrich_with_books

AT = datetime(2026, 10, 13, 10, tzinfo=UTC)
BTC = "hyperliquid/mainnet:perp:default/BTC"
ETH = "hyperliquid/mainnet:perp:default/ETH"
SHA = sha256(b"book").hexdigest()


def snapshot(*, origin="PROSPECTIVE_OBSERVED", count=1, same_cluster=False):
    wallets = tuple(
        WalletIdentity(
            f"wallet{i}",
            sha256(f"wallet{i}".encode()).hexdigest(),
            cluster="parent-group" if same_cluster else f"cluster{i}",
        )
        for i in range(count)
    )
    events = tuple(
        WalletEvent(
            event_id=f"e{i}",
            wallet=f"wallet{i}",
            instrument=BTC,
            event_at=(AT - timedelta(minutes=3)).isoformat(),
            first_known_at=(
                (AT - timedelta(minutes=2)).isoformat() if origin != "HISTORICAL_PROXY" else None
            ),
            origin=origin,
            position_before="0",
            position_after="2",
            strategy_style="UNKNOWN",
            book_complete=None,
        )
        for i in range(count)
    )
    return ObservationSnapshot(
        "roster",
        (AT - timedelta(days=1)).isoformat(),
        wallets,
        events,
        "HISTORICAL_PROXY" if origin == "HISTORICAL_PROXY" else "PROSPECTIVE_OBSERVED",
    )


def book(
    wallet="wallet0",
    *,
    positions=((BTC, "2"),),
    time=AT,
    spot=True,
    chain=True,
    eq="10000",
    strat=None,
):
    return CoherentBook(
        wallet=wallet,
        source_event_at=time.isoformat(),
        first_known_at=time.isoformat(),
        source_sha256=SHA,
        equity_usd=eq,
        positions=positions,
        all_dexes_complete=True,
        subaccounts_complete=True,
        spot_exposure_verified_absent=spot,
        position_chain_complete=chain,
        account_mode="STANDARD_SEPARATE_DEX_BALANCES",
        verified_strategy=strat,
    )


def test_only_full_coherent_asof_book_supplies_equity_and_specialization():
    before = snapshot()
    after = enrich_with_books(before, (book(),), decision_at=AT.isoformat())
    assert before.events[0].source_equity_usd is None
    assert after.events[0].source_equity_usd == "10000"
    assert after.events[0].strategy_style == "DIRECTIONAL"
    assert after.events[0].book_complete is True
    assert after.events[0].book_id == book().version_sha256
    grade = TraderIntelligence().evaluate(after, AT.isoformat())[0]
    assert grade.grade == "C"
    assert grade.research_r == "0"


def test_mixed_signed_whole_book_blocks_directional_signal():
    after = enrich_with_books(
        snapshot(),
        (book(positions=((BTC, "2"), (ETH, "-2"))),),
        decision_at=AT.isoformat(),
    )
    assert after.events[0].strategy_style == "HEDGED_BASKET"
    grade = TraderIntelligence().evaluate(after, AT.isoformat())[0]
    assert grade.grade == "X"
    assert "HEDGED_BASKET" in grade.reasons


def test_spot_chain_unknown_and_wrong_position_do_not_enrich():
    before = snapshot()
    for bad_book in (
        book(spot=False),
        book(chain=False),
        book(eq=None),
        book(positions=((BTC, "5"),)),
    ):
        after = enrich_with_books(before, (bad_book,), decision_at=AT.isoformat())
        assert after.events[0].source_equity_usd is None
        assert after.events[0].book_complete is None


def test_future_book_cannot_change_prior_decision_or_hash():
    later = book(time=AT + timedelta(minutes=15))
    before = snapshot()
    s1 = enrich_with_books(before, (), decision_at=AT.isoformat())
    s2 = enrich_with_books(before, (later,), decision_at=AT.isoformat())
    assert s1.sha256 == s2.sha256
    assert TraderIntelligence().evaluate(s1, AT.isoformat()) == TraderIntelligence().evaluate(
        s2, AT.isoformat()
    )


def test_historical_vendor_event_not_converted_to_prospective():
    s = snapshot(origin="HISTORICAL_PROXY")
    result = enrich_with_books(s, (book(),), decision_at=AT.isoformat())
    assert result.events[0].book_complete is None
    assert result.events[0].first_known_at is None


def test_same_cut_conflicting_source_book_rejected():
    with pytest.raises(ValueError, match="CONTRADICTORY_SAME_CUT_BOOK"):
        enrich_with_books(
            snapshot(),
            (book(), replace(book(), source_sha256=sha256(b"other").hexdigest())),
            decision_at=AT.isoformat(),
        )


def test_parent_related_wallets_do_not_multiply_independent_votes():
    s = snapshot(count=2, same_cluster=True)
    enriched = enrich_with_books(s, (book(), book(wallet="wallet1")), decision_at=AT.isoformat())
    grade = TraderIntelligence().evaluate(enriched, AT.isoformat())[0]
    assert grade.qualified_contributors == 2
    assert grade.independent_clusters == 1
    assert "DEPENDENT_SOURCE_WALLETS" in grade.reasons


def test_unattested_positive_estimates_never_manufacture_a_b():
    base = enrich_with_books(snapshot(), (book(),), decision_at=AT.isoformat())
    model = sha256(b"unfitted-ti-v1").hexdigest()
    policy = sha256(b"research-only-ti-v1").hexdigest()
    calib = Calibration(
        model_sha256=model,
        policy_sha256=policy,
        calibrated_at=(AT - timedelta(hours=1)).isoformat(),
        training_end_at=(AT - timedelta(hours=2)).isoformat(),
        evidence_origin="PROSPECTIVE_OBSERVED",
        a_lower_bound_r="0.5",
        b_lower_bound_r="0.1",
        evidence_sha256=SHA,
    )
    a = TraderIntelligence(calibration=calib).evaluate(
        base,
        AT.isoformat(),
        follower_evidence={(BTC, "LONG"): ("100", "100")},
    )[0]
    assert a.grade == "C"
    assert "UNATTESTED_FOLLOWER_ESTIMATE_NO_A_B" in a.reasons


def test_funding_carry_verified_style_rejected():
    enriched = enrich_with_books(
        snapshot(),
        (book(strat="FUNDING_CARRY"),),
        decision_at=AT.isoformat(),
    )
    grade = TraderIntelligence().evaluate(enriched, AT.isoformat())[0]
    assert grade.grade == "X"
    assert grade.research_r == "0"
