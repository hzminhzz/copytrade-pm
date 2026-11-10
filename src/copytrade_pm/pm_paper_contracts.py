"""Typed paper opportunity decisions; PM-03/04 remain the only financial owners.

These projections never hash source evidence or authorize orders. Versioned
ledger application owns persistence. Old journals keep their original reducer.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .pm_source_contracts import NativeKey, Sha, exact_decimal, quantity_text, utc_clock

ENTRY_DELAY_SECONDS = 300
ENTRY_GRACE_SECONDS = 30


class PaperContract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class OpportunityUpdate(PaperContract):
    at: str
    source_seq: Annotated[int, Field(gt=0)]
    source_sha: Sha


class OpportunityTiming(PaperContract):
    first_known_at: str
    due_at: str
    deadline_at: str
    decision_at: str
    modeled_attempt_at: str | None
    scheduler_jitter_seconds: str
    reason: Literal["ON_TIME", "LATE_WITHIN_GRACE", "EXPIRED_WITHOUT_ATTEMPT"]

    @model_validator(mode="after")
    def causal(self):
        known, due, deadline, decision = map(
            utc_clock, (self.first_known_at, self.due_at, self.deadline_at, self.decision_at)
        )
        if due - known != timedelta(seconds=ENTRY_DELAY_SECONDS) or deadline - due != timedelta(
            seconds=ENTRY_GRACE_SECONDS
        ):
            raise ValueError("PAPER_OPPORTUNITY_WINDOW_INVALID")
        delay = decision - due
        seconds = Decimal(delay.days * 86400 + delay.seconds) + Decimal(
            delay.microseconds
        ) / Decimal(1000000)
        if exact_decimal(self.scheduler_jitter_seconds) != seconds:
            raise ValueError("PAPER_SCHEDULER_JITTER_MISMATCH")
        if self.modeled_attempt_at is None:
            if decision <= deadline or self.reason != "EXPIRED_WITHOUT_ATTEMPT":
                raise ValueError("PAPER_EXPIRY_CLOCK_INVALID")
        elif utc_clock(self.modeled_attempt_at) != decision or not due <= decision <= deadline:
            raise ValueError("PAPER_ATTEMPT_OUTSIDE_WINDOW")
        elif self.reason != ("ON_TIME" if decision == due else "LATE_WITHIN_GRACE"):
            raise ValueError("PAPER_ATTEMPT_REASON_MISMATCH")
        return self


class PaperOpportunity(PaperContract):
    intent_id: Sha
    pod: Annotated[str, Field(min_length=1)]
    source_seq: Annotated[int, Field(gt=0)]
    source_sha: Sha
    source_event_at: str
    first_known_at: str
    due_at: str
    deadline_at: str
    created_at: str
    updated_at: str
    status: Literal[
        "PENDING_5M",
        "CANCELED",
        "CANCELED_SOURCE_GAP",
        "EXPIRED_NO_TRADE",
        "FILLED",
        "PARTIAL",
        "REJECTED",
    ]
    positions: dict[NativeKey, str]
    updates: list[OpportunityUpdate]
    # Optional only for replay of pre-versioned historical journals. New
    # prospective T+300 sources pin both values in their original PM03 event.
    frozen_k: str | None = None
    release_sha256: Sha | None = None
    terminal_at: str | None = None
    attempted_at: str | None = None
    reason: str | None = None
    order_ids: dict[NativeKey, Sha] | None = None
    timing: OpportunityTiming | None = None

    @model_validator(mode="after")
    def invariant(self):
        known, due, deadline, created, updated, source = map(
            utc_clock,
            (
                self.first_known_at,
                self.due_at,
                self.deadline_at,
                self.created_at,
                self.updated_at,
                self.source_event_at,
            ),
        )
        if due - known != timedelta(seconds=ENTRY_DELAY_SECONDS) or deadline - due != timedelta(
            seconds=ENTRY_GRACE_SECONDS
        ):
            raise ValueError("PAPER_OPPORTUNITY_WINDOW_INVALID")
        if not known <= created <= updated or source > updated:
            raise ValueError("PAPER_OPPORTUNITY_CLOCK_INVALID")
        if any(not exact_decimal(qty) for qty in self.positions.values()):
            raise ValueError("PAPER_OPPORTUNITY_ZERO_POSITION")
        if (self.frozen_k is None) != (self.release_sha256 is None):
            raise ValueError("PAPER_OPPORTUNITY_K_RELEASE_INCOMPLETE")
        if self.frozen_k is not None:
            k = exact_decimal(self.frozen_k)
            if not k.is_finite() or k <= 0:
                raise ValueError("PAPER_OPPORTUNITY_FROZEN_K_INVALID")
        if (
            not self.updates
            or self.updates[-1].source_seq != self.source_seq
            or self.updates[-1].source_sha != self.source_sha
            or utc_clock(self.updates[-1].at) != updated
        ):
            raise ValueError("PAPER_OPPORTUNITY_UPDATE_BINDING")
        for previous, current in zip(self.updates, self.updates[1:]):
            if previous.source_seq >= current.source_seq or utc_clock(previous.at) > utc_clock(
                current.at
            ):
                raise ValueError("PAPER_OPPORTUNITY_UPDATE_ORDER")
        if self.terminal_at is not None and utc_clock(self.terminal_at) < updated:
            raise ValueError("PAPER_OPPORTUNITY_TERMINAL_CLOCK")
        if self.status == "PENDING_5M":
            if any(
                value is not None
                for value in (self.terminal_at, self.attempted_at, self.order_ids, self.timing)
            ):
                raise ValueError("PAPER_PENDING_ALREADY_CONSUMED")
        elif self.terminal_at is None:
            raise ValueError("PAPER_TERMINAL_CLOCK_REQUIRED")
        if self.status in ("FILLED", "PARTIAL", "REJECTED"):
            if (
                self.attempted_at is None
                or self.attempted_at != self.terminal_at
                or not due <= utc_clock(self.attempted_at) <= deadline
            ):
                raise ValueError("PAPER_ATTEMPT_OUTSIDE_WINDOW")
        if self.timing is not None and (
            self.timing.first_known_at != self.first_known_at
            or self.timing.due_at != self.due_at
            or self.timing.deadline_at != self.deadline_at
            or self.timing.decision_at != self.terminal_at
            or self.timing.modeled_attempt_at != self.attempted_at
        ):
            raise ValueError("PAPER_TIMING_BINDING_MISMATCH")
        return self

    def coalesce(
        self,
        *,
        source_seq: int,
        source_sha: str,
        source_event_at: str,
        positions: dict[str, str],
        decision_at: str,
    ) -> PaperOpportunity:
        if self.status != "PENDING_5M" or source_seq <= self.source_seq:
            raise ValueError("PAPER_OPPORTUNITY_NOT_COALESCIBLE")
        row = self.model_dump(exclude_none=True)
        row.update(
            source_seq=source_seq,
            source_sha=source_sha,
            source_event_at=source_event_at,
            positions=dict(positions),
            updated_at=decision_at,
        )
        row["updates"].append(
            {"at": decision_at, "source_seq": source_seq, "source_sha": source_sha}
        )
        return PaperOpportunity.model_validate(row)

    def eligibility(self, decision_at: str) -> Literal["TERMINAL", "WAIT", "READY", "EXPIRED"]:
        decision = utc_clock(decision_at)
        if self.status != "PENDING_5M":
            return "TERMINAL"
        if decision < utc_clock(self.due_at):
            return "WAIT"
        if decision > utc_clock(self.deadline_at):
            return "EXPIRED"
        return "READY"

    def terminal_timing(self, decision_at: str, *, attempted: bool) -> OpportunityTiming:
        delay = utc_clock(decision_at) - utc_clock(self.due_at)
        seconds = Decimal(delay.days * 86400 + delay.seconds) + Decimal(
            delay.microseconds
        ) / Decimal(1000000)
        return OpportunityTiming(
            first_known_at=self.first_known_at,
            due_at=self.due_at,
            deadline_at=self.deadline_at,
            decision_at=decision_at,
            modeled_attempt_at=decision_at if attempted else None,
            scheduler_jitter_seconds=quantity_text(seconds),
            reason=("ON_TIME" if not seconds else "LATE_WITHIN_GRACE")
            if attempted
            else "EXPIRED_WITHOUT_ATTEMPT",
        )


class FollowerExitDecision(PaperContract):
    """A projection of existing financial/reconciliation evidence, not inventory."""

    pod_flat: bool
    unresolved_exposure: bool
    pending_order_quantity: bool
    reconciliation_known: bool

    @property
    def clear_obsolete_target(self) -> bool:
        return (
            self.pod_flat
            and not self.unresolved_exposure
            and not self.pending_order_quantity
            and self.reconciliation_known
        )
