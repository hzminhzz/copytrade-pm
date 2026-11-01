"""Frozen A/B/C pod identities and explicit E0 readiness routing.

No private alias/address map or vendor payload is embedded. This module does
not manufacture Q3 books or silently substitute episode-level source fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D
from typing import Mapping

from .pm_wallet_replica import Replica, WalletBook, fidelity, replicate

PORTFOLIOS: dict[str, tuple[str, str, str]] = {
    "A": ("W028", "W042", "W030"),
    "B": ("W044", "CA-005", "W031"),
    "C": ("CO-001", "W015", "VS066"),
}


@dataclass(frozen=True)
class PortfolioE0:
    name: str
    status: str
    books: dict[str, Replica]
    blocked: dict[str, str]
    evidence_class: str = "PROSPECTIVE_INTENT_ONLY_NOT_FOLLOWER_ECONOMICS"


def prepare_portfolio(
    name: str, *, source_books: Mapping[str, WalletBook],
    decision_at: str, pod_capital_usd: D = D("2000"),
) -> PortfolioE0:
    """All-or-nothing E0: one blocked pod means NO portfolio target.

    Never drops a hedge or a wallet when a source book cannot be authenticated.
    Evidence provenance must be independently checked before calling this seam.
    """
    if name not in PORTFOLIOS:
        raise ValueError("UNKNOWN_FROZEN_PORTFOLIO")
    expected = PORTFOLIOS[name]
    if set(source_books) != set(expected):
        missing = sorted(set(expected) - set(source_books))
        extra = sorted(set(source_books) - set(expected))
        raise ValueError(f"E0_PORTFOLIO_ROSTER_MISMATCH missing={missing} extra={extra}")
    valid: dict[str, Replica] = {}
    blocked: dict[str, str] = {}
    for wallet in expected:
        book = source_books[wallet]
        if book.wallet != wallet:
            blocked[wallet] = "E0_WALLET_IDENTITY_MISMATCH"
            continue
        try:
            valid[wallet] = replicate(
                book, decision_at=decision_at, pod_capital_usd=pod_capital_usd
            )
        except ValueError as exc:
            blocked[wallet] = str(exc)
    if blocked:
        return PortfolioE0(name, "BLOCKED_EVIDENCE", {}, blocked)
    return PortfolioE0(name, "SOURCE_INTENT_READY_NOT_AUTHORIZED", valid, {})


def assess_portfolio(
    prepared: PortfolioE0, *,
    risk_approved: Mapping[str, Mapping[str, D]],
    executed: Mapping[str, Mapping[str, D]],
    marks: Mapping[str, D],
) -> dict[str, object]:
    """Compute per-pod stage fidelity without inventing account PnL."""
    if prepared.status != "SOURCE_INTENT_READY_NOT_AUTHORIZED":
        raise ValueError("E0_BLOCKED_PORTFOLIO_CANNOT_ASSESS")
    if set(prepared.books) != set(risk_approved) or set(prepared.books) != set(executed):
        raise ValueError("E0_MISSING_POD_RISK_OR_EXECUTION_BOOK")
    return {
        "portfolio": prepared.name,
        "status": "SOURCE_FIDELITY_MEASURED_NOT_ECONOMICALLY_QUALIFIED",
        "pods": {
            pod: fidelity(replica, approved=risk_approved[pod],
                          executed=executed[pod], marks={
                              key: marks[key] for key in
                              (set(replica.intended) | set(risk_approved[pod]) | set(executed[pod]))
                              if key in marks
                          })
            for pod, replica in prepared.books.items()
        },
        "realized_follower_pnl_verified": False,
        "authorized": False,
    }
