"""Conservative public L2 price/fee estimate, never an admitted paper fill.

The current CCXT feed captures a SHA-bound best bid/ask with displayed sizes,
not venue-complete traded volume, depth trajectory, or impact. Restrict quote
estimates to the *observed* best level and label them SCENARIO_ONLY.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .pm03_account import clock, digest, number
from .pm_forward_journal import PaperJournal


def preview_top_level_paper_cost(
    evidence: dict[str, Any],
    *,
    signed_qty: Decimal,
    fee_bps: Decimal,
    as_of: str,
    adverse_bps: Decimal = Decimal("0"),
    max_quote_age_seconds: int = 30,
) -> dict:
    """Price a hypothetical market order against an observed best level.

    No cross-level fill, no invented market volume, no spread double charge,
    and NO mutation to PM-03 accounts.
    """
    PaperJournal._validate_market_quote(evidence)
    checked = clock(as_of)
    known = clock(evidence["first_known_at"])
    if type(max_quote_age_seconds) is not int or not 1 <= max_quote_age_seconds <= 300:
        raise ValueError("QUOTE_COST_FRESHNESS_POLICY_INVALID")
    age = (checked - known).total_seconds()
    if age < 0:
        return {
            "status": "BLOCKED_QUOTE_NOT_YET_KNOWN",
            "quote_first_known_at": evidence["first_known_at"],
            "as_of": as_of,
            "paper_executed": False,
            "order_route": "NONE",
        }
    if age > max_quote_age_seconds:
        return {
            "status": "BLOCKED_QUOTE_STALE_AS_OF",
            "quote_first_known_at": evidence["first_known_at"],
            "as_of": as_of,
            "quote_age_seconds": age,
            "paper_executed": False,
            "order_route": "NONE",
        }
    qty, fee_rate, extra = number(signed_qty), number(fee_bps), number(adverse_bps)
    if qty == 0:
        return {"status": "NO_NET_DELTA", "order_route": "NONE", "paper_executed": False}
    if not (Decimal("0") <= fee_rate <= Decimal("100") and Decimal("0") <= extra <= Decimal("200")):
        raise ValueError("QUOTE_COST_POLICY_INVALID")
    bid, ask = number(evidence["best_bid"]), number(evidence["best_ask"])
    mid = number(evidence["mid_quote"])
    buy = qty > 0
    displayed = number(evidence["ask_size"] if buy else evidence["bid_size"])
    if abs(qty) > displayed:
        return {
            "status": "BLOCKED_UNPROVEN_DEPTH",
            "displayed_base": str(displayed),
            "requested_base": str(abs(qty)),
            "paper_executed": False,
            "order_route": "NONE",
        }
    # The side of the book already contains half-spread: do not charge it twice.
    side_price = ask if buy else bid
    multiplier = Decimal("1") + (extra / Decimal("10000")) * (1 if buy else -1)
    price = side_price * multiplier
    notional = abs(qty) * price
    fee = notional * fee_rate / Decimal("10000")
    half_spread_cost = abs(qty) * abs(side_price - mid)
    additional_slippage = abs(qty) * abs(price - side_price)
    return {
        "schema": "paper_quote_only_cost_estimate_v1",
        "status": "SCENARIO_ONLY_PRICE_ESTIMATE",
        "quote_sha": digest(evidence),
        "instrument": evidence["instrument"],
        "first_known_at": evidence["first_known_at"],
        "as_of": as_of,
        "quote_age_seconds": age,
        "market_orderability_attested": False,
        "side": "BUY" if buy else "SELL",
        "quantity": str(abs(qty)),
        "mid": str(mid),
        "best_level": str(side_price),
        "modeled_price": str(price),
        "notional": str(notional),
        "taker_fee": str(fee),
        "half_spread_cost": str(half_spread_cost),
        "additional_slippage_cost": str(additional_slippage),
        "impact_or_deeper_book_observed": False,
        "complete_volume_attested": False,
        "paper_executed": False,
        "order_route": "NONE",
    }
