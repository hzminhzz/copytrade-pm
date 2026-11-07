"""Shared Vike fill journal: native identity, PIT clocks and restart recovery."""
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.pm_vike_selected_fills import (
    apply_frame, current_cursor, had_gap, open_selected_journal,
    record_event, selected_subscription,
)


W1 = "0x" + "a" * 40
W2 = "0x" + "b" * 40
T = datetime.now(UTC)


def event(wallet=W1, tid=101, *, usd=3.5):
    return {
        "schema": "vike.event.v1", "source": "hl.fills",
        "kind": "fill", "event_id": f"hl.fills:{wallet}:test:{tid}",
        "subject": {"wallet": wallet, "symbol": "xyz:BRENTOIL"},
        "ts": (T - timedelta(seconds=2)).isoformat(),
        "data": {"trade_id": tid, "price": 65, "size_token": .05,
                 "size_usd": usd, "side": "buy"},
    }


def frame(wallet=W1, tid=101, cursor="1793930404464-0001"):
    return {"type": "event", "ids": ["copytrade_selected"],
            "cursor": cursor, "event": event(wallet, tid)}


def test_shared_subscription_zero_minimum_and_distinct_native_wallets():
    sub = selected_subscription((W2, W1), None)
    assert sub["filter"] == {"wallet": [W1, W2], "min_usd": 0}
    with pytest.raises(ValueError, match="UNIVERSE_INVALID"):
        selected_subscription((W1, W1), None)


def test_two_wallets_atomic_cursor_dedupe_and_private_restart(tmp_path):
    root = tmp_path / "selected"
    with closing(open_selected_journal(root)) as db:
        assert apply_frame(db, frame(), (W1, W2), T.isoformat()) == "PROSPECTIVE_FILL"
        assert apply_frame(db, frame(W2, 102, "1793930404464-0002"),
                           (W1, W2), T.isoformat()) == "PROSPECTIVE_FILL"
        assert apply_frame(db, frame(), (W1, W2), T.isoformat()) == "DUPLICATE"
        assert current_cursor(db) == "1793930404464-0002"
        assert db.execute("SELECT count(*) FROM selected_fills").fetchone()[0] == 2
        assert db.execute("SELECT min(prospective) FROM selected_fills").fetchone()[0] == 1
    with closing(open_selected_journal(root)) as db:
        assert current_cursor(db) == "1793930404464-0002"
        assert db.execute("SELECT count(*) FROM selected_fills").fetchone()[0] == 2
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / "selected-fills.sqlite3").stat().st_mode & 0o777 == 0o600


def test_duplicate_payload_drift_does_not_advance_checkpoint(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        apply_frame(db, frame(), (W1, W2), T.isoformat())
        altered = frame(cursor="1793930404464-0002")
        altered["event"]["data"]["price"] = 80
        with pytest.raises(ValueError, match="PAYLOAD_DRIFT"):
            apply_frame(db, altered, (W1, W2), T.isoformat())
        assert current_cursor(db) == "1793930404464-0001"


def test_retroactive_rest_does_not_manufacture_prospective_known_time(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        result = record_event(
            db, event(), cursor="1793930404464-0001",
            known_at=T.isoformat(), wallets=(W1, W2), prospective=False,
        )
        assert result == "RECOVERED_FILL"
        assert db.execute("SELECT prospective FROM selected_fills").fetchone()[0] == 0
        assert apply_frame(db, frame(), (W1, W2), T.isoformat()) == "DUPLICATE"
        assert db.execute("SELECT prospective FROM selected_fills").fetchone()[0] == 0


def test_gap_remains_latched_and_cannot_be_explained_away(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        assert apply_frame(
            db, {"type": "gap", "channel": "hl.fills",
                 "cursor": "1793930404464-0001"}, (W1, W2), T.isoformat(),
        ) == "GAP"
        assert had_gap(db) is True
        assert apply_frame(db, frame(cursor="1793930404464-0002"),
                           (W1, W2), T.isoformat()) == "PROSPECTIVE_FILL"
        assert had_gap(db) is True


def test_wallet_unknown_and_future_event_rejected(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        with pytest.raises(ValueError, match="WALLET_UNKNOWN"):
            apply_frame(db, frame("0x" + "c" * 40), (W1, W2), T.isoformat())
        future = frame()
        future["event"]["ts"] = (T + timedelta(seconds=15)).isoformat()
        with pytest.raises(ValueError, match="AFTER_RECEIPT"):
            apply_frame(db, future, (W1, W2), T.isoformat())
        assert db.execute("SELECT count(*) FROM selected_fills").fetchone()[0] == 0
