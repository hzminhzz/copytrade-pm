"""Predeclared, deterministic PM-03 account risk governance.

Research thresholds are NOT Propr rules or institutional proprietary limits.
Every proposal is advisory; the supervisor owns shadow-account approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D

from .pm03_account import Account, Instrument, RiskState, ZERO, number


@dataclass(frozen=True)
class RiskPolicy:
    # Ratio of contractual headroom to modeled worst stress + reserve.
    yellow_ratio: D = D("3")
    orange_ratio: D = D("2")
    red_ratio: D = D("1.25")
    reserve_fraction_initial: D = D("0.005")
    max_gross_leverage: D = D("2")
    max_instrument_fraction_equity: D = D("0.5")
    yellow_scale: D = D("0.75")
    orange_scale: D = D("0.5")

    def __post_init__(self) -> None:
        if not self.yellow_ratio > self.orange_ratio > self.red_ratio > D("1"):
            raise ValueError("INVALID_RISK_TIERS")
        if not ZERO < self.orange_scale < self.yellow_scale < D("1"):
            raise ValueError("INVALID_RISK_SCALING")
        if self.reserve_fraction_initial < ZERO or self.max_gross_leverage <= ZERO:
            raise ValueError("INVALID_RISK_LIMITS")
        if not ZERO < self.max_instrument_fraction_equity <= D("1"):
            raise ValueError("INVALID_CONCENTRATION_LIMIT")


@dataclass(frozen=True)
class RiskEvidence:
    trusted: bool
    account_state_known: bool
    market_state_known: bool
    market_coverage_valid: bool
    pending_unknown_orders: bool
    input_status: str  # RESEARCH_SYNTHETIC or PROSPECTIVE_OBSERVED
    pm02_qualified: bool
    # Extra losses from broken hedges or unmodeled liquidity; explicit assumptions.
    stressed_liquidity_loss: D = ZERO
    hedge_break_loss: D = ZERO


def loss_under_shock(
    positions: dict[Instrument, D],
    marks: dict[Instrument, D],
    shocks: dict[Instrument, D],
) -> D:
    if set(positions) - set(marks) or set(positions) - set(shocks):
        raise ValueError("INCOMPLETE_STRESS_SHOCK")
    change = sum((q * marks[k] * shocks[k] for k, q in positions.items()), ZERO)
    return max(ZERO, -change)


def classify(
    account: Account,
    proposed: dict[str, dict[Instrument, D]],
    quotes: dict[Instrument, D],
    scenario_shocks: tuple[dict[Instrument, D], ...],
    evidence: RiskEvidence,
    policy: RiskPolicy,
) -> dict:
    target = account.external_targets(proposed)
    reasons: list[str] = []
    if account.breached or account.risk == RiskState.HALT:
        reasons.append("PERSISTENT_HALT")
    if account.stage_passed:
        reasons.append("STAGE_ALREADY_PASSED")
    if not evidence.trusted or not account.rulebook.confirmed:
        reasons.append("UNVERIFIED_INPUT_OR_RULEBOOK")
    if not evidence.account_state_known or not evidence.market_state_known:
        reasons.append("UNKNOWN_ACCOUNT_OR_MARKET")
    if not evidence.market_coverage_valid or evidence.pending_unknown_orders:
        reasons.append("MISSING_COVERAGE_OR_PENDING")
    if evidence.input_status not in {
        "RESEARCH_SYNTHETIC",
        "PROSPECTIVE_OBSERVED",
        "FORWARD_PAPER_SIMULATED_v1",
    }:
        reasons.append("HINDSIGHT_OR_UNKNOWN_SIGNAL")
    if evidence.input_status == "PROSPECTIVE_OBSERVED" and not evidence.pm02_qualified:
        reasons.append("PM02_ZERO_QUALIFICATION")
    if target and not account.rulebook.permitted:
        reasons.append("UNKNOWN_MARKET_ALLOWLIST")
    if any(k not in account.rulebook.permitted for k in target):
        reasons.append("UNSUPPORTED_INSTRUMENT")
    if any(k not in quotes or number(quotes[k]) <= ZERO for k in target):
        reasons.append("UNKNOWN_PRICE")
    for instrument in target:
        legs = [book.get(instrument, ZERO) for book in proposed.values()]
        if any(q > ZERO for q in legs) and any(q < ZERO for q in legs):
            if evidence.hedge_break_loss <= ZERO:
                reasons.append("MISSING_HEDGE_BREAK_STRESS")
                break
    floor, floors = account.floor()
    if floor is None:
        reasons.append("UNKNOWN_CONTRACT_FLOOR")
    if evidence.stressed_liquidity_loss < ZERO or evidence.hedge_break_loss < ZERO:
        raise ValueError("NEGATIVE_STRESS_ASSUMPTION")
    worst = evidence.stressed_liquidity_loss + evidence.hedge_break_loss
    if target and not scenario_shocks:
        reasons.append("MISSING_STRESS_MODEL")
    if not reasons:
        for scenario in scenario_shocks:
            worst = max(
                worst,
                loss_under_shock(target, quotes, scenario)
                + evidence.stressed_liquidity_loss
                + evidence.hedge_break_loss,
            )
    reserve = policy.reserve_fraction_initial * account.rulebook.initial_balance
    headroom = account.equity - floor if floor is not None else ZERO
    shock_requirement = worst + reserve
    tier = RiskState.GREEN
    if account.breached or headroom <= ZERO:
        tier = RiskState.HALT
        reasons.append("CONTRACTUAL_FLOOR")
    elif shock_requirement > ZERO:
        ratio = headroom / shock_requirement
        if ratio <= D("1"):
            tier = RiskState.HALT
            reasons.append("MODELED_STRESS_EXCEEDS_HEADROOM")
        elif ratio <= policy.red_ratio:
            tier = RiskState.RED
        elif ratio <= policy.orange_ratio:
            tier = RiskState.ORANGE
        elif ratio <= policy.yellow_ratio:
            tier = RiskState.YELLOW
    if reasons and tier != RiskState.HALT:
        tier = RiskState.RED
    # No automatic risk-state de-escalation: a manual, logged reset is required.
    order = list(RiskState)
    tier = max(account.risk, tier, key=order.index)
    if tier == RiskState.HALT:
        account.latch_halt(";".join(sorted(set(reasons))) or "RISK_POLICY_HALT")
    else:
        account.risk = tier
    account.risk_reasons = tuple(sorted(set(reasons)))
    scale = {
        RiskState.GREEN: D("1"),
        RiskState.YELLOW: policy.yellow_scale,
        RiskState.ORANGE: policy.orange_scale,
    }.get(tier, ZERO)
    if tier in (RiskState.RED, RiskState.HALT):
        # Permit only requested per-PM reductions, and only if whole-account
        # absolute net position does NOT grow as apparent hedges disappear.
        candidate = {}
        for pm in set(proposed) | set(account.pm_quantities):
            book = {}
            for k in set(proposed.get(pm, {})) | set(account.pm_quantities.get(pm, {})):
                prior = account.pm_quantities.get(pm, {}).get(k, ZERO)
                suggested = proposed.get(pm, {}).get(k, ZERO)
                value = (
                    suggested
                    if prior * suggested >= ZERO and (abs(suggested) <= abs(prior))
                    else prior
                )
                if value:
                    book[k] = value
            if book:
                candidate[pm] = book
        net_new = account.external_targets(candidate)
        if any(abs(net_new.get(k, ZERO)) > abs(old) for k, old in account.quantities.items()):
            candidate = {pm: dict(book) for pm, book in account.pm_quantities.items()}
        allowed = False
    else:
        candidate = {
            pm: {k: number(q) * scale for k, q in book.items()} for pm, book in proposed.items()
        }
        allowed = True
    signed = account.external_targets(candidate)
    if signed and all(k in quotes for k in signed):
        gross = sum((abs(q * quotes[k]) for k, q in signed.items()), ZERO)
        contract_leverage = account.rulebook.max_gross_leverage
        leverage = (
            min(policy.max_gross_leverage, contract_leverage)
            if (contract_leverage is not None)
            else policy.max_gross_leverage
        )
        concentration = max((abs(q * quotes[k]) for k, q in signed.items()), default=ZERO)
        if gross > account.equity * leverage or (
            concentration > account.equity * policy.max_instrument_fraction_equity
        ):
            reasons.append("LEVERAGE_OR_CONCENTRATION")
            candidate = {pm: dict(book) for pm, book in account.pm_quantities.items()}
            allowed = False
            if account.risk != RiskState.HALT:
                account.risk = RiskState.RED
    return {
        "state": account.risk.value,
        "approved_new_risk": allowed and not reasons,
        "reason_codes": sorted(set(reasons)),
        "approved": candidate,
        "proposed": proposed,
        "worst_stress_loss": str(worst),
        "headroom": str(headroom),
        "reserve": str(reserve),
        "floors": {k: str(v) for k, v in floors.items()},
        "not_a_guaranteed_stop": True,
        "research_policy_only": True,
    }
