"""Whole-book source eligibility, cross-instrument causality, as-of admission."""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("polars")

from copytrade_pm.pm_offline_intents import compile_whole_book_intents
from copytrade_pm.pm_offline_manifest import ManifestBlocked

T = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
BTC = "hyperliquid:mainnet:perp:default:BTC"
ETH = "hyperliquid:mainnet:perp:default:ETH"


def opening(qty="0", *, equity_at=None, known_at=None, prices=None):
    known = known_at or T - timedelta(minutes=1)
    return {
        ("W001", "default"): {
            "account": "W001",
            "dex": "default",
            "atomic_source_verified": True,
            "positions": {"BTC": qty, "ETH": "0"},
            "leader_prices": {"BTC": "100"} if qty != "0" else (prices or {}),
            "first_known_at": known,
            "first_known_basis": "HISTORICAL_ORACLE",
            "source_equity": "1000",
            "source_equity_known_at": equity_at or known,
        }
    }


def event(id, instrument, sec, *, qty, book, px=None):
    known = T + timedelta(seconds=sec)
    return {
        "account": "W001",
        "dex": "default",
        "instrument": instrument,
        "event_id": id,
        "source_event_at": known,
        "first_known_at": known,
        "position_after": qty,
        "whole_book_after": book,
        "leader_prices": px or {"BTC": "100", "ETH": "151"},
        "source_equity": "1000",
        "source_equity_known_at": T - timedelta(minutes=1),
    }


def compile(events, anchors=None, *, delay=0, max_age=1440, engine="streaming"):
    return compile_whole_book_intents(
        events,
        anchors or opening(),
        delay_minutes=delay,
        start=T,
        end=T + timedelta(minutes=15),
        max_equity_age_minutes=max_age,
        clock_basis="HISTORICAL_ORACLE",
        engine=engine,
    )


@pytest.mark.parametrize("delay", [0, 1, 2, 5, 10])
def test_latest_eligible_complete_book_wins_across_instruments(delay):
    # ETH was seen first, BTC later, but lexical BTC sorts BEFORE ETH.
    # The last-known BTC event must supply the final complete book.
    early = event(
        "eth-first",
        "ETH",
        5,
        qty="2",
        book={"BTC": "0", "ETH": "2"},
        px={"BTC": "100", "ETH": "150"},
    )
    late = event(
        "btc-latest",
        "BTC",
        30,
        qty="1",
        book={"BTC": "1", "ETH": "2"},
        px={"BTC": "101", "ETH": "151"},
    )
    a = compile([early, late], delay=delay)
    b = compile([late, early], delay=delay, engine="in-memory")
    assert a["sha256"] == b["sha256"]
    at = (T + timedelta(minutes=delay + 1)).isoformat()
    row = next(u for u in a["updates"][at] if u["manager"] == "W001")
    assert row["book"] == {BTC: "1", ETH: "2"}
    assert row["leader_prices"] == {BTC: "101", ETH: "151"}
    assert row["source_event_id"] == "btc-latest"
    assert row["source_known_at"] == (T + timedelta(seconds=30)).isoformat()


def test_nonflat_initial_book_is_an_explicit_eligible_admission():
    anchor = opening("1")
    first = event("new", "BTC", 10, qty="2", book={"BTC": "2", "ETH": "0"})
    result = compile([first], anchor, delay=2)
    # Anchor known 11:59:00, due strictly after 12:01:00 -> 12:02.
    assert result["updates"][(T + timedelta(minutes=2)).isoformat()][0]["book"][BTC] == "1"
    assert result["updates"][(T + timedelta(minutes=3)).isoformat()][0]["book"][BTC] == "2"


def test_missing_nonflat_initial_leader_mark_blocks():
    anchor = opening("1")
    anchor[("W001", "default")]["leader_prices"] = {}
    first = event("new", "BTC", 10, qty="2", book={"BTC": "2", "ETH": "0"})
    with pytest.raises(ManifestBlocked, match="MISSING_NONZERO_HEDGE_LEADER_PRICE"):
        compile([first], anchor)


def test_unpriced_atomic_flat_hedge_is_not_inferred_from_future_fill():
    first = event("later", "BTC", 90, qty="1", book={"BTC": "1", "ETH": "0"})
    result = compile([first], opening())
    initial = result["updates"][T.isoformat()][0]
    assert initial["book"] == {BTC: "0", ETH: "0"}
    assert initial["leader_prices"] == {}


def test_equity_staleness_evaluated_at_actual_execution_not_fill_time():
    first = event("f", "BTC", 0, qty="1", book={"BTC": "1", "ETH": "0"})
    with pytest.raises(ManifestBlocked, match="STALE_SOURCE_EQUITY_AT_EXECUTION"):
        compile([first], delay=10, max_age=5)


def test_future_or_unverified_opening_book_blocks():
    first = event("f", "BTC", 0, qty="1", book={"BTC": "1", "ETH": "0"})
    anchor = opening(known_at=T + timedelta(minutes=3))
    with pytest.raises(ManifestBlocked, match="EVENT_KNOWN_BEFORE_OPENING_BOOK"):
        compile([first], anchor, delay=0)
    anchor = opening()
    anchor[("W001", "default")]["atomic_source_verified"] = False
    with pytest.raises(ManifestBlocked, match="UNVERIFIED_ATOMIC_OPENING_BOOK"):
        compile([first], anchor)


def test_later_not_eligible_event_cannot_change_earlier_target():
    earlier = event("early", "BTC", 10, qty="1", book={"BTC": "1", "ETH": "0"})
    later = event("later", "BTC", 70, qty="9", book={"BTC": "9", "ETH": "0"})
    base = compile([earlier], delay=2)
    full = compile([earlier, later], delay=2)
    due = (T + timedelta(minutes=3)).isoformat()
    assert base["updates"][due] == full["updates"][due]
    assert full["updates"][(T + timedelta(minutes=4)).isoformat()][0]["book"][BTC] == "9"
