"""Identical-path PM-03 shadow policy comparison; synthetic research ONLY.

This is a narrow account-path comparator, not a general-purpose backtester.
No forward pass probabilities or live authorization can be inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D
from math import ceil

from .pm03_account import Account, Instrument, RiskState, Rulebook, ZERO, clock, digest
from .pm03_attribution import IntendedVirtualBooks, explain_economics
from .pm03_execution import CostModel, MarketObservation, execute_targets
from .pm03_risk import RiskEvidence, RiskPolicy, classify, loss_under_shock


@dataclass(frozen=True)
class ScenarioStep:
    as_of: str
    hypothetical_fill_at: str
    proposed: dict[str, dict[Instrument, D]]
    observations: dict[Instrument, MarketObservation]
    shocks: tuple[dict[Instrument, D], ...]
    trusted: bool = True
    capacity_known: bool = True
    hedge_break_loss: D = ZERO

    def validate(self, previous_time: str) -> None:
        if clock(self.as_of) <= clock(previous_time):
            raise ValueError("NONMONOTONE_SCENARIO_PATH")
        if clock(self.hypothetical_fill_at) < clock(self.as_of):
            raise ValueError("INVALID_FILL_TIME")
        if not self.shocks or self.hedge_break_loss < ZERO:
            raise ValueError("UNKNOWN_STRESS_INPUT")
        for q in self.observations.values():
            q.validate(self.as_of)


def _target_equal_risk(
    proposed: dict[str, dict[Instrument, D]],
    marks: dict[Instrument, D],
    shocks: tuple[dict[Instrument, D], ...],
    initial_equity: D,
) -> dict[str, dict[Instrument, D]]:
    """Equal modeled worst-scenario dollar risk, not volatility-based risk parity."""
    if not proposed:
        return {}
    budget_per_pm = initial_equity * D("0.01") / D(len(proposed))
    result = {}
    for pm, book in sorted(proposed.items()):
        if not book:
            result[pm] = {}
            continue
        worst = max((loss_under_shock(book, marks, shock) for shock in shocks), default=ZERO)
        # Unknown/zero stress is NOT evidence of riskless capacity.
        if worst <= ZERO:
            result[pm] = {}
            continue
        scale = min(D("1"), budget_per_pm / worst)
        result[pm] = {k: q * scale for k, q in book.items()}
    return result


def _tail(returns: list[D]) -> str | None:
    if not returns:
        return None
    n = max(1, ceil(len(returns) * 0.05))
    return str(sum(sorted(returns)[:n], ZERO) / n)


def compare_policies(
    *,
    rulebook: Rulebook,
    started_at: str,
    steps: list[ScenarioStep],
    cost_model: CostModel,
    historical_scores: dict[str, D],
    policy: RiskPolicy | None = None,
) -> dict:
    """Same market snapshots for equal-risk, top-PnL and supervised policy.

    historical_scores are frozen input research scores; if computed after the
    path they are look-ahead/hindsight, and this comparator MUST be labeled.
    """
    if not rulebook.confirmed or not rulebook.permitted:
        raise ValueError("SYNTHETIC_RULEBOOK_AND_MARKET_FIXTURE_REQUIRED")
    if not steps:
        raise ValueError("EMPTY_SCENARIO_PATH")
    prev = started_at
    for step in steps:
        step.validate(prev)
        prev = step.as_of
    report = {
        "schema": "pm03_same_path_policy_comparison_v1",
        "label": "RESEARCH_SYNTHETIC_NOT_VALIDATED_PASS_PROBABILITY",
        "input_sha": digest(
            {
                "rulebook_sha": rulebook.sha,
                "steps": [
                    {
                        "as_of": s.as_of,
                        "hypothetical_fill_at": s.hypothetical_fill_at,
                        "proposed": {
                            pm: {k.key: str(q) for k, q in sorted(b.items())}
                            for pm, b in sorted(s.proposed.items())
                        },
                        "quotes": {
                            k.key: {
                                "mark": str(q.mark),
                                "volume": str(q.volume_base),
                                "event_at": q.event_at,
                                "first_known_at": q.first_known_at,
                                "quality": q.quality,
                                "supported": q.supported,
                            }
                            for k, q in sorted(s.observations.items())
                        },
                        "shocks": [
                            {k.key: str(v) for k, v in sorted(shock.items())} for shock in s.shocks
                        ],
                        "trusted": s.trusted,
                        "capacity_known": s.capacity_known,
                        "hedge_break_loss": str(s.hedge_break_loss),
                    }
                    for s in steps
                ],
                "cost_model": {
                    k: str(getattr(cost_model, k))
                    for k in (
                        "fee_bps",
                        "full_spread_bps",
                        "slippage_bps",
                        "impact_bps_at_full_participation",
                        "max_participation",
                        "max_age_seconds",
                        "latency_seconds",
                    )
                },
                "historical_scores": {k: str(v) for k, v in sorted(historical_scores.items())},
            }
        ),
        "comparison": {},
        "hindsight_top_pnl_is_not_a_prospective_policy": True,
        "economically_qualified_wallet_count": 0,
        "no_live_authorization": True,
    }
    risk_policy = policy or RiskPolicy()
    best = (
        max(historical_scores, key=lambda x: (historical_scores[x], x))
        if historical_scores
        else None
    )
    for strategy in ("equal_risk", "historical_top_pnl", "central_risk"):
        a = Account.start(rulebook, started_at)
        path = [a.equity]
        events = []
        intent = IntendedVirtualBooks()
        intent_unknown = False
        price_drag = ZERO
        turnover = ZERO
        missing = []
        for step in steps:
            quote_prices = {k: o.mark for k, o in step.observations.items()}
            known = (
                step.trusted
                and step.capacity_known
                and all(q.supported for q in step.observations.values())
            )
            if not intent_unknown and step.trusted:
                try:
                    intent.mark_and_target(step.proposed, quote_prices)
                except ValueError:
                    intent_unknown = True
            else:
                intent_unknown = True
            tracked = set(a.quantities) | {
                k for book in a.pm_quantities.values() for k, q in book.items() if q
            }
            if tracked - set(quote_prices):
                a.risk = RiskState.HALT
                a.halt_reason = "MISSING_REQUIRED_MARK"
                missing.append(step.as_of)
                path.append(a.equity)
                continue
            a.mark(quote_prices, step.as_of)
            if a.breached:
                path.append(a.equity)
                events.append(
                    {
                        "as_of": step.as_of,
                        "state": "HALT",
                        "reason": "CONTRACTUAL_BREACH",
                        "fills": [],
                    }
                )
                continue
            if strategy == "equal_risk":
                proposed = _target_equal_risk(
                    step.proposed, quote_prices, step.shocks, rulebook.initial_balance
                )
                event_reason = "EQUAL_STRESSED_DOLLAR_RISK_PROXY"
            elif strategy == "historical_top_pnl":
                proposed = {best: step.proposed[best]} if best in step.proposed else {}
                event_reason = "HISTORICAL_SCORE_HINDSIGHT_BIAS_POSSIBLE"
            else:
                evidence = RiskEvidence(
                    trusted=step.trusted,
                    account_state_known=True,
                    market_state_known=bool(step.observations),
                    market_coverage_valid=step.capacity_known,
                    pending_unknown_orders=False,
                    input_status="RESEARCH_SYNTHETIC",
                    pm02_qualified=False,
                    hedge_break_loss=step.hedge_break_loss,
                )
                d = classify(a, step.proposed, quote_prices, step.shocks, evidence, risk_policy)
                proposed = d["approved"]
                event_reason = ",".join(d["reason_codes"]) or a.risk.value
            fill = execute_targets(
                a,
                proposed,
                step.observations,
                cost_model,
                decision_at=step.as_of,
                hypothetical_fill_at=step.hypothetical_fill_at,
                permitted=known and not a.breached,
            )
            price_drag += sum(
                (
                    D(row["quantity"]) * (D(row["execution_price"]) - D(row["mid_price"]))
                    for row in fill["fills"]
                ),
                ZERO,
            )
            turnover += sum(
                (abs(D(row["quantity"]) * D(row["execution_price"])) for row in fill["fills"]), ZERO
            )
            if fill["remaining"] or fill["rejections"]:
                missing.append(step.as_of)
            events.append(
                {
                    "as_of": step.as_of,
                    "state": a.risk.value,
                    "reason": event_reason,
                    "execution_status": fill["status"],
                    "internal_crosses": fill["internal_crosses"],
                    "rejections": fill["rejections"],
                    "remaining": fill["remaining"],
                    "fills": fill["fills"],
                    "breached": a.breached,
                }
            )
            path.append(a.equity)
        peak = path[0]
        maxdd = ZERO
        for eq in path:
            peak = max(peak, eq)
            maxdd = max(maxdd, peak - eq)
        returns = [path[i] - path[i - 1] for i in range(1, len(path))]
        report["comparison"][strategy] = {
            "equity": [str(x) for x in path],
            "max_drawdown": str(maxdd),
            "profit_target_progress": str(
                (path[-1] - rulebook.initial_balance) / rulebook.profit_target
            )
            if rulebook.profit_target
            else None,
            "contract_breach": a.breached,
            "stage_passed": a.stage_passed,
            "historical_expected_shortfall": _tail(returns),
            "fees": str(a.costs),
            "funding": str(a.funding),
            "turnover": str(turnover),
            "pm_attribution": {k: str(v) for k, v in a.pm_equity_pnl().items()},
            "final_balance": str(a.balance),
            "final_equity": str(a.equity),
            "risk_interventions": events,
            "unknown_or_unfilled_steps": missing,
            "hindsight_label": strategy == "historical_top_pnl",
            "economic_attribution": (
                explain_economics(a, intent, price_drag) if not intent_unknown else None
            ),
            "economic_attribution_quality": (
                "UNKNOWN_MISSING_PIT_MARKS"
                if intent_unknown
                else "SYNTHETIC_COSTLESS_MID_INTENT_VS_EXECUTED_ACCOUNT"
            ),
        }
    report["report_sha"] = digest(report)
    return report
