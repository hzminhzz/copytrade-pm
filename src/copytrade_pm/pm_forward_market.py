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
    observation: dict | None = None,
    quote_evidence: dict | None = None,
    costs: dict | None = None,
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
    if observed_quality == "VERIFIED_QUOTE":
        from .pm_forward_ccxt_market import verify_l2_evidence

        if observation is None:
            reasons.append("MARKET_CCXT_L2_OBSERVATION_MISSING")
        else:
            reasons.extend(
                verify_l2_evidence(quote_evidence, contract, observation, decision_at=decision_at)
            )
        try:
            if costs is None or digest(costs) != costs_sha:
                raise ValueError
            quoted_spread = number(contract["observed_spread_bps"])
            modeled_spread = number(contract["modeled_spread_bps"])
            if quoted_spread < 0 or modeled_spread < quoted_spread:
                reasons.append("MARKET_COST_UNDERESTIMATES_OBSERVED_SPREAD")
            if modeled_spread != number(costs["full_spread_bps"]):
                reasons.append("MARKET_COST_SPREAD_CONTRACT_MISMATCH")
        except ValueError, KeyError, TypeError:
            reasons.append("MARKET_CCXT_COST_ASSUMPTIONS_UNKNOWN")
        try:
            mark = number(contract["quote_mid"])
            min_notional = number(contract["minimum_notional"])
            if mark <= 0 or min_notional <= 0:
                raise ValueError
            if number(target_quantity) and abs(number(target_quantity) * mark) < min_notional:
                reasons.append("MARKET_NATIVE_MIN_NOTIONAL_VIOLATION")
        except ValueError, KeyError, TypeError:
            reasons.append("MARKET_NATIVE_MIN_NOTIONAL_UNKNOWN")
    return tuple(sorted(set(reasons)))
