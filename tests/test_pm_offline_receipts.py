"""Synthetic prospective clock receipts must match exact source identities."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from copytrade_pm.pm_offline_manifest import ManifestBlocked
from copytrade_pm.pm_offline_receipts import validate_receipt_bundle, SCHEMA

T = datetime(2026, 10, 20, tzinfo=UTC)


def _bundle(tmp_path, *, source_offset=0, omit_opening=False):
    known = T + timedelta(seconds=10)
    source = T + timedelta(seconds=source_offset)
    opening = {
        "account": "W001",
        "dex": "default",
        "source_event_at": T - timedelta(minutes=2),
        "first_known_at": T - timedelta(minutes=1),
    }
    fills = [
        {
            "account": "W001",
            "dex": "default",
            "instrument": "BTC",
            "event_id": "x",
            "source_event_at": source,
            "first_known_at": known,
        }
    ]
    observed = [
        {
            "account": "W001",
            "dex": "default",
            "instrument": "*",
            "event_id": "__opening__",
            "source_event_at": opening["source_event_at"].isoformat(),
            "first_known_at": opening["first_known_at"].isoformat(),
        },
        {
            "account": "W001",
            "dex": "default",
            "instrument": "BTC",
            "event_id": "x",
            "source_event_at": source.isoformat(),
            "first_known_at": known.isoformat(),
        },
    ]
    if omit_opening:
        observed.pop(0)
    doc = {
        "schema": SCHEMA,
        "producer": "fixture-independent-receipt",
        "capture_method": "PERSISTED_LOCAL_RECEIPT",
        "observations": observed,
    }
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps(doc))
    return path, opening, fills


def test_receipt_matches_opening_and_fill_identity(tmp_path):
    path, initial, fills = _bundle(tmp_path)
    digest = validate_receipt_bundle(
        path,
        expected_account="W001",
        expected_dex="default",
        initial_book=initial,
        fills=fills,
    )
    assert len(digest) == 64


def test_missing_receipt_event_or_opening_fails(tmp_path):
    path, initial, fills = _bundle(tmp_path, omit_opening=True)
    with pytest.raises(ManifestBlocked, match="MISSING_OR_UNKNOWN_RECEIPT_EVENT_IDS"):
        validate_receipt_bundle(
            path,
            expected_account="W001",
            expected_dex="default",
            initial_book=initial,
            fills=fills,
        )


def test_attached_wrong_clock_refused_even_when_file_sha_matches(tmp_path):
    path, initial, fills = _bundle(tmp_path)
    doc = json.loads(path.read_text())
    doc["observations"][1]["first_known_at"] = (T + timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked, match="SOURCE_AND_RECEIPT_CLOCK_MISMATCH"):
        validate_receipt_bundle(
            path,
            expected_account="W001",
            expected_dex="default",
            initial_book=initial,
            fills=fills,
        )


def test_wrong_account_and_inverted_receipt_clocks_refused(tmp_path):
    path, initial, fills = _bundle(tmp_path)
    doc = json.loads(path.read_text())
    doc["observations"][1]["account"] = "W002"
    path.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked, match="CROSS_ACCOUNT_RECEIPT_REFERENCE"):
        validate_receipt_bundle(
            path,
            expected_account="W001",
            expected_dex="default",
            initial_book=initial,
            fills=fills,
        )
