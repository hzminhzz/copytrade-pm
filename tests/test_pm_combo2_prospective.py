"""Credential-free first-local source capture -> prospective paper acceptance."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
import json
import os

import pytest

from copytrade_pm.pm_combo2 import Combo2PaperTracker
from copytrade_pm.pm_combo2_capture import (
    CapturedSourceScope,
    ingest_captured_book,
    ingest_e4_generation,
)

START = datetime(2026, 11, 2, 12, tzinfo=UTC)
BTC = "hyperliquid/mainnet:perp:default/BTC"
NAMES = ("W028", "CA-008", "W015")
ADDRESSES = {name: "0x" + str(index) * 40 for index, name in enumerate(NAMES, 1)}
HASHES = {k: sha256(v.lower().encode()).hexdigest() for k, v in ADDRESSES.items()}
SESSION = "gE420261102T120000000000Z-a1b2c3d4"


def at(seconds=0):
    return (START + timedelta(seconds=seconds)).isoformat()


def scope(manager):
    return CapturedSourceScope(
        manager=manager,
        address=ADDRESSES[manager],
        expected_dexs=frozenset({"default"}),
        account_mode="STANDARD_SEPARATE_DEX_BALANCES",
        subaccount_scope_complete=True,
        verified_no_subaccounts=True,
        spot_collateral_verified_absent=True,
        evidence_sha256="e" * 64,
    )


def receipt(manager, *, qty="0", equity="100000", seconds=0, generation=SESSION):
    state = {
        "marginSummary": {
            "accountValue": equity,
            "totalNtlPos": "0",
            "totalMarginUsed": "0",
        },
        "assetPositions": (
            [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": qty,
                        "positionValue": str(abs(D(qty) * D("100000"))),
                    }
                }
            ]
            if D(qty)
            else []
        ),
    }
    raw = json.dumps(
        {
            "channel": "allDexsClearinghouseState",
            "data": {
                "user": ADDRESSES[manager],
                "clearinghouseStates": [["", state]],
            },
        }
    ).encode()
    meta = {
        "schema": "e4_live_received_frame_v1",
        "subject": manager,
        "channel": "allDexsClearinghouseState",
        "locally_received_at": at(seconds),
        "source_raw_sha256": sha256(raw).hexdigest(),
        "source_is_snapshot": seconds == 0,
    }
    return raw, meta, generation


def paper(tmp_path):
    return Combo2PaperTracker(
        tmp_path,
        run_id="prospective-1",
        started_at=at(),
        source_subject_hashes=HASHES,
        prospective=True,
        source_evidence_hashes={m: "e" * 64 for m in NAMES},
        market_contract_sha="a" * 64,
    )


def ingest(engine, manager, *, qty="0", equity="100000", seconds=0, generation=SESSION):
    raw, meta, generation = receipt(
        manager, qty=qty, equity=equity, seconds=seconds, generation=generation
    )
    return ingest_captured_book(
        engine,
        raw_frame=raw,
        metadata=meta,
        scope=scope(manager),
        generation=generation,
        ingested_at=at(seconds),
    )


def market(seconds):
    return {
        BTC: {
            "first_known_at": at(seconds),
            "mark": "100000",
            "lot": ".0000001",
            "minimum": ".0000001",
            "volume_base": "1000",
            "fee_bps": "0",
            "spread_bps": "0",
            "slippage_bps": "0",
            "session_open": True,
            "supported": True,
            "native_market_id": "BTC-PERP",
            "verified_native_market_id": True,
        }
    }


def due(engine, seconds=310, *, proof=True, override=None):
    data = {
        "markets": market(seconds),
        "shocks": [{BTC: "-0.01"}],
        "hedge_break_loss": "0",
        "market_scope_verified": proof,
        "market_attestation_sha": "a" * 64 if proof else None,
    }
    if override is not None:
        data["leaders"] = override
    return engine.record(
        kind="PAPER_REBALANCE",
        event_id="due-" + str(seconds),
        source_event_at=at(10),
        first_known_at=at(seconds),
        decision_at=at(seconds),
        hypothetical_fill_at=at(seconds),
        data=data,
    )


def test_three_manager_baselines_do_not_enter_historical_positions(tmp_path):
    engine = paper(tmp_path)
    for manager in NAMES:
        ingest(engine, manager, qty="3" if manager == "W028" else "0")
    assert engine.state()["meta"]["pending"] == {}
    assert engine.account.quantities == {}
    assert len(engine.ledger.read()) == 3
    assert engine.state()["live_trading_authorized"] is False


def test_live_receipts_schedule_fixed_300s_and_use_latest_equity(tmp_path):
    engine = paper(tmp_path)
    for name in NAMES:
        ingest(engine, name)
    ingest(engine, "W028", qty="3", seconds=10)
    assert engine.state()["meta"]["pending"]["W028|" + BTC] == at(310)
    ingest(engine, "W028", qty="4", equity="200000", seconds=30)
    assert engine.state()["meta"]["pending"]["W028|" + BTC] == at(310)
    for name in NAMES:
        ingest(
            engine,
            name,
            qty="4" if name == "W028" else "0",
            equity="200000" if name == "W028" else "100000",
            seconds=305,
        )
    with pytest.raises(ValueError, match="NO_DUE"):
        due(engine, 309)
    result = due(engine)
    # Four BTC at $100k with current $200k leader equity: desired $2k,
    # capped at the pre-net instrument gross limit of $1,250.
    report = result["meta"]["last_report"]
    assert D(report["desired"]["W028"][BTC]) == D(".02")
    assert D(report["allowed"]["W028"][BTC]) == D(".0125")
    assert D(result["account"]["quantities"][BTC]) == D(".0125")
    assert report["actions"][0]["hypothetical"] is True
    restored = paper(tmp_path)
    assert restored.state() == result
    assert restored.head == result["journal_head"]
    assert ingest(restored, "W028", qty="4", equity="200000", seconds=305) == result


def test_source_gap_clears_pending_then_rebaseline_without_trade(tmp_path):
    engine = paper(tmp_path)
    for name in NAMES:
        ingest(engine, name)
    ingest(engine, "W028", qty="3", seconds=10)
    engine.record(
        kind="SOURCE_GAP",
        event_id="gap-w028",
        source_event_at=at(20),
        first_known_at=at(20),
        decision_at=at(20),
        hypothetical_fill_at=at(20),
        data={"manager": "W028", "reason": "WEBSOCKET_RECONNECT"},
    )
    assert engine.state()["meta"]["pending"] == {}
    assert engine.state()["meta"]["status"] == "BLOCKED_SOURCE"
    with pytest.raises(ValueError, match="NO_DUE"):
        due(engine)
    ingest(engine, "W028", qty="3", seconds=31)
    assert engine.state()["meta"]["status"] == "ACTIVE_PAPER"
    assert engine.state()["meta"]["pending"] == {}
    ingest(engine, "W028", qty="2", seconds=32)
    assert engine.state()["meta"]["pending"]["W028|" + BTC] == at(332)


def test_rotated_session_cannot_turn_reconnection_snapshot_into_trade(tmp_path):
    engine = paper(tmp_path)
    for name in NAMES:
        ingest(engine, name)
    ingest(engine, "W028", qty="3", seconds=10)
    new_session = "gE420261102T120030000000Z-b2c3d4e5"
    ingest(engine, "W028", qty="5", seconds=30, generation=new_session)
    assert engine.state()["meta"]["pending"] == {}
    assert engine.state()["meta"]["source_books"]["W028"]["capture_session"] == new_session
    ingest(engine, "W028", qty="4", seconds=60, generation=new_session)
    assert engine.state()["meta"]["pending"]["W028|" + BTC] == at(360)


def test_untrusted_captured_frame_and_scope_are_rejected_atomically(tmp_path):
    engine = paper(tmp_path)
    raw, meta, generation = receipt("W028")
    before = engine.state()
    with pytest.raises(ValueError, match="METADATA_MISMATCH"):
        ingest_captured_book(
            engine, raw_frame=raw + b" ", metadata=meta, scope=scope("W028"), generation=generation
        )
    with pytest.raises(ValueError, match="METADATA_MISMATCH"):
        ingest_captured_book(
            engine, raw_frame=raw, metadata=meta, scope=scope("CA-008"), generation=generation
        )
    with pytest.raises(ValueError, match="SOURCE_ACCOUNT_SCOPE"):
        CapturedSourceScope(
            "W028",
            ADDRESSES["W028"],
            frozenset({"default"}),
            "STANDARD_SEPARATE_DEX_BALANCES",
            True,
            False,
            True,
            "e" * 64,
        )
    with pytest.raises(ValueError, match="SOURCE_ACCOUNT_SCOPE"):
        CapturedSourceScope(
            "W028",
            ADDRESSES["W028"],
            frozenset({"default"}),
            "UNIFIED",
            True,
            True,
            True,
            "e" * 64,
        )
    assert engine.state() == before


def test_live_book_cannot_be_overridden_or_market_metadata_unattested(tmp_path):
    engine = paper(tmp_path)
    for name in NAMES:
        ingest(engine, name)
    ingest(engine, "W028", qty="3", seconds=10)
    for name in NAMES:
        ingest(engine, name, qty="3" if name == "W028" else "0", seconds=305)
    baseline = engine.state()
    with pytest.raises(ValueError, match="OVERRIDE_PROHIBITED"):
        due(engine, override={"W028": {}})
    with pytest.raises(ValueError, match="MARKET_SHA_MISMATCH"):
        due(engine, proof=False)
    assert engine.state() == baseline


def test_missing_three_fresh_source_books_fail_closed(tmp_path):
    engine = paper(tmp_path)
    ingest(engine, "W028")
    ingest(engine, "W028", qty="3", seconds=10)
    ingest(engine, "W028", qty="3", seconds=305)
    with pytest.raises(ValueError, match="THREE_SOURCE_BASELINES"):
        due(engine)
    assert engine.account.quantities == {}


def test_e4_receipt_import_only_from_private_hash_checked_generation(tmp_path):
    engine = paper(tmp_path)
    root = tmp_path / SESSION
    for sub in ("metadata", "frames", "discovery"):
        (root / sub).mkdir(parents=True, mode=0o700)
    dex_catalog = b"[null]"
    (root / "discovery" / "dex_catalog.json").write_bytes(dex_catalog)
    os.chmod(root / "discovery" / "dex_catalog.json", 0o600)
    report = {
        "schema": "e4_live_readonly_stream_session_v2",
        "source": "OFFICIAL_HYPERLIQUID_WS_PUBLIC_INFO_ONLY",
        "dex_catalog_sha256": sha256(dex_catalog).hexdigest(),
        "subaccount_counts": {name: 0 for name in NAMES},
        "connection": "CONNECTED",
        "disconnect_reason": "BOUNDED_SESSION_ROTATION",
        "errors": [],
        "unobserved_subjects": [],
        "account_window_count": 1,
        "subjects": HASHES,
    }
    (root / "session-report.json").write_text(json.dumps(report))
    os.chmod(root / "session-report.json", 0o600)
    raw, metadata, _ = receipt("W028")
    metadata["filename"] = "00000000.json"
    (root / "frames" / metadata["filename"]).write_bytes(raw)
    (root / "metadata" / "00000000.json").write_text(json.dumps(metadata))
    os.chmod(root / "frames" / metadata["filename"], 0o600)
    os.chmod(root / "metadata" / "00000000.json", 0o600)
    result = ingest_e4_generation(
        engine, generation_dir=root, scopes={k: scope(k) for k in NAMES}, ingested_at=at(1)
    )
    assert result["source_books_recorded"] == 1
    assert engine.state()["meta"]["pending"] == {}
    assert "W028" in engine.state()["meta"]["source_books"]
    assert (
        ingest_e4_generation(
            paper(tmp_path),
            generation_dir=root,
            scopes={k: scope(k) for k in NAMES},
            ingested_at=at(1),
        )["paper_journal_head"]
        == result["paper_journal_head"]
    )
    report["subaccount_counts"]["W028"] = 7
    (root / "session-report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="SOURCE_SESSION_HAS_SUBACCOUNTS"):
        ingest_e4_generation(
            engine,
            generation_dir=root,
            scopes={k: scope(k) for k in NAMES},
            ingested_at=at(1),
        )
    report["subaccount_counts"]["W028"] = 0
    (root / "session-report.json").write_text(json.dumps(report))
    metadata["source_raw_sha256"] = "0" * 64
    (root / "metadata" / "00000000.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="METADATA_MISMATCH"):
        ingest_e4_generation(
            engine,
            generation_dir=root,
            scopes={k: scope(k) for k in NAMES},
            ingested_at=at(1),
        )


def test_capture_consumer_clock_not_backdated_from_producer(tmp_path):
    engine = paper(tmp_path)
    raw, metadata, generation = receipt("W028", seconds=10)
    with pytest.raises(ValueError, match="STALE_OR_FUTURE_PRODUCER_RECEIPT"):
        ingest_captured_book(
            engine,
            raw_frame=raw,
            metadata=metadata,
            scope=scope("W028"),
            generation=generation,
            ingested_at=at(101),
        )
    assert engine.state()["meta"].get("source_books") is None
    before_start, before_meta, _ = receipt("W028", seconds=-1)
    with pytest.raises(ValueError, match="PRESTART_PRODUCER_RECEIPT"):
        ingest_captured_book(
            engine,
            raw_frame=before_start,
            metadata=before_meta,
            scope=scope("W028"),
            generation=generation,
            ingested_at=at(),
        )
    result = ingest_captured_book(
        engine,
        raw_frame=raw,
        metadata=metadata,
        scope=scope("W028"),
        generation=generation,
        ingested_at=at(15),
    )
    source_book = result["meta"]["source_books"]["W028"]
    assert source_book["producer_first_known_at"] == at(10)
    assert source_book["first_known_at"] == at(15)
    event = engine.ledger.read()[0]["event"]
    assert event["source_event_at"] == at(10)
    assert event["first_known_at"] == at(15)


def test_source_scope_attestation_is_frozen_with_paper_manifest(tmp_path):
    engine = paper(tmp_path)
    raw, metadata, generation = receipt("W028")
    forged = CapturedSourceScope(
        "W028",
        ADDRESSES["W028"],
        frozenset({"default"}),
        "STANDARD_SEPARATE_DEX_BALANCES",
        True,
        True,
        True,
        "f" * 64,
    )
    with pytest.raises(ValueError, match="SOURCE_CAPTURE_SCOPE_EVIDENCE_MISMATCH"):
        ingest_captured_book(
            engine,
            raw_frame=raw,
            metadata=metadata,
            scope=forged,
            generation=generation,
            ingested_at=at(),
        )
    assert engine.ledger.read() == []


def test_initial_snapshot_after_resubscribe_is_not_a_new_signal(tmp_path):
    engine = paper(tmp_path)
    for name in NAMES:
        ingest(engine, name)
    ingest(engine, "W028", qty="3", seconds=10)
    assert engine.state()["meta"]["pending"]
    raw, metadata, generation = receipt("W028", qty="4", seconds=30)
    metadata["source_is_snapshot"] = True
    ingest_captured_book(
        engine,
        raw_frame=raw,
        metadata=metadata,
        scope=scope("W028"),
        generation=generation,
        ingested_at=at(30),
    )
    assert engine.state()["meta"]["pending"] == {}
    assert engine.account.quantities == {}


def test_prospective_mode_cannot_be_switched_on_existing_fixture(tmp_path):
    engine = paper(tmp_path)
    with pytest.raises(ValueError, match="IMMUTABLE_FILE_CONFLICT"):
        Combo2PaperTracker(
            tmp_path, run_id="prospective-1", started_at=at(), source_subject_hashes=HASHES
        )
    assert engine.state()["paper_only"]
