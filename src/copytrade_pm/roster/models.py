"""Deep-immutable roster state: seats, leases, bench, vetoes and the Q12 latch.

This module is the vocabulary of :mod:`copytrade_pm.roster`. It is pure: stdlib
plus the shared ``copytrade_kernel`` clocks, no IO, no SQLite, no pydantic and
no Polars. Every financial value is an exact :class:`~decimal.Decimal`; every
clock is an integer UTC millisecond supplied by the caller.

Invariants encoded here (illegal states cannot be constructed):

* A :class:`SeatLease` is keyed by ``(account, seat, generation)`` and its
  :attr:`SeatLease.owner` digest matches the ``CopyMandate`` owner digest
  ``digest([account_id, mandate_id, generation])``, so a promoted successor can
  never collide with a draining predecessor in ``KernelState`` (Q16/Q21).
* :attr:`SeatLease.baseline_required` is always ``True``: a lease is promoted
  under ``new_pos_only`` (Q14=A) and never inherits another owner's positions.
* A :class:`SeatBook` keeps occupied seats and draining owners in separate
  tuples; an owner cannot be both, and no seat may be leased to an owner that
  is draining.
* :class:`RosterCUSUMState` latches ``CUSUM_KILL`` for the whole policy epoch
  and never self-clears on a later episode. Only
  :meth:`RosterCUSUMState.clear_for_epoch` with a *different* epoch resets it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

from copytrade_kernel import KnownAtTs

__all__ = [
    "AllocationMode",
    "BenchCandidate",
    "DrainingOwner",
    "GateFailure",
    "OperatorVeto",
    "ReconcilerPolicy",
    "RosterCUSUMState",
    "SeatBook",
    "SeatLease",
    "SeatSpec",
    "WalletScorecard",
    "canonical",
    "digest",
    "mandate_id",
    "owner_id",
    "wallet_address",
]

_ADDRESS_RE = re.compile(r"0x[0-9a-f]{40}")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}")
_DAY_MS = 86_400_000


def canonical(value: Any) -> bytes:
    """Order-independent JSON bytes; floats and non-string keys are refused."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("INVALID_DECIMAL")
    return format(value, "f")


def as_decimal(value: object, code: str = "INVALID_DECIMAL") -> Decimal:
    """Exact decimal from ``Decimal``/``str``/``int``; floats never enter state."""
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(code)
    else:
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(code) from exc
    if not parsed.is_finite():
        raise ValueError(code)
    return parsed


def _ms(value: object, code: str = "INVALID_CLOCK") -> int:
    if type(value) is not int or value < 0:
        raise ValueError(code)
    return value


def _sha(value: object, code: str = "INVALID_SHA256") -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ValueError(code)
    return value


def wallet_address(value: object) -> str:
    """Canonical lowercase 20-byte Hyperliquid/EVM address."""
    if not isinstance(value, str):
        raise ValueError("INVALID_WALLET_ADDRESS")
    normalised = value.strip().lower()
    if _ADDRESS_RE.fullmatch(normalised) is None:
        raise ValueError("INVALID_WALLET_ADDRESS")
    return normalised


def _identifier(value: object, code: str = "INVALID_IDENTIFIER") -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(code)
    return value


def owner_id(account_id: str, mandate: str, generation: int) -> str:
    """Owner digest shared with :class:`copytrade_pm.pm_mandate.SignedMandate`."""
    if type(generation) is not int or generation < 1:
        raise ValueError("INVALID_GENERATION")
    return digest([account_id, mandate, generation])


def mandate_id(account_id: str, seat_id: str, generation: int) -> str:
    """Deterministic mandate identity for one seat generation (Q18=A)."""
    if type(generation) is not int or generation < 1:
        raise ValueError("INVALID_GENERATION")
    return f"{_identifier(account_id)}:{_identifier(seat_id)}:g{generation}"


class AllocationMode(StrEnum):
    """Seat occupancy. ``FLAT`` (0 seats) is a first-class valid state."""

    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    FLAT = "FLAT"


