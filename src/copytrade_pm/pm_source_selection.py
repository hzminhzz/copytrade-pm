"""Point-in-time source membership from the canonical RosterStore."""

from __future__ import annotations

from pathlib import Path

from copytrade_kernel import KnownAtTs

from .roster.sealed import select_sealed_book, timestamp_ms
from .roster.store import RosterStore


def selected_parents(
    registry_db: Path, *, portfolios: tuple[str, ...], as_of: str
) -> dict[str, str]:
    if not portfolios or len(portfolios) != len(set(portfolios)):
        raise ValueError("CWSA_SELECTED_PORTFOLIOS_INVALID")
    parents: dict[str, str] = {}
    cutoff = timestamp_ms(as_of)
    with RosterStore(registry_db) as store, store.read_snapshot():
        for account_id in portfolios:
            adopted = store.observation_selection(account_id, as_of=KnownAtTs(cutoff))
            if adopted is not None:
                members = adopted["members"]
            else:
                selection = select_sealed_book(
                    store, account_id.replace("/", ":"), cutoff, require_attestation=False
                )
                members = {member.seat_id: member.wallet for member in selection.members}
            for alias, wallet in members.items():
                if parents.setdefault(alias, wallet) != wallet:
                    raise ValueError("CWSA_SHARED_SELECTED_ACCOUNT_CONFLICT")
    if len(set(parents.values())) != len(parents):
        raise ValueError("CWSA_SELECTED_DUPLICATE_ACCOUNTS")
    return dict(sorted(parents.items()))
