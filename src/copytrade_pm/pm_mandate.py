"""Signed Copy Mandate boundary: kernel-owned fields, PM-owned authorization.

Field validation, wire parsing and the Q14/Q18/Q21 lifecycle are owned by
``copytrade_kernel``. This module only adds what belongs to the paper consumer:
the offline signature check, and the exact evidence digests the PM journals
persist (``mandate_sha`` and owner identity).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from copytrade_kernel import (
    CopyMandateSpec,
    MandateEvent,
    MandatePhase,
    MandateState,
    MandateTransition,
    NativeInstrument,
)
from copytrade_kernel import transition_mandate as _kernel_transition

from .pm03_account import digest
from .production_manifest import verify

__all__ = (
    "MandateEvent",
    "MandatePhase",
    "MandateState",
    "MandateTransition",
    "NativeInstrument",
    "SignedMandate",
    "companion_json",
    "mandate_json",
    "state_json",
    "state_parse",
    "state_sha",
    "transition_mandate",
    "verify_mandate",
)


def companion_json(value: object) -> str:
    """Compact, order-independent JSON for journal rows that persist kernel data."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


_WIRE_DEFAULTS = {
    "schema": "copy_mandate_v1",
    "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
    "entry_policy": "ONE_SHOT_CHECKPOINT_V3",
    "exit_policy": "NATIVE_SAFE_CROSS_OR_REDUCE_V3",
}


@dataclass(frozen=True)
class SignedMandate:
    """A kernel-parsed mandate plus the PM evidence digests over its wire payload."""

    spec: CopyMandateSpec
    sha: str
    owner: str

    @classmethod
    def parse(cls, payload: dict) -> SignedMandate:
        spec = CopyMandateSpec.parse(payload)
        return cls(
            spec,
            digest(spec.data),
            digest([spec.account_id, spec.mandate_id, spec.generation]),
        )

    @classmethod
    def from_fields(cls, **fields) -> SignedMandate:
        """Build from the wire field names used by release builders and tests."""
        payload = {**_WIRE_DEFAULTS, **fields}
        payload["k"] = payload["k"] if isinstance(payload["k"], str) else str(payload["k"])
        payload["allowed_markets"] = list(payload["allowed_markets"])
        return cls.parse(payload)

    @classmethod
    def from_json(cls, raw: str) -> SignedMandate:
        return cls.parse(json.loads(raw))

    def model_copy(self, *, update: dict | None = None, deep: bool = False) -> SignedMandate:
        if not update:
            return self
        return SignedMandate.from_fields(**(self.spec.data | dict(update)))

    @property
    def data(self) -> dict:
        return self.spec.data

    # Compatibility surface for the receipt-shaped call sites; no new semantics.
    def model_dump(self, mode: str = "python") -> dict:
        return self.spec.data

    def model_dump_json(self, **_: object) -> str:
        return companion_json(self.spec.data)

    @property
    def mandate_id(self) -> str:
        return self.spec.mandate_id

    @property
    def generation(self) -> int:
        return self.spec.generation

    @property
    def account_id(self) -> str:
        return self.spec.account_id

    @property
    def pod_id(self) -> str:
        return self.spec.seat_id

    @property
    def source_id(self) -> str:
        return self.spec.source_id

    @property
    def source_scope_generation(self) -> str:
        return self.spec.source_scope_generation

    @property
    def source_account_sha(self) -> str:
        return self.spec.source_account_sha

    @property
    def policy_epoch(self) -> str:
        return self.spec.policy_epoch

    @property
    def risk_policy_sha(self) -> str:
        return self.spec.risk_policy_sha

    @property
    def rulebook_sha(self) -> str:
        return self.spec.rulebook_sha

    @property
    def k(self) -> Decimal:
        return self.spec.sizing.k

    @property
    def allowed_markets(self) -> tuple[str, ...]:
        return tuple(instrument.key for instrument in self.spec.allowed_markets)

    @property
    def effective_from_ms(self) -> int:
        return self.spec.effective_from_ms.value

    @property
    def effective_until_ms(self) -> int:
        return self.spec.effective_until_ms.value


def verify_mandate(envelope, key, *, account_id: str) -> SignedMandate:
    """Verify the offline signature, then hand the signed payload to the kernel."""
    payload = verify(envelope, key, "copy-mandate-v1")
    result = SignedMandate.parse(payload)
    if result.account_id != account_id:
        raise ValueError("MANDATE_DESTINATION_MISMATCH")
    return result


def state_parse(raw: str) -> MandateState:
    return MandateState.parse(json.loads(raw))


def transition_parse(raw: str) -> MandateTransition:
    data = json.loads(raw)
    state = MandateState.parse
    return MandateTransition(
        predecessor=state(data["predecessor"]),
        event=MandateEvent(data["event"]),
        evidence_sha=data["evidence_sha"],
        at_ms=data["at_ms"],
        guard=data["guard"],
        successor=state(data["successor"]),
        effect=data["effect"],
        checkpoint_ms=data["checkpoint_ms"],
    )


def state_json(state: MandateState) -> str:
    return companion_json(state.data)


def state_sha(state: MandateState) -> str:
    return digest(state.data)


def mandate_json(transition: MandateTransition) -> str:
    return companion_json(transition.data)


def transition_mandate(
    mandate: SignedMandate,
    before: MandateState,
    *,
    event: MandateEvent | str,
    evidence_sha: str,
    at_ms: int,
    checkpoint_ms: int | None = None,
) -> MandateTransition:
    return _kernel_transition(
        mandate.spec,
        before,
        mandate_sha=mandate.sha,
        event=MandateEvent(event),
        evidence_sha=evidence_sha,
        at_ms=at_ms,
        checkpoint_ms=checkpoint_ms,
    )
