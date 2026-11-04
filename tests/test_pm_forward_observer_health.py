"""Independent local read-only observer watcher: never PAPER_RUNNING."""

from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_observer_health import (
    _readonly_tape_snapshot,
    inspect_public_observer_heartbeat,
    publish_public_observer_heartbeat,
)
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import sample_state
from test_pm_forward_observer import seeded
from test_pm_forward_ccxt_market import BTC, at, ccxt_market, orderbook


T = datetime.fromtimestamp(1793294400, UTC)


def epoch():
    return {
        "schema": "paper_readonly_observer_service_epoch_v1",
        "epoch": 1,
        "status": "BLOCKED_NO_TRADE",
        "observed_native_market_count": 2,
        "capture_gaps": 0,
        "protected_worker_attested": False,
        "source_nav_attested": False,
        "trade_volume_complete": False,
        "financial_events_committed": 0,
        "paper_observed": False,
        "order_route": "NONE",
    }


def test_hashed_source_snapshot_and_local_process_health_still_degraded(tmp_path):
    _, _, _, journal = seeded(tmp_path)
    before = sha256(journal.path.read_bytes()).hexdigest()
    snap = _readonly_tape_snapshot(journal.path)
    assert snap["source"]["S035"]["cursor"] == 1
    assert snap["source"]["S051"]["cursor"] == 0
    assert snap["quotes"] == {}
    published = publish_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        epoch_report=epoch(),
        observed_at=(T + timedelta(seconds=4)).isoformat(),
    )
    assert published["status"] == "OBSERVER_ONLY_HEARTBEAT_PERSISTED"
    inspection = inspect_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        as_of=(T + timedelta(seconds=6)).isoformat(),
    )
    assert inspection["health"] == "DEGRADED_OBSERVER_ONLY"
    assert inspection["observer_process_verified"] is True
    assert inspection["source_aliases_checked"] == 5
    assert inspection["source_aliases_with_receipts"] == 1
    assert inspection["market_quote_tapes_verified"] == 0
    assert inspection["heartbeat_age_seconds"] == 2
    assert "NO_NATIVE_MARKET_QUOTE_RECEIPTS" in inspection["reason_codes"]
    assert "UNPROTECTED_PUBLIC_OBSERVER_ONLY" in inspection["reason_codes"]
    assert inspection["protected_worker_attested"] is False
    assert inspection["paper_observed"] is False
    assert inspection["order_route"] == "NONE"
    assert sha256(journal.path.read_bytes()).hexdigest() == before
    path = journal.root / "p1p14-public-observer.heartbeat.json"
    assert path.stat().st_mode & 0o077 == 0


def test_missing_stale_or_forged_health_fails_readonly(tmp_path):
    _, _, _, journal = seeded(tmp_path)
    unknown = inspect_public_observer_heartbeat(
        journal.root, journal_db=journal.path, as_of=(T + timedelta(seconds=4)).isoformat()
    )
    assert unknown["health"] == "UNKNOWN"
    publish_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        epoch_report=epoch(),
        observed_at=(T + timedelta(seconds=4)).isoformat(),
    )
    stale = inspect_public_observer_heartbeat(
        journal.root, journal_db=journal.path, as_of=(T + timedelta(seconds=180)).isoformat()
    )
    assert stale["health"] == "UNKNOWN"
    assert "OBSERVER_HEARTBEAT_STALE_OR_FUTURE" in stale["reason_codes"]
    path = journal.root / "p1p14-public-observer.heartbeat.json"
    saved = json.loads(path.read_text())
    edited = deepcopy(saved)
    edited["process_identity"]["start_ticks"] += 1
    from copytrade_pm.pm03_account import digest

    edited["payload_sha"] = digest({k: v for k, v in edited.items() if k != "payload_sha"})
    path.write_text(json.dumps(edited))
    forged = inspect_public_observer_heartbeat(
        journal.root, journal_db=journal.path, as_of=(T + timedelta(seconds=6)).isoformat()
    )
    assert forged["health"] == "UNKNOWN"
    assert "OBSERVER_HEARTBEAT_PROCESS_IDENTITY_CHANGED" in forged["reason_codes"]
    edited["payload_sha"] = "f" * 64
    path.write_text(json.dumps(edited))
    corrupted = inspect_public_observer_heartbeat(
        journal.root, journal_db=journal.path, as_of=(T + timedelta(seconds=6)).isoformat()
    )
    assert corrupted["health"] == "UNKNOWN"
    assert "OBSERVER_HEARTBEAT_PAYLOAD_TAMPERED" in corrupted["reason_codes"]


