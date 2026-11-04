"""Receipt-bundle identity checks for synthetic prospective-clock fixtures.

A file SHA alone proves only local bytes; it cannot establish a real independent
capture service or the authenticity of a historical first-known timestamp.
This module rejects unlinked receipt files and cross-account clock mismatches.
Actual scientific prospective qualification remains a separate attestation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from .pm_offline_manifest import ManifestBlocked, ManifestInvalid

SCHEMA = "pm_offline_receipt_bundle_v1"


def _clock(value: object) -> datetime:
    if not isinstance(value, str):
        raise ManifestInvalid("INVALID_RECEIPT_CLOCK")
    try:
        when = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ManifestInvalid("INVALID_RECEIPT_CLOCK") from exc
    if when.tzinfo is None or when.utcoffset() is None:
        raise ManifestInvalid("NAIVE_RECEIPT_CLOCK")
    return when.astimezone(UTC)


def validate_receipt_bundle(
    receipt_path: Path,
    *,
    expected_account: str,
    expected_dex: str,
    initial_book: dict,
    fills: list[dict],
) -> str:
    """Validate exact one-to-one source/receipt event identity and clocks.

    Each source fill must appear in this sealed local receipt bundle with the
    same source time and first-known local timestamp; an opening book must
    be observed too. Duplicate or unknown events fail closed. Producer strings
    are metadata, NOT cryptographic independent evidence.
    """
    path = Path(receipt_path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ManifestBlocked("MISSING_OR_OVERSIZED_RECEIPT_BUNDLE")
    raw = path.read_bytes()
    try:
        bundle = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ManifestBlocked("MALFORMED_RECEIPT_BUNDLE") from exc
    if (
        not isinstance(bundle, dict)
        or set(bundle) != {"schema", "producer", "capture_method", "observations"}
        or bundle["schema"] != SCHEMA
        or not isinstance(bundle["producer"], str)
        or not bundle["producer"]
        or bundle["capture_method"] != "PERSISTED_LOCAL_RECEIPT"
        or not isinstance(bundle["observations"], list)
    ):
        raise ManifestInvalid("INVALID_RECEIPT_BUNDLE_SCHEMA")
    expected: dict[tuple[str, str], tuple[datetime, datetime]] = {}
    initial_known = initial_book.get("first_known_at")
    initial_source = initial_book.get("source_event_at")
    if initial_source is None:
        raise ManifestBlocked("MISSING_INDEPENDENT_OPENING_SOURCE_CLOCK")
    expected[("__opening__", "*")] = (
        _clock(
            initial_source.isoformat() if isinstance(initial_source, datetime) else initial_source
        ),
        _clock(initial_known.isoformat() if isinstance(initial_known, datetime) else initial_known),
    )
    for row in fills:
        key = (row.get("event_id"), row.get("instrument"))
        if key in expected:
            raise ManifestInvalid("DUPLICATE_RECEIPT_EXPECTED_EVENT")
        expected[key] = (
            _clock(row["source_event_at"].isoformat()),
            _clock(row["first_known_at"].isoformat()),
        )
    observed = {}
    for row in bundle["observations"]:
        if not isinstance(row, dict) or set(row) != {
            "account",
            "dex",
            "instrument",
            "event_id",
            "source_event_at",
            "first_known_at",
        }:
            raise ManifestInvalid("INVALID_RECEIPT_OBSERVATION_SCHEMA")
        if row["account"] != expected_account or row["dex"] != expected_dex:
            raise ManifestBlocked("CROSS_ACCOUNT_RECEIPT_REFERENCE")
        key = (row["event_id"], row["instrument"])
        if key in observed:
            raise ManifestBlocked("DUPLICATE_RECEIPT_OBSERVATION")
        source_at, known_at = _clock(row["source_event_at"]), _clock(row["first_known_at"])
        if known_at < source_at:
            raise ManifestInvalid("RECEIPT_KNOWN_BEFORE_SOURCE")
        observed[key] = (source_at, known_at)
    if expected.keys() != observed.keys():
        raise ManifestBlocked("MISSING_OR_UNKNOWN_RECEIPT_EVENT_IDS")
    if any(observed[key] != value for key, value in expected.items()):
        raise ManifestBlocked("SOURCE_AND_RECEIPT_CLOCK_MISMATCH")
    return sha256(raw).hexdigest()
