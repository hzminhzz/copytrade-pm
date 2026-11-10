"""Read-only PM03/PM04 candidate-k financial accounting preflight.

Imports the original account snapshot and existing PM03 risk/PM04 budget rules.
It NEVER mutates a paper journal, original account, registry, or release.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .pm03_account import Account, Instrument, RiskState, Rulebook, clock, digest, number
from .pm03_risk import RiskEvidence, RiskPolicy, classify
from .pm04_shadow import _fund_independent_pod_budgets, validate_policy
from .pm_exposure_sizing import target_from_fixed_k

if TYPE_CHECKING:
    from .pm_k_recalibration import KResearchInput

SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
STEP = Annotated[Decimal, Field(gt=0)]
MINIMUM = Annotated[Decimal, Field(ge=0)]


class PM03FinanceFrame(BaseModel):
    """An imported, SHA-checked snapshot; SHA binding is not external attestation."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    rulebook: dict
    account_snapshot: dict
    account_snapshot_sha256: SHA
    pm04_policy: dict
    pm04_policy_sha256: SHA
    account_known_at: str
    source_known_at: str
    quote_known_at: str
    lot_steps: dict[str, STEP]
    minimum_notionals: dict[str, MINIMUM]
    funding_complete: bool
    capacity_complete: bool
    pending_unknown_orders: bool
    unresolved_exposures: bool
    correlation_stress_usd: MINIMUM
    liquidity_stress_usd: MINIMUM

    @model_validator(mode="after")
    def inspect(self):
        validate_policy(self.pm04_policy)
        if digest(self.pm04_policy) != self.pm04_policy_sha256:
            raise ValueError("PM04_POLICY_SNAPSHOT_SHA_MISMATCH")
        if digest(self.account_snapshot) != self.account_snapshot_sha256:
            raise ValueError("PM03_ACCOUNT_SNAPSHOT_SHA_MISMATCH")
        for name in ("account_known_at", "source_known_at", "quote_known_at"):
            clock(getattr(self, name))
        return self


