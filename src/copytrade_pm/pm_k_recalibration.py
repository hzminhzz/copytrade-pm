"""Track C offline k research and nonactivating SHADOW release verification.

Consumes independently produced PM03/04 financial measurements. This is NOT a
financial simulator, risk permit, paper-journal writer or active policy loader.
"""

from __future__ import annotations

from decimal import Decimal
from math import sqrt
from statistics import NormalDist
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .pm03_account import Instrument, clock, digest, number
from .pm03_risk import loss_under_shock
from .pm_exposure_sizing import target_from_fixed_k
from .pm_k_finance import PM03FinanceFrame, assess_finance

SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Positive = Annotated[Decimal, Field(gt=0)]
Nonnegative = Annotated[Decimal, Field(ge=0)]


class Frozen(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", serialize_by_alias=True, allow_inf_nan=False
    )


class Trial(Frozen):
    """Each evaluated or rejected variant stays in the denominator."""

    trial_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    selection_as_of: str
    status: Literal["ACCEPTED", "REJECTED", "BLOCKED"]
    evidence_sha256: SHA
    variant_k: Positive

    @model_validator(mode="after")
    def clocks(self):
        clock(self.selection_as_of)
        return self


class FinanceWindow(Frozen):
    """Attested imported financial outcomes, never inferred from leader PnL."""

    label: Literal["TRAIN", "OOS", "FORWARD"]
    class_of_evidence: Literal["PM03_HISTORICAL_PROXY", "PM03_PROSPECTIVE_SHADOW"]
    report_sha256: SHA
    known_at: str
    period_end: str
    period_start: str | None = None
    independent_episodes: int = Field(ge=0)
    follower_realized_net_usd: Decimal
    follower_mtm_net_usd: Decimal
    fees_usd: Nonnegative
    slippage_usd: Nonnegative
    funding_usd: Decimal | None
    financing_complete: bool
    capacity_verified: bool
    quote_coverage_complete: bool
    selection_frozen_before_window: bool
    cash_control_net_usd: Decimal
    matched_control_net_usd: Decimal | None
    market_control_net_usd: Decimal | None
    max_drawdown_usd: Nonnegative
    concentration_fraction: Annotated[Decimal, Field(ge=0, le=1)]
    max_pair_correlation: Annotated[Decimal, Field(ge=-1, le=1)]
    uncertainty_lower_incremental_net_usd: Decimal | None

    @model_validator(mode="after")
    def clocks(self):
        if clock(self.known_at) < clock(self.period_end):
            raise ValueError("FINANCE_WINDOW_NOT_KNOWN")
        if self.period_start is not None and clock(self.period_start) >= clock(self.period_end):
            raise ValueError("FINANCE_WINDOW_PERIOD_INVALID")
        return self


class PairedControlBlock(Frozen):
    """One predeclared, separately accounted follower/net comparison block."""

    trial_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    scenario: Literal["BASE", "DELAYED", "ADVERSE", "V4_PAPER"]
    split: Literal["OOS", "FORWARD"]
    started_at: str
    ended_at: str
    known_at: str
    follower_report_sha256: SHA
    candidate_follower_net_usd: Decimal
    current_k_follower_net_usd: Decimal
    cash_net_usd: Decimal
    matched_wallet_net_usd: Decimal | None
    market_net_usd: Decimal | None
    fees_usd: Nonnegative
    slippage_usd: Nonnegative
    funding_usd: Decimal | None
    capacity_verified: bool

    @model_validator(mode="after")
    def causal(self):
        if not clock(self.started_at) < clock(self.ended_at) <= clock(self.known_at):
            raise ValueError("PAIRED_BLOCK_NONCAUSAL")
        return self


