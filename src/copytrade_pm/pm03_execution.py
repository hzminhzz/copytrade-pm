"""Deterministic PM-03 hypothetical execution, NOT broker routing.

1m OHLCV snapshots are proxies, never bid/ask/order book claims. Internal
virtual crosses transfer attribution at the known mark without market fills.
Only residual external deltas incur modeled execution costs and capacity caps.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D

from .pm03_account import Account, Instrument, RiskState, ZERO, clock, number


@dataclass(frozen=True)
class MarketObservation:
    instrument: Instrument
    event_at: str
    first_known_at: str
    mark: D
    volume_base: D | None
    quality: str = "SYNTHETIC"
    supported: bool = False
    # Displayed best-level liquidity is not traded volume. The two modes are
    # deliberately disjoint so quote depth can never be silently relabeled ADV.
    capacity_basis: str = "TRADED_VOLUME"
    best_bid: D | None = None
    best_ask: D | None = None
    bid_size: D | None = None
    ask_size: D | None = None
    quantity_step: D | None = None
    minimum_notional: D | None = None

    def validate(self, decision_at: str) -> None:
        if clock(self.event_at) > clock(self.first_known_at) or (
            clock(self.first_known_at) > clock(decision_at)
        ):
            raise ValueError("MARKET_POINT_IN_TIME_VIOLATION")
        if number(self.mark) <= ZERO:
            raise ValueError("INVALID_MARK")
        if self.volume_base is not None and number(self.volume_base) < ZERO:
            raise ValueError("INVALID_VOLUME")
        if self.quality not in ("SYNTHETIC", "OHLCV_1M_PROXY", "VERIFIED_QUOTE"):
            raise ValueError("UNSUPPORTED_MARKET_QUALITY")
        if self.capacity_basis not in ("TRADED_VOLUME", "DISPLAYED_L2_TOP_LEVEL"):
            raise ValueError("UNKNOWN_CAPACITY_BASIS")
        if self.capacity_basis == "DISPLAYED_L2_TOP_LEVEL":
            if self.quality != "VERIFIED_QUOTE" or self.volume_base is not None:
                raise ValueError("L2_DEPTH_MUST_NOT_BE_TRADED_VOLUME")
            if any(v is None for v in (self.best_bid, self.best_ask, self.bid_size, self.ask_size)):
                raise ValueError("INCOMPLETE_L2_TOP_LEVEL")
            if not (
                ZERO < number(self.best_bid) <= number(self.mark) <= number(self.best_ask)
                and number(self.bid_size) > ZERO
                and number(self.ask_size) > ZERO
            ):
                raise ValueError("INVALID_L2_TOP_LEVEL")
            if self.quantity_step is None or self.minimum_notional is None:
                raise ValueError("L2_NATIVE_LOT_CONTRACT_MISSING")
            if number(self.quantity_step) <= ZERO or number(self.minimum_notional) <= ZERO:
                raise ValueError("L2_NATIVE_LOT_CONTRACT_INVALID")

    def capacity_for(self, delta: D) -> D | None:
        if self.capacity_basis == "DISPLAYED_L2_TOP_LEVEL":
            return number(self.ask_size if delta > ZERO else self.bid_size)
        return self.volume_base


@dataclass(frozen=True)
class CostModel:
    fee_bps: D
    full_spread_bps: D
    slippage_bps: D
    impact_bps_at_full_participation: D
    max_participation: D
    max_age_seconds: int
    latency_seconds: int

    def __post_init__(self) -> None:
        for name in (
            "fee_bps",
            "full_spread_bps",
            "slippage_bps",
            "impact_bps_at_full_participation",
        ):
            if number(getattr(self, name)) < ZERO:
                raise ValueError("NEGATIVE_COST_ASSUMPTION")
        if not ZERO < number(self.max_participation) <= D("1"):
            raise ValueError("INVALID_PARTICIPATION")
        if self.max_age_seconds < 0 or self.latency_seconds < 0:
            raise ValueError("INVALID_EXECUTION_TIME")

    def price_and_fee(self, qty: D, quote: MarketObservation) -> tuple[D, D, dict]:
        liquidity = quote.capacity_for(qty)
        if liquidity is None or liquidity <= ZERO:
            raise ValueError("MISSING_LIQUIDITY")
        if quote.capacity_basis == "DISPLAYED_L2_TOP_LEVEL":
            # Model only the displayed side. Never infer deeper book or actual
            # execution; spread is already embedded in the best bid/ask.
            side = number(quote.best_ask if qty > ZERO else quote.best_bid)
            direction = D("1") if qty > ZERO else D("-1")
            px = (side * (D("1") + direction * self.slippage_bps / D("10000"))).quantize(
                D("0.00000001")
            )
            if px <= ZERO:
                raise ValueError("NEGATIVE_EXECUTION_PRICE")
            fee = (abs(qty * px) * self.fee_bps / D("10000")).quantize(D("0.00000001"))
            return (
                px,
                fee,
                {
                    "execution_price": str(px),
                    "fee": str(fee),
                    "spread_slippage_impact_bps": str(
                        (px / quote.mark - D("1")) * direction * D("10000")
                    ),
                    "mid_price": str(quote.mark),
                    "quality": quote.quality,
                    "capacity_basis": quote.capacity_basis,
                    "not_real_bid_ask": False,
                    "hypothetical_only": True,
                    "deeper_book_and_actual_fill_unknown": True,
                },
            )
        share = abs(qty) / liquidity
        bps = (
            self.full_spread_bps / 2
            + self.slippage_bps
            + self.impact_bps_at_full_participation * share.sqrt()
        )
        direction = D("1") if qty > ZERO else D("-1")
        px = (quote.mark * (D("1") + direction * bps / D("10000"))).quantize(D("0.00000001"))
        if px <= ZERO:
            raise ValueError("NEGATIVE_EXECUTION_PRICE")
        fee = (abs(qty * px) * self.fee_bps / D("10000")).quantize(D("0.00000001"))
        return (
            px,
            fee,
            {
                "execution_price": str(px),
                "fee": str(fee),
                "spread_slippage_impact_bps": str(bps),
                "mid_price": str(quote.mark),
                "quality": quote.quality,
                "not_real_bid_ask": quote.quality == "OHLCV_1M_PROXY",
            },
        )


def _allocate(qty: D, leftovers: dict[str, D]) -> dict[str, D]:
    """Deterministic, sign-consistent pro rata bounded by each pod's request.

    A complete fill must preserve original high-precision target quantities
    exactly; rounding them to 12 decimals can overshoot a pod and falsely
    reject a valid total execution. For partial fills, quantize preliminary
    shares, cap to each request, then allocate any final rounding residual
    to pods with remaining room in deterministic key order.
    """
    if not leftovers or not qty:
        return {}
    pending = {pm: x for pm, x in sorted(leftovers.items()) if x}
    if not pending:
        return {}
    if any(x * qty < ZERO for x in pending.values()):
        raise ValueError("INCOMPATIBLE_ALLOCATION_SIDE")
    total = sum((abs(x) for x in pending.values()), ZERO)
    if abs(qty) > total:
        raise ValueError("OVERSIZED_PARTIAL_ALLOCATION")
    if abs(qty) == total:
        return dict(pending)
    sign = D("1") if qty > ZERO else D("-1")
    keys = sorted(pending)
    result: dict[str, D] = {}
    consumed = ZERO
    for pm in keys[:-1]:
        raw = (qty * abs(pending[pm]) / total).quantize(D("0.000000000001"))
        part = min(abs(raw), abs(pending[pm]), abs(qty - consumed)) * sign
        result[pm] = part
        consumed += part
    tail = keys[-1]
    result[tail] = qty - consumed
    excess = max(ZERO, abs(result[tail]) - abs(pending[tail]))
    if excess:
        for pm in keys[:-1]:
            room = abs(pending[pm]) - abs(result[pm])
            moved = min(room, excess)
            result[pm] += sign * moved
            result[tail] -= sign * moved
            excess -= moved
            if not excess:
                break
    if excess or any(abs(x) > abs(pending[pm]) for pm, x in result.items()):
        raise ValueError("OVERSIZED_PARTIAL_ALLOCATION")
    if sum(result.values(), ZERO) != qty:
        raise ValueError("PARTIAL_ALLOCATION_RECONCILIATION")
    return result


def execute_targets(
    account: Account,
    desired: dict[str, dict[Instrument, D]],
    observations: dict[Instrument, MarketObservation],
    costs: CostModel,
    *,
    decision_at: str,
    hypothetical_fill_at: str,
    permitted: bool,
) -> dict:
    """Mutates a SHADOW account; caller must log its event before committing state.

    No assumed fill when capacity is unknown, when quote clocks are invalid,
    or when a mark is stale. The return is an auditable hypothetical fill plan.
    """
    if clock(hypothetical_fill_at) < clock(decision_at):
        raise ValueError("HYPOTHETICAL_FILL_BEFORE_DECISION")
    if (clock(hypothetical_fill_at) - clock(decision_at)).total_seconds() < costs.latency_seconds:
        raise ValueError("HYPOTHETICAL_LATENCY_UNSATISFIED")
    if not permitted or account.breached:
        return {
            "status": "BLOCKED",
            "fills": [],
            "internal_crosses": [],
            "rejections": ["UNAUTHORIZED_OR_BREACHED"],
            "remaining": {},
        }
    desired_keys = {k for book in desired.values() for k in book}
    active_keys = {k for k, q in account.quantities.items() if q}
    active_keys |= {k for b in account.pm_quantities.values() for k, q in b.items() if q}
    keys = sorted(desired_keys | active_keys)
    rejections: list[str] = []
    for key in keys:
        quote = observations.get(key)
        if key not in account.rulebook.permitted:
            rejections.append(f"UNVERIFIED_CONTRACT_MARKET:{key.key}")
        if quote is None:
            rejections.append(f"MISSING_QUOTE:{key.key}")
            continue
        quote.validate(decision_at)
        if not quote.supported:
            rejections.append(f"UNSUPPORTED_MARKET:{key.key}")
        if (
            clock(decision_at) - clock(quote.first_known_at)
        ).total_seconds() > costs.max_age_seconds:
            rejections.append(f"STALE_QUOTE:{key.key}")
        if quote.capacity_for(D("1")) is None or quote.capacity_for(D("-1")) is None:
            rejections.append(f"UNKNOWN_CAPACITY:{key.key}")
    if rejections:
        account.risk = RiskState.RED
        account.risk_reasons = tuple(sorted(rejections))
        return {
            "status": "BLOCKED",
            "fills": [],
            "internal_crosses": [],
            "rejections": sorted(rejections),
            "remaining": {
                key.key: str(
                    account.external_targets(desired).get(key, ZERO)
                    - account.quantities.get(key, ZERO)
                )
                for key in keys
            },
        }
    account.mark({k: quote.mark for k, quote in observations.items()}, decision_at)
    if account.breached:
        return {
            "status": "BLOCKED",
            "fills": [],
            "internal_crosses": [],
            "rejections": ["FLOOR_BREACH"],
            "remaining": {},
        }
    report: dict = {
        "status": "EXECUTED",
        "fills": [],
        "internal_crosses": [],
        "rejections": [],
        "remaining": {},
    }
    for key in keys:
        quote = observations[key]
        # Managers not listed in desired are explicitly targeted to zero, never
        # interpreted as unknown manager state by the core engine.
        pms = sorted(set(desired) | set(account.pm_quantities))
        deltas = {
            pm: number(desired.get(pm, {}).get(key, ZERO))
            - account.pm_quantities.get(pm, {}).get(key, ZERO)
            for pm in pms
        }
        buys = {pm: qty for pm, qty in deltas.items() if qty > ZERO}
        sells = {pm: -qty for pm, qty in deltas.items() if qty < ZERO}
        for buyer in sorted(buys):
            for seller in sorted(sells):
                crossed = min(buys[buyer], sells[seller])
                if crossed <= ZERO:
                    continue
                account.internal_cross(key, buyer, seller, crossed, quote.mark)
                buys[buyer] -= crossed
                sells[seller] -= crossed
                report["internal_crosses"].append(
                    {
                        "instrument": key.key,
                        "buy_pm": buyer,
                        "sell_pm": seller,
                        "quantity": str(crossed),
                        "price": str(quote.mark),
                        "not_external_execution": True,
                    }
                )
        pending = {pm: q for pm, q in buys.items() if q > ZERO}
        if not pending:
            pending = {pm: -q for pm, q in sells.items() if q > ZERO}
        net = sum(pending.values(), ZERO)
        # Risk-stop permits only net reduction; never represent rejected close as flat.
        prior = account.quantities.get(key, ZERO)
        if account.stage_passed and abs(prior + net) > abs(prior):
            report["rejections"].append(f"STAGE_PASSED_NO_INCREASE:{key.key}")
            report["remaining"][key.key] = str(net)
            continue
        if account.risk in (RiskState.RED, RiskState.HALT) and abs(prior + net) > abs(prior):
            report["rejections"].append(f"RISK_REDUCTION_ONLY:{key.key}")
            report["remaining"][key.key] = str(net)
            continue
        capacity = (quote.capacity_for(net) or ZERO) * costs.max_participation
        if capacity <= ZERO and net:
            report["rejections"].append(f"NO_EXECUTION_CAPACITY:{key.key}")
            report["remaining"][key.key] = str(net)
            continue
        bounded = min(abs(net), capacity)
        if quote.capacity_basis == "DISPLAYED_L2_TOP_LEVEL":
            # Never manufacture a fill that the native size increment rejects.
            step = number(quote.quantity_step)
            bounded = (bounded // step) * step
            px_basis = number(quote.best_ask if net > ZERO else quote.best_bid)
            if bounded and bounded * px_basis < number(quote.minimum_notional):
                bounded = ZERO
        filled = bounded * (D("1") if net >= ZERO else D("-1"))
        if filled:
            allocation = _allocate(filled, pending)
            px, fee, attribution = costs.price_and_fee(filled, quote)
            account.simulate_fill(key, filled, px, fee, accepted=True, allocated=allocation)
            report["fills"].append(
                {
                    "instrument": key.key,
                    "quantity": str(filled),
                    "allocation": {pm: str(q) for pm, q in allocation.items()},
                    "hypothetical_fill_at": hypothetical_fill_at,
                    **attribution,
                }
            )
            if account.breached:
                report["status"] = "HALT_DURING_HYPOTHETICAL_EXECUTION"
                report["rejections"].append("CONTRACTUAL_BREACH_MID_BATCH")
                report["remaining"][key.key] = str(net - filled)
                report["unprocessed_instruments"] = [k.key for k in keys if k > key]
                break
        remaining = net - filled
        if remaining:
            report["status"] = "PARTIAL"
            report["remaining"][key.key] = str(remaining)
    if report["rejections"] and report["status"] == "EXECUTED":
        report["status"] = "PARTIAL" if report["fills"] else "REJECTED"
    account.verify()
    return report
