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
        if quote.volume_base is None or quote.volume_base <= ZERO:
            raise ValueError("MISSING_LIQUIDITY")
        share = abs(qty) / quote.volume_base
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
    """Deterministic sign-consistent pro rata, with exact final remainder."""
    if not leftovers or not qty:
        return {}
    total = sum((abs(x) for x in leftovers.values()), ZERO)
    if qty * next(iter(leftovers.values())) < ZERO:
        raise ValueError("INCOMPATIBLE_ALLOCATION_SIDE")
    consumed = ZERO
    result: dict[str, D] = {}
    keys = sorted(leftovers)
    for pm in keys[:-1]:
        part = (qty * abs(leftovers[pm]) / total).quantize(D("0.000000000001"))
        result[pm] = part
        consumed += part
    result[keys[-1]] = qty - consumed
    if any(abs(x) > abs(leftovers[pm]) for pm, x in result.items()):
        raise ValueError("OVERSIZED_PARTIAL_ALLOCATION")
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
        if quote.volume_base is None:
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
        capacity = quote.volume_base * costs.max_participation
        if capacity <= ZERO and net:
            report["rejections"].append(f"NO_EXECUTION_CAPACITY:{key.key}")
            report["remaining"][key.key] = str(net)
            continue
        filled = min(abs(net), capacity) * (D("1") if net >= ZERO else D("-1"))
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
