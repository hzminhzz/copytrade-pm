"""Read-only SQLite-sealed selected parent/policy proof for strategy health."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .pm_forward_observed_paper import PAPER_PROFILES, verify_portfolio_selection
from .pm_source_selection import selected_parents
from .strategy_health import StrategyScope


def verify_selected_registry(scope: StrategyScope, registry_db: Path) -> dict:
    if scope.tier != "SELECTED" or scope.selection_known_at is None:
        raise ValueError("STRATEGY_SELECTED_SCOPE_REQUIRED")
    if registry_db.is_symlink() or not registry_db.is_file():
        raise ValueError("STRATEGY_REGISTRY_ORIGINAL_UNAVAILABLE")
    if scope.selected_portfolio not in PAPER_PROFILES:
        raise ValueError("STRATEGY_PORTFOLIO_NOT_AN_OFFICIAL_SELECTED_PROFILE")
    selection = verify_portfolio_selection(
        registry_db,
        PAPER_PROFILES[scope.selected_portfolio],
        as_of=scope.selection_known_at.isoformat(),
    )
    if selection["definition_sha256"] != scope.selection_seal_sha256:
        raise ValueError("STRATEGY_ORIGINAL_SELECTION_SEAL_DRIFT")
    selected = selected_parents(
        registry_db,
        portfolios=(scope.selected_portfolio,),
        as_of=scope.selection_known_at.isoformat(),
    )
    if scope.source_alias not in selected:
        raise ValueError("STRATEGY_ALIAS_NOT_OFFICIALLY_SELECTED")
    addr = selected[scope.source_alias]
    expected = sha256(addr.encode()).hexdigest()
    if expected != scope.source_account_sha256:
        raise ValueError("STRATEGY_ORIGINAL_SOURCE_ACCOUNT_DRIFT")
    return {
        "schema": "strategy_original_sqlite_selection_v1",
        "source_alias": scope.source_alias,
        "source_account_sha256": expected,
        "selected_portfolio": scope.selected_portfolio,
        "selection_seal_sha256": selection["definition_sha256"],
        "selection_version": selection["version"],
        "read_only": True,
        "trading_authorized": False,
        "selected": {scope.source_alias: addr},
    }
