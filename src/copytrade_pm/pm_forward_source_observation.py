"""Safe read-only bridge for official Hyperliquid all-DEX account frames.

Reuse the native E4 parser rather than inventing a new position extractor.
An all-DEX frame is one *account's* perp scope at local receive time; it is
NOT a complete parent+subaccount+spot+vault NAV and cannot authorize a
forward-paper fill. No trade/exchange mutation API is imported.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from .pm03_account import clock, digest
from .pm_e4_prospective import _account_state, _dex_universe, _subaccount_roster
from .pm_forward_admission import admit_source_book
from .pm_forward_journal import PaperJournal


def _native_time(milliseconds: Any) -> str:
    if type(milliseconds) is not int or milliseconds <= 0:
        raise ValueError("SOURCE_PER_DEX_EVENT_CLOCK_UNKNOWN")
    try:
        return datetime.fromtimestamp(milliseconds / 1000, UTC).isoformat()
    except (OverflowError, ValueError) as exc:
        raise ValueError("SOURCE_PER_DEX_EVENT_CLOCK_INVALID") from exc


def read_public_all_dex_scope(
    *,
    alias: str,
    address: str,
    frame: dict,
    dex_catalog: object,
    discovered_subaccounts: object,
    first_known_at: str,
    max_age_seconds: float = 120,
) -> dict:
    """Produce a PIT account-scope observation that ALWAYS remains unadmitted."""
    known = clock(first_known_at)
    if not (0 < max_age_seconds <= 300):
        raise ValueError("SOURCE_PER_DEX_AGE_POLICY_INVALID")
    if frame.get("channel") != "allDexsClearinghouseState" or not isinstance(
        frame.get("data"), dict
    ):
        raise ValueError("SOURCE_FRAME_NOT_ALL_DEX_ACCOUNT")
    dexes = _dex_universe(dex_catalog)
    subaccounts = _subaccount_roster(discovered_subaccounts, address)
    parsed = _account_state(frame["data"], address, dexes)
    event_times = [_native_time(dex["state_at"]) for dex in parsed["per_dex"]]
    newest, oldest = max(event_times, key=clock), min(event_times, key=clock)
    if clock(newest) > known:
        raise ValueError("SOURCE_PROVIDER_EVENT_IN_FUTURE")
    if (known - clock(oldest)).total_seconds() > max_age_seconds:
        raise ValueError("SOURCE_PROVIDER_DEX_BOOK_STALE_OR_ASYNCHRONOUS")
    if (
        not alias
        or len(alias) > 70
        or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for char in alias
        )
    ):
        raise ValueError("SOURCE_ALIAS_INVALID")
    frame_sha = digest(frame)
    # We know there are N subaccounts; we do NOT know their simultaneous
    # collateral, positions, or their cross-dex/spot/vault completeness.
    partial = {
        "schema": "paper_source_book_v1",
        "wallet_id": alias,
        "account_id": sha256(address.lower().encode()).hexdigest(),
        "snapshot_kind": "OFFICIAL_WS_PER_ACCOUNT_ALL_DEX_ONLY",
        "account_scope_complete": False,
        "hedges_complete": False,
        "spot_scope_known": False,
        "vault_scope_known": False,
        "margin_mode": "UNKNOWN_WHOLE_ACCOUNT",
        "dex_census": ["mainnet:perp:" + name for name in sorted(dexes)],
        "observed_dexes": ["mainnet:perp:" + name for name in sorted(dexes)],
        "subaccounts": [sha256(item.lower().encode()).hexdigest() for item in subaccounts],
        "observed_subaccounts": [],
        "source_event_at": newest,
        "first_known_at": first_known_at,
        "source_equity": None,
        "collateral_denominator": None,
        "collateral_value": None,
        "positions": parsed["positions"],
        "per_dex_margin_diagnostics": parsed["per_dex"],
        "position_margin_diagnostics": parsed["native_position_risk_metadata"],
        "whole_wallet_margin_reconciled": False,
        "source_marks": {},
        "synthetic_fixture": False,
        "provider_raw_sha": frame_sha,
        "provider_signed": False,
    }
    partial["snapshot_sha"] = digest(partial)
    blockers = admit_source_book(
        partial,
        decision_at=first_known_at,
        fill_at=first_known_at,
    )
    if blockers.admitted:
        raise ValueError("SOURCE_PARTIAL_SCOPE_UNEXPECTEDLY_ADMITTED")
    return {
        "schema": "paper_first_known_source_v1",
        "source_id": alias,
        "source_event_at": newest,
        "first_known_at": first_known_at,
        "captured_at": first_known_at,
        "payload_sha": partial["snapshot_sha"],
        "source_book": partial,
        "evidence_class": "OFFICIAL_PUBLIC_PER_ACCOUNT_OBSERVED_NOT_WHOLE_WALLET",
        "status": "BLOCKED_INCOMPLETE_WHOLE_WALLET",
        "admission_reasons": list(blockers.reason_codes),
        "account_position_count": parsed["position_count"],
        "dex_count": len(dexes),
        "discovered_subaccount_count": len(subaccounts),
        "source_sha": frame_sha,
        "account_scope_first_known": True,
        "whole_wallet_equity_attested": False,
        "paper_observed": False,
        "order_route": "NONE",
    }


def append_public_scope(
    journal: PaperJournal,
    *,
    alias: str,
    seq: int | None,
    receipt: dict,
    stream_event: dict | None = None,
) -> dict:
    if receipt.get("schema") not in ("paper_first_known_source_v1", "paper_first_known_source_v2"):
        raise ValueError("SOURCE_UNVERIFIED_RECEIPT_VERSION")
    if receipt.get("schema") == "paper_first_known_source_v2" and (
        receipt.get("source_book", {}).get("schema") != "paper_source_book_v2"
        or receipt.get("wire_raw_sha") != (stream_event or {}).get("raw_sha")
        or (stream_event or {}).get("schema") != "paper_observer_stream_event_v2"
    ):
        raise ValueError("SOURCE_COMPACT_PROOF_MISSING")
    if receipt.get("source_id") != alias or receipt.get("status") != (
        "BLOCKED_INCOMPLETE_WHOLE_WALLET"
    ):
        raise ValueError("SOURCE_UNVERIFIED_SCOPE_REFUSED")
    if receipt.get("whole_wallet_equity_attested") is not False:
        raise ValueError("SOURCE_FALSE_ATTESTATION_REFUSED")
    if receipt.get("evidence_class") != ("OFFICIAL_PUBLIC_PER_ACCOUNT_OBSERVED_NOT_WHOLE_WALLET"):
        raise ValueError("SOURCE_WRONG_EVIDENCE_CLASS")
    book = receipt.get("source_book", {})
    if (
        not isinstance(book, dict)
        or book.get("snapshot_kind") != "OFFICIAL_WS_PER_ACCOUNT_ALL_DEX_ONLY"
        or book.get("synthetic_fixture") is not False
        or book.get("account_scope_complete") is not False
        or book.get("source_equity") is not None
        or receipt.get("payload_sha") != book.get("snapshot_sha")
        or book["snapshot_sha"]
        != digest({key: value for key, value in book.items() if key != "snapshot_sha"})
    ):
        raise ValueError("SOURCE_BOOK_RECEIPT_HASH_MISMATCH")
    return journal.append_source_receipt(
        alias, seq, digest(receipt), receipt, stream_event=stream_event
    )
