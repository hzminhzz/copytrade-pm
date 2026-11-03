"""PIT whole-book enrichment without inventing missing wallet exposure.

An exchange state seen at T does not prove an earlier trade was first known at T.
Only prospective transitions whose latest signed positions reconcile exactly to
a coherent as-known account snapshot are eligible for book-enriched research.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .trader_intelligence import (
    ObservationSnapshot,
    WalletEvent,
    _instrument,
    _sha,
    decimal,
    digest,
    utc,
)


@dataclass(frozen=True)
class CoherentBook:
    wallet: str
    source_event_at: str
    first_known_at: str
    source_sha256: str
    equity_usd: str | None
    positions: tuple[tuple[str, str], ...]
    all_dexes_complete: bool
    subaccounts_complete: bool
    spot_exposure_verified_absent: bool
    position_chain_complete: bool
    account_mode: str
    verified_strategy: str | None = None

    def __post_init__(self) -> None:
        _sha(self.source_sha256)
        if not self.wallet or utc(self.first_known_at) < utc(self.source_event_at):
            raise ValueError("INVALID_BOOK_CLOCK_OR_IDENTITY")
        if self.equity_usd is not None and decimal(self.equity_usd) <= 0:
            raise ValueError("NONPOSITIVE_WHOLE_BOOK_EQUITY")
        if self.verified_strategy not in (None, "FUNDING_CARRY", "MARKET_NEUTRAL"):
            raise ValueError("UNSUPPORTED_BOOK_STRATEGY_ATTESTATION")
        seen: set[str] = set()
        for market, quantity in self.positions:
            _instrument(market)
            decimal(quantity)
            if market in seen:
                raise ValueError("DUPLICATED_BOOK_POSITION")
            seen.add(market)

    @property
    def usable(self) -> bool:
        return (
            self.equity_usd is not None
            and self.all_dexes_complete
            and self.subaccounts_complete
            and self.spot_exposure_verified_absent
            and self.position_chain_complete
            and self.account_mode == "STANDARD_SEPARATE_DEX_BALANCES"
        )

    @property
    def version_sha256(self) -> str:
        return digest(
            {
                "wallet": self.wallet,
                "source_event_at": self.source_event_at,
                "first_known_at": self.first_known_at,
                "source_sha256": self.source_sha256,
                "equity_usd": self.equity_usd,
                "positions": sorted(self.positions),
                "all_dexes_complete": self.all_dexes_complete,
                "subaccounts_complete": self.subaccounts_complete,
                "spot_exposure_verified_absent": self.spot_exposure_verified_absent,
                "position_chain_complete": self.position_chain_complete,
                "account_mode": self.account_mode,
                "verified_strategy": self.verified_strategy,
            }
        )


def enrich_with_books(
    snapshot: ObservationSnapshot,
    books: tuple[CoherentBook, ...],
    *,
    decision_at: str,
) -> ObservationSnapshot:
    """Attach only verified as-of coherent books to latest source observations.

    Historical vendor fills remain retrospective without first-local receipts.
    Later books cannot rewrite a past decision; they must have been known at cut.
    """
    cut = utc(decision_at)
    active: dict[str, CoherentBook] = {}
    for book in sorted(books, key=lambda x: (utc(x.first_known_at), x.version_sha256)):
        if utc(book.first_known_at) > cut or utc(book.source_event_at) > cut:
            continue
        if book.wallet not in {w.alias for w in snapshot.wallets}:
            raise ValueError("BOOK_WALLET_OUTSIDE_MONITORED_ROSTER")
        older = active.get(book.wallet)
        if older and utc(older.first_known_at) == utc(book.first_known_at):
            if older.version_sha256 != book.version_sha256:
                raise ValueError("CONTRADICTORY_SAME_CUT_BOOK")
        active[book.wallet] = book

    by_scope: dict[tuple[str, str], WalletEvent] = {}
    for event in sorted(snapshot.events, key=lambda e: (e.known_at, e.event_id)):
        if event.known_at > cut:
            continue
        by_scope[(event.wallet, event.instrument)] = event

    changed: list[WalletEvent] = []
    for event in snapshot.events:
        book = active.get(event.wallet)
        if book is None or not book.usable or event.origin == "HISTORICAL_PROXY":
            changed.append(event)
            continue
        if event is not by_scope.get((event.wallet, event.instrument)):
            changed.append(event)
            continue
        if event.known_at > utc(book.first_known_at):
            changed.append(event)
            continue
        known = dict(book.positions)
        if event.position_after is None or event.instrument not in known:
            changed.append(event)
            continue
        if decimal(event.position_after) != decimal(known[event.instrument]):
            changed.append(event)
            continue
        nonzero_signs = {
            1 if decimal(qty) > 0 else -1 for qty in known.values() if decimal(qty) != 0
        }
        if book.verified_strategy:
            style = book.verified_strategy
        elif len(nonzero_signs) > 1:
            style = "HEDGED_BASKET"
        elif nonzero_signs:
            style = "DIRECTIONAL"
        else:
            style = "UNKNOWN"
        changed.append(
            replace(
                event,
                book_complete=True,
                source_equity_usd=book.equity_usd,
                strategy_style=style,
                book_id=book.version_sha256,
            )
        )
    return ObservationSnapshot(
        roster_id=snapshot.roster_id,
        roster_known_at=snapshot.roster_known_at,
        wallets=snapshot.wallets,
        events=tuple(changed),
        roster_origin=snapshot.roster_origin,
    )
