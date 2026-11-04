"""Paper-only market identity, clock and lot admission (FP-07).

Never infer a live exchange book from a candle or a ticker alias.
"""

from __future__ import annotations

from decimal import Decimal

from .pm03_account import Instrument, clock, digest, number


def market_contract_reasons(
    contract: dict | None,
    *,
    instrument: Instrument,
    observed_quality: str,
    decision_at: str,
    target_quantity: Decimal,
    costs_sha: str,
) -> tuple[str, ...]:
    """Return explicit refusal reasons, never round or fabricate lots."""
    if not isinstance(contract, dict):
        return ("MARKET_CONTRACT_UNKNOWN",)
    reasons: list[str] = []
    body = {k: v for k, v in contract.items() if k != "contract_sha"}
    if contract.get("contract_sha") != digest(body):
        reasons.append("MARKET_CONTRACT_SHA_MISMATCH")
    if contract.get("schema") != "paper_market_contract_v1":
        reasons.append("MARKET_CONTRACT_SCHEMA_UNKNOWN")
    if contract.get("instrument") != instrument.key:
        reasons.append("MARKET_NATIVE_ID_MISMATCH")
    if contract.get("quality") != observed_quality:
        reasons.append("MARKET_QUALITY_MISMATCH")
    if contract.get("costs_sha") != costs_sha:
        reasons.append("MARKET_COST_POLICY_SHA_MISMATCH")
    if contract.get("session_open") is not True:
        reasons.append("MARKET_SESSION_UNKNOWN_OR_CLOSED")
    if contract.get("market_permitted") is not True:
        reasons.append("MARKET_NOT_PERMITTED")
    try:
        if clock(contract["first_known_at"]) > clock(decision_at):
            raise ValueError
    except ValueError, KeyError, TypeError:
        reasons.append("MARKET_CONTRACT_NOT_YET_KNOWN")
    try:
        step = number(contract["quantity_step"])
        minimum = number(contract["minimum_quantity"])
        qty = abs(number(target_quantity))
        if step <= 0 or minimum <= 0 or minimum < step:
            raise ValueError
        if qty and (qty < minimum or qty % step):
            reasons.append("MARKET_UNSUPPORTED_QUANTITY_INCREMENT")
    except ValueError, TypeError, KeyError:
        reasons.append("MARKET_LOT_CONTRACT_UNKNOWN")
    return tuple(sorted(set(reasons)))
