"""Prospective ledger adversarial boundaries for REST, tamper and concurrency."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json

import pytest

from copytrade_pm.pm_hyperx_forward import store_first_local_receipt
from copytrade_pm.pm_hyperx_rest_forward import _recent_observation
from copytrade_pm.pm_prospective_ledger import ProspectiveLedger
from copytrade_pm.pm_sources import CohortEntry
from test_pm_prospective_ledger import ADDRESS, IDENTITY, IMPORTED, MANIFEST, NOW, first_receipt


def test_rest_receipt_is_retained_as_history_not_promoted_after_signed_audit(tmp_path):
    entry = CohortEntry(
        "W001",
        "original",
        ADDRESS,
        IDENTITY,
        "HISTORICAL_ONLY",
        1,
        1,
    )
    raw = {
        "user": ADDRESS,
        "coin": "BTC",
        "tid": 77,
        "time": int(NOW.timestamp() * 1000),
        "sz": "2",
        "px": "100",
        "side": "B",
        "start_position": "0",
    }
    recent = _recent_observation(
        raw,
        entry,
        "BTC",
        requested_at=NOW - timedelta(seconds=2),
        received_at=NOW + timedelta(seconds=1),
    )
    assert recent is not None and recent["source_snapshot"]
    folder = tmp_path / "rest"
    store_first_local_receipt(folder, recent)
    journal = ProspectiveLedger(
        tmp_path / "ledger",
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        clock_source=lambda: IMPORTED,
    )
    journal.ingest_folder(folder)
    assert len(journal.receipts_asof(IMPORTED.isoformat())) == 1
    assert journal.pm02_rows_asof(IMPORTED.isoformat()) == {}
    assert journal.receipts_asof(IMPORTED.isoformat())[0]["source_stream"].startswith(
        "HYPERX_DATA_API_REST"
    )


def test_corrupted_or_truncated_receipt_chain_does_not_silently_repair(tmp_path):
    source = tmp_path / "producer"
    first_receipt(source)
    journal = ProspectiveLedger(
        tmp_path / "ledger",
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        clock_source=lambda: IMPORTED,
    )
    journal.ingest_folder(source)
    original = journal.journal.read_bytes()
    journal.journal.write_bytes(original + b'{"event_id":')
    with pytest.raises(ValueError, match="TRUNCATED_PROSPECTIVE_LEDGER"):
        journal.read()
    journal.journal.write_bytes(original)
    event = json.loads(original)
    event["payload"]["first_known_at"] = "2000-01-01T00:00:00+00:00"
    journal.journal.write_bytes(json.dumps(event).encode() + b"\n")
    with pytest.raises(ValueError, match="SHA_CHAIN_BROKEN"):
        journal.read()


def test_conflicting_source_same_id_never_relabels_original_first_known(tmp_path):
    source = tmp_path / "producer"
    first_receipt(source)
    journal = ProspectiveLedger(
        tmp_path / "ledger",
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        clock_source=lambda: IMPORTED,
    )
    journal.ingest_folder(source)
    old = journal.receipts_asof(IMPORTED.isoformat())
    file = next(source.glob("hyperx-observation-*.json"))
    saved = json.loads(file.read_bytes())
    saved["source_fill_price"] = "9999"
    file.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="CONFLICTING_SOURCE_EVENT_RECEIPT"):
        journal.ingest_folder(source)
    assert journal.receipts_asof(IMPORTED.isoformat()) == old


def test_concurrent_duplicate_import_is_one_sealed_event(tmp_path):
    folder = tmp_path / "producer"
    first_receipt(folder)
    root = tmp_path / "ledger"
    ProspectiveLedger(
        root,
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        clock_source=lambda: IMPORTED,
    )

    def ingest(_):
        journal = ProspectiveLedger.open_existing(
            root,
            cohort={"W001": IDENTITY},
            cohort_manifest_sha=MANIFEST,
            audit_public_key=None,
            clock_source=lambda: IMPORTED,
        )
        return journal.ingest_folder(folder)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(ingest, range(10)))
    checked = ProspectiveLedger.open_existing(
        root,
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        audit_public_key=None,
    )
    assert len(checked.read()) == 1
    assert checked.read()[0]["sequence"] == 1
