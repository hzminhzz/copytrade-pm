"""Conservative offline bridge from immutable, first-local Hyperliquid receipts.

No HTTP, WebSocket, broker or trading client is imported. The acquisition
service owns the local arrival clock and the immutable raw frame. Historical
vendor fills and trade timestamps cannot be substituted for this input.

Single-account scopes are deliberately accepted only with explicit evidence
that the source manager has no unobserved subaccounts. A parent with children
is BLOCKED, never silently sized on parent NAV alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
from typing import Any

from .pm03_account import clock, digest
from .pm_combo2 import Combo2PaperTracker, MANAGERS
from .pm_combo2_source import standard_mode_book
from .pm_e4_prospective import _dex_universe

_HEX_SHA = re.compile(r"[a-f0-9]{64}")
_ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}")
_GENERATION = re.compile(r"gE4[0-9A-Za-z_-]{12,80}")
MAX_INGEST_LAG_SECONDS = 90


def _arrival_guard(producer_at: str, accepted_at: str, started_at: str) -> None:
    if clock(producer_at) < clock(started_at):
        raise ValueError("PRESTART_PRODUCER_RECEIPT_NONACTIONABLE")
    lag = (clock(accepted_at) - clock(producer_at)).total_seconds()
    if lag < 0 or lag > MAX_INGEST_LAG_SECONDS:
        raise ValueError("STALE_OR_FUTURE_PRODUCER_RECEIPT_NOT_ACTIONABLE")


@dataclass(frozen=True)
class CapturedSourceScope:
    """Owner-private, independently checked exact source account scope."""

    manager: str
    address: str
    expected_dexs: frozenset[str]
    account_mode: str
    subaccount_scope_complete: bool
    verified_no_subaccounts: bool
    spot_collateral_verified_absent: bool
    evidence_sha256: str

    def __post_init__(self) -> None:
        if self.manager not in MANAGERS or not _ADDRESS.fullmatch(self.address):
            raise ValueError("SOURCE_IDENTITY_UNATTESTED")
        if (
            self.account_mode != "STANDARD_SEPARATE_DEX_BALANCES"
            or not self.expected_dexs
            or "default" not in self.expected_dexs
            or not self.subaccount_scope_complete
            or not self.verified_no_subaccounts
            or not self.spot_collateral_verified_absent
            or not _HEX_SHA.fullmatch(self.evidence_sha256)
        ):
            raise ValueError("SOURCE_ACCOUNT_SCOPE_NOT_FULLY_ATTESTED")

    @property
    def subject_sha(self) -> str:
        return sha256(self.address.lower().encode()).hexdigest()


def _private_file(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("SOURCE_CAPTURE_SYMLINK")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("SOURCE_CAPTURE_NOT_PRIVATE")
    return path.read_bytes()


def capture_book(
    *,
    raw_frame: bytes,
    metadata: dict[str, Any],
    scope: CapturedSourceScope,
    generation: str,
) -> tuple[dict, dict]:
    """Verify a locally witnessed official all-DEX frame and normalize it.

    Local first-receipt is taken ONLY from immutable producer metadata, never
    from source event times or import time.
    """
    if not _GENERATION.fullmatch(generation):
        raise ValueError("INVALID_CAPTURE_SESSION")
    if (
        metadata.get("schema") != "e4_live_received_frame_v1"
        or metadata.get("subject") != scope.manager
        or metadata.get("channel") != "allDexsClearinghouseState"
        or metadata.get("source_raw_sha256") != sha256(raw_frame).hexdigest()
    ):
        raise ValueError("SOURCE_CAPTURE_METADATA_MISMATCH")
    at = metadata.get("locally_received_at")
    if not isinstance(at, str):
        raise ValueError("MISSING_FIRST_LOCAL_RECEIPT")
    clock(at)
    try:
        wire = json.loads(raw_frame)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_OFFICIAL_SOURCE_FRAME") from exc
    if (
        not isinstance(wire, dict)
        or wire.get("channel") != "allDexsClearinghouseState"
        or not isinstance(wire.get("data"), dict)
        or str(wire["data"].get("user", "")).lower() != scope.address.lower()
    ):
        raise ValueError("SOURCE_FRAME_SUBJECT_MISMATCH")
    book = standard_mode_book(
        manager=scope.manager,
        address=scope.address,
        received_at=at,
        raw_all_dexs=wire["data"],
        expected_dexs=set(scope.expected_dexs),
        account_mode=scope.account_mode,
        subaccount_scope_complete=scope.subaccount_scope_complete,
        spot_collateral_verified_absent=scope.spot_collateral_verified_absent,
    )
    book["capture_session"] = generation
    book["producer_first_known_at"] = at
    book["source_scope_evidence_sha256"] = scope.evidence_sha256
    return book, {
        "producer": "OFFICIAL_HYPERLIQUID_LOCAL_RECEIPT",
        "source_raw_sha256": metadata["source_raw_sha256"],
        "source_book": book,
        "source_was_initial_snapshot": metadata.get("source_is_snapshot") is True,
    }


def ingest_captured_book(
    tracker: Combo2PaperTracker,
    *,
    raw_frame: bytes,
    metadata: dict[str, Any],
    scope: CapturedSourceScope,
    generation: str,
    ingested_at: str | None = None,
) -> dict:
    """One first-known paper event. Old producer files never become new trades."""
    if not tracker.prospective:
        raise ValueError("PROSPECTIVE_CAPTURE_REQUIRES_PROSPECTIVE_RUN")
    if tracker.manifest["source_subject_hashes"][scope.manager] != scope.subject_sha:
        raise ValueError("SOURCE_CAPTURE_RUN_IDENTITY_MISMATCH")
    if tracker.manifest["source_scope_evidence_shas"].get(scope.manager) != scope.evidence_sha256:
        raise ValueError("SOURCE_CAPTURE_SCOPE_EVIDENCE_MISMATCH")
    book, evidence = capture_book(
        raw_frame=raw_frame, metadata=metadata, scope=scope, generation=generation
    )
    producer_at = book["producer_first_known_at"]
    event_id = "captured-book-" + digest(
        {
            "manager": scope.manager,
            "generation": generation,
            "source_raw_sha256": evidence["source_raw_sha256"],
            "producer_received_at": producer_at,
        }
    )
    # Existing durable evidence wins on restart, so a duplicate file does not
    # get a new actionable first-known clock or multiply any batch.
    if any(row["event"]["event_id"] == event_id for row in tracker.ledger.read()):
        return tracker.state()
    accepted_at = ingested_at or datetime.now(UTC).isoformat()
    _arrival_guard(producer_at, accepted_at, tracker.manifest["started_at"])
    # The consumer's *own* first-known clock is later than the producer's.
    book["first_known_at"] = accepted_at
    evidence["source_book"] = book
    return tracker.record(
        kind="SOURCE_BOOK",
        event_id=event_id,
        source_event_at=producer_at,  # Original local evidence; native event time unknown.
        first_known_at=accepted_at,
        decision_at=accepted_at,
        hypothetical_fill_at=accepted_at,  # No fill: mandatory event schema clock only.
        data=evidence,
    )


def ingest_e4_generation(
    tracker: Combo2PaperTracker,
    *,
    generation_dir: Path,
    scopes: dict[str, CapturedSourceScope],
    ingested_at: str | None = None,
) -> dict:
    """Read one finished, private, hash-checked observer generation.

    Only actual captured account frames are consumed. A session that reports
    errors, unobserved subjects or rotated account windows cannot establish a
    complete Combo2 source scope; it is rejected rather than backfilled.
    """
    if set(scopes) != set(MANAGERS):
        raise ValueError("THREE_MANAGER_SOURCE_SCOPE_REQUIRED")
    if not generation_dir.is_dir() or generation_dir.is_symlink():
        raise ValueError("INVALID_SOURCE_GENERATION")
    report = json.loads(_private_file(generation_dir / "session-report.json"))
    if (
        report.get("schema") != "e4_live_readonly_stream_session_v2"
        or report.get("source") != "OFFICIAL_HYPERLIQUID_WS_PUBLIC_INFO_ONLY"
        or report.get("errors")
        or report.get("unobserved_subjects")
        or report.get("account_window_count") != 1
        or report.get("connection") != "CONNECTED"
        or report.get("disconnect_reason")
        not in ("BOUNDED_SESSION_ROTATION", "OPERATOR_REQUESTED_STOP")
    ):
        raise ValueError("SOURCE_SESSION_INCOMPLETE_OR_GAPPED")
    catalog_raw = _private_file(generation_dir / "discovery" / "dex_catalog.json")
    if sha256(catalog_raw).hexdigest() != report.get("dex_catalog_sha256"):
        raise ValueError("SOURCE_OFFICIAL_DEX_CATALOG_SHA_MISMATCH")
    catalog = _dex_universe(json.loads(catalog_raw))
    subjects = report.get("subjects")
    if not isinstance(subjects, dict):
        raise ValueError("SOURCE_SESSION_IDENTITIES_UNKNOWN")
    child_counts = report.get("subaccount_counts")
    if not isinstance(child_counts, dict):
        raise ValueError("SOURCE_SESSION_SUBACCOUNT_CENSUS_MISSING")
    for manager, scope in scopes.items():
        if scope.expected_dexs != catalog:
            raise ValueError("SOURCE_OFFICIAL_DEX_CATALOG_MISMATCH")
        if manager in subjects and subjects[manager] != scope.subject_sha:
            raise ValueError("SOURCE_SESSION_IDENTITY_MISMATCH")
        if manager in subjects and child_counts.get(manager) != 0:
            raise ValueError("SOURCE_SESSION_HAS_SUBACCOUNTS")
    candidates = []
    for metadata_path in sorted((generation_dir / "metadata").glob("*.json")):
        metadata = json.loads(_private_file(metadata_path))
        manager = metadata.get("subject")
        if manager not in scopes or metadata.get("channel") != "allDexsClearinghouseState":
            continue
        if subjects.get(manager) != scopes[manager].subject_sha:
            raise ValueError("SOURCE_SESSION_MANAGER_NOT_OBSERVED")
        filename = metadata.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("SOURCE_CAPTURE_FILENAME_INVALID")
        raw_frame = _private_file(generation_dir / "frames" / filename)
        # Preflight the whole immutable source generation before any append.
        capture_book(
            raw_frame=raw_frame,
            metadata=metadata,
            scope=scopes[manager],
            generation=generation_dir.name,
        )
        candidates.append((raw_frame, metadata, scopes[manager]))
    # A malformed or stale later frame cannot cause earlier frames to be
    # partly committed from the same purportedly complete generation.
    preflight_at = ingested_at or datetime.now(UTC).isoformat()
    last_receipt = None
    for _, metadata, _ in candidates:
        producer_at = metadata["locally_received_at"]
        _arrival_guard(producer_at, preflight_at, tracker.manifest["started_at"])
        if last_receipt is not None and clock(producer_at) < clock(last_receipt):
            raise ValueError("REORDERED_PRODUCER_RECEIPTS")
        last_receipt = producer_at
    for raw_frame, metadata, scope in candidates:
        ingest_captured_book(
            tracker,
            raw_frame=raw_frame,
            metadata=metadata,
            scope=scope,
            generation=generation_dir.name,
            ingested_at=ingested_at,
        )
    return {
        "schema": "combo2_prospective_ingest_v1",
        "raw_generation_sha256": sha256(
            _private_file(generation_dir / "session-report.json")
        ).hexdigest(),
        "source_books_recorded": len(candidates),
        "paper_journal_head": tracker.head,
        "live_trading_authorized": False,
        "network_order_requests": 0,
    }
