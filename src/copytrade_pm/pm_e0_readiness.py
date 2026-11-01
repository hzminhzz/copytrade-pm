"""Fail-closed E0 promotion gates for the frozen A/B/C portfolios.

Decision evidence is supplied by independent audited producers. A Boolean here
is a *claim by the caller*, not an authenticated proof; this module never
authorizes an order or transforms retrospective timestamps into PIT receipts.
"""
from __future__ import annotations

from dataclasses import dataclass

from .pm_portfolio_e0 import PORTFOLIOS


@dataclass(frozen=True)
class PortfolioEvidence:
    wallet: str
    historical_complete_book: bool = False
    historical_equity_reconciled: bool = False
    historical_native_marks_complete: bool = False
    prospective_first_known_verified: bool = False
    independent_matched_economics: bool = False
    predeclared_oos_pass: bool = False
    account_specific_rulebook_confirmed: bool = False
    copying_api_permission_verified: bool = False
    executable_market_ids_verified: bool = False
    real_broker_reconciliation_verified: bool = False


HISTORICAL = (
    "historical_complete_book",
    "historical_equity_reconciled",
    "historical_native_marks_complete",
)
SCIENTIFIC = (
    "prospective_first_known_verified",
    "independent_matched_economics",
    "predeclared_oos_pass",
)
CONTRACT = (
    "account_specific_rulebook_confirmed",
    "copying_api_permission_verified",
    "executable_market_ids_verified",
    "real_broker_reconciliation_verified",
)


def assess_readiness(
    portfolio: str, evidence: dict[str, PortfolioEvidence],
) -> dict[str, object]:
    if portfolio not in PORTFOLIOS:
        raise ValueError("UNKNOWN_FROZEN_PORTFOLIO")
    expected = set(PORTFOLIOS[portfolio])
    if set(evidence) != expected:
        raise ValueError("E0_READINESS_REQUIRES_ALL_THREE_PODS")
    if any(evidence[pod].wallet != pod for pod in expected):
        raise ValueError("E0_READINESS_IDENTITY_MISMATCH")
    missing = {
        phase: {
            pod: [field for field in fields if getattr(evidence[pod], field) is not True]
            for pod in PORTFOLIOS[portfolio]
            if any(getattr(evidence[pod], field) is not True for field in fields)
        }
        for phase, fields in (
            ("historical_replay", HISTORICAL),
            ("scientific_qualification", SCIENTIFIC),
            ("contract_readiness", CONTRACT),
        )
    }
    return {
        "portfolio": portfolio,
        "historical_replay": "EVIDENCE_READY_FOR_RESEARCH_ONLY" if not missing["historical_replay"] else "BLOCKED_EVIDENCE",
        "scientific_qualification": "REQUIRES_INDEPENDENT_REVIEW" if not missing["scientific_qualification"] else "UNQUALIFIED",
        "contract_readiness": "REQUIRES_HUMAN_AUTHORIZATION" if not missing["contract_readiness"] else "NOT_AUTHORIZED",
        "missing": missing,
        "live_orders_enabled": False,
        "note": "Self-declared flags do not independently authenticate evidence or permit trading.",
    }