class KResearchInput(Frozen):
    contract_schema: Literal["track_c_k_research_input_v1"] = Field(
        default="track_c_k_research_input_v1", alias="schema"
    )
    portfolio_version: str = Field(min_length=1)
    portfolio_definition_sha256: SHA
    pod_id: str = Field(min_length=1)
    selected_account_sha256: SHA
    sizing_policy_version: str = Field(min_length=1)
    sizing_policy: Literal["FIXED_K_NATIVE_QUANTITY"] = "FIXED_K_NATIVE_QUANTITY"
    as_of: str
    current_frozen_k: Positive
    candidate_k: Positive
    cost_policy_version: str = Field(min_length=1)
    risk_policy_version: str = Field(min_length=1)
    algorithm_version: Literal["track_c_k_v1"] = "track_c_k_v1"
    source_sha256: SHA
    screen_report_sha256: SHA | None = None
    screen_cost_policy_version: str | None = None
    trial_roster_sha256: SHA
    trials: tuple[Trial, ...]
    windows: tuple[FinanceWindow, ...]
    paired_control_blocks: tuple[PairedControlBlock, ...] = ()
    pod_loss_budget_usd: Positive
    follower_equity_usd: Positive
    max_gross_notional_usd: Positive
    max_market_notional_usd: Positive
    daily_headroom_usd: Positive
    trailing_headroom_usd: Positive
    source_quantities: dict[str, Decimal]
    source_marks: dict[str, Positive]
    follower_marks: dict[str, Positive]
    stress_shocks: tuple[dict[str, Decimal], ...]
    adverse_price_extra_loss_usd: Nonnegative
    latency_extra_loss_usd: Nonnegative
    lot_notional_valid: bool
    unresolved_financial_effects: bool
    portfolio_correlation_checked: bool
    evidence_expired: bool
    finance_frame: PM03FinanceFrame | None = None
    coverage_missing: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_scope(self):
        if any(clock(t.selection_as_of) > clock(self.as_of) for t in self.trials):
            raise ValueError("TRIAL_FROM_FUTURE")
        if any(clock(f.known_at) > clock(self.as_of) for f in self.windows):
            raise ValueError("FINANCE_REPORT_FROM_FUTURE")
        if any(clock(b.known_at) > clock(self.as_of) for b in self.paired_control_blocks):
            raise ValueError("PAIRED_BLOCK_FROM_FUTURE")
        if len(self.trials) > 1000 or len(self.paired_control_blocks) > 10000:
            raise ValueError("UNBOUNDED_RESEARCH_TRIAL_INPUT")
        if not self.trials or len({t.trial_id for t in self.trials}) != len(self.trials):
            raise ValueError("TRIAL_REGISTRY_INCOMPLETE")
        if any(
            w.period_start is not None and clock(t.selection_as_of) >= clock(w.period_start)
            for t in self.trials
            for w in self.windows
            if w.label in ("OOS", "FORWARD")
        ):
            raise ValueError("TRIAL_SELECTION_NOT_FROZEN_BEFORE_OOS")
        roster = {t.trial_id: t for t in self.trials}
        if any(b.trial_id not in roster for b in self.paired_control_blocks):
            raise ValueError("PAIRED_BLOCK_UNKNOWN_TRIAL")
        if any(
            roster[b.trial_id].variant_k != self.candidate_k
            or roster[b.trial_id].status != "ACCEPTED"
            or clock(roster[b.trial_id].selection_as_of) >= clock(b.started_at)
            for b in self.paired_control_blocks
        ):
            raise ValueError("PAIRED_BLOCK_FUTURE_OR_UNSELECTED_TRIAL")
        if (self.screen_report_sha256 is None) != (self.screen_cost_policy_version is None):
            raise ValueError("HISTORICAL_SCREEN_LINEAGE_INCOMPLETE")
        if self.screen_cost_policy_version == self.cost_policy_version:
            raise ValueError("SCREEN_AND_PAPER_COST_POLICIES_MUST_DIFFER")
        if self.candidate_k > Decimal("10") or self.current_frozen_k > Decimal("10"):
            raise ValueError("INVALID_K_LIMIT")
        clock(self.as_of)
        return self