class GateFailure(StrEnum):
    """Typed research/operations verdicts. Each gate is independent evidence."""

    ACCOUNT_VALUE_BELOW_FLOOR = "LOW_ACCOUNT_VALUE_LT_1K"
    NO_ACTIVE_FILLS = "NO_ACTIVE_FILLS"
    NEGATIVE_5M_MARKOUT = "NEGATIVE_5M_MARKOUT"
    MARKOUT_NOT_COPYABLE = "COPYABLE_DRIFT_UNPROVEN"
    PARTICIPATION_LIMIT = "P95_PARTICIPATION_ABOVE_LIMIT"
    MARGINAL_CDAR_LIMIT = "MARGINAL_CDAR_ABOVE_LIMIT"
    CUSUM_KILL = "CUSUM_KILL"
    OPERATOR_VETO = "OPERATOR_VETO"


ALL_GATES = frozenset(GateFailure)


def _failures(value: object) -> tuple[GateFailure, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, GateFailure)):
        raise ValueError("FAILURES_MUST_BE_SEQUENCE")
    try:
        items = tuple(GateFailure(item) for item in value)  # type: ignore[union-attr]
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_GATE") from exc
    if len(set(items)) != len(items):
        raise ValueError("DUPLICATE_GATE")
    return tuple(sorted(items, key=lambda gate: gate.value))


@dataclass(frozen=True, slots=True)
class SeatSpec:
    """One logical seat of an account. Occupancy is derived; this is the slot."""

    seat_id: str
    risk_unit_usd: Decimal
    max_cdar_share: Decimal

    def __post_init__(self) -> None:
        _identifier(self.seat_id, "INVALID_SEAT_ID")
        if as_decimal(self.risk_unit_usd) <= 0:
            raise ValueError("INVALID_RISK_UNIT")
        share = as_decimal(self.max_cdar_share)
        if not 0 < share <= 1:
            raise ValueError("INVALID_CDAR_SHARE")
        object.__setattr__(self, "risk_unit_usd", as_decimal(self.risk_unit_usd))
        object.__setattr__(self, "max_cdar_share", share)

    @property
    def data(self) -> dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "risk_unit_usd": decimal_text(self.risk_unit_usd),
            "max_cdar_share": decimal_text(self.max_cdar_share),
        }


@dataclass(frozen=True, slots=True)
class WalletScorecard:
    """Point-in-time wallet research verdict plus the evidence behind it.

    ``failures`` is the research layer's verdict, not a threshold recomputation:
    the roster never invents a gate from a number it does not own. Missing
    evidence is expressed by a *missing* scorecard, never by a zero.
    """

    wallet: str
    as_of: KnownAtTs
    account_value_usd: Decimal
    active_days_14d: int
    markout_5m_bps: Decimal
    p95_participation_1m: Decimal
    euler_cdar_share: Decimal
    suggested_k: Decimal
    cluster_id: str
    copyable_drift: bool
    failures: tuple[GateFailure, ...]
    source_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        if not isinstance(self.as_of, KnownAtTs):
            raise ValueError("INVALID_SCORECARD_CLOCK")
        for name in (
            "account_value_usd",
            "markout_5m_bps",
            "p95_participation_1m",
            "euler_cdar_share",
            "suggested_k",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name)))
        if self.account_value_usd < 0:
            raise ValueError("INVALID_ACCOUNT_VALUE")
        if type(self.active_days_14d) is not int or not 0 <= self.active_days_14d <= 14:
            raise ValueError("INVALID_ACTIVE_DAYS")
        if not 0 <= self.p95_participation_1m <= 1:
            raise ValueError("INVALID_PARTICIPATION")
        if not 0 <= self.euler_cdar_share <= 1:
            raise ValueError("INVALID_CDAR_SHARE")
        if not 0 < self.suggested_k <= 10:
            raise ValueError("INVALID_FIXED_K")
        _identifier(self.cluster_id, "INVALID_CLUSTER_ID")
        if type(self.copyable_drift) is not bool:
            raise ValueError("INVALID_COPYABLE_DRIFT")
        object.__setattr__(self, "failures", _failures(self.failures))
        _sha(self.source_sha)

    @property
    def data(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "as_of_ms": self.as_of.value,
            "account_value_usd": decimal_text(self.account_value_usd),
            "active_days_14d": self.active_days_14d,
            "markout_5m_bps": decimal_text(self.markout_5m_bps),
            "p95_participation_1m": decimal_text(self.p95_participation_1m),
            "euler_cdar_share": decimal_text(self.euler_cdar_share),
            "suggested_k": decimal_text(self.suggested_k),
            "cluster_id": self.cluster_id,
            "copyable_drift": self.copyable_drift,
            "failures": [gate.value for gate in self.failures],
            "source_sha": self.source_sha,
        }

    @property
    def sha(self) -> str:
        return digest(self.data)

    @property
    def eligible(self) -> bool:
        return not self.failures

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> WalletScorecard:
        from copytrade_kernel import KnownAtTs as _KnownAtTs

        return cls(
            wallet=value["wallet"],
            as_of=_KnownAtTs(int(value["as_of_ms"])),
            account_value_usd=value["account_value_usd"],
            active_days_14d=value["active_days_14d"],
            markout_5m_bps=value["markout_5m_bps"],
            p95_participation_1m=value["p95_participation_1m"],
            euler_cdar_share=value["euler_cdar_share"],
            suggested_k=value["suggested_k"],
            cluster_id=value["cluster_id"],
            copyable_drift=value["copyable_drift"],
            failures=tuple(GateFailure(item) for item in value["failures"]),
            source_sha=value["source_sha"],
        )

    def with_failure(self, gate: GateFailure) -> WalletScorecard:
        """Read-time merge of an independent verdict (Q12 latch, operator veto)."""
        if gate in self.failures:
            return self
        return replace_scorecard(self, failures=(*self.failures, gate))


