"""Contract: producer-local HyperX receipts must not become PM-02 signals unaudited."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_hyperx_forward import extract_observations, store_first_local_receipt
from copytrade_pm.pm_prospective_ledger import ProspectiveLedger

NOW = datetime(2026, 10, 31, 2, 0, tzinfo=UTC)
RECEIVED = NOW + timedelta(seconds=1)
IMPORTED = NOW + timedelta(seconds=5)
ADDRESS = "0x" + "a" * 40
IDENTITY = sha256(ADDRESS.encode()).hexdigest()
MANIFEST = "a" * 64


def first_receipt(folder, *, snapshot=False, tid=12):
    raw = json.dumps(
        {
            "type": "fills",
            "data": {
                "user": ADDRESS,
                "isSnapshot": snapshot,
                "fills": [
                    {
                        "coin": "BTC",
                        "time": int(NOW.timestamp() * 1000),
                        "tid": tid,
                        "px": "100",
                        "sz": "2",
                        "side": "B",
                        "start_position": "0",
                    }
                ],
            },
        }
    )
    rows = extract_observations(
        raw,
        RECEIVED,
        {"W001": ADDRESS},
        connected_at=NOW - timedelta(seconds=2),
    )
    assert len(rows) == 1
    assert store_first_local_receipt(folder, rows[0])
    return rows[0]


def ledger(path, *, now=IMPORTED):
    return ProspectiveLedger(
        path,
        cohort={"W001": IDENTITY},
        cohort_manifest_sha=MANIFEST,
        clock_source=lambda: now,
    )


def test_producer_receipt_is_immutable_and_asof_gated_without_promotion(tmp_path):
    source = tmp_path / "private-source"
    first_receipt(source)
    journal = ledger(tmp_path / "private-ledger")
    imported = journal.ingest_folder(source)
    assert imported["ingested"] == 1
    assert imported["rejected"] == 0
    assert not journal.receipts_asof((IMPORTED - timedelta(milliseconds=1)).isoformat())
    rows = journal.receipts_asof(IMPORTED.isoformat())
    assert len(rows) == 1
    row = rows[0]
    assert row["wallet"] == "W001"
    assert row["source_event_at"] == NOW.isoformat()
    assert row["locally_received_at"] == RECEIVED.isoformat()
    assert row["first_known_at"] == IMPORTED.isoformat()
    assert row["verified_first_known"] is False
    assert row["oracle_hindsight"] is False
    assert journal.pm02_rows_asof(IMPORTED.isoformat()) == {}
    assert journal.ingest_folder(source)["ingested"] == 0
    assert journal.receipts_asof(IMPORTED.isoformat()) == rows
    assert (tmp_path / "private-ledger" / "events.jsonl").stat().st_mode & 0o077 == 0


def test_snapshot_is_recorded_but_not_a_forward_qualifiable_episode(tmp_path):
    source = tmp_path / "private-source"
    first_receipt(source, snapshot=True)
    journal = ledger(tmp_path / "private-ledger")
    journal.ingest_folder(source)
    row = journal.receipts_asof(IMPORTED.isoformat())[0]
    assert row["source_snapshot"] is True
    assert row["verified_first_known"] is False
    assert journal.pm02_rows_asof(IMPORTED.isoformat()) == {}


def test_unrecognized_alias_and_future_receipt_fail_closed(tmp_path):
    source = tmp_path / "private-source"
    first_receipt(source)
    other = ledger(tmp_path / "ledger-other")
    receipt_file = next(source.glob("hyperx-observation-*.json"))
    original = json.loads(receipt_file.read_text())
    bad = dict(original, wallet="W999")
    receipt_file.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="COHORT"):
        other.ingest_folder(source)
    assert other.receipts_asof(IMPORTED.isoformat()) == []
    receipt_file.write_text(
        json.dumps({**original, "locally_received_at": (IMPORTED + timedelta(days=1)).isoformat()})
    )
    with pytest.raises(ValueError, match="FUTURE_RECEIPT"):
        other.ingest_folder(source)
