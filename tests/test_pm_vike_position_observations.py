"""Vike position notifications are immutable evidence, never source-book authority."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
import sqlite3

import pytest

from copytrade_pm.pm_vike_position_observations import (
    apply_frame,
    checkpoint,
    coverage,
    initialize,
    position_subscription,
)

W1 = "0x" + "a" * 40
W2 = "0x" + "b" * 40
T = datetime.now(UTC)


def event(wallet=W1, trade_id=123, *, position_after=4.0, dex="HL", symbol="BTC"):
    return {
        "schema": "vike.event.v1",
        "event_id": f"hl.positions:{wallet}:1794310000000:{trade_id}",
        "source": "hl.positions",
        "kind": "position",
        "ts": (T - timedelta(seconds=3)).isoformat(),
        "subject": {"wallet": wallet, "symbol": symbol},
        "data": {
            "action": "increase",
            "side": "buy",
            "size_usd": 100,
            "size_token": 1,
            "start_position": 3,
            "position_after": position_after,
            "trade_id": trade_id,
            "dex": dex,
        },
    }


def frame(*, event_body=None, cursor="1794310000000-0000"):
    return {
        "type": "event",
        "ids": ["copytrade_position"],
        "cursor": cursor,
        "event": event_body or event(),
    }


def receive(db, frame_body, wallets=(W1, W2), prospective=True):
    return apply_frame(
        db,
        frame_body,
        wallets,
        T.isoformat(),
        raw_wire=json.dumps(frame_body, sort_keys=True),
        prospective=prospective,
    )


def test_multiwallet_subscription_excludes_default_minimum():
    selected = position_subscription((W2, W1))
    assert selected["filter"] == {"wallet": [W1, W2], "min_usd": 0}
    assert selected["channel"] == "hl.positions"
    with pytest.raises(ValueError, match="SELECTION_INVALID"):
        position_subscription((W1, W1))


def test_position_original_wire_receipt_is_atomic_and_not_a_complete_book(tmp_path):
    with closing(sqlite3.connect(tmp_path / "vike.sqlite")) as db:
        initialize(db)
        assert receive(db, frame()) == "PROSPECTIVE_POSITION_EVENT"
        assert receive(db, frame()) == "DUPLICATE"
        # At-least-once delivery may carry a later frame cursor or subscription.
        assert receive(db, frame(cursor="1794310000000-0001")) == "DUPLICATE"
        assert (
            receive(
                db,
                frame(event_body=event(W2, 124), cursor="1794310000000-0002"),
                prospective=False,
            )
            == "RECOVERED_POSITION_EVENT"
        )
        rows = db.execute(
            "SELECT COUNT(*),SUM(prospective) FROM selected_position_events"
        ).fetchone()
        assert rows == (2, 1)
        assert checkpoint(db) == ("1794310000000-0002", False)
        assert (
            db.execute(
                "SELECT SUM(observed_count) FROM selected_position_wallet_health"
            ).fetchone()[0]
            == 2
        )
        report = coverage(db, (W1, W2))
        assert report["selected_account_count"] == 2
        assert report["paper_new_risk_eligible"] is False
        assert all(not account["complete_book_verified"] for account in report["accounts"].values())
    with closing(sqlite3.connect(tmp_path / "vike.sqlite")) as db:
        initialize(db)
        assert db.execute("SELECT COUNT(*) FROM selected_position_events").fetchone()[0] == 2
        assert (
            db.execute(
                "SELECT SUM(observed_count) FROM selected_position_wallet_health"
            ).fetchone()[0]
            == 2
        )


def test_mismatching_event_id_market_and_native_quantities_fail_closed(tmp_path):
    with closing(sqlite3.connect(tmp_path / "vike.sqlite")) as db:
        initialize(db)
        bad = event()
        bad["data"]["position_after"] = "NaN"
        with pytest.raises(ValueError, match="NATIVE_QUANTITY_INVALID"):
            receive(db, frame(event_body=bad))
        bad = event()
        bad["data"]["size_token"] = 0
        with pytest.raises(ValueError, match="SIZE_NOT_POSITIVE"):
            receive(db, frame(event_body=bad))
        bad = event()
        bad["data"]["dex"] = "xyz"
        with pytest.raises(ValueError, match="DEX_SYMBOL_CONFLICT"):
            receive(db, frame(event_body=bad))
        bad = event()
        bad["subject"]["wallet"] = "0x" + "c" * 40
        with pytest.raises(ValueError, match="UNSELECTED_WALLET"):
            receive(db, frame(event_body=bad))
        assert db.execute("SELECT COUNT(*) FROM selected_position_events").fetchone()[0] == 0
        assert checkpoint(db) == (None, False)


def test_gap_remains_latched_after_new_events_and_restart(tmp_path):
    path = tmp_path / "vike.sqlite"
    with closing(sqlite3.connect(path)) as db:
        initialize(db)
        ack = {
            "type": "subscribed",
            "id": "copytrade_position",
            "channel": "hl.positions",
            "cursor": "1794310000000-0000",
        }
        assert receive(db, ack) == "SUBSCRIBED"
        ack_status = coverage(db, (W1, W2))
        assert ack_status["subscription_acknowledged"] is True
        assert ack_status["subscription_acknowledgments"] == 1
        gap = {"type": "gap", "channel": "hl.positions", "cursor": "1794310000000-0001"}
        assert receive(db, gap) == "GAP"
        assert receive(db, frame(cursor="1794310000000-0002")) == "PROSPECTIVE_POSITION_EVENT"
        assert checkpoint(db) == ("1794310000000-0002", True)
    with closing(sqlite3.connect(path)) as db:
        assert checkpoint(db)[1] is True
        assert coverage(db, (W1, W2))["paper_new_risk_eligible"] is False
        assert coverage(db, (W1, W2))["stream_gap"] is True


def test_ambiguous_duplicate_wire_json_keys_are_rejected(tmp_path):
    with closing(sqlite3.connect(tmp_path / "vike.sqlite")) as db:
        initialize(db)
        original = frame()
        raw = json.dumps(original)
        mutated = raw.replace('"type": "event"', '"type": "gap", "type": "event"', 1)
        with pytest.raises(ValueError, match="DUPLICATE_WIRE_KEY"):
            apply_frame(db, original, (W1, W2), T.isoformat(), raw_wire=mutated)
        assert checkpoint(db) == (None, False)


def test_wire_hash_identity_collision_fails_closed(tmp_path):
    with closing(sqlite3.connect(tmp_path / "vike.sqlite")) as db:
        initialize(db)
        first = frame()
        assert receive(db, first) == "PROSPECTIVE_POSITION_EVENT"
        mutated = frame()
        mutated["event"]["data"]["position_after"] = 5.0
        with pytest.raises(ValueError, match="PAYLOAD_DRIFT"):
            receive(db, mutated)
        assert db.execute("SELECT COUNT(*) FROM selected_position_events").fetchone()[0] == 1