class KProposal(Frozen):
    contract_schema: Literal["track_c_k_proposal_v1"] = Field(
        default="track_c_k_proposal_v1", alias="schema"
    )
    identity_sha256: SHA
    portfolio_version: str
    portfolio_definition_sha256: SHA
    pod_id: str
    sizing_policy_version: str
    as_of: str
    current_frozen_k: Decimal
    candidate_k: Decimal
    decision: Literal["HOLD", "DECREASE", "INCREASE", "INSUFFICIENT_EVIDENCE"]
    source_sha256: SHA
    screen_report_sha256: SHA | None
    screen_cost_policy_version: str | None
    trial_roster_sha256: SHA
    cost_policy_version: str
    risk_policy_version: str
    evidence_report_shas: tuple[SHA, ...]
    tested_trials: int
    rejected_trials: int
    effective_independent_episodes: int
    follower_net_oos_usd: Decimal | None
    finance_check: dict | None
    paired_economics: dict
    evidence_class: Literal["HISTORICAL_ONLY", "AUTHENTIC_PROSPECTIVE_PRESENT"]
    reasons: tuple[str, ...]
    confidence: Literal["LOW", "CONDITIONAL"]
    research_only: Literal[True] = True
    original_prospective_proof_verified: Literal[False] = False
    authorized_for_trading: Literal[False] = False
    release_activated: Literal[False] = False
    order_route: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def identity(self):
        body = self.model_dump(mode="json", by_alias=True, exclude={"identity_sha256"})
        if digest(body) != self.identity_sha256:
            raise ValueError("K_PROPOSAL_SHA_MISMATCH")
        if self.decision == "INCREASE" and (
            not self.original_prospective_proof_verified
            or self.candidate_k <= self.current_frozen_k
            or self.confidence != "CONDITIONAL"
            or self.evidence_class != "AUTHENTIC_PROSPECTIVE_PRESENT"
        ):
            raise ValueError("UNSUPPORTED_K_INCREASE")
        return self


def _paired_economic_check(study: KResearchInput) -> dict:
    """Multiplicity-aware diagnostic on supplied *paired* PM03 net blocks.

    It cannot independently certify their source, independence, or forward status.
    Bonferroni-normal confidence is illustrative pending approved block policy.
    """
    reasons: set[str] = set()
    blocks = study.paired_control_blocks
    if not blocks:
        return {
            "independent_blocks": 0,
            "calendar_days": 0,
            "trials_in_denominator": len(study.trials),
            "lower_incremental_usd": None,
            "reasons": ["PAIRED_CONTROL_BLOCKS_NOT_SUPPLIED"],
            "original_reports_verified": False,
        }
    grouped: dict[str, list[PairedControlBlock]] = {}
    for block in blocks:
        grouped.setdefault(block.scenario, []).append(block)
        if (
            block.funding_usd is None
            or not block.capacity_verified
            or block.matched_wallet_net_usd is None
            or block.market_net_usd is None
        ):
            reasons.add("PAIRED_FINANCING_CAPACITY_OR_CONTROL_MISSING")
    base = grouped.get("BASE", [])
    unique = {b.block_id: b for b in base}
    if len(unique) != len(base):
        reasons.add("DUPLICATE_PAIRED_BASE_BLOCK")
    dates = {clock(b.ended_at).date() for b in unique.values()}
    if len(unique) < 7 or len(dates) < 7:
        reasons.add("INSUFFICIENT_INDEPENDENT_PAIRED_DAYS")
    base_ids = set(unique)
    for scenario in ("DELAYED", "ADVERSE"):
        relevant = grouped.get(scenario, [])
        if base_ids != {b.block_id for b in relevant} or len(relevant) != len(base_ids):
            reasons.add("PAIRED_SCENARIO_ALIGNMENT_MISSING:" + scenario)
        elif (
            sum(
                (b.candidate_follower_net_usd - b.current_k_follower_net_usd for b in relevant),
                Decimal("0"),
            )
            <= 0
        ):
            reasons.add("PAIRED_TIMING_OR_COST_STRESS_NOT_SURVIVED:" + scenario)
    if not any(b.split == "FORWARD" for b in base):
        reasons.add("PAIRED_FORWARD_WINDOW_MISSING")
    deltas = [
        b.candidate_follower_net_usd
        - max(
            b.current_k_follower_net_usd,
            b.cash_net_usd,
            b.matched_wallet_net_usd
            if b.matched_wallet_net_usd is not None
            else Decimal("Infinity"),
            b.market_net_usd if b.market_net_usd is not None else Decimal("Infinity"),
        )
        for b in unique.values()
    ]
    lower = None
    if len(deltas) > 1 and all(v.is_finite() for v in deltas):
        avg = sum(deltas, Decimal("0")) / len(deltas)
        variance = sum(((v - avg) ** 2 for v in deltas), Decimal("0")) / (len(deltas) - 1)
        z = Decimal(str(NormalDist().inv_cdf(1 - 0.05 / len(study.trials))))
        lower = avg - z * Decimal(str(sqrt(float(variance) / len(deltas))))
        if lower <= 0:
            reasons.add("PAIRED_MULTIPLICITY_ADJUSTED_BOUND_NONPOSITIVE")
    else:
        reasons.add("PAIRED_UNCERTAINTY_NOT_ESTIMABLE")
    return {
        "independent_blocks": len(unique),
        "calendar_days": len(dates),
        "trials_in_denominator": len(study.trials),
        "lower_incremental_usd": str(lower) if lower is not None else None,
        "reasons": sorted(reasons),
        "original_reports_verified": False,
    }


