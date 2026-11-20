"""Pure daily seat reconciliation: sticky leases, hard eviction, Q14 promotion.

``reconcile_roster`` is a total function of recorded evidence. It never reads a
clock, a file or a database, and it never authorizes trading: it only decides
which logical seats stay occupied, which retired owners start draining, and
which bench candidate (if any) takes a freed seat.

Discipline:

* **Sticky incumbents.** A healthy incumbent keeps its seat even when the bench
  offers a better score. Churn is a cost, not a signal.
* **Missing evidence never evicts.** A seat whose wallet has no scorecard is
  retained and reported as a warning; absence of evidence is not a failure and
  is never coerced to zero or to ``FLAT``.
* **Hard eviction is typed.** ``CUSUM_KILL`` (terminal latch), account value
  below the floor, negative 5m markout, dormancy and an active operator veto
  retire the owner into ``draining``; the seat is freed immediately.
* **Q16/Q21 isolation.** A retired owner is never re-seated and never transfers
  positions. Its successor is a *new* generation owner with ``new_pos_only``
  semantics, so residual risk stays pinned to the old owner book.
* **Q14=A promotion.** A freed seat accepts the best eligible orthogonal bench
  candidate immediately; with no eligible candidate the seat stays vacant and a
  fully vacant book reports :attr:`AllocationMode.FLAT`.
* **Cooldown.** Wallets evicted for non-edge operational reasons
  (``LOW_ACCOUNT_VALUE_LT_1K``, dormancy) become bench-eligible again only after
  a continuous cooldown window (14 days by default) with account value at or
  above the re-admission floor, active fills and proven copyable 5m drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Sequence

from copytrade_kernel import KnownAtTs

from .models import (
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
    digest,
    wallet_address,
)

__all__ = ["ReconcilePlan", "SeatChange", "reconcile_roster"]

_EVICTION_PRIORITY = (
    GateFailure.CUSUM_KILL,
    GateFailure.OPERATOR_VETO,
    GateFailure.ACCOUNT_VALUE_BELOW_FLOOR,
    GateFailure.NEGATIVE_5M_MARKOUT,
    GateFailure.NO_ACTIVE_FILLS,
)

_COOLDOWN_GATES = frozenset({GateFailure.ACCOUNT_VALUE_BELOW_FLOOR, GateFailure.NO_ACTIVE_FILLS})

ChangeAction = Literal["RETAIN", "VACATE", "EVICT", "PROMOTE"]


@dataclass(frozen=True, slots=True)
class SeatChange:
    """One typed transition applied to a seat by a reconciliation plan."""

    seat_id: str
    action: ChangeAction
    wallet: str | None = None
    owner: str | None = None
    generation: int | None = None
    reason: str | None = None

    @property
    def data(self) -> dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "action": self.action,
            "wallet": self.wallet,
            "owner": self.owner,
            "generation": self.generation,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReconcilePlan:
    """Deterministic, idempotent outcome of one daily reconciliation."""

    account_id: str
    as_of: KnownAtTs
    before: SeatBook
    next_book: SeatBook
    policy_sha: str
    changes: tuple[SeatChange, ...]
    warnings: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return self.next_book.sha != self.before.sha

    @property
    def mode(self) -> AllocationMode:
        return self.next_book.mode

    @property
    def trading_authorized(self) -> bool:
        """Structural: reconciliation is research/paper state, never permission."""
        return False

    @property
    def promoted(self) -> tuple[SeatChange, ...]:
        return tuple(change for change in self.changes if change.action == "PROMOTE")

    @property
    def evicted(self) -> tuple[SeatChange, ...]:
        return tuple(change for change in self.changes if change.action == "EVICT")

    @property
    def vacated(self) -> tuple[SeatChange, ...]:
        return tuple(change for change in self.changes if change.action == "VACATE")

    @property
    def data(self) -> dict[str, Any]:
        return {
            "schema": "roster_reconcile_plan_v1",
            "account_id": self.account_id,
            "as_of_ms": self.as_of.value,
            "policy_sha": self.policy_sha,
            "changed": self.changed,
            "mode": self.mode.value,
            "before_sha": self.before.sha,
            "next_sha": self.next_book.sha,
            "changes": [change.data for change in self.changes],
            "warnings": list(self.warnings),
            "trading_authorized": False,
        }

    @property
    def sha(self) -> str:
        return digest(self.data)


def _scorecards(
    scorecard: WalletScorecard | Mapping[str, WalletScorecard] | None,
) -> dict[str, WalletScorecard]:
    if scorecard is None:
        return {}
    if isinstance(scorecard, WalletScorecard):
        return {scorecard.wallet: scorecard}
    cards: dict[str, WalletScorecard] = {}
    for key, value in scorecard.items():
        if not isinstance(value, WalletScorecard):
            raise ValueError("INVALID_SCORECARD")
        wallet = wallet_address(key)
        if wallet != value.wallet:
            raise ValueError("SCORECARD_KEY_MISMATCH")
        cards[wallet] = value
    return cards


def _latches(
    latches: Mapping[str, RosterCUSUMState] | Iterable[RosterCUSUMState] | None,
) -> dict[str, RosterCUSUMState]:
    if latches is None:
        return {}
    items = latches.values() if isinstance(latches, Mapping) else latches
    out: dict[str, RosterCUSUMState] = {}
    for state in items:
        if not isinstance(state, RosterCUSUMState):
            raise ValueError("INVALID_CUSUM_STATE")
        out[state.wallet] = state
    return out


def _cooldowns(records: Iterable[CooldownRecord] | None) -> dict[str, CooldownRecord]:
    out: dict[str, CooldownRecord] = {}
    for record in records or ():
        if not isinstance(record, CooldownRecord):
            raise ValueError("INVALID_COOLDOWN_RECORD")
        out[record.wallet] = record
    return out


def _vetoes(vetoes: Iterable[OperatorVeto] | None, as_of: KnownAtTs) -> dict[str, OperatorVeto]:
    active: dict[str, OperatorVeto] = {}
    for veto in vetoes or ():
        if not isinstance(veto, OperatorVeto):
            raise ValueError("INVALID_VETO")
        if veto.active(as_of):
            active[veto.wallet] = veto
    return active


def _effective_failures(
    wallet: str,
    cards: Mapping[str, WalletScorecard],
    latches: Mapping[str, RosterCUSUMState],
    vetoes: Mapping[str, OperatorVeto],
) -> tuple[GateFailure, ...]:
    failures: set[GateFailure] = set(cards[wallet].failures) if wallet in cards else set()
    state = latches.get(wallet)
    if state is not None and state.latched:
        failures.add(GateFailure.CUSUM_KILL)
    if wallet in vetoes:
        failures.add(GateFailure.OPERATOR_VETO)
    return tuple(sorted(failures, key=lambda gate: gate.value))


def _eviction_reason(failures: Sequence[GateFailure]) -> GateFailure | None:
    present = set(failures)
    for gate in _EVICTION_PRIORITY:
        if gate in present:
            return gate
    return None


def _draining_entries(
    current: SeatBook,
    new_entries: Iterable[DrainingOwner],
    settled: frozenset[str],
) -> tuple[DrainingOwner, ...]:
    merged = {entry.owner: entry for entry in current.draining if entry.owner not in settled}
    for entry in new_entries:
        merged.setdefault(entry.owner, entry)
    return tuple(
        sorted(merged.values(), key=lambda item: (item.retired_ms, item.seat_id, item.owner))
    )


def reconcile_roster(
    *,
    current: SeatBook,
    policy: ReconcilerPolicy | None = None,
    as_of: KnownAtTs | None = None,
    scorecard: WalletScorecard | Mapping[str, WalletScorecard] | None = None,
    bench: Sequence[BenchCandidate] = (),
    vetoes: Sequence[OperatorVeto] = (),
    latches: Mapping[str, RosterCUSUMState] | Iterable[RosterCUSUMState] | None = None,
    cooldowns: Sequence[CooldownRecord] = (),
    settled_owners: Iterable[str] = (),
) -> ReconcilePlan:
    """Reconcile one account's :class:`SeatBook` against recorded evidence.

    Returns a plan whose ``next_book`` is exactly ``current`` when nothing
    changed (same clock, same SHA, no sequence bump), so applying the same plan
    twice is a no-op.
    """
    if not isinstance(current, SeatBook):
        raise ValueError("INVALID_SEAT_BOOK")
    decision_policy = policy or ReconcilerPolicy.sticky_pit_bench()
    if not isinstance(decision_policy, ReconcilerPolicy):
        raise ValueError("INVALID_POLICY")
    now = as_of or current.as_of
    if not isinstance(now, KnownAtTs):
        raise ValueError("INVALID_CLOCK")
    if now.value < current.as_of.value:
        raise ValueError("BOOK_CLOCK_REGRESSION")

    cards = _scorecards(scorecard)
    states = _latches(latches)
    active_vetoes = _vetoes(vetoes, now)
    cooling = _cooldowns(cooldowns)
    settled = frozenset(settled_owners)

    warnings: list[str] = []
    changes: list[SeatChange] = []
    new_draining: list[DrainingOwner] = []
    new_cooldowns: dict[str, CooldownRecord] = {}
    retained: list[tuple[SeatSpec, SeatLease | None]] = []
    vacant: list[SeatSpec] = []

    # 1. Decide every occupied seat: retain (sticky) or evict (hard gate/veto/latch).
    for spec, lease in current.seats:
        if lease is None:
            vacant.append(spec)
            retained.append((spec, None))
            continue
        wallet = lease.wallet
        if wallet not in cards:
            # Missing evidence is a warning, never a failure: the incumbent stays.
            warnings.append(f"SCORECARD_MISSING:{spec.seat_id}")
        failures = _effective_failures(wallet, cards, states, active_vetoes)
        reason = _eviction_reason(failures)
        if reason is not None and reason in decision_policy.evict_on:
            new_draining.append(
                DrainingOwner(
                    owner=lease.owner,
                    wallet=wallet,
                    seat_id=spec.seat_id,
                    generation=lease.generation,
                    retired_ms=now.value,
                    reason=reason,
                )
            )
            if reason in _COOLDOWN_GATES:
                new_cooldowns[wallet] = CooldownRecord(
                    wallet=wallet,
                    evicted_ms=now.value,
                    last_failure_ms=now.value,
                    reason=reason,
                )
            changes.append(
                SeatChange(
                    seat_id=spec.seat_id,
                    action="EVICT",
                    wallet=wallet,
                    owner=lease.owner,
                    generation=lease.generation,
                    reason=reason.value,
                )
            )
            vacant.append(spec)
            retained.append((spec, None))
            continue
        retained.append((spec, lease))
        changes.append(
            SeatChange(
                seat_id=spec.seat_id,
                action="RETAIN",
                wallet=wallet,
                owner=lease.owner,
                generation=lease.generation,
            )
        )

    # 2. Draining owners: keep every unsettled residual, drop the settled ones.
    draining = _draining_entries(current, new_draining, settled)

    # 3. Promotion. Orthogonality must be provable from seated scorecards.
    seated: list[tuple[SeatSpec, SeatLease | None]] = list(retained)
    seated_wallets = {lease.wallet for _, lease in seated if lease is not None}
    seated_clusters: set[str] = set()
    clusters_proven = True
    for _, lease in seated:
        if lease is None:
            continue
        card = cards.get(lease.wallet)
        if card is None:
            clusters_proven = False
        else:
            seated_clusters.add(card.cluster_id)
    if not clusters_proven:
        warnings.append("ORTHOGONALITY_UNPROVEN:seated_scorecard_missing")

    inflight: set[str] = set()
    occupied_seats = {spec.seat_id: index for index, (spec, _) in enumerate(seated)}
    for spec in vacant:
        chosen: BenchCandidate | None = None
        order = sorted(bench, key=lambda item: item.rank_key)
        for candidate in order:
            if candidate.wallet in inflight or candidate.wallet in seated_wallets:
                continue
            if candidate.wallet in active_vetoes:
                continue
            state = states.get(candidate.wallet)
            if state is not None and state.latched:
                continue
            card = cards.get(candidate.wallet)
            if card is None or card.sha != candidate.scorecard_sha:
                warnings.append(f"BENCH_SCORECARD_UNPROVEN:{candidate.wallet}")
                continue
            failures = _effective_failures(candidate.wallet, cards, states, active_vetoes)
            if any(gate in decision_policy.admission_block for gate in failures):
                continue
            floor = decision_policy.admission_min_account_value
            record = cooling.get(candidate.wallet)
            if record is not None:
                if not record.ready(now, decision_policy.cooldown_ms):
                    continue
                floor = decision_policy.readmit_min_account_value
            if card.account_value_usd < floor:
                continue
            if card.active_days_14d <= 0:
                continue
            if not card.copyable_drift:
                warnings.append(f"BENCH_DRIFT_UNPROVEN:{candidate.wallet}")
                continue
            if candidate.marginal_cdar_share > spec.max_cdar_share:
                continue
            if not clusters_proven:
                continue
            if card.cluster_id in seated_clusters:
                continue
            if candidate.cluster_distance < decision_policy.min_cluster_distance:
                continue
            chosen = candidate
            break
        if chosen is None:
            changes.append(SeatChange(seat_id=spec.seat_id, action="VACATE"))
            continue
        card = cards[chosen.wallet]
        prior = max(
            [
                lease.generation
                for _, lease in seated
                if lease is not None and lease.seat_id == spec.seat_id
            ]
            + [entry.generation for entry in draining if entry.seat_id == spec.seat_id]
            + [0]
        )
        generation = prior + 1
        lease = SeatLease(
            account_id=current.account_id,
            seat_id=spec.seat_id,
            wallet=chosen.wallet,
            generation=generation,
            k=chosen.suggested_k,
            since_ms=now.value,
            scorecard_sha=card.sha,
        )
        index = occupied_seats[spec.seat_id]
        seated[index] = (spec, lease)
        seated_wallets.add(chosen.wallet)
        inflight.add(chosen.wallet)
        seated_clusters.add(card.cluster_id)
        changes.append(
            SeatChange(
                seat_id=spec.seat_id,
                action="PROMOTE",
                wallet=chosen.wallet,
                owner=lease.owner,
                generation=generation,
                reason="BENCH_PROMOTION",
            )
        )

    next_book = current
    if len(seated) != len(current.seats) or any(
        before != after for before, after in zip(current.seats, seated, strict=True)
    ):
        next_book = SeatBook(
            account_id=current.account_id,
            as_of=now,
            policy_epoch=current.policy_epoch,
            seats=tuple(seated),
            draining=draining,
            sequence=current.sequence,
        )
    elif draining != current.draining:
        next_book = current.replace(draining=draining, as_of=now)

    return ReconcilePlan(
        account_id=current.account_id,
        as_of=now,
        before=current,
        next_book=next_book,
        policy_sha=decision_policy.sha,
        changes=tuple(changes),
        warnings=tuple(warnings),
    )


def plan_from_book(
    book: SeatBook, policy: ReconcilerPolicy | None = None, *, as_of: KnownAtTs | None = None
) -> ReconcilePlan:
    """Reconcile a book against no new evidence (used by CLI previews)."""
    return reconcile_roster(current=book, policy=policy, as_of=as_of)
