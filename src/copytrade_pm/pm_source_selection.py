"""Sealed source-account selection and historical official receipt adapter.

Selection is registry-first, point-in-time and independent of a signal-timing
policy. The official_accounts adapter is retained only for historical evidence
verification; CWSA runs via the REST checkpoint collector, not legacy WS.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Callable

from .pm03_account import digest
from .pm_e4_prospective import dex_universe, guarded_info
from .pm_forward_journal import PaperJournal
from .pm_forward_source_stream import PersistentAccount

from .roster.sealed import select_sealed_book, timestamp_ms
from .roster.store import RosterStore


def selected_parents(
    registry_db: Path, *, portfolios: tuple[str, ...], as_of: str
) -> dict[str, str]:
    """Resolve occupied source accounts under their canonical seat labels."""
    if not portfolios or len(portfolios) != len(set(portfolios)):
        raise ValueError("V4_SELECTED_PORTFOLIOS_INVALID")
    parents: dict[str, str] = {}
    cutoff = timestamp_ms(as_of)
    with RosterStore(registry_db) as store, store.read_snapshot():
        for account_id in portfolios:
            selection = select_sealed_book(store, account_id, cutoff, require_attestation=False)
            for member in selection.members:
                if parents.setdefault(member.seat_id, member.wallet) != member.wallet:
                    raise ValueError("V4_SHARED_SELECTED_ACCOUNT_CONFLICT")
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
    from .pm_source_campaign_roster import IDENTITIES, load_campaign

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
    info: Callable = guarded_info,
    compact_evidence: bool = False,
) -> dict[str, PersistentAccount]:
    """Historical complete-position receipt verifier; not a running V4 collector."""
    if not parents:
        raise ValueError("V4_SELECTED_ACCOUNTS_EMPTY")
    catalog, raw, provided_sha = info({"type": "perpDexs"})
    if not isinstance(raw, bytes) or sha256(raw).hexdigest() != provided_sha:
        raise ValueError("V4_OFFICIAL_DEX_CATALOG_PROVENANCE_INVALID")
    dex_universe(catalog)
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