def evaluate_k(input: KResearchInput) -> KProposal:
    """Conservative read-only proposal; all realized economics are external PM03/04 facts."""
    reasons: set[str] = set(input.coverage_missing)
    finance_check = None
    paired_economics = _paired_economic_check(input)
    if input.candidate_k > input.current_frozen_k:
        reasons.update(paired_economics["reasons"])
    if input.finance_frame is None:
        reasons.add("PM03_ACCOUNT_SNAPSHOT_REQUIRED")
    else:
        finance_check = assess_finance(input, input.finance_frame)
        reasons.update(finance_check["blockers"])
    if input.candidate_k > input.current_frozen_k:
        # A JSON label or Pydantic flag cannot attest original prospective fills.
        # An independent original-PM03/04 proof adapter is not yet implemented.
        reasons.add("INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED")
    if input.evidence_expired:
        reasons.add("EXPIRED_EVIDENCE")
    if input.unresolved_financial_effects:
        reasons.add("UNRESOLVED_EXECUTIONS_OR_INVENTORY")
    if not input.portfolio_correlation_checked:
        reasons.add("CORRELATION_NOT_VALIDATED")
    if not input.lot_notional_valid:
        reasons.add("LOT_OR_MINIMUM_NOTIONAL_INVALID")
    if input.trial_roster_sha256 != digest([t.model_dump(mode="json") for t in input.trials]):
        reasons.add("TRIAL_ROSTER_SHA_MISMATCH")
    if not input.windows:
        reasons.add("NO_PM03_FINANCIAL_REPORT")
    for window in input.windows:
        if not (
            window.financing_complete
            and window.capacity_verified
            and window.quote_coverage_complete
            and window.selection_frozen_before_window
        ):
            reasons.add("FINANCIAL_COVERAGE_INCOMPLETE")
        if window.funding_usd is None:
            reasons.add("FUNDING_UNAVAILABLE")
        if window.matched_control_net_usd is None or window.market_control_net_usd is None:
            reasons.add("MISSING_CONTROLS")
    # The native calculation is an intent only; PM03/04 have sole authority to book.
    try:
        intent = target_from_fixed_k(
            source_quantities=input.source_quantities,
            k=input.candidate_k,
            source_marks=input.source_marks,
            follower_marks=input.follower_marks,
            follower_equity_usd=input.follower_equity_usd,
            max_gross_notional_usd=input.max_gross_notional_usd,
            max_market_notional_usd=input.max_market_notional_usd,
            pod_loss_budget_usd=input.pod_loss_budget_usd,
        )
        positions = {Instrument.parse(k): number(v) for k, v in intent["target_quantities"].items()}
        marks = {Instrument.parse(k): v for k, v in input.follower_marks.items()}
        if not input.stress_shocks:
            reasons.add("MISSING_STRESS_SHOCKS")
        else:
            worst = max(
                loss_under_shock(
                    positions, marks, {Instrument.parse(k): v for k, v in shocks.items()}
                )
                for shocks in input.stress_shocks
            )
            total = worst + input.adverse_price_extra_loss_usd + input.latency_extra_loss_usd
            if total > min(
                input.pod_loss_budget_usd, input.daily_headroom_usd, input.trailing_headroom_usd
            ):
                reasons.add("PM03_STRESS_HEADROOM_EXCEEDED")
    except ValueError as exc:
        reasons.add("FIXED_K_INTENT_" + str(exc))
    oos = [w for w in input.windows if w.label in ("OOS", "FORWARD")]
    prospective = [w for w in oos if w.class_of_evidence == "PM03_PROSPECTIVE_SHADOW"]
    if not oos or sum(w.independent_episodes for w in oos) < 30:
        reasons.add("INSUFFICIENT_INDEPENDENT_OOS_EPISODES")
    if any(w.period_start is None for w in oos):
        reasons.add("INDEPENDENT_OOS_START_CLOCK_MISSING")
    if not prospective:
        reasons.add("NO_AUTHENTIC_PROSPECTIVE_FINANCE")
    if not any(w.label == "TRAIN" for w in input.windows):
        reasons.add("MISSING_TRAIN_WINDOW")
    if any(
        w.uncertainty_lower_incremental_net_usd is None
        or w.uncertainty_lower_incremental_net_usd <= 0
        for w in oos
    ):
        reasons.add("NO_POSITIVE_LOWER_INCREMENTAL_BOUND")
    if any(
        w.follower_mtm_net_usd
        <= max(
            w.cash_control_net_usd,
            w.matched_control_net_usd
            if w.matched_control_net_usd is not None
            else Decimal("Infinity"),
            w.market_control_net_usd
            if w.market_control_net_usd is not None
            else Decimal("Infinity"),
        )
        for w in oos
    ):
        reasons.add("CONTROL_NOT_BEATEN")
    if any(
        w.max_drawdown_usd > min(input.daily_headroom_usd, input.trailing_headroom_usd) for w in oos
    ):
        reasons.add("OOS_DRAWDOWN_BREACH")
    if not all(t.status in ("ACCEPTED", "REJECTED", "BLOCKED") for t in input.trials):
        reasons.add("TRIAL_STATUS_UNKNOWN")
    if input.candidate_k < input.current_frozen_k:
        decision = (
            "DECREASE"
            if input.finance_frame is not None
            and not {"EXPIRED_EVIDENCE", "UNRESOLVED_EXECUTIONS_OR_INVENTORY"} & reasons
            else "INSUFFICIENT_EVIDENCE"
        )
    elif input.candidate_k == input.current_frozen_k:
        decision = "HOLD"
    else:
        decision = "INCREASE" if not reasons else "INSUFFICIENT_EVIDENCE"
    body = {
        "schema": "track_c_k_proposal_v1",
        "portfolio_version": input.portfolio_version,
        "portfolio_definition_sha256": input.portfolio_definition_sha256,
        "pod_id": input.pod_id,
        "sizing_policy_version": input.sizing_policy_version,
        "as_of": input.as_of,
        "current_frozen_k": input.current_frozen_k,
        "candidate_k": input.candidate_k,
        "decision": decision,
        "source_sha256": input.source_sha256,
        "screen_report_sha256": input.screen_report_sha256,
        "screen_cost_policy_version": input.screen_cost_policy_version,
        "trial_roster_sha256": input.trial_roster_sha256,
        "cost_policy_version": input.cost_policy_version,
        "risk_policy_version": input.risk_policy_version,
        "evidence_report_shas": tuple(sorted(w.report_sha256 for w in input.windows)),
        "tested_trials": len(input.trials),
        "rejected_trials": sum(t.status != "ACCEPTED" for t in input.trials),
        "effective_independent_episodes": sum(w.independent_episodes for w in oos),
        "follower_net_oos_usd": sum((w.follower_mtm_net_usd for w in oos), Decimal("0"))
        if oos
        else None,
        "finance_check": finance_check,
        "paired_economics": paired_economics,
        "evidence_class": "AUTHENTIC_PROSPECTIVE_PRESENT" if prospective else "HISTORICAL_ONLY",
        "reasons": tuple(sorted(reasons)),
        "confidence": "CONDITIONAL" if not reasons and prospective else "LOW",
        "research_only": True,
        "original_prospective_proof_verified": False,
        "authorized_for_trading": False,
        "release_activated": False,
        "order_route": "NONE",
    }
    return KProposal.model_validate(
        {
            **body,
            "identity_sha256": digest(
                KProposal.model_construct(**body).model_dump(mode="json", by_alias=True)
            ),
        }
    )


