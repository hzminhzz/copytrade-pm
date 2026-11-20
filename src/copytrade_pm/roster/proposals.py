"""Unsigned release proposals built from a committed roster book.

A proposal is the *exact* ``portfolio_release_v2`` payload body without the
signature envelope and without ``mandate_authority_sha`` (which depends on the
offline signing key and is added by :func:`copytrade_pm.production_manifest.sign`
through :func:`finalise_payload`). Nothing here signs, and nothing here invents
a research provenance field: ``research_commit``, ``decision_sha``,
``selection_known_at_ms``, the checkpoint pins and the per-seat market scope all
come from a :class:`ReleaseBinding` recorded by the research/release owner.

:func:`_release_body` is the single construction site for that body: the staging
path and the pre-sign gate in :mod:`copytrade_pm.roster.sealed` both call it, so a
staged body that differs from the derived one cannot reach a signing key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from typing import Any, Literal, Mapping

from copytrade_kernel import CopyMandateSpec, DecisionMs, FixedKSizing, NativeInstrument

from .models import (
    AllocationMode,
    SeatBook,
    as_decimal,
    canonical,
    decimal_text,
    digest,
)

__all__ = [
    "ReleaseBinding",
    "ReleaseProposal",
    "build_release_proposal",
    "finalise_payload",
]

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_SHA_RE = re.compile(r"[0-9a-f]{64}")


def _sha(value: object, code: str = "INVALID_SHA256") -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ValueError(code)
    return value


def _ms(value: object, code: str = "INVALID_CLOCK") -> int:
    if type(value) is not int or value < 0:
        raise ValueError(code)
    return value


@dataclass(frozen=True, slots=True)
class ReleaseBinding:
    """Research/release provenance pinned once per account release generation."""

    account_id: str
    generation: int
    research_commit: str
    decision_sha: str
    selection_known_at_ms: int
    source_mode: Literal["SYNTHETIC", "PROSPECTIVE"]
    risk_policy_sha: str
    rulebook_sha: str
    checkpoint_policy: Mapping[str, Any]
    checkpoint_scopes: Mapping[str, Mapping[str, Any]]
    allowed_markets: Mapping[str, tuple[str, ...]]
    created_ms: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, str) or not 1 <= len(self.account_id) <= 100:
            raise ValueError("INVALID_ACCOUNT_ID")
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("INVALID_GENERATION")
        if (
            not isinstance(self.research_commit, str)
            or _COMMIT_RE.fullmatch(self.research_commit) is None
        ):
            raise ValueError("INVALID_RESEARCH_COMMIT")
        _sha(self.decision_sha, "INVALID_DECISION_SHA")
        _ms(self.selection_known_at_ms)
        if self.source_mode not in ("SYNTHETIC", "PROSPECTIVE"):
            raise ValueError("INVALID_SOURCE_MODE")
        _sha(self.risk_policy_sha, "INVALID_RISK_POLICY_SHA")
        _sha(self.rulebook_sha, "INVALID_RULEBOOK_SHA")
        if not isinstance(self.checkpoint_policy, Mapping) or not self.checkpoint_policy:
            raise ValueError("INVALID_CHECKPOINT_POLICY")
        if not isinstance(self.checkpoint_scopes, Mapping) or not self.checkpoint_scopes:
            raise ValueError("INVALID_CHECKPOINT_SCOPES")
        markets: dict[str, tuple[str, ...]] = {}
        for seat_id, keys in dict(self.allowed_markets).items():
            if not isinstance(seat_id, str) or not seat_id:
                raise ValueError("INVALID_SEAT_ID")
            tuple_keys = tuple(keys)
            if not tuple_keys or any(not NativeInstrument.valid(key) for key in tuple_keys):
                raise ValueError("INVALID_ALLOWED_MARKETS")
            if tuple_keys != tuple(sorted(set(tuple_keys))):
                raise ValueError("MARKETS_NOT_CANONICAL")
            markets[seat_id] = tuple_keys
        object.__setattr__(self, "allowed_markets", markets)
        _ms(self.created_ms)
        _ms(self.expires_at_ms)
        if self.expires_at_ms <= max(self.created_ms, self.selection_known_at_ms):
            raise ValueError("INVALID_RELEASE_WINDOW")
        # Canonicalise the pinned JSON so the epoch digest is order-independent.
        object.__setattr__(
            self, "checkpoint_policy", json.loads(canonical(dict(self.checkpoint_policy)))
        )
        object.__setattr__(
            self,
            "checkpoint_scopes",
            {
                str(key): json.loads(canonical(dict(value)))
                for key, value in dict(self.checkpoint_scopes).items()
            },
        )

    @property
    def policy_epoch(self) -> str:
        return digest(self.checkpoint_policy)

    @property
    def data(self) -> dict[str, Any]:
        return {
            "schema": "roster_release_binding_v1",
            "account_id": self.account_id,
            "generation": self.generation,
            "research_commit": self.research_commit,
            "decision_sha": self.decision_sha,
            "selection_known_at_ms": self.selection_known_at_ms,
            "source_mode": self.source_mode,
            "risk_policy_sha": self.risk_policy_sha,
            "rulebook_sha": self.rulebook_sha,
            "checkpoint_policy": dict(self.checkpoint_policy),
            "checkpoint_scopes": {k: dict(v) for k, v in self.checkpoint_scopes.items()},
            "allowed_markets": {k: list(v) for k, v in sorted(self.allowed_markets.items())},
            "created_ms": self.created_ms,
            "expires_at_ms": self.expires_at_ms,
        }

    @property
    def sha(self) -> str:
        return digest(self.data)

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> ReleaseBinding:
        return cls(
            account_id=value["account_id"],
            generation=value["generation"],
            research_commit=value["research_commit"],
            decision_sha=value["decision_sha"],
            selection_known_at_ms=value["selection_known_at_ms"],
            source_mode=value["source_mode"],
            risk_policy_sha=value["risk_policy_sha"],
            rulebook_sha=value["rulebook_sha"],
            checkpoint_policy=value["checkpoint_policy"],
            checkpoint_scopes=value["checkpoint_scopes"],
            allowed_markets={k: tuple(v) for k, v in value["allowed_markets"].items()},
            created_ms=value["created_ms"],
            expires_at_ms=value["expires_at_ms"],
        )


@dataclass(frozen=True, slots=True)
class ReleaseProposal:
    """One batched, unsigned daily proposal for a single account."""

    account_id: str
    day: str
    generation: int
    plan_sha: str
    book_sha: str
    binding_sha: str
    payload: Mapping[str, Any]
    created_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.payload, Mapping) or not self.payload:
            raise ValueError("INVALID_PROPOSAL_PAYLOAD")
        if "signature" in self.payload or "authority" in self.payload:
            raise ValueError("PROPOSAL_MUST_BE_UNSIGNED")
        _sha(self.plan_sha, "INVALID_PLAN_SHA")
        _sha(self.book_sha, "INVALID_BOOK_SHA")
        _sha(self.binding_sha, "INVALID_BINDING_SHA")
        _ms(self.created_ms)

    @property
    def payload_json(self) -> dict[str, Any]:
        return json.loads(canonical(dict(self.payload)))

    @property
    def sha(self) -> str:
        """Digest of the unsigned payload; the sign step covers it verbatim."""
        return digest(self.payload_json)

    @property
    def data(self) -> dict[str, Any]:
        return {
            "schema": "roster_release_proposal_v1",
            "account_id": self.account_id,
            "day": self.day,
            "generation": self.generation,
            "plan_sha": self.plan_sha,
            "book_sha": self.book_sha,
            "binding_sha": self.binding_sha,
            "created_ms": self.created_ms,
            "payload": self.payload_json,
            "trading_authorized": False,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> ReleaseProposal:
        return cls(
            account_id=value["account_id"],
            day=value["day"],
            generation=value["generation"],
            plan_sha=value["plan_sha"],
            book_sha=value["book_sha"],
            binding_sha=value["binding_sha"],
            payload=value["payload"],
            created_ms=value["created_ms"],
        )


def _members(book: SeatBook, binding: ReleaseBinding) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for lease in book.leases:
        markets = binding.allowed_markets.get(lease.seat_id)
        if not markets:
            raise ValueError(f"RELEASE_MARKET_SCOPE_MISSING:{lease.seat_id}")
        members.append(
            {
                "pod_id": lease.seat_id,
                "source_identity": lease.wallet,
                "identity_known_at_ms": lease.since_ms,
                "account_scope": [lease.wallet],
                "allocation": decimal_text(book.spec(lease.seat_id).risk_unit_usd),
                "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
                "k": decimal_text(lease.k),
                "allowed_markets": list(markets),
            }
        )
    return members


def _mandates(book: SeatBook, binding: ReleaseBinding, members: list[dict[str, Any]]) -> list[dict]:
    mandates: list[dict[str, Any]] = []
    by_seat = {member["pod_id"]: member for member in members}
    scopes = binding.checkpoint_scopes
    for lease in book.leases:
        member = by_seat[lease.seat_id]
        scope = scopes.get(lease.wallet)
        if scope is None:
            raise ValueError(f"RELEASE_CHECKPOINT_SCOPE_MISSING:{lease.seat_id}")
        if not isinstance(scope.get("generation"), str):
            raise ValueError(f"RELEASE_SCOPE_GENERATION_MISSING:{lease.seat_id}")
        spec = CopyMandateSpec(
            mandate_id=lease.mandate_id,
            generation=lease.generation,
            source_id=lease.wallet,
            source_scope_generation=scope["generation"],
            source_account_sha=scope["account_sha"],
            account_id=book.account_id,
            seat_id=lease.seat_id,
            k_wire=decimal_text(lease.k),
            sizing=FixedKSizing(lease.k),
            allowed_markets=tuple(NativeInstrument(key) for key in member["allowed_markets"]),
            policy_epoch=binding.policy_epoch,
            risk_policy_sha=binding.risk_policy_sha,
            rulebook_sha=binding.rulebook_sha,
            effective_from_ms=DecisionMs(binding.created_ms),
            effective_until_ms=DecisionMs(binding.expires_at_ms),
        )
        mandates.append(spec.data)
    return mandates


def finalise_payload(payload: Mapping[str, Any], authority_sha: str) -> dict[str, Any]:
    """Add the signer-dependent ``mandate_authority_sha`` and canonicalise."""
    _sha(authority_sha, "INVALID_AUTHORITY_SHA")
    body = json.loads(canonical(dict(payload)))
    body["mandate_authority_sha"] = authority_sha
    return json.loads(canonical(body))


def _release_body(
    book: SeatBook,
    binding: ReleaseBinding,
    *,
    inventory_sha: str,
    stamp: int,
) -> dict[str, Any]:
    """Derive the exact unsigned ``portfolio_release_v2`` body for one committed book.

    This is the single construction site for the body the release key signs:
    :func:`build_release_proposal` stages it, and
    :func:`copytrade_pm.roster.sealed.verify_staged_selection` re-derives it from
    the independently verified book, binding and roster inventory pin. Every byte
    a signer covers is therefore either a validated input or a digest of those
    inputs — ``definition_sha``, ``inventory_sha``, ``source_sha`` and
    ``batch_seconds`` included — so a staged body carrying a field the producer
    never derived cannot reach a signing key.
    """
    _sha(inventory_sha, "INVALID_INVENTORY_SHA")
    if book.account_id != binding.account_id:
        raise ValueError("RELEASE_ACCOUNT_MISMATCH")
    if book.policy_epoch != binding.policy_epoch:
        raise ValueError("RELEASE_POLICY_EPOCH_DRIFT")
    if book.mode is AllocationMode.FLAT:
        raise ValueError("ROSTER_FLAT_NO_RELEASE")
    if not book.leases:
        raise ValueError("ROSTER_FLAT_NO_RELEASE")
    for lease in book.leases:
        if lease.generation > binding.generation:
            raise ValueError("RELEASE_GENERATION_BEHIND_SEAT")
        if not binding.created_ms <= lease.since_ms <= binding.expires_at_ms:
            raise ValueError(f"LEASE_OUTSIDE_RELEASE_WINDOW:{lease.seat_id}")
    if not binding.created_ms <= stamp < binding.expires_at_ms:
        raise ValueError("INVALID_RELEASE_CLOCK")
    if binding.selection_known_at_ms > binding.created_ms or book.as_of.value > stamp:
        raise ValueError("RELEASE_SELECTION_NOT_KNOWN")
    members = _members(book, binding)
    mandates = _mandates(book, binding, members)
    definition_sha = digest(members)
    inventory = digest(
        {"roster": inventory_sha, "book": book.sha, "policy_epoch": binding.policy_epoch}
    )
    selection_known_at_ms = binding.selection_known_at_ms
    source_sha = digest(
        {
            "research_commit": binding.research_commit,
            "decision_sha": binding.decision_sha,
            "inventory_sha": inventory,
            "definition_sha": definition_sha,
            "selection_known_at_ms": selection_known_at_ms,
        }
    )
    return {
        "schema": "portfolio_release_v2",
        "generation": binding.generation,
        "account_binding": binding.account_id,
        "created_at_ms": stamp,
        "expires_at_ms": binding.expires_at_ms,
        "selection_known_at_ms": selection_known_at_ms,
        "members": members,
        "definition_sha": definition_sha,
        "inventory_sha": inventory,
        "decision_sha": binding.decision_sha,
        "source_sha": source_sha,
        "research_commit": binding.research_commit,
        "risk_policy_sha": binding.risk_policy_sha,
        "rulebook_sha": binding.rulebook_sha,
        "batch_seconds": 300,
        "source_mode": binding.source_mode,
        "checkpoint_policy": json.loads(canonical(dict(binding.checkpoint_policy))),
        "checkpoint_scopes": {
            key: json.loads(canonical(dict(value)))
            for key, value in sorted(binding.checkpoint_scopes.items())
        },
        "mandates": mandates,
    }


def build_release_proposal(
    book: SeatBook,
    binding: ReleaseBinding,
    *,
    inventory_sha: str,
    plan_sha: str,
    created_ms: int | None = None,
) -> ReleaseProposal:
    """Build the unsigned ``portfolio_release_v2`` body for one committed book."""
    if not isinstance(book, SeatBook):
        raise ValueError("INVALID_SEAT_BOOK")
    if not isinstance(binding, ReleaseBinding):
        raise ValueError("INVALID_RELEASE_BINDING")
    _sha(plan_sha, "INVALID_PLAN_SHA")
    stamp = binding.created_ms if created_ms is None else _ms(created_ms)
    payload = _release_body(book, binding, inventory_sha=inventory_sha, stamp=stamp)
    return ReleaseProposal(
        account_id=book.account_id,
        day=datetime.fromtimestamp(stamp / 1000, UTC).date().isoformat(),
        generation=binding.generation,
        plan_sha=plan_sha,
        book_sha=book.sha,
        binding_sha=binding.sha,
        payload=payload,
        created_ms=stamp,
    )


_ = (as_decimal, sha256)
