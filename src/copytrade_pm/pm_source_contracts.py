"""Strict prospective source contracts; existing journals retain all authority.

Raw evidence is never hashed from a Pydantic dump. These projections classify
economic equality, not source authenticity, follower admission or order permits.
Historical v1 parsers and journal canonicalization remain unchanged.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .pm03_account import digest


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NativeKey = Annotated[str, Field(pattern=r"^hyperliquid/mainnet:perp:[^/\s:]+/[^/\s:]+$")]


def exact_decimal(value: object) -> Decimal:
    """Explicit native adapter; bool, binary floats and non-finite values fail."""
    if type(value) not in (str, int, Decimal):
        raise ValueError("SOURCE_EXACT_DECIMAL_REQUIRED")
    if (
        type(value) is str
        and re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value)
        is None
    ):
        raise ValueError("SOURCE_DECIMAL_INVALID")
    if len(str(value)) > 128:
        raise ValueError("SOURCE_DECIMAL_BOUND_EXCEEDED")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("SOURCE_DECIMAL_INVALID") from exc
    if not result.is_finite():
        raise ValueError("SOURCE_DECIMAL_NONFINITE")
    if abs(result.as_tuple().exponent) > 128:
        raise ValueError("SOURCE_DECIMAL_BOUND_EXCEEDED")
    return result


def utc_clock(value: str) -> datetime:
    if type(value) is not str:
        raise ValueError("SOURCE_UTC_CLOCK_REQUIRED")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("SOURCE_UTC_CLOCK_INVALID") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("SOURCE_UTC_CLOCK_REQUIRED")
    return result.astimezone(UTC)


def quantity_text(value: Decimal) -> str:
    """Canonical decimal text without normalize(), rounding or float conversion."""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


NativeDecimal = Annotated[Decimal, BeforeValidator(exact_decimal)]
FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


class SourceEvidenceRef(Contract):
    schema_version: Literal[2] = 2
    source_id: Annotated[str, Field(min_length=1, max_length=70)]
    raw_sha: Sha
    native_frame_sha: Sha
    first_known_at: datetime
    source_event_at: datetime

    @model_validator(mode="after")
    def causal(self):
        for at in (self.first_known_at, self.source_event_at):
            if at.tzinfo is None or at.utcoffset() != timedelta(0):
                raise ValueError("SOURCE_UTC_CLOCK_REQUIRED")
        if self.source_event_at > self.first_known_at:
            raise ValueError("SOURCE_CLOCK_IN_FUTURE")
        return self


class SelectedPerpScope(Contract):
    schema_version: Literal[2] = 2
    account_sha: Sha
    dexes: tuple[str, ...]
    generation: Sha
    namespace: Literal["hyperliquid/mainnet:perp"] = "hyperliquid/mainnet:perp"
    selected_perp_complete: Literal[True] = True
    whole_wallet_finance: Literal["UNAVAILABLE"] = "UNAVAILABLE"

    @model_validator(mode="after")
    def census(self):
        if (
            not self.dexes
            or "default" not in self.dexes
            or tuple(sorted(set(self.dexes))) != self.dexes
        ):
            raise ValueError("SOURCE_CANONICAL_SCOPE_INVALID")
        if any(not d or any(c in d for c in "/: ") for d in self.dexes):
            raise ValueError("SOURCE_CANONICAL_SCOPE_INVALID")
        return self


class Position(Contract):
    instrument: NativeKey
    quantity: FiniteDecimal


class DexClock(Contract):
    dex: str
    milliseconds: Annotated[int, Field(gt=0)]


class CanonicalPositionBook(Contract):
    schema_version: Literal[2] = 2
    evidence: SourceEvidenceRef
    scope: SelectedPerpScope
    positions: tuple[Position, ...]
    clocks: tuple[DexClock, ...]

    @model_validator(mode="after")
    def complete(self):
        keys = [p.instrument for p in self.positions]
        if keys != sorted(set(keys)) or any(p.quantity == 0 for p in self.positions):
            raise ValueError("SOURCE_CANONICAL_POSITION_DUPLICATE_OR_ZERO")
        if tuple(c.dex for c in self.clocks) != self.scope.dexes:
            raise ValueError("SOURCE_CANONICAL_CLOCK_SCOPE_MISMATCH")
        if any(
            p.instrument.split("/")[1].split(":")[-1] not in self.scope.dexes
            for p in self.positions
        ):
            raise ValueError("SOURCE_CANONICAL_POSITION_SCOPE_MISMATCH")
        latest = max(c.milliseconds for c in self.clocks)
        oldest = min(c.milliseconds for c in self.clocks)
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        if epoch + timedelta(milliseconds=latest) != self.evidence.source_event_at:
            raise ValueError("SOURCE_CANONICAL_CLOCK_MISMATCH")
        if (
            self.evidence.first_known_at - epoch - timedelta(milliseconds=oldest)
        ).total_seconds() > 120:
            raise ValueError("SOURCE_NATIVE_CLOCK_STALE")
        return self

    @property
    def vector(self) -> dict[str, Decimal]:
        return {p.instrument: p.quantity for p in self.positions}

    @property
    def economic_sha(self) -> str:
        return digest(
            [
                self.scope.generation,
                {p.instrument: quantity_text(p.quantity) for p in self.positions},
            ]
        )


class PositionObservation(Contract):
    schema_version: Literal[2] = 2
    status: Literal["VALID"] = "VALID"
    kind: Literal["BASELINE", "UNCHANGED_STATE", "OBSERVED_STATE_CHANGE", "DUPLICATE"]
    evidence: SourceEvidenceRef
    scope_generation: Sha
    economic_sha: Sha
    changed_instruments: tuple[str, ...]
    financial_admission: Literal["NOT_GRANTED"] = "NOT_GRANTED"


class SourceTransitionDecision(Contract):
    observation: PositionObservation
    next_book: CanonicalPositionBook
    journal_kind: Literal["BASELINE", "UNCHANGED", "OBSERVATION", "NONE"]


class UnavailableObservation(Contract):
    status: Literal[
        "INVALID", "INCOMPLETE", "STALE", "UNSUPPORTED_VERSION", "TEMPORARILY_UNAVAILABLE"
    ]
    reason: str
    financial_admission: Literal["NOT_GRANTED"] = "NOT_GRANTED"


# Native fields are explicitly inventoried from official docs and authentic S0
# frames. Known optional diagnostics stay opaque and cannot change positions or
# confer NAV completeness; unknown fields at a replacement boundary fail closed.
class _Margin(Contract):
    accountValue: NativeDecimal
    totalNtlPos: NativeDecimal
    totalMarginUsed: NativeDecimal
    totalRawUsd: NativeDecimal | None = None


class _NativePosition(Contract):
    coin: Annotated[str, Field(min_length=1)]
    szi: NativeDecimal
    leverage: Any = None
    marginUsed: Any = None
    entryPx: Any = None
    liquidationPx: Any = None
    maxLeverage: Any = None
    positionValue: Any = None
    returnOnEquity: Any = None
    unrealizedPnl: Any = None
    cumFunding: Any = None


class _NativeRow(Contract):
    position: _NativePosition
    type: Literal["oneWay"] | None = None


class _NativeState(Contract):
    marginSummary: _Margin
    assetPositions: list[_NativeRow]
    time: Annotated[int, Field(gt=0)]
    crossMarginSummary: Any = None
    crossMaintenanceMarginUsed: Any = None
    withdrawable: Any = None


def canonical_source_book(
    *, frame: dict, receipt: dict, raw_sha: str, scope_generation: str
) -> CanonicalPositionBook:
    """Validate critical wire semantics, then derive an immutable projection.

    The existing native parser must first establish selected account/DEX parity,
    instrument identity and required margin fields. Never serialize this return
    value into an original receipt or use its economic SHA as an event identity.
    """
    for _, state in frame["data"]["clearinghouseStates"]:
        _NativeState.model_validate(state)
    book = receipt["source_book"]
    evidence = SourceEvidenceRef(
        source_id=receipt["source_id"],
        raw_sha=raw_sha,
        native_frame_sha=receipt["source_sha"],
        first_known_at=utc_clock(receipt["first_known_at"]),
        source_event_at=utc_clock(receipt["source_event_at"]),
    )
    rows = sorted(book["per_dex_margin_diagnostics"], key=lambda row: row["dex"])
    scope = SelectedPerpScope(
        account_sha=book["account_id"],
        dexes=tuple(row["dex"] for row in rows),
        generation=scope_generation,
    )
    return CanonicalPositionBook(
        evidence=evidence,
        scope=scope,
        positions=tuple(
            Position(instrument=k, quantity=exact_decimal(v))
            for k, v in sorted(book["positions"].items())
        ),
        clocks=tuple(DexClock(dex=row["dex"], milliseconds=row["state_at"]) for row in rows),
    )


def decide_source_transition(
    book: CanonicalPositionBook, *, previous: dict, snapshot: bool, frame_semantic_sha: str
) -> SourceTransitionDecision:
    """Pure transition owner; no clocks, IO, journal mutation or finance."""
    clocks = {c.dex: c.milliseconds for c in book.clocks}
    prior_clocks = previous.get("dex_clocks", {})
    if any(value < prior_clocks.get(dex, 0) for dex, value in clocks.items()):
        raise ValueError("SOURCE_NATIVE_CLOCK_REGRESSION")
    baseline = not previous.get("baseline_valid", False) or snapshot
    before = {k: exact_decimal(v) for k, v in previous.get("positions", {}).items()}
    current = book.vector
    changed = (
        ()
        if baseline
        else tuple(
            k
            for k in sorted(before.keys() | current.keys())
            if before.get(k, Decimal(0)) != current.get(k, Decimal(0))
        )
    )
    if changed and clocks == prior_clocks:
        raise ValueError("SOURCE_SAME_CLOCK_CONFLICTING_POSITIONS")
    if baseline:
        kind, journal = "BASELINE", "BASELINE"
    elif frame_semantic_sha == previous.get("semantic_sha"):
        kind, journal = "DUPLICATE", "NONE"
    elif changed:
        kind, journal = "OBSERVED_STATE_CHANGE", "OBSERVATION"
    else:
        kind, journal = "UNCHANGED_STATE", "UNCHANGED"
    return SourceTransitionDecision(
        observation=PositionObservation(
            kind=kind,
            evidence=book.evidence,
            scope_generation=book.scope.generation,
            economic_sha=book.economic_sha,
            changed_instruments=changed,
        ),
        next_book=book,
        journal_kind=journal,
    )
