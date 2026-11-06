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

from .pm03_account import digest
from .pm_forward_admission import Admission
from .pm_forward_paper import PaperCampaign, PaperManifest

DEFAULT_REGISTRY_PATH = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")


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


def _verify_sealed_definition_sha(
    conn: sqlite3.Connection,
    portfolio_name: str,
    version: int,
    members: tuple[str, ...],
    expected_sha: str,
    *,
    as_of: str | None = None,
) -> dict:
    """Use the registry owner to verify independent source, seal and membership."""
    from .wallet_registry_portfolios import select_asof

    try:
        sealed = select_asof(
            conn, portfolio_name, as_of or datetime.now(UTC).isoformat(), version=version
        )
    except (ValueError, sqlite3.DatabaseError) as exc:
        raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO") from exc
    if (
        sealed["definition_sha256"] != expected_sha
        or tuple(sealed["members"]) != members
        or sealed.get("version") != version
    ):
        raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO")
    return sealed


def load_sealed_paper_portfolio(
    portfolio_name: str,
    db_path: Path | str = DEFAULT_REGISTRY_PATH,
) -> FrozenPaperPortfolio:
    """Load a sealed portfolio definition dynamically from SQLite registry.

    Fails closed with UNSEALED_FORWARD_PAPER_PORTFOLIO if unsealed, unknown,
    or if the stored membership does not match the sealed definition record.
    """
    path = Path(db_path)
    if not path.is_file():
        raise ValueError(f"REGISTRY_DATABASE_NOT_FOUND: {path}")

    # Exact legacy FP-09 aliases match
    if portfolio_name == "P1":
        return P1
    if portfolio_name == "P14":
        return P14

    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.portfolio_id, s.version, s.definition_sha256
            FROM portfolio_seals s
            WHERE s.portfolio_id = ?
            ORDER BY s.version DESC
            LIMIT 1
            """,
            (portfolio_name,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"UNSEALED_FORWARD_PAPER_PORTFOLIO: {portfolio_name}")

        version = row["version"]
        definition_sha256 = row["definition_sha256"]

        cur.execute(
            """
            SELECT member_alias
            FROM portfolio_memberships
            WHERE portfolio_id = ? AND version = ?
            ORDER BY member_alias
            """,
            (portfolio_name, version),
        )
        members = tuple(r["member_alias"] for r in cur.fetchall())
        if not members:
            raise ValueError(f"UNSEALED_FORWARD_PAPER_PORTFOLIO: empty members {portfolio_name}")

        # Strictly verify definition hash matches canonical seal
        _verify_sealed_definition_sha(conn, portfolio_name, version, members, definition_sha256)

        return FrozenPaperPortfolio(
            name=portfolio_name,
            members=members,
            definition_sha256=definition_sha256,
        )
    finally:
        conn.close()


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
            sealed = load_sealed_paper_portfolio(portfolio.name, self.registry_db)
        except ValueError as exc:
            raise ValueError("UNSEALED_FORWARD_PAPER_PORTFOLIO") from exc

        if portfolio.name != sealed.name or portfolio.members != sealed.members:
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