class KReleaseCandidate(Frozen):
    contract_schema: Literal["track_c_k_release_candidate_v1"] = Field(
        default="track_c_k_release_candidate_v1", alias="schema"
    )
    identity_sha256: SHA
    portfolio_version: str
    portfolio_definition_sha256: SHA
    pod_membership: tuple[str, ...]
    sizing_policy_version: str
    cost_policy_version: str
    risk_policy_version: str
    effective_at: str
    proposed_at: str
    rollback_release_sha256: SHA
    proposals: tuple[KProposal, ...]
    current_policy_sha256: SHA | None = None
    operator_signature: None = None
    activated: Literal[False] = False
    shadow_only: Literal[True] = True
    trading_authorized: Literal[False] = False
    order_route: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def verify(self):
        # Frozen models have mutable nested mappings. Recheck every nested
        # proposal content identity at the trust/publication boundary.
        for proposal in self.proposals:
            KProposal.model_validate_json(proposal.model_dump_json(by_alias=True))
        if clock(self.effective_at) <= clock(self.proposed_at):
            raise ValueError("RELEASE_EFFECTIVE_TIME_NOT_FUTURE")
        if len(set(self.pod_membership)) != len(self.pod_membership) or not self.pod_membership:
            raise ValueError("RELEASE_MEMBERSHIP_INVALID")
        if set(self.pod_membership) != {p.pod_id for p in self.proposals}:
            raise ValueError("RELEASE_PROPOSALS_MISSING_PODS")
        if any(
            p.portfolio_version != self.portfolio_version
            or p.portfolio_definition_sha256 != self.portfolio_definition_sha256
            or p.sizing_policy_version != self.sizing_policy_version
            or p.cost_policy_version != self.cost_policy_version
            or p.risk_policy_version != self.risk_policy_version
            or clock(p.as_of) > clock(self.proposed_at)
            or p.decision in {"INSUFFICIENT_EVIDENCE", "INCREASE"}
            for p in self.proposals
        ):
            raise ValueError("RELEASE_PROPOSAL_SCOPE_OR_EVIDENCE_INVALID")
        if self.identity_sha256 != digest(
            self.model_dump(mode="json", by_alias=True, exclude={"identity_sha256"})
        ):
            raise ValueError("RELEASE_IDENTITY_SHA_MISMATCH")
        return self