def replace_scorecard(card: WalletScorecard, *, failures: Iterable[GateFailure]) -> WalletScorecard:
    return WalletScorecard(
        wallet=card.wallet,
        as_of=card.as_of,
        account_value_usd=card.account_value_usd,
        active_days_14d=card.active_days_14d,
        markout_5m_bps=card.markout_5m_bps,
        p95_participation_1m=card.p95_participation_1m,
        euler_cdar_share=card.euler_cdar_share,
        suggested_k=card.suggested_k,
        cluster_id=card.cluster_id,
        copyable_drift=card.copyable_drift,
        failures=tuple(failures),
        source_sha=card.source_sha,
    )


@dataclass(frozen=True, slots=True)
class BenchCandidate:
    """Portfolio-conditioned bench entry; separate from the static scorecard."""

    wallet: str
    scorecard_sha: str
    suggested_k: Decimal
    marginal_cdar_share: Decimal
    cluster_id: str
    cluster_distance: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        _sha(self.scorecard_sha)
        k = as_decimal(self.suggested_k)
        if not 0 < k <= 10:
            raise ValueError("INVALID_FIXED_K")
        object.__setattr__(self, "suggested_k", k)
        share = as_decimal(self.marginal_cdar_share)
        if not 0 <= share <= 1:
            raise ValueError("INVALID_CDAR_SHARE")
        object.__setattr__(self, "marginal_cdar_share", share)
        _identifier(self.cluster_id, "INVALID_CLUSTER_ID")
        distance = as_decimal(self.cluster_distance)
        if distance < 0:
            raise ValueError("INVALID_CLUSTER_DISTANCE")
        object.__setattr__(self, "cluster_distance", distance)

    @property
    def data(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "scorecard_sha": self.scorecard_sha,
            "suggested_k": decimal_text(self.suggested_k),
            "marginal_cdar_share": decimal_text(self.marginal_cdar_share),
            "cluster_id": self.cluster_id,
            "cluster_distance": decimal_text(self.cluster_distance),
        }

    @property
    def sha(self) -> str:
        return digest(self.data)

    @property
    def rank_key(self) -> tuple[Decimal, Decimal, str]:
        """Deterministic preference: lowest marginal CDaR, then highest k, then wallet."""
        return (-self.marginal_cdar_share, -self.suggested_k, self.wallet)

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> BenchCandidate:
        return cls(
            wallet=value["wallet"],
            scorecard_sha=value["scorecard_sha"],
            suggested_k=value["suggested_k"],
            marginal_cdar_share=value["marginal_cdar_share"],
            cluster_id=value["cluster_id"],
            cluster_distance=value["cluster_distance"],
        )


