"""Frozen P1/P14 paper definitions and shared read-only observation fanout.

This is a portfolio admission/view projection, NOT a second wallet registry,
scheduler, or source-equity execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from .pm03_account import digest
from .pm_forward_admission import Admission
from .pm_forward_paper import PaperCampaign, PaperManifest


@dataclass(frozen=True)
class FrozenPaperPortfolio:
    name: str
    members: tuple[str, ...]
    starting_capital: int = 10_000
    total_nominal_risk: int = 600

    def __post_init__(self) -> None:
        if not self.name or not self.members or len(self.members) != len(set(self.members)):
            raise ValueError("INVALID_PORTFOLIO_MEMBERSHIP")
        if self.starting_capital != 10_000 or self.total_nominal_risk != 600:
            raise ValueError("UNAPPROVED_PORTFOLIO_RISK")

    @property
    def sha(self) -> str:
        return digest(
            {
                "schema": "frozen_paper_portfolio_v1",
                "name": self.name,
                "members": list(self.members),
                "starting_capital": self.starting_capital,
                "total_nominal_risk": self.total_nominal_risk,
            }
        )

    @property
    def nominal_risk_per_member(self) -> str:
        from decimal import Decimal

        return str(Decimal(self.total_nominal_risk) / Decimal(len(self.members)))


P1 = FrozenPaperPortfolio("P1", ("S035", "S051", "S053"))
P14 = FrozenPaperPortfolio("P14", ("S035", "S051", "S053", "S064", "Whale_0x5f94"))


class PaperPortfolioView:
    """Non-executing, read-only fanout over independently sealed PM-03 accounts."""

    def __init__(self, campaign: PaperCampaign) -> None:
        self.campaign = campaign
        self.portfolios: dict[str, FrozenPaperPortfolio] = {}
        self.run_ids: dict[str, str] = {}
        self.books: dict[str, Admission] = {}

    def register(self, portfolio: FrozenPaperPortfolio, manifest: PaperManifest) -> dict:
        # An approved *research priority* is not a registered paper trial.
        # P1/P14 are the only sealed FP-09 baselines in this version;
        # E6/E2 require their own versioned WR+FP campaign, not an alias
        # substitution with a matching initial balance or risk budget.
        if portfolio != {"P1": P1, "P14": P14}.get(portfolio.name):
            raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO")
        if portfolio.name in self.portfolios:
            raise ValueError("PORTFOLIO_ALREADY_SEALED")
        if manifest.portfolio_sha != portfolio.sha:
            raise ValueError("PORTFOLIO_MANIFEST_SHA_MISMATCH")
        if any(existing == manifest.run_id for existing in self.run_ids.values()):
            raise ValueError("DUPLICATE_PORTFOLIO_RUN_ID")
        state = self.campaign.register(manifest)
        self.portfolios[portfolio.name] = portfolio
        self.run_ids[portfolio.name] = manifest.run_id
        return state

    def observe(self, alias: str, admission: Admission) -> dict:
        if alias not in {m for p in self.portfolios.values() for m in p.members}:
            raise ValueError("SOURCE_NOT_IN_FROZEN_PORTFOLIOS")
        self.books[alias] = admission
        return {
            name: self.status(name)["source_admission"]
            for name, portfolio in self.portfolios.items()
            if alias in portfolio.members
        }

    def status(self, name: str) -> dict:
        portfolio = self.portfolios[name]
        state = self.campaign.status(self.run_ids[name])
        missing = [m for m in portfolio.members if m not in self.books]
        rejected = {
            m: list(self.books[m].reason_codes)
            for m in portfolio.members
            if m in self.books and not self.books[m].admitted
        }
        if missing or rejected:
            source_admission = "BLOCKED"
        else:
            source_admission = "SYNTHETIC_BOOKS_ONLY"
        return {
            **state,
            "portfolio_name": name,
            "portfolio_members": list(portfolio.members),
            "nominal_risk_per_member": portfolio.nominal_risk_per_member,
            "source_admission": source_admission,
            "missing_members": missing,
            "rejected_members": rejected,
            "active_paper_orders": 0,
        }
