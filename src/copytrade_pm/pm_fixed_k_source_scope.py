"""Read-only, NAV-independent selected-source scope diagnostic.

Research observation is not independent live execution attestation. Source
positions and first-local clocks are required; unrelated source parent/child
collateral is neither required nor inferred for a *parent-only* copy policy.
"""

from __future__ import annotations

import re
from typing import Any

from .pm03_account import Instrument, clock, digest, number


def assess_selected_parent_perp_scope(
    book: dict[str, Any] | None,
    *,
    decision_at: str,
    max_age_seconds: float = 180,
) -> dict[str, object]:
    reasons: list[str] = []
    if not isinstance(book, dict):
        return {
            "status": "BLOCKED",
            "reasons": ["SELECTED_SOURCE_BOOK_MISSING"],
            "source_nav_required": False,
            "position_scope_observed": False,
        }
    if book.get("schema") != "paper_source_book_v1" or book.get("snapshot_sha") != digest(
        {key: value for key, value in book.items() if key != "snapshot_sha"}
    ):
        reasons.append("SELECTED_SOURCE_SHA_OR_SCHEMA_INVALID")
    if (
        not isinstance(book.get("wallet_id"), str)
        or not book["wallet_id"]
        or not isinstance(book.get("account_id"), str)
        or re.fullmatch(r"[0-9a-f]{64}", book["account_id"]) is None
    ):
        reasons.append("SELECTED_SOURCE_IDENTITY_MISSING")
    if book.get("snapshot_kind") != "OFFICIAL_WS_PER_ACCOUNT_ALL_DEX_ONLY":
        reasons.append("SELECTED_SOURCE_NOT_PER_ACCOUNT_ALL_DEX")
    if book.get("synthetic_fixture") is not False:
        reasons.append("SELECTED_SOURCE_NOT_REAL_PUBLIC_OBSERVATION")
    census, observed = book.get("dex_census"), book.get("observed_dexes")
    if (
        not isinstance(census, list)
        or not census
        or not all(isinstance(x, str) and x for x in census)
        or len(set(census)) != len(census)
        or not isinstance(observed, list)
        or not all(isinstance(x, str) and x for x in observed)
        or len(set(observed)) != len(observed)
        or set(census) != set(observed)
    ):
        reasons.append("SELECTED_SOURCE_DEX_CENSUS_INCOMPLETE")
    raw_positions = book.get("positions")
    if not isinstance(raw_positions, dict):
        reasons.append("SELECTED_SOURCE_POSITIONS_UNKNOWN")
    else:
        try:
            for key, qty in raw_positions.items():
                inst = Instrument.parse(key)
                if inst.venue != "hyperliquid" or inst.market not in (census or ()):
                    raise ValueError
                number(qty)
        except ValueError, TypeError:
            reasons.append("SELECTED_SOURCE_POSITION_INVALID")
    try:
        source_at = clock(book["source_event_at"])
        known_at = clock(book["first_known_at"])
        now = clock(decision_at)
        if (
            not 0 <= (now - known_at).total_seconds() <= max_age_seconds
            or not source_at <= known_at
        ):
            raise ValueError
    except ValueError, TypeError, KeyError:
        reasons.append("SELECTED_SOURCE_CLOCK_STALE_OR_INVALID")
    # Provider raw SHA must come from the original official frame, even though
    # it is NOT a provider cryptographic signature / execution authorization.
    raw_sha = book.get("provider_raw_sha")
    if not isinstance(raw_sha, str) or re.fullmatch(r"[0-9a-f]{64}", raw_sha) is None:
        reasons.append("SELECTED_SOURCE_PROVIDER_FRAME_SHA_MISSING")
    return {
        "status": "SELECTED_SCOPE_OBSERVED_RESEARCH_ONLY" if not reasons else "BLOCKED",
        "reasons": sorted(set(reasons)),
        "source_nav_required": False,
        "position_scope_observed": not reasons,
        "source_equity_relative_fidelity": False,
        "source_account_scope": "PARENT_PERPS_ONLY",
        "trading_authorized": False,
        "order_route": "NONE",
    }
