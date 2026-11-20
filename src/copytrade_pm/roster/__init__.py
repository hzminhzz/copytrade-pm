"""Seat leases, sticky reconciliation and daily unsigned release proposals.

Public surface (three deep operations plus typed evidence)::

    from copytrade_pm.roster import ReconcilerPolicy, RosterStore, reconcile_roster

    roster = RosterStore("~/.local/share/copytrade/roster.sqlite", writable=True)
    roster.register_account("cft-10k-paper", seats, policy_epoch=epoch)
    plan = reconcile_roster(
        current=roster.book_at("cft-10k-paper", as_of=now),
        scorecard=roster.latest_scorecard(as_of=now),
        bench=roster.latest_bench("cft-10k-paper", as_of=now),
        vetoes=roster.active_vetoes(as_of=now),
        policy=ReconcilerPolicy.sticky_pit_bench(),
        as_of=now,
    )
    roster.commit_plan(plan)  # stages one unsigned release proposal per UTC day

Layering:

* :mod:`copytrade_pm.roster.models` — deep-immutable typed state (no IO).
* :mod:`copytrade_pm.roster.reconciler` — pure ``reconcile_roster``.
* :mod:`copytrade_pm.roster.store` — stdlib-only SQLite persistence.
* :mod:`copytrade_pm.roster.proposals` — unsigned ``portfolio_release_v2`` body.

The package never imports ``facts``, scoring, paper risk or broker code, and it
never claims trading authorization: :attr:`ReconcilePlan.trading_authorized` is
structurally ``False``.
"""

from __future__ import annotations

from .models import (
    ALL_GATES,
    AllocationMode,
    BenchCandidate,
    CooldownRecord,
    DrainingOwner,
    GateFailure,
    OperatorVeto,
    ReconcilerPolicy,
    RosterCUSUMState,
    SeatBook,
    SeatLease,
    SeatSpec,
    WalletScorecard,
    canonical,
    digest,
    mandate_id,
    owner_id,
    wallet_address,
)
from .proposals import (
    ReleaseBinding,
    ReleaseProposal,
    build_release_proposal,
    finalise_payload,
)
from .reconciler import ReconcilePlan, SeatChange, reconcile_roster
from .store import DEFAULT_ROSTER_PATH, SCHEMA_VERSION, CommitReceipt, RosterStore, RosterStoreError
from .sealed import (
    SealedRosterMember,
    SealedRosterSelection,
    SealedSelectionError,
    select_sealed_book,
    verify_staged_selection,
)

__all__ = [
    "DEFAULT_ROSTER_PATH",
    "SealedRosterMember",
    "SealedRosterSelection",
    "SealedSelectionError",
    "select_sealed_book",
    "verify_staged_selection",
    "ALL_GATES",
    "AllocationMode",
    "BenchCandidate",
    "CommitReceipt",
    "CooldownRecord",
    "DrainingOwner",
    "GateFailure",
    "OperatorVeto",
    "ReconcilePlan",
    "ReconcilerPolicy",
    "ReleaseBinding",
    "ReleaseProposal",
    "RosterCUSUMState",
    "RosterStore",
    "RosterStoreError",
    "SCHEMA_VERSION",
    "SeatBook",
    "SeatChange",
    "SeatLease",
    "SeatSpec",
    "WalletScorecard",
    "build_release_proposal",
    "canonical",
    "digest",
    "finalise_payload",
    "mandate_id",
    "owner_id",
    "reconcile_roster",
    "wallet_address",
]