def test_source_receipt_update_after_heartbeat_is_detected(tmp_path):
    _, primary, _, journal = seeded(tmp_path)
    publish_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        epoch_report=epoch(),
        observed_at=(T + timedelta(seconds=4)).isoformat(),
    )
    address = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    state = deepcopy(sample_state())
    state["user"] = address
    second = read_public_all_dex_scope(
        alias="S035",
        address=address,
        frame={"channel": "allDexsClearinghouseState", "data": state},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(T + timedelta(seconds=5)).isoformat(),
    )
    append_public_scope(journal, alias="S035", seq=2, receipt=second)
    invalid = inspect_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        as_of=(T + timedelta(seconds=6)).isoformat(),
    )
    assert invalid["health"] == "UNKNOWN"
    assert "OBSERVER_HEARTBEAT_TAPE_HEAD_DIVERGENCE" in invalid["reason_codes"]


def test_public_observer_watchdog_refuses_false_positive_claims_and_unprotected_file(tmp_path):
    _, _, _, journal = seeded(tmp_path)
    with pytest.raises(ValueError, match="OBSERVER_HEARTBEAT_UNTRUSTED_EPOCH_REPORT"):
        publish_public_observer_heartbeat(
            journal.root,
            journal_db=journal.path,
            epoch_report={**epoch(), "protected_worker_attested": True},
        )
    with pytest.raises(ValueError, match="OBSERVER_HEARTBEAT_UNTRUSTED_EPOCH_REPORT"):
        publish_public_observer_heartbeat(
            journal.root,
            journal_db=journal.path,
            epoch_report={**epoch(), "order_route": "BROKER"},
        )
    publish_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        epoch_report=epoch(),
        observed_at=(T + timedelta(seconds=4)).isoformat(),
    )
    path = journal.root / "p1p14-public-observer.heartbeat.json"
    path.chmod(0o644)
    result = inspect_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        as_of=(T + timedelta(seconds=6)).isoformat(),
    )
    assert result["health"] == "UNKNOWN"
    assert "OBSERVER_HEARTBEAT_FILE_PERMISSION_OR_SIZE" in result["reason_codes"]
    with pytest.raises(ValueError, match="OBSERVER_HEARTBEAT_DESTINATION_PERMISSION_INVALID"):
        publish_public_observer_heartbeat(
            journal.root, journal_db=journal.path, epoch_report=epoch()
        )
    path.unlink()
    other = tmp_path / "external"
    other.write_text("keep")
    path.symlink_to(other)
    with pytest.raises(ValueError, match="OBSERVER_HEARTBEAT_DESTINATION_INVALID"):
        publish_public_observer_heartbeat(
            journal.root, journal_db=journal.path, epoch_report=epoch()
        )
    assert other.read_text() == "keep"


def test_verified_market_quote_tape_divergence_blocks_watchdog(tmp_path):
    _, _, _, journal = seeded(tmp_path)
    native = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    quote = parse_ccxt_book(native, orderbook(seconds=2), first_known_at=at(3)).payload()
    journal.append_market_quote(quote)
    publish_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        epoch_report=epoch(),
        observed_at=at(4),
    )
    healthy = inspect_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        as_of=at(6),
    )
    assert healthy["market_quote_tapes_verified"] == 1
    assert "NO_NATIVE_MARKET_QUOTE_RECEIPTS" not in healthy["reason_codes"]
    assert healthy["health"] == "DEGRADED_OBSERVER_ONLY"
    with closing(sqlite3.connect(journal.path)) as db:
        with db:
            db.execute(
                "UPDATE market_quote_receipts SET chain_sha=? WHERE instrument=?",
                ("f" * 64, BTC.key),
            )
    invalid = inspect_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        as_of=at(6),
    )
    assert invalid["health"] == "UNKNOWN"
    assert "PAPER_MARKET_READONLY_TAPE_DIVERGENCE" in invalid["reason_codes"]


def test_tampered_source_chain_fails_independent_observer_health(tmp_path):
    _, _, _, journal = seeded(tmp_path)
    publish_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        epoch_report=epoch(),
        observed_at=(T + timedelta(seconds=4)).isoformat(),
    )
    with closing(sqlite3.connect(journal.path)) as db:
        with db:
            db.execute(
                "UPDATE source_receipts SET chain_sha=? WHERE source_id=?",
                ("f" * 64, "S035"),
            )
    health = inspect_public_observer_heartbeat(
        journal.root,
        journal_db=journal.path,
        as_of=(T + timedelta(seconds=6)).isoformat(),
    )
    assert health["health"] == "UNKNOWN"
    assert "PAPER_SOURCE_READONLY_TAPE_DIVERGENCE" in health["reason_codes"]