def make_candidate(
    *,
    portfolio_version: str,
    portfolio_definition_sha256: str,
    pod_membership: tuple[str, ...],
    sizing_policy_version: str,
    cost_policy_version: str,
    risk_policy_version: str,
    effective_at: str,
    proposed_at: str,
    rollback_release_sha256: str,
    proposals: tuple[KProposal, ...],
    current_policy_sha256: str | None = None,
) -> KReleaseCandidate:
    for proposal in proposals:
        KProposal.model_validate_json(proposal.model_dump_json(by_alias=True))
    body = dict(
        schema="track_c_k_release_candidate_v1",
        portfolio_version=portfolio_version,
        portfolio_definition_sha256=portfolio_definition_sha256,
        pod_membership=pod_membership,
        sizing_policy_version=sizing_policy_version,
        cost_policy_version=cost_policy_version,
        risk_policy_version=risk_policy_version,
        effective_at=effective_at,
        proposed_at=proposed_at,
        rollback_release_sha256=rollback_release_sha256,
        proposals=proposals,
        current_policy_sha256=current_policy_sha256,
        operator_signature=None,
        activated=False,
        shadow_only=True,
        trading_authorized=False,
        order_route="NONE",
    )
    return KReleaseCandidate.model_validate(
        {
            **body,
            "identity_sha256": digest(
                KReleaseCandidate.model_construct(**body).model_dump(mode="json", by_alias=True)
            ),
        }
    )


