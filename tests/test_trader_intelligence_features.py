"""PIT feature extraction: holding, parent dependence and no invented exposure."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from copytrade_pm.trader_intelligence import ObservationSnapshot, WalletEvent, WalletIdentity
from copytrade_pm.trader_intelligence_features import extract_asof_features, feature_report

NOW = datetime(2026, 11, 3, 2, tzinfo=UTC)
MARKET = "hyperliquid/mainnet:perp:default/BTC"


def event(eid, minutes, before, after, *, book=True, style="DIRECTIONAL", price="100"):
    t = NOW + timedelta(minutes=minutes)
    return WalletEvent(
        event_id=eid,
        wallet="W1",
        instrument=MARKET,
        event_at=t.isoformat(),
        first_known_at=t.isoformat(),
        origin="PROSPECTIVE_OBSERVED",
        position_before=before,
        position_after=after,
        book_complete=book,
        source_equity_usd="1000" if book else None,
        strategy_style=style,
        observed_price=price,
    )


def snapshot(*events):
    return ObservationSnapshot(
        "r1",
        (NOW - timedelta(days=1)).isoformat(),
        (WalletIdentity("W1", sha256(b"w1").hexdigest(), cluster="wrong-cluster", parent="P1"),),
        events,
        "PROSPECTIVE_OBSERVED",
    )


def test_reduce_long_is_still_long_and_tenure_starts_at_observed_open():
    s = snapshot(event("open", 0, "0", "4"), event("reduce", 2, "4", "2"))
    at = (NOW + timedelta(minutes=3)).isoformat()
    f = extract_asof_features(s, decision_at=at)[0]
    assert f.direction == "LONG"
    assert f.latest_transition == "REDUCE"
    assert f.independent_group == "parent:P1"
    assert f.holding_minutes_lower_bound == 3
    assert f.exposure_fraction_of_equity == "0.2"
    assert feature_report(s, decision_at=at) == feature_report(s, decision_at=at)


def test_future_fill_does_not_rewrite_prior_features():
    early = snapshot(event("open", 0, "0", "4"))
    extended = snapshot(*early.events, event("exit", 10, "4", "0"))
    at = (NOW + timedelta(minutes=3)).isoformat()
    assert feature_report(early, decision_at=at) == feature_report(extended, decision_at=at)


def test_incomplete_book_and_unknown_entry_are_not_zero_exposure_or_tenure():
    s = snapshot(event("add", 0, "10", "12", book=False))
    f = extract_asof_features(s, decision_at=(NOW + timedelta(minutes=1)).isoformat())[0]
    assert f.direction == "LONG"
    assert f.holding_minutes_lower_bound is None
    assert f.exposure_fraction_of_equity is None
    assert f.evidence_status == "INCOMPLETE_OR_UNKNOWN_BOOK"


def test_chain_gap_blocks_tenure_and_equity_normalization():
    s = snapshot(event("open", 0, "0", "4"), event("add", 1, "8", "9"))
    f = extract_asof_features(s, decision_at=(NOW + timedelta(minutes=2)).isoformat())[0]
    assert f.evidence_status == "UNKNOWN_OR_DISCONTINUOUS_POSITION_CHAIN"
    assert f.holding_minutes_lower_bound is None
    assert f.exposure_fraction_of_equity is None


def test_verified_hedged_or_unknown_style_never_promoted_to_directional():
    s = snapshot(event("open", 0, "0", "4", style="HEDGED_BASKET"))
    f = extract_asof_features(s, decision_at=(NOW + timedelta(minutes=1)).isoformat())[0]
    assert f.evidence_status == "NON_DIRECTIONAL_OR_UNKNOWN_STYLE"
    assert f.strategy_style == "HEDGED_BASKET"


def test_vendor_fill_never_becomes_prospective_local_first_known():
    e = replace(event("open", 0, "0", "4"), origin="HISTORICAL_PROXY", first_known_at=None)
    f = extract_asof_features(snapshot(e), decision_at=(NOW + timedelta(minutes=1)).isoformat())[0]
    assert f.first_known_at is None
    assert f.holding_minutes_lower_bound is None
    assert f.exposure_fraction_of_equity is None
    assert f.evidence_status == "RETROSPECTIVE_VENDOR_CLOCK_ONLY"


def test_future_roster_is_rejected():
    s = snapshot(event("open", 0, "0", "4"))
    with pytest.raises(ValueError, match="FUTURE_ROSTER"):
        extract_asof_features(
            replace(s, roster_known_at=(NOW + timedelta(minutes=5)).isoformat()),
            decision_at=NOW.isoformat(),
        )