@dataclass(frozen=True, slots=True)
class SeatLease:
    """An occupied seat bound to exactly one owner generation."""

    account_id: str
    seat_id: str
    wallet: str
    generation: int
    k: Decimal
    since_ms: int
    scorecard_sha: str

    def __post_init__(self) -> None:
        _identifier(self.account_id, "INVALID_ACCOUNT_ID")
        _identifier(self.seat_id, "INVALID_SEAT_ID")
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("INVALID_GENERATION")
        k = as_decimal(self.k)
        if not 0 < k <= 10:
            raise ValueError("INVALID_FIXED_K")
        object.__setattr__(self, "k", k)
        _ms(self.since_ms)
        _sha(self.scorecard_sha)

    @property
    def mandate_id(self) -> str:
        return mandate_id(self.account_id, self.seat_id, self.generation)

    @property
    def owner(self) -> str:
        return owner_id(self.account_id, self.mandate_id, self.generation)

    @property
    def baseline_required(self) -> bool:
        """Q14=A: a promoted seat always mints a new baseline, never inherits."""
        return True

    @property
    def data(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "seat_id": self.seat_id,
            "wallet": self.wallet,
            "generation": self.generation,
            "mandate_id": self.mandate_id,
            "owner": self.owner,
            "k": decimal_text(self.k),
            "since_ms": self.since_ms,
            "scorecard_sha": self.scorecard_sha,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> SeatLease:
        return cls(
            account_id=value["account_id"],
            seat_id=value["seat_id"],
            wallet=value["wallet"],
            generation=value["generation"],
            k=value["k"],
            since_ms=value["since_ms"],
            scorecard_sha=value["scorecard_sha"],
        )


@dataclass(frozen=True, slots=True)
class DrainingOwner:
    """A retired owner whose open residuals are still managed by ``KernelState``."""

    owner: str
    wallet: str
    seat_id: str
    generation: int
    retired_ms: int
    reason: GateFailure

    def __post_init__(self) -> None:
        _sha(self.owner, "INVALID_OWNER")
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        _identifier(self.seat_id, "INVALID_SEAT_ID")
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("INVALID_GENERATION")
        _ms(self.retired_ms)
        if not isinstance(self.reason, GateFailure):
            raise ValueError("INVALID_EVICTION_REASON")

    @property
    def data(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "wallet": self.wallet,
            "seat_id": self.seat_id,
            "generation": self.generation,
            "retired_ms": self.retired_ms,
            "reason": self.reason.value,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> DrainingOwner:
        return cls(
            owner=value["owner"],
            wallet=value["wallet"],
            seat_id=value["seat_id"],
            generation=value["generation"],
            retired_ms=value["retired_ms"],
            reason=GateFailure(value["reason"]),
        )


@dataclass(frozen=True, slots=True)
class OperatorVeto:
    """Human containment (compromised key, Sybil, off-chain failure)."""

    wallet: str
    reason: str
    actor: str
    created_ms: int
    expires_ms: int | None = None
    revoked_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        if not isinstance(self.reason, str) or not 1 <= len(self.reason) <= 200:
            raise ValueError("INVALID_VETO_REASON")
        if not isinstance(self.actor, str) or not 1 <= len(self.actor) <= 100:
            raise ValueError("INVALID_VETO_ACTOR")
        _ms(self.created_ms)
        if self.expires_ms is not None:
            _ms(self.expires_ms)
            if self.expires_ms <= self.created_ms:
                raise ValueError("INVALID_VETO_WINDOW")
        if self.revoked_ms is not None:
            _ms(self.revoked_ms)
            if self.revoked_ms < self.created_ms:
                raise ValueError("INVALID_VETO_WINDOW")

    def active(self, as_of: KnownAtTs) -> bool:
        if not isinstance(as_of, KnownAtTs):
            raise ValueError("INVALID_CLOCK")
        if self.revoked_ms is not None and as_of.value >= self.revoked_ms:
            return False
        if as_of.value < self.created_ms:
            return False
        return self.expires_ms is None or as_of.value < self.expires_ms

    @property
    def data(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "reason": self.reason,
            "actor": self.actor,
            "created_ms": self.created_ms,
            "expires_ms": self.expires_ms,
            "revoked_ms": self.revoked_ms,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> OperatorVeto:
        return cls(
            wallet=value["wallet"],
            reason=value["reason"],
            actor=value["actor"],
            created_ms=value["created_ms"],
            expires_ms=value["expires_ms"],
            revoked_ms=value["revoked_ms"],
        )


@dataclass(frozen=True, slots=True)
class RosterCUSUMState:
    """One-sided CUSUM memory. ``retired_latch`` is terminal for the epoch."""

    wallet: str
    policy_epoch: str
    s_neg: Decimal
    episodes_seen: int
    retired_latch: bool
    retired_reason: GateFailure | None
    observed_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        _sha(self.policy_epoch, "INVALID_POLICY_EPOCH")
        value = as_decimal(self.s_neg)
        if value < 0:
            raise ValueError("INVALID_CUSUM_STATE")
        object.__setattr__(self, "s_neg", value)
        if type(self.episodes_seen) is not int or self.episodes_seen < 0:
            raise ValueError("INVALID_CUSUM_EPISODES")
        if type(self.retired_latch) is not bool:
            raise ValueError("INVALID_CUSUM_LATCH")
        if self.retired_latch != (self.retired_reason is not None):
            raise ValueError("INVALID_CUSUM_LATCH_REASON")
        _ms(self.observed_ms)

    @classmethod
    def initial(cls, wallet: str, policy_epoch: str, *, at_ms: int = 0) -> RosterCUSUMState:
        return cls(wallet, policy_epoch, Decimal("0"), 0, False, None, at_ms)

    def observe(self, increment: Decimal, *, threshold: Decimal, at_ms: int) -> RosterCUSUMState:
        """Add one CUSUM increment; latch permanently once ``threshold`` is crossed."""
        step = as_decimal(increment)
        if step < 0:
            raise ValueError("INVALID_CUSUM_INCREMENT")
        limit = as_decimal(threshold)
        if limit <= 0:
            raise ValueError("INVALID_CUSUM_THRESHOLD")
        _ms(at_ms)
        if self.retired_latch:
            # Terminal: later episodes never clear a latched kill.
            return self
        s_neg = max(Decimal("0"), self.s_neg + step)
        episodes = self.episodes_seen + (1 if step > 0 else 0)
        if s_neg >= limit:
            return RosterCUSUMState(
                self.wallet,
                self.policy_epoch,
                s_neg,
                episodes,
                True,
                GateFailure.CUSUM_KILL,
                at_ms,
            )
        return RosterCUSUMState(self.wallet, self.policy_epoch, s_neg, episodes, False, None, at_ms)

    def clear_for_epoch(self, policy_epoch: str, *, at_ms: int) -> RosterCUSUMState:
        """Reset only on an explicit *new* policy epoch (never on a new episode)."""
        _sha(policy_epoch, "INVALID_POLICY_EPOCH")
        if policy_epoch == self.policy_epoch:
            raise ValueError("CUSUM_LATCH_EPOCH_UNCHANGED")
        _ms(at_ms)
        return RosterCUSUMState.initial(self.wallet, policy_epoch, at_ms=at_ms)

    @property
    def latched(self) -> bool:
        return self.retired_latch

    @property
    def data(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "policy_epoch": self.policy_epoch,
            "s_neg": decimal_text(self.s_neg),
            "episodes_seen": self.episodes_seen,
            "retired_latch": self.retired_latch,
            "retired_reason": self.retired_reason.value if self.retired_reason else None,
            "observed_ms": self.observed_ms,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> RosterCUSUMState:
        reason = value["retired_reason"]
        latch = value["retired_latch"]
        if latch not in (0, 1, True, False):
            raise ValueError("INVALID_CUSUM_LATCH")
        return cls(
            wallet=value["wallet"],
            policy_epoch=value["policy_epoch"],
            s_neg=value["s_neg"],
            episodes_seen=value["episodes_seen"],
            retired_latch=bool(latch),
            retired_reason=GateFailure(reason) if reason is not None else None,
            observed_ms=value["observed_ms"],
        )


@dataclass(frozen=True, slots=True)
class CooldownRecord:
    """Non-edge eviction window: 14 continuous days from the last failing observation."""

    wallet: str
    evicted_ms: int
    last_failure_ms: int
    reason: GateFailure

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", wallet_address(self.wallet))
        _ms(self.evicted_ms)
        _ms(self.last_failure_ms)
        if self.last_failure_ms < self.evicted_ms:
            raise ValueError("INVALID_COOLDOWN_WINDOW")
        if not isinstance(self.reason, GateFailure):
            raise ValueError("INVALID_EVICTION_REASON")

    @property
    def continuous_since_ms(self) -> int:
        return max(self.evicted_ms, self.last_failure_ms)

    def ready(self, as_of: KnownAtTs, cooldown_ms: int) -> bool:
        _ms(cooldown_ms, "INVALID_COOLDOWN")
        return as_of.value - self.continuous_since_ms >= cooldown_ms

    @property
    def data(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "evicted_ms": self.evicted_ms,
            "last_failure_ms": self.last_failure_ms,
            "reason": self.reason.value,
        }

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> CooldownRecord:
        return cls(
            wallet=value["wallet"],
            evicted_ms=value["evicted_ms"],
            last_failure_ms=value["last_failure_ms"],
            reason=GateFailure(value["reason"]),
        )


DEFAULT_EVICT_ON = frozenset(
    {
        GateFailure.CUSUM_KILL,
        GateFailure.ACCOUNT_VALUE_BELOW_FLOOR,
        GateFailure.NEGATIVE_5M_MARKOUT,
        GateFailure.NO_ACTIVE_FILLS,
        GateFailure.OPERATOR_VETO,
    }
)

DEFAULT_ADMISSION_BLOCK = frozenset(
    {
        GateFailure.ACCOUNT_VALUE_BELOW_FLOOR,
        GateFailure.NO_ACTIVE_FILLS,
        GateFailure.NEGATIVE_5M_MARKOUT,
        GateFailure.MARKOUT_NOT_COPYABLE,
        GateFailure.PARTICIPATION_LIMIT,
        GateFailure.MARGINAL_CDAR_LIMIT,
        GateFailure.CUSUM_KILL,
        GateFailure.OPERATOR_VETO,
    }
)


@dataclass(frozen=True, slots=True)
class ReconcilerPolicy:
    """Sticky-incumbent reconciliation with an explicit, typed eviction policy."""

    evict_on: frozenset[GateFailure] = DEFAULT_EVICT_ON
    admission_block: frozenset[GateFailure] = DEFAULT_ADMISSION_BLOCK
    admission_min_account_value: Decimal = Decimal("1000")
    readmit_min_account_value: Decimal = Decimal("5000")
    cooldown_ms: int = 14 * _DAY_MS
    min_cluster_distance: Decimal = Decimal("0")
    cusum_threshold: Decimal = Decimal("3")
    sticky_incumbents: bool = True

    def __post_init__(self) -> None:
        for name in ("evict_on", "admission_block"):
            gates = getattr(self, name)
            if not isinstance(gates, frozenset) or not gates <= ALL_GATES:
                raise ValueError("INVALID_GATE_SET")
        floor = as_decimal(self.admission_min_account_value)
        readmit = as_decimal(self.readmit_min_account_value)
        if floor <= 0 or readmit < floor:
            raise ValueError("INVALID_ACCOUNT_VALUE_FLOOR")
        object.__setattr__(self, "admission_min_account_value", floor)
        object.__setattr__(self, "readmit_min_account_value", readmit)
        _ms(self.cooldown_ms, "INVALID_COOLDOWN")
        if self.cooldown_ms <= 0:
            raise ValueError("INVALID_COOLDOWN")
        distance = as_decimal(self.min_cluster_distance)
        if distance < 0:
            raise ValueError("INVALID_CLUSTER_DISTANCE")
        object.__setattr__(self, "min_cluster_distance", distance)
        threshold = as_decimal(self.cusum_threshold)
        if threshold <= 0:
            raise ValueError("INVALID_CUSUM_THRESHOLD")
        object.__setattr__(self, "cusum_threshold", threshold)
        if type(self.sticky_incumbents) is not bool:
            raise ValueError("INVALID_STICKINESS")
        if GateFailure.CUSUM_KILL not in self.evict_on:
            raise ValueError("CUSUM_KILL_MUST_EVICT")
        if GateFailure.OPERATOR_VETO not in self.evict_on:
            raise ValueError("OPERATOR_VETO_MUST_EVICT")

    @classmethod
    def sticky_pit_bench(cls) -> ReconcilerPolicy:
        return cls()

    @property
    def data(self) -> dict[str, Any]:
        return {
            "evict_on": sorted(gate.value for gate in self.evict_on),
            "admission_block": sorted(gate.value for gate in self.admission_block),
            "admission_min_account_value": decimal_text(self.admission_min_account_value),
            "readmit_min_account_value": decimal_text(self.readmit_min_account_value),
            "cooldown_ms": self.cooldown_ms,
            "min_cluster_distance": decimal_text(self.min_cluster_distance),
            "cusum_threshold": decimal_text(self.cusum_threshold),
            "sticky_incumbents": self.sticky_incumbents,
        }

    @property
    def sha(self) -> str:
        return digest(self.data)


@dataclass(frozen=True, slots=True)
class SeatBook:
    """Seat occupancy and draining owners for one account at one known-at clock."""

    account_id: str
    as_of: KnownAtTs
    policy_epoch: str
    seats: tuple[tuple[SeatSpec, SeatLease | None], ...]
    draining: tuple[DrainingOwner, ...] = ()
    sequence: int = 0

    def __post_init__(self) -> None:
        _identifier(self.account_id, "INVALID_ACCOUNT_ID")
        if not isinstance(self.as_of, KnownAtTs):
            raise ValueError("INVALID_BOOK_CLOCK")
        _sha(self.policy_epoch, "INVALID_POLICY_EPOCH")
        if not isinstance(self.seats, tuple):
            raise ValueError("INVALID_SEATS")
        if not isinstance(self.draining, tuple):
            raise ValueError("INVALID_DRAINING")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("INVALID_BOOK_SEQUENCE")
        self.validate()

    def validate(self) -> None:
        seat_ids: set[str] = set()
        leased_wallets: set[str] = set()
        owners: set[str] = set()
        for spec, lease in self.seats:
            if not isinstance(spec, SeatSpec):
                raise ValueError("INVALID_SEAT_SPEC")
            if spec.seat_id in seat_ids:
                raise ValueError("DUPLICATE_SEAT_ID")
            seat_ids.add(spec.seat_id)
            if lease is None:
                continue
            if not isinstance(lease, SeatLease):
                raise ValueError("INVALID_LEASE")
            if lease.seat_id != spec.seat_id or lease.account_id != self.account_id:
                raise ValueError("LEASE_SEAT_MISMATCH")
            if lease.wallet in leased_wallets:
                raise ValueError("DUPLICATE_LEASED_WALLET")
            leased_wallets.add(lease.wallet)
            if lease.owner in owners:
                raise ValueError("DUPLICATE_LEASE_OWNER")
            owners.add(lease.owner)
            if lease.since_ms > self.as_of.value:
                raise ValueError("LEASE_AFTER_BOOK_CLOCK")
        draining_owners: set[str] = set()
        for entry in self.draining:
            if not isinstance(entry, DrainingOwner):
                raise ValueError("INVALID_DRAINING_OWNER")
            if entry.owner in draining_owners:
                raise ValueError("DUPLICATE_DRAINING_OWNER")
            if entry.owner in owners:
                raise ValueError("OWNER_BOTH_LEASED_AND_DRAINING")
            draining_owners.add(entry.owner)
            if entry.seat_id not in seat_ids:
                raise ValueError("DRAINING_SEAT_UNKNOWN")
            if entry.retired_ms > self.as_of.value:
                raise ValueError("DRAINING_AFTER_BOOK_CLOCK")

    @classmethod
    def empty(
        cls,
        account_id: str,
        seats: Iterable[SeatSpec],
        *,
        as_of: KnownAtTs,
        policy_epoch: str,
    ) -> SeatBook:
        specs = tuple(seats)
        if not specs:
            raise ValueError("EMPTY_SEAT_SET")
        return cls(
            account_id=account_id,
            as_of=as_of,
            policy_epoch=policy_epoch,
            seats=tuple((spec, None) for spec in specs),
        )

    @property
    def specs(self) -> tuple[SeatSpec, ...]:
        return tuple(spec for spec, _ in self.seats)

    @property
    def leases(self) -> tuple[SeatLease, ...]:
        return tuple(lease for _, lease in self.seats if lease is not None)

    @property
    def occupied(self) -> int:
        return sum(1 for _, lease in self.seats if lease is not None)

    @property
    def mode(self) -> AllocationMode:
        occupied = self.occupied
        if occupied == 0:
            return AllocationMode.FLAT
        return AllocationMode.ACTIVE if occupied == len(self.seats) else AllocationMode.PARTIAL

    @property
    def wallets(self) -> tuple[str, ...]:
        return tuple(lease.wallet for lease in self.leases)

    @property
    def draining_owners(self) -> tuple[str, ...]:
        return tuple(entry.owner for entry in self.draining)

    @property
    def draining_wallets(self) -> tuple[str, ...]:
        return tuple(entry.wallet for entry in self.draining)

    def lease(self, seat_id: str) -> SeatLease | None:
        for spec, lease in self.seats:
            if spec.seat_id == seat_id:
                return lease
        raise KeyError(seat_id)

    def spec(self, seat_id: str) -> SeatSpec:
        for spec, _ in self.seats:
            if spec.seat_id == seat_id:
                return spec
        raise KeyError(seat_id)

    def next_generation(self, seat_id: str) -> int:
        """Monotonic per seat, independent of the source epoch (Q18=A)."""
        current = self.lease(seat_id)
        return 1 if current is None else current.generation + 1

    @property
    def data(self) -> dict[str, Any]:
        return {
            "schema": "roster_seat_book_v1",
            "account_id": self.account_id,
            "as_of_ms": self.as_of.value,
            "policy_epoch": self.policy_epoch,
            "sequence": self.sequence,
            "seats": [
                {"spec": spec.data, "lease": lease.data if lease else None}
                for spec, lease in self.seats
            ],
            "draining": [entry.data for entry in self.draining],
        }

    @property
    def sha(self) -> str:
        return digest(self.data)

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> SeatBook:
        from copytrade_kernel import KnownAtTs as _KnownAtTs

        return cls(
            account_id=value["account_id"],
            as_of=_KnownAtTs(int(value["as_of_ms"])),
            policy_epoch=value["policy_epoch"],
            seats=tuple(
                (
                    SeatSpec(
                        seat_id=row["spec"]["seat_id"],
                        risk_unit_usd=row["spec"]["risk_unit_usd"],
                        max_cdar_share=row["spec"]["max_cdar_share"],
                    ),
                    SeatLease.parse(row["lease"]) if row["lease"] else None,
                )
                for row in value["seats"]
            ),
            draining=tuple(DrainingOwner.parse(row) for row in value["draining"]),
            sequence=int(value["sequence"]),
        )

    def replace(
        self,
        *,
        seats: tuple[tuple[SeatSpec, SeatLease | None], ...] | None = None,
        draining: tuple[DrainingOwner, ...] | None = None,
        as_of: KnownAtTs | None = None,
        sequence: int | None = None,
    ) -> SeatBook:
        return SeatBook(
            account_id=self.account_id,
            as_of=as_of or self.as_of,
            policy_epoch=self.policy_epoch,
            seats=self.seats if seats is None else seats,
            draining=self.draining if draining is None else draining,
            sequence=self.sequence if sequence is None else sequence,
        )
