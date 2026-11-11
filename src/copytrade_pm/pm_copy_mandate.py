"""Signed immutable Copy Mandates and explicit destination lifecycle."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .pm03_account import digest
from .pm_source_contracts import Contract, FiniteDecimal, Sha, exact_decimal
from .production_manifest import verify

Phase = Literal["ABSENT", "AWAITING_BASELINE", "ACTIVE", "PAUSED", "RETIRED"]
Event = Literal["ACTIVATE", "COMPLETE_BASELINE", "PAUSE", "RETIRE"]


class CopyMandate(Contract):
    model_config = {"serialize_by_alias": True}
    schema_name: Literal["copy_mandate_v1"] = Field("copy_mandate_v1", alias="schema")
    mandate_id: Annotated[str, Field(min_length=1, max_length=100)]
    generation: Annotated[int, Field(gt=0)]
    source_id: Annotated[str, Field(min_length=1, max_length=100)]
    source_scope_generation: Sha
    source_account_sha: Sha
    account_id: Annotated[str, Field(min_length=1, max_length=100)]
    pod_id: Annotated[str, Field(min_length=1, max_length=100)]
    k: FiniteDecimal
    allowed_markets: tuple[str, ...]
    policy_epoch: Sha
    risk_policy_sha: Sha
    rulebook_sha: Sha
    effective_from_ms: Annotated[int, Field(ge=0)]
    effective_until_ms: Annotated[int, Field(gt=0)]
    sizing_policy: Literal["FIXED_K_NATIVE_QUANTITY"] = "FIXED_K_NATIVE_QUANTITY"
    entry_policy: Literal["ONE_SHOT_CHECKPOINT_V3"] = "ONE_SHOT_CHECKPOINT_V3"
    exit_policy: Literal["NATIVE_SAFE_CROSS_OR_REDUCE_V3"] = "NATIVE_SAFE_CROSS_OR_REDUCE_V3"

    @field_validator("k", mode="before")
    @classmethod
    def exact_k(cls, value):
        return exact_decimal(value)

    @model_validator(mode="after")
    def valid_mandate(self):
        from .pm_source_contracts import Position

        if not 0 < self.k <= 10 or self.effective_until_ms <= self.effective_from_ms:
            raise ValueError("MANDATE_K_OR_EFFECTIVE_INTERVAL")
        if not self.allowed_markets or self.allowed_markets != tuple(
            sorted(set(self.allowed_markets))
        ):
            raise ValueError("MANDATE_ALLOWED_MARKETS")
        for market in self.allowed_markets:
            Position(instrument=market, quantity=self.k)
        return self

    @property
    def sha(self) -> str:
        return digest(self.model_dump(mode="json"))

    @property
    def owner(self) -> str:
        return digest([self.account_id, self.mandate_id, self.generation])


class MandateState(Contract):
    phase: Phase
    mandate_sha: Sha
    sequence: Annotated[int, Field(ge=0)]
    activated_ms: Annotated[int, Field(ge=0)] | None = None
    baseline_outcome_id: Sha | None = None

    @classmethod
    def initial(cls, mandate: CopyMandate):
        return cls(phase="ABSENT", mandate_sha=mandate.sha, sequence=0)

    @property
    def sha(self) -> str:
        return digest(self.model_dump(mode="json"))


class MandateTransition(Contract):
    model_config = {"serialize_by_alias": True}
    schema_name: Literal["copy_mandate_transition_v1"] = Field(
        "copy_mandate_transition_v1", alias="schema"
    )
    predecessor: MandateState
    event: Event
    evidence_sha: Sha
    actor: Literal["RELEASE_AUTHORITY", "SOURCE_CONSUMER"]
    at_ms: Annotated[int, Field(ge=0)]
    guard: Literal[
        "PROSPECTIVE_ACTIVATION",
        "POST_ACTIVATION_COMPLETE",
        "AUTHORIZED_STOP",
        "ILLEGAL_EDGE",
        "INVALID_CLOCK",
    ]
    successor: MandateState
    effect: Literal[
        "AWAIT_BASELINE", "BASELINE_ONLY", "STOP_NEW_RISK_PRESERVE_OBLIGATIONS", "REJECTED"
    ]
    checkpoint_ms: Annotated[int, Field(ge=0)] | None = None

    @property
    def sha(self) -> str:
        return digest(self.model_dump(mode="json"))


def verify_mandate(envelope, key, *, account_id: str) -> CopyMandate:
    import json

    payload = verify(envelope, key, "copy-mandate-v1")
    result = CopyMandate.model_validate_json(json.dumps(payload))
    if result.account_id != account_id:
        raise ValueError("MANDATE_DESTINATION_MISMATCH")
    return result


def transition_mandate(
    mandate: CopyMandate,
    before: MandateState,
    *,
    event: Event,
    evidence_sha: str,
    at_ms: int,
    checkpoint_ms: int | None = None,
) -> MandateTransition:
    if before.mandate_sha != mandate.sha or type(at_ms) is not int or at_ms < 0:
        raise ValueError("MANDATE_PREDECESSOR_OR_CLOCK")
    body = before.model_dump() | {"sequence": before.sequence + 1}
    guard, effect = "ILLEGAL_EDGE", "REJECTED"
    if event == "ACTIVATE" and before.phase == "ABSENT":
        if at_ms <= mandate.effective_from_ms:
            body.update(phase="AWAITING_BASELINE", activated_ms=at_ms)
            guard, effect = "PROSPECTIVE_ACTIVATION", "AWAIT_BASELINE"
        else:
            guard = "INVALID_CLOCK"
    elif event == "COMPLETE_BASELINE" and before.phase == "AWAITING_BASELINE":
        if (
            type(checkpoint_ms) is int
            and mandate.effective_from_ms <= checkpoint_ms <= at_ms
            and at_ms < mandate.effective_until_ms
        ):
            body.update(phase="ACTIVE", baseline_outcome_id=evidence_sha)
            guard, effect = "POST_ACTIVATION_COMPLETE", "BASELINE_ONLY"
        else:
            guard = "INVALID_CLOCK"
    elif (event == "PAUSE" and before.phase in ("AWAITING_BASELINE", "ACTIVE")) or (
        event == "RETIRE" and before.phase in ("AWAITING_BASELINE", "ACTIVE", "PAUSED")
    ):
        if before.activated_ms is not None and at_ms >= before.activated_ms:
            body["phase"] = "PAUSED" if event == "PAUSE" else "RETIRED"
            guard, effect = "AUTHORIZED_STOP", "STOP_NEW_RISK_PRESERVE_OBLIGATIONS"
        else:
            guard = "INVALID_CLOCK"
    return MandateTransition(
        predecessor=before,
        event=event,
        evidence_sha=evidence_sha,
        actor="SOURCE_CONSUMER" if event == "COMPLETE_BASELINE" else "RELEASE_AUTHORITY",
        at_ms=at_ms,
        guard=guard,
        successor=MandateState(**body),
        effect=effect,
        checkpoint_ms=checkpoint_ms,
    )
