"""Sealed source-account selection and historical official receipt adapter.

Selection is registry-first, point-in-time and independent of a signal-timing
policy. The official_accounts adapter is retained only for historical evidence
verification; CWSA runs via the REST checkpoint collector, not legacy WS.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import Callable

from .pm03_account import digest
from .pm_e4_prospective import _dex_universe, _guarded_info
from .pm_forward_journal import PaperJournal
from .pm_forward_observed_paper import PAPER_PROFILES, _readonly, _verify_portfolio_selection
from .pm_forward_source_stream import PersistentAccount

CWSA_PORTFOLIOS = frozenset(
    {"A", "B", "C", "Combo2", "regime.macro/TriadA", "regime.macro/TriadChop"}
)
HISTORICAL_PAPER_PORTFOLIOS = frozenset(PAPER_PROFILES)
APPROVED_PORTFOLIOS = HISTORICAL_PAPER_PORTFOLIOS | CWSA_PORTFOLIOS


def selected_parents(
    registry_db: Path, *, portfolios: tuple[str, ...], as_of: str
) -> dict[str, str]:
    """Resolve the exact sealed source roster without follower NAV inference."""
    if not portfolios or len(portfolios) != len(set(portfolios)):
        raise ValueError("V4_SELECTED_PORTFOLIOS_INVALID")
    if any(pid not in APPROVED_PORTFOLIOS for pid in portfolios):
        raise ValueError("V4_SELECTED_PORTFOLIO_UNAPPROVED")
    parents: dict[str, str] = {}
    with closing(_readonly(registry_db)) as db:
        db.execute("BEGIN")
        try:
            for pid in portfolios:
                if pid in PAPER_PROFILES:
                    selection = _verify_portfolio_selection(
                        registry_db, PAPER_PROFILES[pid], as_of=as_of
                    )
                    items = tuple(PAPER_PROFILES[pid].registry_aliases.items())
                else:
                    from .wallet_registry_portfolios import select_asof

                    selection = select_asof(db, pid, as_of)
                    if not selection.get("definition_sha256"):
                        raise ValueError("V4_SELECTED_PORTFOLIO_SEAL_MISSING")
                    items = tuple((m, m) for m in selection.get("members", []))
                if not selection.get("definition_sha256"):
                    raise ValueError("V4_SELECTED_PORTFOLIO_SEAL_MISSING")
                for alias, full in items:
                    addresses = db.execute(
                        "SELECT DISTINCT w.address FROM wallets w "
                        "JOIN wallet_aliases a ON a.wallet_id=w.wallet_id "
                        "WHERE a.alias=? AND a.known_at<=?",
                        (full, as_of),
                    ).fetchall()
                    if len(addresses) != 1:
                        raise ValueError("V4_SELECTED_ACCOUNT_IDENTITY_AMBIGUOUS")
                    address = addresses[0][0].lower()
                    if (
                        not address.startswith("0x")
                        or len(address) != 42
                        or any(c not in "0123456789abcdef" for c in address[2:])
                    ):
                        raise ValueError("V4_SELECTED_ADDRESS_INVALID")
                    previous = parents.setdefault(alias, address)
                    if previous != address:
                        raise ValueError("V4_SHARED_SELECTED_ACCOUNT_CONFLICT")
        finally:
            db.execute("ROLLBACK")
    if len(set(parents.values())) != len(parents):
        raise ValueError("V4_SELECTED_DUPLICATE_ACCOUNTS")
    return dict(sorted(parents.items()))


def selected_source_parents(
    registry_db: Path,
    *,
    portfolios: tuple[str, ...],
    as_of: str,
    campaign_manifest: Path | None = None,
    campaign_sha256: str | None = None,
) -> dict[str, str]:
    """Preserve historical campaign selection without activating its V4 policy."""
    if campaign_manifest is None:
        if campaign_sha256 is not None:
            raise ValueError("V4_CAMPAIGN_REQUIRES_PRIVATE_MANIFEST")
        return selected_parents(registry_db, portfolios=portfolios, as_of=as_of)
    from .pm_v4_sixteen_scenarios import IDENTITIES, load_campaign

    if (
        campaign_sha256 is None
        or len(portfolios) != len(IDENTITIES)
        or set(portfolios) != set(IDENTITIES)
    ):
        raise ValueError("V4_CAMPAIGN_PORTFOLIO_SCOPE_MISMATCH")
    return load_campaign(
        manifest=campaign_manifest,
        registry_db=registry_db,
        at=as_of,
        expected_sha256=campaign_sha256,
    ).parents


def official_accounts(
    journal: PaperJournal,
    parents: dict[str, str],
    *,
    info: Callable = _guarded_info,
    compact_evidence: bool = False,
) -> dict[str, PersistentAccount]:
    """Historical complete-position receipt verifier; not a running V4 collector."""
    if not parents:
        raise ValueError("V4_SELECTED_ACCOUNTS_EMPTY")
    catalog, raw, provided_sha = info({"type": "perpDexs"})
    if not isinstance(raw, bytes) or sha256(raw).hexdigest() != provided_sha:
        raise ValueError("V4_OFFICIAL_DEX_CATALOG_PROVENANCE_INVALID")
    _dex_universe(catalog)
    scope_sha = digest(
        [
            "SELECTED_PARENT_PERP_ONLY",
            sorted((alias, sha256(addr.encode()).hexdigest()) for alias, addr in parents.items()),
            provided_sha,
        ]
    )
    return {
        alias: PersistentAccount(
            journal=journal,
            alias=alias,
            address=address,
            dex_catalog=catalog,
            subaccounts=None,
            parent_alias=alias,
            scope_sha=scope_sha,
            compact_evidence=compact_evidence,
        )
        for alias, address in parents.items()
    }
