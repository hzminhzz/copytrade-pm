"""Pure selected-account Vike position reducer, independent of paper finance.

This module never emits a V4 OBSERVED_STATE_CHANGE or any broker action.
It builds *candidate* native quantities for later independently versioned proof.
The original Vike frame journal and the official archive remain the evidence
owners; derived books are not independent sources of truth.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .pm03_account import clock, digest
from .pm_vike_position_observations import validate
from .pm_vike_stream_canary import _cursor, allowed_wallet

MARKET_PREFIX = "hyperliquid/mainnet:perp:"
ALLOWED_NATIVE_ROUNDING = Decimal("0.00000001")
MAX_EVENT_LAG_SECONDS = 120


class CandidatePositionBook(BaseModel):
    """Immutable-in-structure contract. Not accepted by any finance consumer."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    contract_version: Literal["vike_complete_perp_candidate_v1"] = "vike_complete_perp_candidate_v1"
    account_sha256: str
    baseline_manifest_sha256: str
    last_official_manifest_sha256: str
    epoch_id: str
    dexes: tuple[str, ...]
    positions: tuple[tuple[str, str], ...]
    baseline_known_at: str
    last_first_known_at: str
    last_provider_event_at: str
    last_stream_cursor: str
    last_event_id_sha256: str | None = None
    event_chain_sha256: str = "0" * 64
    event_count: int = 0
    status: Literal[
        "BASELINE_NON_ACTIONABLE",
        "PENDING_INDEPENDENT_RECONCILIATION",
        "RECONCILED_CANDIDATE_NOT_PAPER_PROOF",
        "GAP_INELIGIBLE",
    ] = "BASELINE_NON_ACTIONABLE"
    gap_reason: str | None = None
    official_parity_verified: bool = False
    first_known_transition: str | None = None
    paper_new_risk_eligible: Literal[False] = False
    order_route: Literal["NONE"] = "NONE"


