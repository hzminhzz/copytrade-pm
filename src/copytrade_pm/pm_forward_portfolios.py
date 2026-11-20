"""Dynamic, SQLite-sealed paper portfolio definitions and view projection.

Loads any sealed portfolio directly from the private SQLite registry,
supporting arbitrary multi-portfolio virtual deployments without code churn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sqlite3

from .roster.sealed import select_sealed_book, timestamp_ms
from .roster.store import DEFAULT_ROSTER_PATH, RosterStore

from .pm03_account import digest
from .pm_forward_admission import Admission
from .pm_forward_paper import PaperCampaign, PaperManifest

DEFAULT_REGISTRY_PATH = DEFAULT_ROSTER_PATH


@dataclass(frozen=True)
class FrozenPaperPortfolio:
    name: str
    members: tuple[str, ...]
    starting_capital: int = 10_000
    total_nominal_risk: int = 600
    definition_sha256: str | None = None

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
        return str(Decimal(self.total_nominal_risk) / Decimal(len(self.members)))


# Historical FP-09 baselines preserved for exact contract parity
P1 = FrozenPaperPortfolio("P1", ("S035", "S051", "S053"))
P14 = FrozenPaperPortfolio("P14", ("S035", "S051", "S053", "S064", "Whale_0x5f94"))


def verify_sealed_definition_sha(
    store: RosterStore,
    portfolio_name: str,
    version: int,
    members: tuple[str, ...],
    expected_sha: str,
    *,
    as_of: str | None = None,
) -> dict:
    if not isinstance(store, RosterStore):
        raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO")
    sealed = select_sealed_book(
        store,
        portfolio_name,
        timestamp_ms(as_of or datetime.now(UTC).isoformat()),
        require_attestation=False,
    )
    if (
        sealed.definition_sha256 != expected_sha
        or tuple(member.seat_id for member in sealed.members) != members
        or sealed.version != version
    ):
        raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO")
    return sealed.metadata()


def load_sealed_paper_portfolio(
    portfolio_name: str,
    db_path: Path | str = DEFAULT_REGISTRY_PATH,
    *,
    as_of: str | None = None,
) -> FrozenPaperPortfolio:
    """Load the verified PIT book and expose only canonical seat labels."""
    try:
        with RosterStore(db_path) as store:
            selected = select_sealed_book(
                store,
                portfolio_name,
                timestamp_ms(as_of or datetime.now(UTC).isoformat()),
                require_attestation=False,
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO") from exc
    return FrozenPaperPortfolio(
        name=portfolio_name,
        members=tuple(member.seat_id for member in selected.members),
        definition_sha256=selected.definition_sha256,
    )


class PaperPortfolioView:
    """Non-executing, read-only fanout over independently sealed PM-03 accounts.

    Dynamically verifies against sealed registry definitions while maintaining
    strict fail-closed admission and isolation across portfolios.
    """

    def __init__(
        self,
        campaign: PaperCampaign,
        registry_db: Path | str = DEFAULT_REGISTRY_PATH,
    ) -> None:
        self.campaign = campaign
        self.registry_db = Path(registry_db)
        self.portfolios: dict[str, FrozenPaperPortfolio] = {}
        self.run_ids: dict[str, str] = {}
        self.books: dict[str, Admission] = {}

    def register(self, portfolio: FrozenPaperPortfolio, manifest: PaperManifest) -> dict:
        # Load authoritative sealed definition from SQLite
        try:
            sealed = load_sealed_paper_portfolio(
                portfolio.name, self.registry_db, as_of=manifest.selected_at
            )
        except ValueError as exc:
            raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO") from exc

        if (
            portfolio.name != sealed.name
            or set(portfolio.members) != set(sealed.members)
            or (
                portfolio.definition_sha256 is not None
                and portfolio.definition_sha256 != sealed.definition_sha256
            )
        ):
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
