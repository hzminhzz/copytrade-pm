"""Original-backed, restart-safe Vike candidate journal: no V4 paper admission."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import sqlite3

import pytest

import copytrade_pm.pm_vike_reconciled_journal as journal
from copytrade_pm.pm_vike_position_observations import apply_frame, initialize as init_transport

WALLET = "0x" + "a" * 40
CURSOR = "1794410000000-0000"
NEXT = "1794410001000-0000"
EPOCH = "epoch_vike_candidate_test_1111"
MANIFEST = "f" * 64
MKT = "hyperliquid/mainnet:perp:default/BTC"


def source_census(*, qty="4", at=None):
    known = at or datetime.now(UTC)
    provider = known - timedelta(milliseconds=300)
    return {
        "schema": "copytrade_independent_official_rest_perp_census_v1",
        "account_sha256": sha256(WALLET.encode()).hexdigest(),
        "manifest_sha256": MANIFEST,
        "original_bytes_independently_verified": True,
        "scope_parity": True,
        "dex_provider_times_ms": {"default": int(provider.timestamp() * 1000)},
        "dex_state_shas": {"default": "a" * 64},
        "positions": {MKT: qty},
        "completed_at": known.isoformat(),
    }


def event_body(*, start="4", after="5", trade_id=123, ts=None):
    stamp = ts or datetime.now(UTC) - timedelta(milliseconds=500)
    return {
        "schema": "vike.event.v1",
        "source": "hl.positions",
        "kind": "position",
        "event_id": f"hl.positions:{WALLET}:1794410001000:{trade_id}",
        "ts": stamp.isoformat(),
        "subject": {"wallet": WALLET, "symbol": "BTC"},
        "data": {
            "trade_id": trade_id,
            "dex": "HL",
            "action": "increase",
            "side": "buy",
            "size_usd": 110,
            "start_position": start,
            "size_token": "1",
            "position_after": after,
        },
    }


def original(db, *, body=None, prospective=True):
    event = body or event_body()
    frame = {"type": "event", "ids": ["copytrade_position"], "cursor": NEXT, "event": event}
    apply_frame(
        db,
        frame,
        (WALLET,),
        datetime.now(UTC).isoformat(),
        raw_wire=json.dumps(frame, sort_keys=True),
        prospective=prospective,
    )
    return event["event_id"]


def start(db, monkeypatch, *, gap=False):
    now = datetime.now(UTC) - timedelta(seconds=2)
    census = source_census(at=now)
    monkeypatch.setattr(
        journal,
        "verify_archived_official_census",
        lambda wallet, directory, manifest_sha256: (
            census
            if wallet == WALLET and manifest_sha256 == MANIFEST
            else (_ for _ in ()).throw(ValueError("WRONG_PROOF"))
        ),
    )
    ack_at = now - timedelta(seconds=1)
    ack = {
        "type": "subscribed",
        "id": "copytrade_position",
        "channel": "hl.positions",
        "cursor": CURSOR,
    }
    apply_frame(db, ack, (WALLET,), ack_at.isoformat(), raw_wire=json.dumps(ack))
    if gap:
        apply_frame(
            db,
            {"type": "gap", "channel": "hl.positions", "cursor": CURSOR},
            (WALLET,),
            now.isoformat(),
            raw_wire=json.dumps({"type": "gap", "channel": "hl.positions", "cursor": CURSOR}),
        )
    return journal.begin_epoch(
        db,
        account=WALLET,
        archive_dir=__import__("pathlib").Path("/not/accessed"),
        manifest_sha256=MANIFEST,
        subscription_ack_at=ack_at.isoformat(),
        stream_cursor=CURSOR,
        epoch_id=EPOCH,
    )


def connection(tmp_path):
    db = sqlite3.connect(tmp_path / "candidate.sqlite3")
    init_transport(db)
    journal.initialize(db)
    return db


def test_durable_original_backed_event_and_replay_restart(tmp_path, monkeypatch):
    path = tmp_path / "candidate.sqlite3"
    with closing(connection(tmp_path)) as db:
        assert start(db, monkeypatch)["status"] == "BASELINE_NON_ACTIONABLE"
        eid = original(db)
        committed = journal.observe_committed_original(
            db, account=WALLET, event_id=eid, epoch_id=EPOCH
        )
        assert committed["revision"] == 2
        assert committed["status"] == "PENDING_INDEPENDENT_RECONCILIATION"
        assert committed["paper_new_risk_eligible"] is False
        assert journal.verify_history(db, account=WALLET)["events_verified"] == 2
        assert (
            journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)[
                "status"
            ]
            == "DUPLICATE_NO_MUTATION"
        )
    with closing(sqlite3.connect(path)) as db:
        assert journal.status(db, account=WALLET)["revision"] == 2
        assert journal.status(db, account=WALLET)["state"]["positions"] == [[MKT, "5"]]
        assert journal.verify_history(db, account=WALLET)["events_verified"] == 2
        assert journal.status(db, account=WALLET)["paper_new_risk_eligible"] is False


def test_provider_gap_latches_and_does_not_flatten(tmp_path, monkeypatch):
    with closing(connection(tmp_path)) as db:
        assert start(db, monkeypatch, gap=True)["status"] == "GAP_INELIGIBLE"
        eid = original(db)
        observed = journal.observe_committed_original(
            db, account=WALLET, event_id=eid, epoch_id=EPOCH
        )
        assert observed["status"] == "GAP_INELIGIBLE"
        data = journal.status(db, account=WALLET)
        assert data["state"]["positions"] == [[MKT, "4"]]
        assert data["state"]["first_known_transition"] is None
        assert data["paper_new_risk_eligible"] is False
        assert journal.verify_history(db, account=WALLET)["events_verified"] == 2


def test_reject_wire_mutation_and_missing_proof_without_head_change(tmp_path, monkeypatch):
    with closing(connection(tmp_path)) as db:
        start(db, monkeypatch)
        eid = original(db)
        db.execute(
            "UPDATE selected_position_events SET raw_wire_sha256=? WHERE event_id=?",
            ("0" * 64, eid),
        )
        db.commit()
        with pytest.raises(ValueError, match="WIRE_HASH_MISMATCH"):
            journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        assert journal.status(db, account=WALLET)["revision"] == 1
        with pytest.raises(ValueError, match="ORIGINAL_EVENT_MISSING_OR_FOREIGN"):
            journal.observe_committed_original(
                db, account=WALLET, event_id="missing", epoch_id=EPOCH
            )
        assert journal.verify_history(db, account=WALLET)["events_verified"] == 1


def test_gap_after_valid_event_and_bounded_chain_tamper(tmp_path, monkeypatch):
    with closing(connection(tmp_path)) as db:
        start(db, monkeypatch)
        eid = original(db)
        journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        at = datetime.now(UTC).isoformat()
        journal.gap(db, account=WALLET, reason="PROVIDER_STREAM_GAP", known_at=at)
        assert journal.status(db, account=WALLET)["state"]["status"] == "GAP_INELIGIBLE"
        assert journal.verify_history(db, account=WALLET)["events_verified"] == 3
        with pytest.raises(ValueError, match="BOUNDED_WINDOW"):
            journal.verify_history(db, account=WALLET, max_rows=2)
        account_sha = sha256(WALLET.encode()).hexdigest()
        db.execute(
            "UPDATE selected_position_candidate_history SET prior_chain_sha256=? "
            "WHERE account_sha256=? AND revision=2",
            ("0" * 64, account_sha),
        )
        db.commit()
        with pytest.raises(ValueError, match="CHAIN_DIVERGENCE"):
            journal.verify_history(db, account=WALLET)


def test_nonprospective_event_and_native_prestate_mismatch_fence(tmp_path, monkeypatch):
    with closing(connection(tmp_path)) as db:
        start(db, monkeypatch)
        eid = original(db, prospective=False)
        journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        assert journal.status(db, account=WALLET)["state"]["status"] == "GAP_INELIGIBLE"
    other = tmp_path / "other"
    other.mkdir()
    with closing(connection(other)) as db:
        start(db, monkeypatch)
        eid = original(db, body=event_body(start="9"))
        journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        assert journal.status(db, account=WALLET)["state"]["gap_reason"] == (
            "SOURCE_POSITION_PRESTATE_MISMATCH"
        )


def test_audit_rehashes_original_bytes_after_commit(tmp_path, monkeypatch):
    with closing(connection(tmp_path)) as db:
        start(db, monkeypatch)
        eid = original(db)
        journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        db.execute(
            "UPDATE selected_position_events SET raw_wire=? WHERE event_id=?",
            ('{"malicious":"tamper"}', eid),
        )
        db.commit()
        with pytest.raises(ValueError, match="ORIGINAL_DIVERGENCE"):
            journal.verify_history(db, account=WALLET)


def test_failed_history_append_rolls_back_head_atomically(tmp_path, monkeypatch):
    with closing(connection(tmp_path)) as db:
        start(db, monkeypatch)
        eid = original(db)
        db.execute(
            "CREATE TRIGGER fail_candidate_insert BEFORE INSERT ON "
            "selected_position_candidate_history BEGIN "
            "SELECT RAISE(ABORT,'injected commit failure'); END"
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected commit failure"):
            journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        assert journal.status(db, account=WALLET)["revision"] == 1
        db.execute("DROP TRIGGER fail_candidate_insert")
        db.commit()
        assert (
            journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)[
                "revision"
            ]
            == 2
        )
        assert journal.verify_history(db, account=WALLET)["events_verified"] == 2


def test_baseline_requires_persisted_subscription_ack_and_cursor(tmp_path, monkeypatch):
    from pathlib import Path

    with closing(connection(tmp_path)) as db:
        current = datetime.now(UTC) - timedelta(seconds=2)
        proof = source_census(at=current)
        monkeypatch.setattr(journal, "verify_archived_official_census", lambda *a, **k: proof)
        with pytest.raises(ValueError, match="SUBSCRIPTION_NOT_BOUND"):
            journal.begin_epoch(
                db,
                account=WALLET,
                archive_dir=Path("/not/accessed"),
                manifest_sha256=MANIFEST,
                subscription_ack_at=(current - timedelta(seconds=1)).isoformat(),
                stream_cursor=CURSOR,
                epoch_id=EPOCH,
            )
        assert journal.status(db, account=WALLET)["revision"] == 0
        ack_at = current - timedelta(seconds=1)
        ack = {
            "type": "subscribed",
            "id": "copytrade_position",
            "channel": "hl.positions",
            "cursor": CURSOR,
        }
        apply_frame(db, ack, (WALLET,), ack_at.isoformat(), raw_wire=json.dumps(ack))
        with pytest.raises(ValueError, match="SUBSCRIPTION_NOT_BOUND"):
            journal.begin_epoch(
                db,
                account=WALLET,
                archive_dir=Path("/not/accessed"),
                manifest_sha256=MANIFEST,
                subscription_ack_at=ack_at.isoformat(),
                stream_cursor=NEXT,
                epoch_id=EPOCH,
            )
        assert journal.status(db, account=WALLET)["revision"] == 0


def test_candidate_does_not_satisfy_official_v4_proof(tmp_path, monkeypatch):
    from copytrade_pm.pm_forward_stream_journal import verify_official_position_transition

    with closing(connection(tmp_path)) as db:
        start(db, monkeypatch)
        eid = original(db)
        journal.observe_committed_original(db, account=WALLET, event_id=eid, epoch_id=EPOCH)
        forged = {
            "observation_kind": "OBSERVED_STATE_CHANGE",
            "position_transition_eligible": True,
            "signal_eligible": False,
            "stream_epoch": EPOCH,
            "source_book": {"positions": {MKT: "5"}},
        }
        assert not verify_official_position_transition(
            db,
            alias="test",
            receipt_id=eid,
            receipt_sha="0" * 64,
            receipt=forged,
            require_current_positions=True,
        )
