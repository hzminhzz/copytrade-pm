"""Causal whole-wallet admission for forward paper, independent of vendor PnL.

Synthetic tests are explicitly labeled. Real sources require independently
authenticated complete-book evidence, which this module does not fabricate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .pm03_account import Instrument, clock, digest, number


@dataclass(frozen=True)
class Admission:
    admitted: bool
    reason_codes: tuple[str, ...]
    snapshot_sha: str | None
    source_equity: Decimal | None
    positions: dict[Instrument, Decimal]


def admit_source_book(
    source: dict[str, Any] | None, *, decision_at: str, fill_at: str
) -> Admission:
    """Fail closed unless native whole-book and collateral scope are attested."""
    if source is None or not isinstance(source, dict):
        return Admission(False, ("MISSING_SOURCE_BOOK",), None, None, {})
    reasons: list[str] = []
    sha = source.get("snapshot_sha")
    body = {key: value for key, value in source.items() if key != "snapshot_sha"}
    if sha != digest(body):
        reasons.append("SOURCE_SHA_MISMATCH")
    if source.get("schema") != "paper_source_book_v1":
        reasons.append("SOURCE_SCHEMA_UNKNOWN")
    if not source.get("wallet_id") or not source.get("account_id"):
        reasons.append("SOURCE_IDENTITY_UNKNOWN")
    if source.get("snapshot_kind") != "ATOMIC_WHOLE_ACCOUNT":
        reasons.append("SOURCE_NOT_ATOMIC_WHOLE_ACCOUNT")
    if source.get("account_scope_complete") is not True:
        reasons.append("SOURCE_ACCOUNT_SCOPE_INCOMPLETE")
    if source.get("hedges_complete") is not True:
        reasons.append("SOURCE_HEDGES_INCOMPLETE")
    if source.get("spot_scope_known") is not True:
        reasons.append("SOURCE_SPOT_UNKNOWN")
    if source.get("vault_scope_known") is not True:
        reasons.append("SOURCE_VAULT_UNKNOWN")
    if source.get("margin_mode") not in ("CROSS", "ISOLATED"):
        reasons.append("SOURCE_MARGIN_MODE_UNKNOWN")
    census = source.get("dex_census")
    observed_dexes = source.get("observed_dexes")
    if (
        not isinstance(census, list)
        or not census
        or len(census) != len(set(census))
        or not isinstance(observed_dexes, list)
        or set(census) != set(observed_dexes)
    ):
        reasons.append("SOURCE_DEX_CENSUS_INCOMPLETE")
    subs = source.get("subaccounts")
    observed_subs = source.get("observed_subaccounts")
    if (
        not isinstance(subs, list)
        or not isinstance(observed_subs, list)
        or len(set(subs)) != len(subs)
        or set(subs) != set(observed_subs)
    ):
        reasons.append("SOURCE_SUBACCOUNT_CENSUS_INCOMPLETE")
    timestamps = (
        source.get("source_event_at"),
        source.get("first_known_at"),
        decision_at,
        fill_at,
    )
    try:
        if any(not isinstance(t, str) for t in timestamps):
            raise ValueError
        if not (
            clock(timestamps[0])
            <= clock(timestamps[1])
            <= clock(timestamps[2])
            <= clock(timestamps[3])
        ):
            raise ValueError
    except ValueError, TypeError:
        reasons.append("SOURCE_CLOCK_ORDER_INVALID")
    equity = None
    try:
        if source.get("source_equity") is None:
            raise ValueError
        equity = number(source["source_equity"])
        if equity <= 0:
            raise ValueError
        if not source.get("collateral_denominator"):
            raise ValueError
        if number(source["collateral_value"]) < 0:
            raise ValueError
    except ValueError, TypeError, KeyError:
        reasons.append("SOURCE_EQUITY_OR_COLLATERAL_UNKNOWN")
    positions: dict[Instrument, Decimal] = {}
    raw_positions = source.get("positions")
    if not isinstance(raw_positions, dict):
        reasons.append("SOURCE_POSITIONS_UNKNOWN")
    else:
        try:
            positions = {Instrument.parse(key): number(q) for key, q in raw_positions.items()}
            if any(inst.market not in census for inst in positions):
                raise ValueError
        except ValueError, TypeError:
            reasons.append("SOURCE_NATIVE_POSITIONS_INVALID")
            positions = {}
    # No reader may turn an arbitrary JSON boolean into live source attestation.
    if source.get("synthetic_fixture") is not True:
        reasons.append("INDEPENDENT_REAL_BOOK_ATTESTATION_UNAVAILABLE")
    if reasons:
        return Admission(False, tuple(sorted(set(reasons))), sha, None, {})
    return Admission(True, (), sha, equity, positions)