def bind_opportunity_k(
    *,
    first_known_at: str,
    pending_k: Decimal,
    pending_release_sha256: str,
    candidate: KReleaseCandidate,
    opportunity_already_exists: bool,
) -> dict[str, str]:
    """Pure audit projection; never writes a source, paper or Guardian journal."""
    clock(first_known_at)
    if opportunity_already_exists or clock(first_known_at) < clock(candidate.effective_at):
        return {
            "k": str(pending_k),
            "release_sha256": pending_release_sha256,
            "action": "PRESERVE_EXISTING_OPPORTUNITY",
        }
    return {
        "k": str(pending_k),
        "release_sha256": pending_release_sha256,
        "action": "NO_ACTIVE_RELEASE_CHANGE",
    }


def offline_preflight(
    candidate: KReleaseCandidate,
    *,
    sealed_definition_sha256: str,
    observed_current_release_sha256: str,
    pending_opportunity_count: int,
    open_inventory_count: int,
    registry_path: Path | None = None,
    registry_portfolio_id: str | None = None,
    registry_version: int | None = None,
) -> dict:
    """An offline verification receipt, intentionally no activation method."""
    KReleaseCandidate.model_validate_json(candidate.model_dump_json(by_alias=True))
    blockers = []
    verified_registry = False
    if registry_path is not None:
        if not registry_portfolio_id or registry_version is None:
            blockers.append("SQLITE_REGISTRY_SELECTOR_MISSING")
        else:
            from .wallet_registry_portfolios import select_asof

            try:
                db = Path(registry_path)
                with sqlite3.connect(f"file:{db.resolve(strict=True)}?mode=ro", uri=True) as con:
                    con.execute("PRAGMA query_only=ON")
                    sealed = select_asof(
                        con, registry_portfolio_id, candidate.proposed_at, version=registry_version
                    )
                if sealed.get("definition_sha256") != candidate.portfolio_definition_sha256 or set(
                    sealed.get("members", ())
                ) != set(candidate.pod_membership):
                    blockers.append("SQLITE_INDEPENDENT_PORTFOLIO_MISMATCH")
                else:
                    verified_registry = True
            except OSError, ValueError, sqlite3.DatabaseError:
                blockers.append("SQLITE_INDEPENDENT_SEAL_UNAVAILABLE")
    else:
        blockers.append("SQLITE_INDEPENDENT_SEAL_NOT_CHECKED")
    if candidate.portfolio_definition_sha256 != sealed_definition_sha256:
        blockers.append("SQLITE_PORTFOLIO_SEAL_MISMATCH")
    if candidate.rollback_release_sha256 != observed_current_release_sha256:
        blockers.append("ROLLBACK_RELEASE_MISMATCH")
    if pending_opportunity_count < 0 or open_inventory_count < 0:
        blockers.append("INVALID_JOURNAL_COUNTS")
    return {
        "schema": "track_c_k_preflight_v1",
        "status": "RESEARCH_PREFLIGHT_ONLY" if not blockers else "BLOCKED",
        "registry_seal_independently_verified": verified_registry,
        "finance_report_authenticity_verified": False,
        "release_eligible": False,
        "candidate_sha256": candidate.identity_sha256,
        "blockers": sorted(blockers),
        "pending_opportunities_preserved": pending_opportunity_count,
        "open_inventory_preserved": open_inventory_count,
        "journal_format": "existing PaperJournal / original T0 and frozen profile.k",
        "no_inventory_rebalance": True,
        "no_catchup": True,
        "activated": False,
        "order_route": "NONE",
        "trading_authorized": False,
    }