def assess_finance(study: KResearchInput, frame: PM03FinanceFrame) -> dict:
    """Clone the original financial state; re-run PM03 plus PM04 constraints.

    Cloning is essential: classify() may latch HALT on the copy.
    """
    reasons: set[str] = set()
    account = Account.from_snapshot(Rulebook.from_dict(frame.rulebook), frame.account_snapshot)
    account.verify()
    policy = frame.pm04_policy
    if digest(policy) != frame.pm04_policy_sha256:
        reasons.add("PM04_POLICY_SNAPSHOT_SHA_MISMATCH")
        return {"ok": False, "blockers": sorted(reasons), "order_route": "NONE"}
    if digest(account.snapshot()) != frame.account_snapshot_sha256:
        reasons.add("FINANCIAL_SNAPSHOT_REPLAY_DIVERGENCE")
    if account.pm04_state and account.pm04_state.get("policy") != policy:
        reasons.add("PM04_JOURNAL_POLICY_DRIFT")
    pods = policy["pods"]
    if study.pod_id not in pods or study.pod_id not in policy.get("fixed_k_by_pod", {}):
        reasons.add("POD_NOT_IN_PM04_POLICY")
        return {"ok": False, "blockers": sorted(reasons), "order_route": "NONE"}
    if number(policy["fixed_k_by_pod"][study.pod_id]) != study.current_frozen_k:
        reasons.add("CURRENT_K_NOT_FROZEN_IN_PM04")
    if not account.rulebook.confirmed or not account.rulebook.account_terms_confirmed:
        reasons.add("UNVERIFIED_FINANCIAL_RULEBOOK")
    if account.risk != RiskState.GREEN or account.breached or account.stage_passed:
        reasons.add("PM03_RISK_NOT_GREEN")
    for name in ("account_known_at", "source_known_at", "quote_known_at"):
        age = (clock(study.as_of) - clock(getattr(frame, name))).total_seconds()
        if not 0 <= age <= 180:
            reasons.add("ACCOUNT_SOURCE_OR_QUOTE_STALE")
    if frame.pending_unknown_orders or frame.unresolved_exposures:
        reasons.add("UNRESOLVED_FINANCIAL_EFFECTS")
    if any(book for book in account.pm_quantities.values()):
        # A change in frozen k must never resize existing modeled inventory.
        # A future release needs explicit grandfathered position identities.
        reasons.add("OPEN_INVENTORY_RELEASE_NOT_SAFE")
    paper = account.pm04_state.get("paper_execution", {})
    if paper.get("unresolved_exposures") or any(
        entry.get("status") == "PENDING_5M" for entry in paper.get("history", {}).values()
    ):
        reasons.add("PENDING_T300_OR_UNRESOLVED")
    if not frame.funding_complete:
        reasons.add("FUNDING_UNVERIFIED")
    if not frame.capacity_complete:
        reasons.add("CAPACITY_UNVERIFIED")
    try:
        _fund_independent_pod_budgets(account, policy)
    except ValueError as exc:
        reasons.add("POD_BUDGET_" + str(exc))
    source_keys = set(study.source_quantities)
    if source_keys != set(frame.lot_steps) or source_keys != set(frame.minimum_notionals):
        reasons.add("MARKET_LOT_SCOPE_MISMATCH")
    if set(study.source_quantities) != set(study.source_marks) or (
        source_keys != set(study.follower_marks)
    ):
        reasons.add("INCOMPLETE_SOURCE_OR_FOLLOWER_MARKS")
    if reasons & {"MARKET_LOT_SCOPE_MISMATCH", "INCOMPLETE_SOURCE_OR_FOLLOWER_MARKS"}:
        return {"ok": False, "blockers": sorted(reasons), "order_route": "NONE"}
    try:
        intent = target_from_fixed_k(
            source_quantities=study.source_quantities,
            k=study.candidate_k,
            source_marks=study.source_marks,
            follower_marks=study.follower_marks,
            follower_equity_usd=account.equity,
            max_gross_notional_usd=number(policy["max_gross_notional"]),
            max_market_notional_usd=account.equity
            * number(policy["max_instrument_fraction_equity"]),
            pod_loss_budget_usd=number(pods[study.pod_id]["max_drawdown"]),
        )
    except ValueError as exc:
        reasons.add("FIXED_K_INTENT_" + str(exc))
        return {"ok": False, "blockers": sorted(reasons), "order_route": "NONE"}
    targets: dict[Instrument, Decimal] = {}
    for key, raw in intent["target_quantities"].items():
        qty = number(raw)
        step = frame.lot_steps[key]
        rounded = (abs(qty) / step).to_integral_value(rounding=ROUND_DOWN) * step
        rounded = rounded if qty >= 0 else -rounded
        if not rounded or abs(rounded * study.follower_marks[key]) < frame.minimum_notionals[key]:
            reasons.add("NATIVE_LOT_OR_MINIMUM_NOTIONAL")
        if rounded:
            targets[Instrument.parse(key)] = rounded
    proposed = {pod: dict(book) for pod, book in account.pm_quantities.items()}
    proposed[study.pod_id] = targets
    quotes = {Instrument.parse(key): value for key, value in study.follower_marks.items()}
    for instrument in account.quantities:
        if instrument not in quotes:
            if instrument not in account.marks:
                reasons.add("HELD_POSITION_MARK_MISSING")
            else:
                quotes[instrument] = account.marks[instrument]
    shocks = tuple(
        {Instrument.parse(key): value for key, value in scenario.items()}
        for scenario in study.stress_shocks
    )
    net = account.external_targets(proposed)
    if not shocks or any(set(net) - set(scenario) for scenario in shocks):
        reasons.add("PM03_CORRELATED_PORTFOLIO_SHOCK_MISSING")
    if set(net) - set(quotes):
        reasons.add("PORTFOLIO_FOLLOWER_QUOTE_MISSING")
    risk = None
    if (
        not {"PM03_CORRELATED_PORTFOLIO_SHOCK_MISSING", "PORTFOLIO_FOLLOWER_QUOTE_MISSING"}
        & reasons
    ):
        # PM03 operates on the independent clone; paper live state is never touched.
        risk = classify(
            account,
            proposed,
            quotes,
            shocks,
            RiskEvidence(
                trusted=True,
                account_state_known=True,
                market_state_known=True,
                market_coverage_valid=True,
                pending_unknown_orders=frame.pending_unknown_orders,
                input_status="RESEARCH_SYNTHETIC",
                pm02_qualified=False,
                stressed_liquidity_loss=frame.liquidity_stress_usd
                + study.adverse_price_extra_loss_usd
                + study.latency_extra_loss_usd,
                hedge_break_loss=frame.correlation_stress_usd,
            ),
            RiskPolicy(
                max_gross_leverage=min(
                    Decimal("2"), number(policy["max_gross_notional"]) / account.equity
                ),
                max_instrument_fraction_equity=number(policy["max_instrument_fraction_equity"]),
            ),
        )
        if not risk["approved_new_risk"]:
            reasons.update(risk["reason_codes"] or ["PM03_NEW_RISK_DENIED"])
        if number(risk["worst_stress_loss"]) > number(pods[study.pod_id]["stress_loss"]):
            reasons.add("PM04_POD_STRESS_EXCEEDED")
        if number(risk["worst_stress_loss"]) > number(policy["max_stress_loss"]):
            reasons.add("PM04_TOTAL_STRESS_EXCEEDED")
    return {
        "ok": not reasons,
        "blockers": sorted(reasons),
        "risk_state": risk["state"] if risk else "UNVERIFIED",
        "worst_stress_loss_usd": risk["worst_stress_loss"] if risk else None,
        "follower_equity_usd": str(account.equity),
        "account_snapshot_sha256": frame.account_snapshot_sha256,
        "pm04_policy_sha256": frame.pm04_policy_sha256,
        "financial_account_modified": False,
        "approved_for_trading": False,
        "order_route": "NONE",
    }
