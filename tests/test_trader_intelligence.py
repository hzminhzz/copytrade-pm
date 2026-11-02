"""Public Trader Intelligence boundary regression tests."""

from hashlib import sha256

import pytest

from copytrade_pm.trader_intelligence import (
    ObservationSnapshot,
    TraderIntelligence,
    WalletEvent,
    WalletIdentity,
    assessment_document,
    canonical,
    digest,
)
from copytrade_pm.trader_intelligence_research import (
    FollowerPolicy,
    MinuteBar,
    follower_replay,
)

SHA = sha256(b"known").hexdigest()
MARKET = "hyperliquid/mainnet:perp:default/BTC"
T0 = "2026-10-01T00:00:00Z"
T1 = "2026-10-01T00:01:00Z"
T10 = "2026-10-01T00:10:00Z"


def event(
    *,
    before="0",
    after="2",
    eid="a",
    first=None,
    origin="HISTORICAL_PROXY",
    style="DIRECTIONAL",
    book=True,
    eq="10000",
    wallet="W1",
):
    return WalletEvent(
        event_id=eid,
        wallet=wallet,
        instrument=MARKET,
        event_at=T0,
        first_known_at=first,
        origin=origin,
        position_before=before,
        position_after=after,
        strategy_style=style,
        book_complete=book,
        source_equity_usd=eq,
    )


def snapshot(*events, size=1):
    return ObservationSnapshot(
        "roster",
        T0,
        tuple(
            WalletIdentity(f"W{i}", sha256(f"W{i}".encode()).hexdigest(), cluster=f"C{i}")
            for i in range(1, size + 1)
        ),
        tuple(events),
        "HISTORICAL_PROXY",
    )


def policy():
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
    )


def bars(count=24, *, price="100", exit_price="99"):
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 10, 1, tzinfo=UTC)
    return tuple(
        MinuteBar(
            MARKET,
            (start + timedelta(minutes=i)).isoformat(),
            exit_price if i >= 20 else price,
            exit_price if i >= 20 else price,
            exit_price if i >= 20 else price,
            exit_price if i >= 20 else price,
            "100000",
        )
        for i in range(count)
    )


def test_deterministic_document_no_alpha_without_calibration():
    engine = TraderIntelligence()
    snap = snapshot(event())
    a = engine.evaluate(snap, T1)
    assert len(a) == 1
    assert a[0].grade == "C"
    assert a[0].research_r == "0"
    assert a[0].claim_status == "NOT_QUALIFIED"
    assert a[0].first_known_at is None
    assert a[0].independent_clusters == 1
    doc = assessment_document(a, decision_at=T1, source_sha256=SHA)
    assert doc["order_authorized"] is False
    assert canonical(doc) == canonical(
        assessment_document(engine.evaluate(snap, T1), decision_at=T1, source_sha256=SHA)
    )
    assert digest(doc) == digest(doc)


@pytest.mark.parametrize(
    "before,after,transition,direction",
    [
        ("5", "2", "REDUCE", None),
        ("5", "0", "EXIT", None),
        ("5", "-2", "REVERSE", "SHORT"),
        ("0", "-3", "OPEN", "SHORT"),
        ("-5", "-8", "ADD", "SHORT"),
        ("-5", "-2", "REDUCE", None),
    ],
)
def test_position_semantics(before, after, transition, direction):
    e = event(before=before, after=after)
    assert e.transition == transition
    assert e.direction == direction


def test_historical_proxy_never_first_known():
    with pytest.raises(ValueError, match="VENDOR_TIME_CANNOT_BE_FIRST_KNOWN"):
        event(first=T1)


def test_invalid_future_receipt_and_roster():
    with pytest.raises(ValueError, match="INVALID_FIRST_KNOWN_CLOCK"):
        event(first="2026-09-30T23:59:00Z", origin="PROSPECTIVE_OBSERVED")
    s = snapshot(event())
    assert TraderIntelligence().evaluate(s, T1)
    with pytest.raises(ValueError, match="FUTURE_ROSTER"):
        TraderIntelligence().evaluate(s, "2026-09-30T23:00:00Z")


def test_arbitrary_roster_not_frozen_36():
    for n in (1, 36, 94):
        s = snapshot(event(), size=n)
        assert len(s.wallets) == n
        assert TraderIntelligence().evaluate(s, T1)[0].grade == "C"


def test_conflicting_event_versions_rejected():
    with pytest.raises(ValueError, match="CONTRADICTORY_EVENT_REVISION"):
        snapshot(event(), event(after="-1"))


def test_carry_rejected_and_missing_equity_is_unknown():
    a = TraderIntelligence().evaluate(snapshot(event(style="FUNDING_CARRY")), T1)[0]
    assert a.grade == "X" and "FUNDING_CARRY" in a.reasons
    b = TraderIntelligence().evaluate(snapshot(event(eq=None)), T1)[0]
    assert b.grade == "C"
    assert b.qualified_contributors is None


def test_reduction_cannot_signal_short():
    assert TraderIntelligence().evaluate(snapshot(event(before="10", after="3")), T1) == ()


def test_follower_source_winner_can_lose_after_delay_and_cost():
    outcomes = follower_replay(
        snapshot(event()), bars(), policy(), source_pnl_by_event={"a": "1000"}
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "OK"
    assert outcomes[0].source_pnl_usd == "1000"
    assert float(outcomes[0].net_r) < 0
    assert outcomes[0].hypothetical_entry_at == "2026-10-01T00:05:00Z"
    assert outcomes[0].hypothetical_exit_at == "2026-10-01T00:20:00Z"


def test_incomplete_price_series_unknown_not_zero():
    outcomes = follower_replay(snapshot(event()), bars(8), policy())
    assert outcomes[0].net_r is None
    assert outcomes[0].status == "UNOBSERVED_EXIT"


def test_following_reduction_not_an_episode():
    outcomes = follower_replay(snapshot(event(before="4", after="2")), bars(), policy())
    assert outcomes[0].status == "NOT_DIRECTIONAL_ENTRY"
    assert outcomes[0].net_r is None


def test_late_observation_not_backdated_into_decision():
    e = event(first=T10, origin="PROSPECTIVE_OBSERVED")
    s = ObservationSnapshot(
        "prospective", T0, (WalletIdentity("W1", SHA, cluster="one"),), (e,), "PROSPECTIVE_OBSERVED"
    )
    assert TraderIntelligence().evaluate(s, T1) == ()
    assert TraderIntelligence().evaluate(s, T10)[0].grade == "C"
