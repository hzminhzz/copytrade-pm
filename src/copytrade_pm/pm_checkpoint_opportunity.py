"""Explicit one-shot consumer protocol. No financial or transport authority."""

from typing import Literal

from .pm_source_contracts import Contract, Sha
from .pm_checkpoint_source import Milliseconds

Phase = Literal["UNDECIDED", "REVIEWABLE", "PRE_DISPATCH_BLOCKED", "COMMITTED_ONCE", "MISSED"]
Event = Literal["REVIEW", "BLOCK", "COMMIT", "MISS"]


class OpportunityState(Contract):
    opportunity_id: Sha
    owner: Sha
    signal_id: Sha
    deadline_ms: Milliseconds
    phase: Phase = "UNDECIDED"
    sequence: int = 0
    last_at_ms: Milliseconds = 0


class OpportunityTransition(Contract):
    predecessor: OpportunityState
    event: Event
    evidence_sha: Sha
    at_ms: Milliseconds
    actor: Literal["PAPER", "GUARDIAN"]
    guard: str
    successor: OpportunityState
    effect: Literal["REVIEW_ONLY", "NO_SIDE_EFFECT", "COMMITTED_ONCE", "MISSED"]


def advance(
    before: OpportunityState,
    *,
    event: Event,
    evidence_sha: str,
    at_ms: int,
    actor: Literal["PAPER", "GUARDIAN"],
    guard: str,
    no_side_effect: bool = False,
) -> OpportunityTransition:
    if before.phase in ("COMMITTED_ONCE", "MISSED"):
        raise ValueError("OPPORTUNITY_TERMINAL")
    if at_ms < before.last_at_ms:
        raise ValueError("OPPORTUNITY_CLOCK_REGRESSION")
    if event != "MISS" and at_ms >= before.deadline_ms:
        raise ValueError("OPPORTUNITY_EXPIRED")
    if event == "REVIEW":
        if before.phase not in ("UNDECIDED", "PRE_DISPATCH_BLOCKED") or not no_side_effect:
            raise ValueError("OPPORTUNITY_REVIEW_REQUIRES_NO_SIDE_EFFECT")
        phase, effect = "REVIEWABLE", "REVIEW_ONLY"
    elif event == "BLOCK":
        if before.phase != "REVIEWABLE" or not no_side_effect:
            raise ValueError("OPPORTUNITY_BLOCK_REQUIRES_NO_SIDE_EFFECT")
        phase, effect = "PRE_DISPATCH_BLOCKED", "NO_SIDE_EFFECT"
    elif event == "COMMIT":
        if before.phase != "REVIEWABLE":
            raise ValueError("OPPORTUNITY_COMMIT_PREDECESSOR")
        phase, effect = "COMMITTED_ONCE", "COMMITTED_ONCE"
    else:
        phase, effect = "MISSED", "MISSED"
    after = before.model_copy(
        update={
            "phase": phase,
            "sequence": before.sequence + 1,
            "last_at_ms": at_ms,
        }
    )
    return OpportunityTransition(
        predecessor=before,
        event=event,
        evidence_sha=evidence_sha,
        at_ms=at_ms,
        actor=actor,
        guard=guard,
        successor=after,
        effect=effect,
    )
