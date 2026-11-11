"""Verify source-observer signed V4 packets without widening subscriptions.

A packet signature is not independent original evidence; consumers must supply
the pinned independent public key and the verified original journal.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .pm03_account import digest
from .pm_forward_stream_anchor import VerifiedAnchor, _reader, verify_suffix
from .pm_forward_stream_journal import verify_streams
from .production_manifest import verify
from .v4_source_export import export_signed_events


def verify_packet(
    packet: dict,
    public: Ed25519PublicKey,
    *,
    selected: dict[str, str],
    original_journal: Path,
    after: dict[str, int] | None,
    as_of: datetime,
    policy_version: str,
    frozen_k: str,
    verified_anchor: VerifiedAnchor | None = None,
) -> dict:
    """Check signed original bindings and regenerate exact original event identity.

    The independent verifier uses the original existing journal and scope owner,
    not the report-provided signed digest as evidence of economic authenticity.
    Regeneration uses an ephemeral key solely for building canonical *payloads*;
    signatures are never compared and no journal/source state is written.
    """
    from decimal import Decimal

    if as_of.utcoffset() != __import__("datetime").timedelta(0):
        raise ValueError("SOURCE_ASOF_UTC_REQUIRED")
    if not selected or not isinstance(policy_version, str) or not policy_version:
        raise ValueError("SOURCE_POLICY_REQUIRED")
    k = Decimal(frozen_k)
    if not k.is_finite() or k == 0:
        raise ValueError("SOURCE_FROZEN_K_INVALID")
    if (
        set(packet) != {"schema", "head_cursors", "events", "trading_authorized", "batch_envelope"}
        or packet["schema"] != "v4_signed_source_export_v1"
        or packet["trading_authorized"] is not False
    ):
        raise ValueError("SOURCE_PACKET_SCHEMA")
    verified = verify(packet["batch_envelope"], public, "source-observer-v4-batch")
    if verified != {
        "schema": "v4_source_batch_binding_v1",
        "selected": {k: v.lower() for k, v in selected.items()},
        "head_cursors": packet["head_cursors"],
        "events_sha": digest(packet["events"]),
        "trading_authorized": False,
    }:
        raise ValueError("SOURCE_PACKET_SELECTION_MISMATCH")
    if set(packet["events"]) != set(selected) or set(packet["head_cursors"]) != set(selected):
        raise ValueError("SOURCE_PACKET_SCOPE_MISMATCH")
    # Re-extract original events from the original owner; no self-authenticated
    # local report/packet can replace source receipts and hash chain validation.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    original = export_signed_events(
        original_journal,
        selected=selected,
        signer=Ed25519PrivateKey.generate(),
        after=after,
        verified_anchor=verified_anchor,
    )
    if packet["head_cursors"] != original["head_cursors"]:
        raise ValueError("SOURCE_ORIGINAL_HEAD_DIVERGED")
    opportunities = []
    missing = []
    seen = set()
    for alias, events in sorted(packet["events"].items()):
        expected = original["events"][alias]
        if len(events) != len(expected):
            raise ValueError("SOURCE_PACKET_ORIGINAL_LENGTH")
        for received, source in zip(events, expected, strict=True):
            proof = verify(received["proof"], public, "source-observer-v4")
            actual = source["proof"]["payload"]
            if proof != actual or (received["book"] is None) != (source["book"] is None):
                raise ValueError("SOURCE_ORIGINAL_PROOF_MISMATCH")
            if received["book"] is not None:
                book = verify(received["book"], public, "source-observer")
                if book != source["book"]["payload"]:
                    raise ValueError("SOURCE_ORIGINAL_BOOK_MISMATCH")
            known = datetime.fromtimestamp(proof["first_known_ms"] / 1000, UTC)
            if known > as_of:
                raise ValueError("SOURCE_FUTURE_OBSERVATION")
            key = (proof["stream_id"], proof["stream_cursor"])
            if key in seen:
                raise ValueError("SOURCE_DUPLICATE_CURSOR")
            seen.add(key)
            kind = proof["kind"]
            if kind == "GAP":
                missing.append(
                    {
                        "started_at": known.isoformat(),
                        "recovered_at": None,
                        "reason": "GAP",
                        "missed_opportunities": "UNKNOWN",
                        "original_source_receipt_sha256": proof["source_receipt_sha"],
                        "original_source_cursor": proof["stream_cursor"],
                        "source_epoch": proof["stream_epoch"],
                    }
                )
            elif kind == "BASELINE":
                if missing and missing[-1]["recovered_at"] is None:
                    missing[-1]["recovered_at"] = known.isoformat()
            elif kind == "OBSERVATION":
                if proof["classification"] != "OBSERVED_STATE_CHANGE":
                    raise ValueError("SOURCE_CHANGE_CLASS_INVALID")
                if not proof["continuity"] or not proof["full_selected_scope"]:
                    missing.append(
                        {
                            "started_at": known.isoformat(),
                            "recovered_at": None,
                            "reason": "INCOMPLETE_SCOPE",
                            "missed_opportunities": "UNKNOWN",
                            "original_source_receipt_sha256": proof["source_receipt_sha"],
                            "original_source_cursor": proof["stream_cursor"],
                            "source_epoch": proof["stream_epoch"],
                        }
                    )
                    continue
                first = datetime.fromtimestamp(proof["first_known_ms"] / 1000, UTC)
                observed = datetime.fromtimestamp(proof["source_event_ms"] / 1000, UTC)
                if observed > first:
                    raise ValueError("SOURCE_EVENT_AHEAD_OF_KNOWLEDGE")
                opportunities.append(
                    {
                        "opportunity_id": digest(
                            [
                                proof["stream_id"],
                                proof["stream_cursor"],
                                proof["observer_event_sha"],
                                policy_version,
                            ]
                        ),
                        "source_event_sha256": proof["observer_event_sha"],
                        "source_receipt_sha256": proof["source_receipt_sha"],
                        "source_event_at": observed.isoformat(),
                        "first_known_at": first.isoformat(),
                        "due_at": (
                            first + __import__("datetime").timedelta(seconds=300)
                        ).isoformat(),
                        "stream_cursor": proof["stream_cursor"],
                        "source_epoch": proof["stream_epoch"],
                        "frozen_k_version": policy_version,
                        "frozen_k": frozen_k,
                    }
                )
    # Legacy full-journal hash cannot be inferred from one independently
    # anchored stream. Keep an explicit separate proof version.
    if verified_anchor is None:
        proof_digest = digest(verify_streams(original_journal)["streams"])
    else:
        if len(selected) != 1:
            raise ValueError("SOURCE_ANCHORED_SELECTED_SCOPE_REQUIRED")
        alias, account = next(iter(selected.items()))
        with closing(_reader(original_journal)) as db:
            head_proof = verify_suffix(db, verified_anchor, alias=alias, account=account)
        if head_proof["stream_cursor"] != original["head_cursors"][alias]:
            raise ValueError("SOURCE_ORIGINAL_HEAD_MOVED_DURING_VERIFICATION")
        proof_digest = digest(
            {
                "schema": "strategy_source_anchored_proof_v1",
                "anchor_file_sha256": verified_anchor.seal_file_sha256,
                "auditor_key_sha256": verified_anchor.auditor_key_sha256,
                "selected_account_sha256": verified_anchor.payload["account_sha256"],
                "stream_cursor": head_proof["stream_cursor"],
                "stream_chain_sha": head_proof["stream_chain_sha"],
                "source_cursor": head_proof["source_cursor"],
                "source_chain_sha": head_proof["source_chain_sha"],
            }
        )
    return {
        "schema": (
            "strategy_source_verification_v1"
            if verified_anchor is None
            else "strategy_source_verification_v2_anchored"
        ),
        "source_status": "GAP" if any(x["recovered_at"] is None for x in missing) else "VERIFIED",
        "opportunities": opportunities,
        "missing_intervals": missing,
        "verified_original_journal_sha256": proof_digest,
        "read_only": True,
        "trading_authorized": False,
    }
