"""Adversarial source-receipt, restart/cursor and replay parity canary tests."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
import sys

import pytest

from copytrade_pm import pm_vike_stream_canary as canary

WALLET = "0x" + "a" * 40
OTHER = "0x" + "b" * 40


def event(tid=101, usd=3.25, wallet=WALLET):
    ts = (datetime.now(UTC) - timedelta(seconds=3)).isoformat()
    return {
        "schema": "vike.event.v1",
        "event_id": f"hl.fills:{wallet}:test:{tid}",
        "source": "hl.fills",
        "kind": "fill",
        "ts": ts,
        "cursor": "event-source-not-resume",
        "chain": "hyperliquid",
        "subject": {"wallet": wallet, "symbol": "HYPE"},
        "data": {
            "trade_id": tid,
            "size_usd": usd,
            "size_token": 0.05,
            "price": 65.0,
            "side": "sell",
        },
        "labels": {},
    }


def frame(tid=101, usd=3.25, cursor="1793930404464-0001"):
    return {"type": "event", "ids": [canary.SUB_ID], "cursor": cursor, "event": event(tid, usd)}


def subscribed(cursor="1793930404464-0000"):
    return {
        "type": "subscribed",
        "id": canary.SUB_ID,
        "channel": canary.CHANNEL,
        "cursor": cursor,
        "replay": {"from": "none"},
    }


def test_explicit_zero_and_no_url_token():
    msg = canary.subscription(WALLET, None)
    assert msg["filter"] == {"wallet": [WALLET], "min_usd": 0}
    assert "cursor" not in msg
    assert "token" not in canary.URL
    assert canary.subscription(WALLET, "1793930404464-0001")["cursor"] == "1793930404464-0001"


def test_sqlite_restart_is_idempotent_and_pit_known_at_separate(tmp_path):
    root = tmp_path / "private"
    with closing(canary.open_journal(root)) as con:
        assert canary.apply_frame(con, subscribed(), WALLET, canary.utc_now()) == "SUBSCRIBED"
        msg = frame()
        assert canary.apply_frame(con, msg, WALLET, canary.utc_now()) == "EVENT"
        assert canary.apply_frame(con, msg, WALLET, canary.utc_now()) == "DUPLICATE"
        assert con.execute("SELECT COUNT(*) FROM frames").fetchone()[0] == 1
        assert canary.head(con) == msg["cursor"]
        row = con.execute(
            "SELECT source_ts,receipt_known_at,CAST(size_usd AS REAL) FROM frames"
        ).fetchone()
        assert row[0] != row[1]
        assert row[2] == 3.25
    with closing(canary.open_journal(root)) as con:
        assert canary.head(con) == msg["cursor"]
        assert canary.apply_frame(con, msg, WALLET, canary.utc_now()) == "DUPLICATE"
        assert con.execute("SELECT COUNT(*) FROM frames").fetchone()[0] == 1
    assert (root / "canary.sqlite").stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700


def test_duplicate_payload_drift_rejected_no_cursor_advance(tmp_path):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        msg = frame()
        canary.apply_frame(con, msg, WALLET, canary.utc_now())
        bad = {**msg, "event": {**msg["event"], "data": {**msg["event"]["data"], "price": 999}}}
        bad["cursor"] = "1793930404464-0002"
        with pytest.raises(ValueError, match="VIKE_DUPLICATE_EVENT_ID_PAYLOAD_DRIFT"):
            canary.apply_frame(con, bad, WALLET, canary.utc_now())
        assert canary.head(con) == msg["cursor"]


def test_out_of_order_duplicate_never_rewinds_checkpoint(tmp_path):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        canary.apply_frame(con, frame(101, cursor="1793930404464-0009"), WALLET, canary.utc_now())
        canary.apply_frame(con, frame(102, cursor="1793930404464-0003"), WALLET, canary.utc_now())
        assert canary.head(con) == "1793930404464-0009"
        assert con.execute("SELECT COUNT(*) FROM frames").fetchone()[0] == 2


def test_gap_is_durable_and_prevents_success_parity(tmp_path):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        canary.apply_frame(con, subscribed(), WALLET, canary.utc_now())
        assert (
            canary.apply_frame(
                con,
                {"type": "gap", "channel": canary.CHANNEL, "cursor": "1793930404464-0001"},
                WALLET,
                canary.utc_now(),
            )
            == "GAP"
        )
        assert con.execute("SELECT had_gap FROM checkpoint").fetchone()[0] == 1
        canary.apply_frame(con, frame(101, cursor="1793930404464-0002"), WALLET, canary.utc_now())
        # REST says no gap, but the on-demand WS did observe one.
        old = canary.rest_request
        canary.rest_request = lambda *_args: {
            "events": [{"cursor": "1793930404464-0002", "event": event(101)}],
            "next_cursor": "1793930404464-0002",
            "has_more": False,
        }
        try:
            assert canary.compare_rest(con, WALLET, "1793930404464-0000", "dummy")["status"] == (
                "BLOCKED_REST_TRUNCATED_OR_STREAM_GAP"
            )
        finally:
            canary.rest_request = old


def test_bounded_rest_parity_requires_sub1000_evidence(tmp_path, monkeypatch):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        canary.apply_frame(con, subscribed(), WALLET, canary.utc_now())
        msg = frame()
        canary.apply_frame(con, msg, WALLET, canary.utc_now())
        monkeypatch.setattr(
            canary,
            "rest_request",
            lambda _k, _w, _c: {
                "events": [{"cursor": msg["cursor"], "event": msg["event"]}],
                "next_cursor": msg["cursor"],
                "has_more": False,
            },
        )
        result = canary.compare_rest(con, WALLET, "1793930404464-0000", "dummy")
        assert result["status"] == "PARITY_OBSERVED_SAMPLE_ONLY"
        assert result["ws_sub_1000_count"] == 1
        assert result["symmetric_difference_count"] == 0
        assert result["production_admitted"] is False


def test_rest_extra_event_blocks_parity(tmp_path, monkeypatch):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        canary.apply_frame(con, subscribed(), WALLET, canary.utc_now())
        msg = frame()
        canary.apply_frame(con, msg, WALLET, canary.utc_now())
        monkeypatch.setattr(
            canary,
            "rest_request",
            lambda _k, _w, _c: {
                "events": [
                    {"cursor": msg["cursor"], "event": msg["event"]},
                    {"cursor": msg["cursor"], "event": event(202)},
                ],
                "next_cursor": msg["cursor"],
                "has_more": False,
            },
        )
        result = canary.compare_rest(con, WALLET, "1793930404464-0000", "dummy")
        assert result["status"] == "INCONCLUSIVE_OR_PARITY_MISMATCH"
        assert result["symmetric_difference_count"] == 1


def test_replayed_gap_still_latches_without_rewinding_cursor(tmp_path):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        canary.apply_frame(con, frame(cursor="1793930404464-0009"), WALLET, canary.utc_now())
        canary.apply_frame(
            con,
            {"type": "gap", "channel": canary.CHANNEL, "cursor": "1793930404464-0001"},
            WALLET,
            canary.utc_now(),
        )
        assert canary.head(con) == "1793930404464-0009"
        assert con.execute("SELECT had_gap FROM checkpoint").fetchone()[0] == 1


def test_same_native_id_with_different_rest_payload_cannot_prove_parity(tmp_path, monkeypatch):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        msg = frame()
        canary.apply_frame(con, msg, WALLET, canary.utc_now())
        drifted = {**msg["event"], "data": {**msg["event"]["data"], "price": 999}}
        monkeypatch.setattr(
            canary,
            "rest_request",
            lambda *_: {
                "events": [{"cursor": msg["cursor"], "event": drifted}],
                "next_cursor": msg["cursor"],
                "has_more": False,
            },
        )
        result = canary.compare_rest(con, WALLET, "1793930404464-0000", "dummy")
        assert result["status"] == "INCONCLUSIVE_OR_PARITY_MISMATCH"
        assert result["payload_conflict_count"] == 1


def test_payload_and_source_wallet_mismatch_rejected(tmp_path):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        for bad in (
            {
                "type": "event",
                "ids": [canary.SUB_ID],
                "cursor": "1793930404464-0001",
                "event": event(101, wallet=OTHER),
            },
            {
                "type": "event",
                "ids": ["other"],
                "cursor": "1793930404464-0001",
                "event": event(101),
            },
            {
                "type": "event",
                "ids": [canary.SUB_ID],
                "cursor": "1793930404464-0001",
                "event": {**event(), "schema": "wrong"},
            },
        ):
            with pytest.raises(ValueError):
                canary.apply_frame(con, bad, WALLET, canary.utc_now())
        assert con.execute("SELECT COUNT(*) FROM frames").fetchone()[0] == 0


def test_stale_local_receipt_is_refused(tmp_path):
    with closing(canary.open_journal(tmp_path / "private")) as con:
        old = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
        with pytest.raises(ValueError, match="VIKE_LOCAL_RECEIPT_CLOCK_NOT_CURRENT"):
            canary.apply_frame(con, frame(), WALLET, old)


def test_missing_credentials_fail_before_db_mutation(tmp_path, monkeypatch, capsys):
    root = tmp_path / "private"
    monkeypatch.setenv("VIKE_API_KEY", "")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "canary",
            "--wallet",
            WALLET,
            "--state-root",
            str(root),
            "--live",
            "--dedicated-key-only",
        ],
    )
    assert canary.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED_NO_VPS_VIKE_API_KEY"
    assert not root.exists()
    assert result["production_admitted"] is False