def _native(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("VIKE_REDUCER_NATIVE_BOOLEAN")
    try:
        number = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError("VIKE_REDUCER_NATIVE_QUANTITY_INVALID") from exc
    if not number.is_finite():
        raise ValueError("VIKE_REDUCER_NATIVE_QUANTITY_INVALID")
    return number


def _normalized(positions: dict) -> tuple[tuple[str, str], ...]:
    if not isinstance(positions, dict):
        raise ValueError("VIKE_REDUCER_BOOK_NOT_MAPPING")
    result = []
    for key, value in sorted(positions.items()):
        if not isinstance(key, str) or not key.startswith(MARKET_PREFIX):
            raise ValueError("VIKE_REDUCER_MARKET_INVALID")
        quantity = _native(value)
        if quantity:
            result.append((key, str(quantity)))
    return tuple(result)


def _iso(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("VIKE_REDUCER_TIMESTAMP_INVALID")
    return clock(value)


def _stream_epoch(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
        raise ValueError("VIKE_REDUCER_EPOCH_INVALID")
    return value


def start_nonactionable_baseline(
    account: str,
    *,
    official_census: dict,
    manifest_sha256: str,
    live_subscription_ack_at: str,
    stream_cursor: str,
    stream_epoch: str,
    had_gap: bool,
) -> CandidatePositionBook:
    """Initial official book; a stream GAP cannot be silently cleared here."""
    wallet = allowed_wallet(account)
    if official_census.get("original_bytes_independently_verified") is not True:
        raise ValueError("VIKE_REDUCER_BASELINE_ORIGINAL_PROOF_MISSING")
    if sha256(wallet.encode()).hexdigest() != official_census.get("account_sha256"):
        raise ValueError("VIKE_REDUCER_BASELINE_ACCOUNT_MISMATCH")
    if official_census.get("manifest_sha256") != manifest_sha256:
        raise ValueError("VIKE_REDUCER_BASELINE_ARCHIVE_ID_MISMATCH")
    if official_census.get("scope_parity") is not True:
        raise ValueError("VIKE_REDUCER_BASELINE_DEX_INCOMPLETE")
    ack_time = _iso(live_subscription_ack_at)
    known_at = _iso(official_census["completed_at"])
    if ack_time > known_at:
        raise ValueError("VIKE_REDUCER_BASELINE_ACK_AFTER_BOOK")
    dexs = tuple(sorted(official_census["dex_provider_times_ms"]))
    if not dexs or dexs != tuple(sorted(official_census["dex_state_shas"])):
        raise ValueError("VIKE_REDUCER_BASELINE_DEX_PARITY_MISMATCH")
    provider_time = max(official_census["dex_provider_times_ms"].values())
    event_time = datetime.fromtimestamp(provider_time / 1000, known_at.tzinfo)
    if event_time > known_at or (known_at - event_time).total_seconds() > 30:
        raise ValueError("VIKE_REDUCER_BASELINE_SOURCE_STALE")
    status = "GAP_INELIGIBLE" if had_gap else "BASELINE_NON_ACTIONABLE"
    return CandidatePositionBook(
        account_sha256=sha256(wallet.encode()).hexdigest(),
        baseline_manifest_sha256=manifest_sha256,
        last_official_manifest_sha256=manifest_sha256,
        epoch_id=_stream_epoch(stream_epoch),
        dexes=dexs,
        positions=_normalized(official_census["positions"]),
        baseline_known_at=official_census["completed_at"],
        last_first_known_at=official_census["completed_at"],
        last_provider_event_at=event_time.isoformat(),
        last_stream_cursor=_cursor(stream_cursor),
        status=status,
        gap_reason="PRE_BASELINE_STREAM_GAP" if had_gap else None,
    )


def mark_gap(state: CandidatePositionBook, *, reason: str) -> CandidatePositionBook:
    if not isinstance(reason, str) or not re.fullmatch(r"[A-Z0-9_]{4,90}", reason):
        raise ValueError("VIKE_REDUCER_GAP_REASON_INVALID")
    return state.model_copy(
        update={
            "status": "GAP_INELIGIBLE",
            "gap_reason": reason,
            "official_parity_verified": False,
            "first_known_transition": None,
        }
    )


def _market_key(event: dict) -> tuple[str, str]:
    subject, data = event["subject"], event["data"]
    dex, symbol = data["dex"], subject["symbol"]
    if dex == "HL":
        return "default", MARKET_PREFIX + "default/" + symbol
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dex):
        raise ValueError("VIKE_REDUCER_MARKET_DEX_INVALID")
    return dex, MARKET_PREFIX + dex + "/" + symbol.split(":", 1)[1]


def candidate_from_vike_event(
    state: CandidatePositionBook,
    *,
    event: dict,
    raw_event_sha256: str,
    cursor: str,
    local_first_known_at: str,
    is_prospective: bool,
    has_stream_gap: bool,
    epoch_id: str,
) -> CandidatePositionBook:
    """Build an immutable proposed book; never return actionable source proof."""
    if state.status == "GAP_INELIGIBLE":
        return state
    if has_stream_gap or not is_prospective:
        return mark_gap(state, reason="NONPROSPECTIVE_OR_GAP_EVENT")
    if _stream_epoch(epoch_id) != state.epoch_id:
        return mark_gap(state, reason="SOURCE_EPOCH_CHANGED")
    cursor = _cursor(cursor)
    if cursor <= state.last_stream_cursor:
        return mark_gap(state, reason="STREAM_CURSOR_REORDERED")
    if not re.fullmatch(r"[0-9a-f]{64}", raw_event_sha256):
        return mark_gap(state, reason="SOURCE_ORIGINAL_HASH_INVALID")
    selected_wallet = event.get("subject", {}).get("wallet")
    selected_wallet = allowed_wallet(selected_wallet)
    event_id, _, _, _, after_str = validate(event, (selected_wallet,))
    if sha256(selected_wallet.encode()).hexdigest() != state.account_sha256:
        return mark_gap(state, reason="SOURCE_SELECTED_ACCOUNT_MISMATCH")
    dex, key = _market_key(event)
    if dex not in state.dexes:
        return mark_gap(state, reason="SOURCE_UNKNOWN_PERP_DEX")
    observed_at, event_at = _iso(local_first_known_at), _iso(event["ts"])
    if (
        observed_at < _iso(state.last_first_known_at)
        or event_at <= _iso(state.last_provider_event_at)
        or observed_at < event_at
        or (observed_at - event_at).total_seconds() > MAX_EVENT_LAG_SECONDS
    ):
        return mark_gap(state, reason="SOURCE_EVENT_CLOCK_OR_LAG")
    quantities = dict(state.positions)
    prior = _native(quantities.get(key, "0"))
    start = _native(event["data"]["start_position"])
    amount = _native(event["data"]["size_token"])
    after = _native(after_str)
    if start != prior:
        return mark_gap(state, reason="SOURCE_POSITION_PRESTATE_MISMATCH")
    side = event["data"]["side"]
    expected = start + (amount if side == "buy" else -amount)
    if abs(expected - after) > ALLOWED_NATIVE_ROUNDING:
        return mark_gap(state, reason="SOURCE_NATIVE_DELTA_MISMATCH")
    action = event["data"]["action"]
    calculated_action = (
        "open"
        if start == 0 and after != 0
        else "close"
        if after == 0 and start != 0
        else "flip"
        if start * after < 0
        else "increase"
        if abs(after) > abs(start)
        else "reduce"
        if abs(after) < abs(start)
        else "unchanged"
    )
    if calculated_action != action:
        return mark_gap(state, reason="SOURCE_POSITION_ACTION_MISMATCH")
    if after:
        quantities[key] = str(after)
    else:
        quantities.pop(key, None)
    transition_id = sha256(event_id.encode()).hexdigest()
    chain = digest(
        [state.event_chain_sha256, transition_id, raw_event_sha256, cursor, local_first_known_at]
    )
    return state.model_copy(
        update={
            "positions": _normalized(quantities),
            "last_event_id_sha256": transition_id,
            "last_stream_cursor": cursor,
            "last_first_known_at": local_first_known_at,
            "last_provider_event_at": event["ts"],
            "event_chain_sha256": chain,
            "event_count": state.event_count + 1,
            "status": "PENDING_INDEPENDENT_RECONCILIATION",
            "official_parity_verified": False,
            "first_known_transition": None,
        }
    )


def reconcile_candidate_with_official(
    state: CandidatePositionBook,
    *,
    verified_census: dict,
    manifest_sha256: str,
) -> CandidatePositionBook:
    """Exact independent full-book comparison. Still NOT V4 source admission."""
    if state.status == "GAP_INELIGIBLE":
        return state
    if verified_census.get("original_bytes_independently_verified") is not True:
        return mark_gap(state, reason="SOURCE_RECON_ORIGINAL_PROOF_MISSING")
    if verified_census.get("manifest_sha256") != manifest_sha256:
        return mark_gap(state, reason="SOURCE_RECON_MANIFEST_DRIFT")
    if verified_census.get("account_sha256") != state.account_sha256:
        return mark_gap(state, reason="SOURCE_RECON_ACCOUNT_MISMATCH")
    if tuple(sorted(verified_census.get("dex_state_shas", {}))) != state.dexes:
        return mark_gap(state, reason="SOURCE_RECON_DEX_SCOPE_MISMATCH")
    recon_time = _iso(verified_census["completed_at"])
    if recon_time < _iso(state.last_first_known_at):
        return mark_gap(state, reason="SOURCE_RECON_BEFORE_FIRST_KNOWN")
    if any(
        datetime.fromtimestamp(timestamp / 1000, recon_time.tzinfo)
        < _iso(state.last_provider_event_at)
        for timestamp in verified_census["dex_provider_times_ms"].values()
    ):
        return mark_gap(state, reason="SOURCE_RECON_BEFORE_EVENT")
    if _normalized(verified_census.get("positions")) != state.positions:
        return mark_gap(state, reason="SOURCE_RECON_WHOLE_BOOK_MISMATCH")
    # A quiet baseline periodic check remains non-actionable. An event may
    # become a reconciled candidate, but requires a distinct source proof
    # contract and current stream health before V4 can ever accept it.
    return state.model_copy(
        update={
            "last_official_manifest_sha256": manifest_sha256,
            "status": (
                "RECONCILED_CANDIDATE_NOT_PAPER_PROOF"
                if state.event_count
                else "BASELINE_NON_ACTIONABLE"
            ),
            "official_parity_verified": True,
            "first_known_transition": (state.last_first_known_at if state.event_count else None),
        }
    )
