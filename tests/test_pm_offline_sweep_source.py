"""Source-book completeness and conservative equity as-of contract."""

from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid
from copytrade_pm.pm_offline_source import reconstruct_whole_books

T = datetime(2026, 10, 20, tzinfo=UTC)


def inputs():
    return {
        "fills": [
            {
                "account": "W001",
                "dex": "default",
                "instrument": "BTC",
                "event_id": "a",
                "source_event_at": T + timedelta(minutes=2),
                "first_known_at": T + timedelta(minutes=2),
                "position_before": "1",
                "position_after": "2",
            },
            {
                "account": "W001",
                "dex": "default",
                "instrument": "ETH",
                "event_id": "b",
                "source_event_at": T + timedelta(minutes=3),
                "first_known_at": T + timedelta(minutes=3),
                "position_before": "-3",
                "position_after": "-2",
            },
        ],
        "initial_books": [
            {
                "account": "W001",
                "dex": "default",
                "first_known_at": T,
                "atomic_source_verified": True,
                "positions": {"BTC": "1", "ETH": "-3"},
            }
        ],
        "equity_snapshots": [
            {
                "account": "W001",
                "dex": "default",
                "first_known_at": T,
                "equity": "1000",
                "source_verified": True,
            }
        ],
        "required_instruments": {("W001", "default"): {"BTC", "ETH"}},
        "clock_basis": "HISTORICAL_ORACLE",
        "asof_max_age": timedelta(hours=1),
    }


def compile_data(**changes):
    data = inputs()
    data.update(changes)
    return reconstruct_whole_books(**data)


def test_book_and_equity_are_complete_and_deterministic():
    a = compile_data()
    b = compile_data(fills=inputs()["fills"][::-1])
    assert a["sha256"] == b["sha256"]
    assert a["events"][0]["whole_book_after"] == {"BTC": "2", "ETH": "-3"}
    assert a["events"][1]["whole_book_after"] == {"BTC": "2", "ETH": "-2"}
    assert all(x["source_equity"] == "1000" for x in a["events"])


def test_missing_initial_hedge_blocks():
    data = inputs()
    data["initial_books"][0]["positions"].pop("ETH")
    with pytest.raises(ManifestBlocked, match="INCOMPLETE_INITIAL_HEDGE_BOOK"):
        reconstruct_whole_books(**data)


def test_unverified_atomic_source_blocks():
    data = inputs()
    data["initial_books"][0]["atomic_source_verified"] = False
    with pytest.raises(ManifestBlocked, match="UNVERIFIED_ATOMIC_SOURCE_BOOK"):
        reconstruct_whole_books(**data)


def test_source_position_discontinuity_blocks():
    data = inputs()
    data["fills"][1]["position_before"] = "0"
    with pytest.raises(ManifestBlocked, match="SOURCE_POSITION_DISCONTINUITY"):
        reconstruct_whole_books(**data)


def test_future_only_equity_and_stale_equity_block():
    data = inputs()
    data["equity_snapshots"][0]["first_known_at"] = T + timedelta(days=1)
    with pytest.raises(ManifestBlocked, match="FUTURE_ONLY_SOURCE_EQUITY"):
        reconstruct_whole_books(**data)
    data = inputs()
    data["asof_max_age"] = timedelta(minutes=1)
    with pytest.raises(ManifestBlocked, match="STALE_SOURCE_EQUITY"):
        reconstruct_whole_books(**data)


def test_bad_or_zero_equity_blocks():
    data = inputs()
    data["equity_snapshots"][0]["equity"] = "0"
    with pytest.raises(ManifestBlocked, match="NONPOSITIVE_SOURCE_EQUITY"):
        reconstruct_whole_books(**data)


def test_dex_and_account_cannot_share_initial_state():
    data = inputs()
    data["fills"][0]["dex"] = "xyz"
    with pytest.raises(ManifestBlocked, match="SOURCE_INSTRUMENT_OUTSIDE_COMPLETE_BOOK"):
        reconstruct_whole_books(**data)


def test_duplicate_source_tid_rejected():
    data = inputs()
    data["fills"].append(dict(data["fills"][0]))
    with pytest.raises(ManifestInvalid, match="DUPLICATE_SOURCE_FILL"):
        reconstruct_whole_books(**data)
