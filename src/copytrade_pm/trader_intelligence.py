"""Deterministic, read-only Trader Intelligence: observations -> research grades.

This module deliberately owns neither brokerage transport nor account-risk allocation.
Historical vendor time is a *proxy cut*, never a first-known local receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any, Literal

SCHEMA = "trader_intelligence_v1"
HEX64 = re.compile(r"^[a-f0-9]{64}$")
INSTRUMENT = re.compile(r"^hyperliquid/mainnet:perp:(?:default|[a-z][a-z0-9_-]*)/[A-Za-z0-9_.-]+$")
GRADES = {"A": "1", "B": "0.5", "C": "0", "X": "0"}
ORIGINS = {"HISTORICAL_PROXY", "PROSPECTIVE_OBSERVED", "PROSPECTIVE_VALIDATED"}
STYLES = {"DIRECTIONAL", "FUNDING_CARRY", "MARKET_NEUTRAL", "HEDGED_BASKET", "UNKNOWN"}


def canonical(obj: Any) -> bytes:
    """Stable cross-repository wire bytes: sorted keys, UTF-8, no NaN or whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(obj: Any) -> str:
    return sha256(canonical(obj)).hexdigest()


def utc(value: str | datetime) -> datetime:
    try:
        t = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("INVALID_CLOCK") from exc
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("NAIVE_CLOCK")
    return t.astimezone(UTC)


def norm_clock(value: str | datetime) -> str:
    return utc(value).isoformat().replace("+00:00", "Z")


def decimal(value: str | int | float | Decimal) -> Decimal:
    try:
        v = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("INVALID_DECIMAL") from exc
    if not v.is_finite():
        raise ValueError("NONFINITE_DECIMAL")
    return v


def _sha(value: str) -> None:
    if not HEX64.fullmatch(value):
        raise ValueError("INVALID_PROVENANCE_SHA")


def _instrument(value: str) -> None:
    if not INSTRUMENT.fullmatch(value):
        raise ValueError("UNKNOWN_MARKET_NAMESPACE")


@dataclass(frozen=True)
class WalletIdentity:
    """Alias plus known parent/independent cluster; never an assumed wallet vote."""

    alias: str
    identity_sha256: str
    cluster: str | None = None
    parent: str | None = None

    def __post_init__(self) -> None:
        if not self.alias or len(self.alias) > 100 or not self.alias.isascii():
            raise ValueError("INVALID_WALLET_ALIAS")
        _sha(self.identity_sha256)
        if self.cluster is not None and not self.cluster.strip():
            raise ValueError("EMPTY_INDEPENDENCE_CLUSTER")
        if self.parent is not None and not self.parent.strip():
            raise ValueError("INVALID_PARENT")


@dataclass(frozen=True)
class WalletEvent:
    """A position transition with explicit clocks and evidence quality.

    Decimal quantities are strings to avoid binary floating point nondeterminism.
    A historical event cannot claim a prospective first receipt.
    """

    event_id: str
    wallet: str
    instrument: str
    event_at: str
    origin: Literal["HISTORICAL_PROXY", "PROSPECTIVE_OBSERVED", "PROSPECTIVE_VALIDATED"]
    position_before: str | None
    position_after: str | None
    first_known_at: str | None = None
    book_complete: bool | None = None
    source_equity_usd: str | None = None
    strategy_style: str = "UNKNOWN"
    book_id: str | None = None
    observed_price: str | None = None
    source_sha256: str | None = None
    verified_position_transition: bool = True

    def __post_init__(self) -> None:
        if not self.event_id or len(self.event_id) > 200 or not self.wallet:
            raise ValueError("INVALID_EVENT_IDENTITY")
        _instrument(self.instrument)
        event = utc(self.event_at)
        if self.origin not in ORIGINS:
            raise ValueError("UNKNOWN_OBSERVATION_ORIGIN")
        if self.origin == "HISTORICAL_PROXY":
            if self.first_known_at is not None:
                raise ValueError("VENDOR_TIME_CANNOT_BE_FIRST_KNOWN")
        elif self.first_known_at is None or utc(self.first_known_at) < event:
            raise ValueError("INVALID_FIRST_KNOWN_CLOCK")
        if self.strategy_style not in STYLES:
            raise ValueError("UNKNOWN_STRATEGY_STYLE")
        if self.position_before is not None:
            decimal(self.position_before)
        if self.position_after is not None:
            decimal(self.position_after)
        if self.source_equity_usd is not None and decimal(self.source_equity_usd) <= 0:
            raise ValueError("NONPOSITIVE_SOURCE_EQUITY")
        if self.observed_price is not None and decimal(self.observed_price) <= 0:
            raise ValueError("NONPOSITIVE_SOURCE_PRICE")
        if self.source_sha256 is not None:
            _sha(self.source_sha256)

    @property
    def known_at(self) -> datetime:
        # Historical is explicitly an event-time *research proxy*, never local receipt.
        return utc(self.first_known_at or self.event_at)

    @property
    def transition(self) -> str:
        if not self.verified_position_transition:
            return "UNKNOWN"
        if self.position_before is None or self.position_after is None:
            return "UNKNOWN"
        old, new = decimal(self.position_before), decimal(self.position_after)
        if old == new:
            return "UNCHANGED"
        if old == 0:
            return "OPEN"
        if new == 0:
            return "EXIT"
        if (old > 0) != (new > 0):
            return "REVERSE"
        return "ADD" if abs(new) > abs(old) else "REDUCE"

    @property
    def direction(self) -> str | None:
        if self.transition not in ("OPEN", "ADD", "REVERSE"):
            return None
        if self.position_after is None:
            return None
        return "LONG" if decimal(self.position_after) > 0 else "SHORT"


@dataclass(frozen=True)
class ObservationSnapshot:
    """Roster was known at the decision, not selected retrospectively after it."""

    roster_id: str
    roster_known_at: str
    wallets: tuple[WalletIdentity, ...]
    events: tuple[WalletEvent, ...]
    roster_origin: str
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ValueError("INCOMPATIBLE_OBSERVATION_SCHEMA")
        utc(self.roster_known_at)
        if not self.roster_id or not self.wallets:
            raise ValueError("EMPTY_MONITORED_ROSTER")
        if self.roster_origin not in ("HISTORICAL_PROXY", "PROSPECTIVE_OBSERVED"):
            raise ValueError("INVALID_ROSTER_PROVENANCE")
        aliases = [w.alias for w in self.wallets]
        if len(aliases) != len(set(aliases)):
            raise ValueError("DUPLICATE_ROSTER_ALIAS")
        identities = [w.identity_sha256 for w in self.wallets]
        if len(identities) != len(set(identities)):
            raise ValueError("DUPLICATE_WALLET_IDENTITY")
        if any(e.wallet not in set(aliases) for e in self.events):
            raise ValueError("UNREGISTERED_WALLET_OBSERVATION")
        seen: dict[str, WalletEvent] = {}
        for e in self.events:
            if e.event_id in seen and seen[e.event_id] != e:
                raise ValueError("CONTRADICTORY_EVENT_REVISION")
            seen[e.event_id] = e

    def as_wire(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "roster_id": self.roster_id,
            "roster_known_at": norm_clock(self.roster_known_at),
            "roster_origin": self.roster_origin,
            "wallets": [vars_identity(w) for w in sorted(self.wallets, key=lambda x: x.alias)],
            "events": [
                vars_event(e)
                for e in sorted(
                    {e.event_id: e for e in self.events}.values(),
                    key=lambda x: (x.known_at, x.event_id),
                )
            ],
        }

    @property
    def sha256(self) -> str:
        return digest(self.as_wire())


def vars_identity(w: WalletIdentity) -> dict:
    return {
        "alias": w.alias,
        "identity_sha256": w.identity_sha256,
        "cluster": w.cluster,
        "parent": w.parent,
    }


def vars_event(e: WalletEvent) -> dict:
    return {
        "event_id": e.event_id,
        "wallet": e.wallet,
        "instrument": e.instrument,
        "event_at": norm_clock(e.event_at),
        "origin": e.origin,
        "position_before": None if e.position_before is None else str(decimal(e.position_before)),
        "position_after": None if e.position_after is None else str(decimal(e.position_after)),
        "first_known_at": (norm_clock(e.first_known_at) if e.first_known_at is not None else None),
        "book_complete": e.book_complete,
        "source_equity_usd": e.source_equity_usd,
        "strategy_style": e.strategy_style,
        "book_id": e.book_id,
        "observed_price": e.observed_price,
        "source_sha256": e.source_sha256,
        "verified_position_transition": e.verified_position_transition,
    }


@dataclass(frozen=True)
class Calibration:
    """Exogenously frozen calibration; never inferred from a test/holdout cut.

    A/B require independently recorded calibrated follower economic lower bounds.
    Empty calibration is the safe default.
    """

    model_sha256: str
    policy_sha256: str
    calibrated_at: str
    training_end_at: str
    evidence_origin: str
    a_lower_bound_r: str | None = None
    b_lower_bound_r: str | None = None
    evidence_sha256: str | None = None
    prospectively_validated: bool = False

    def __post_init__(self) -> None:
        _sha(self.model_sha256)
        _sha(self.policy_sha256)
        if self.evidence_sha256 is not None:
            _sha(self.evidence_sha256)
        if utc(self.training_end_at) > utc(self.calibrated_at):
            raise ValueError("FUTURE_TRAINING_CALIBRATION")
        if self.evidence_origin not in ORIGINS:
            raise ValueError("INVALID_CALIBRATION_ORIGIN")
        if self.prospectively_validated and self.evidence_origin != "PROSPECTIVE_VALIDATED":
            raise ValueError("INVALID_PROSPECTIVE_CLAIM")
        if (self.a_lower_bound_r is None) != (self.b_lower_bound_r is None):
            raise ValueError("PARTIAL_CALIBRATION")
        if self.a_lower_bound_r is not None:
            if not self.evidence_sha256:
                raise ValueError("MISSING_CALIBRATION_EVIDENCE")
            if decimal(self.a_lower_bound_r) < decimal(self.b_lower_bound_r):
                raise ValueError("NONMONOTONIC_GRADE_THRESHOLD")
            if decimal(self.b_lower_bound_r) <= 0:
                raise ValueError("CALIBRATION_NOT_POSITIVE")


@dataclass(frozen=True)
class OpportunityAssessment:
    candidate_id: str
    instrument: str
    direction: str
    decision_at: str
    input_sha256: str
    model_sha256: str
    policy_sha256: str
    grade: str
    evidence_status: str
    claim_status: str
    reasons: tuple[str, ...]
    research_r: str
    independent_clusters: int | None
    qualified_contributors: int | None
    first_known_at: str | None
    latest_source_event_at: str | None
    follower_net_r: str | None = None
    follower_lcb_r: str | None = None
    schema: str = SCHEMA
    research_only: bool = True
    order_authorized: bool = False

    def as_wire(self) -> dict[str, Any]:
        _instrument(self.instrument)
        if self.direction not in ("LONG", "SHORT") or self.grade not in GRADES:
            raise ValueError("INVALID_ASSESSMENT")
        if self.research_r != GRADES[self.grade]:
            raise ValueError("R_GRADE_MISMATCH")
        if not self.research_only or self.order_authorized:
            raise ValueError("GRADES_NEVER_AUTHORIZE_ORDERS")
        if self.schema != SCHEMA:
            raise ValueError("INCOMPATIBLE_ASSESSMENT_SCHEMA")
        if self.claim_status not in ("PROVISIONAL", "VALIDATED", "NOT_QUALIFIED"):
            raise ValueError("INVALID_EVIDENCE_CLAIM")
        if self.evidence_status not in ORIGINS and self.evidence_status != "INSUFFICIENT":
            raise ValueError("INVALID_EVIDENCE_STATUS")
        if self.grade in ("A", "B") and (
            self.follower_lcb_r is None or self.claim_status == "NOT_QUALIFIED"
        ):
            raise ValueError("UNSUPPORTED_POSITIVE_GRADE")
        if self.claim_status == "VALIDATED" and self.evidence_status != "PROSPECTIVE_VALIDATED":
            raise ValueError("INVALID_PROSPECTIVE_VALIDATION_CLAIM")
        for sha in (self.input_sha256, self.model_sha256, self.policy_sha256):
            _sha(sha)
        if self.first_known_at is not None and utc(self.first_known_at) > utc(self.decision_at):
            raise ValueError("FUTURE_ASSESSMENT_RECEIPT")
        # Preserve nullable uncertainties and count unknowns.
        if self.independent_clusters is not None and self.independent_clusters < 0:
            raise ValueError("NEGATIVE_CLUSTER_COUNT")
        if self.qualified_contributors is not None and self.qualified_contributors < 0:
            raise ValueError("NEGATIVE_CONTRIBUTOR_COUNT")
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "instrument": self.instrument,
            "direction": self.direction,
            "decision_at": norm_clock(self.decision_at),
            "input_sha256": self.input_sha256,
            "model_sha256": self.model_sha256,
            "policy_sha256": self.policy_sha256,
            "grade": self.grade,
            "evidence_status": self.evidence_status,
            "claim_status": self.claim_status,
            "reasons": list(self.reasons),
            "research_r": self.research_r,
            "independent_clusters": self.independent_clusters,
            "qualified_contributors": self.qualified_contributors,
            "first_known_at": (
                norm_clock(self.first_known_at) if self.first_known_at is not None else None
            ),
            "latest_source_event_at": (
                norm_clock(self.latest_source_event_at)
                if self.latest_source_event_at is not None
                else None
            ),
            "follower_net_r": self.follower_net_r,
            "follower_lcb_r": self.follower_lcb_r,
            "research_only": self.research_only,
            "order_authorized": self.order_authorized,
        }

    @property
    def sha256(self) -> str:
        return digest(self.as_wire())


@dataclass(frozen=True)
class TraderIntelligence:
    """Pure policy, no imported risk/ledger/broker or network libraries."""

    calibration: Calibration | None = None
    max_age_seconds: int = 3600
    model_sha256: str = field(default_factory=lambda: sha256(b"unfitted-ti-v1").hexdigest())
    policy_sha256: str = field(default_factory=lambda: sha256(b"research-only-ti-v1").hexdigest())

    def evaluate(
        self,
        snapshot: ObservationSnapshot,
        decision_at: str,
        *,
        follower_evidence: dict[tuple[str, str], tuple[str, str]] | None = None,
    ) -> tuple[OpportunityAssessment, ...]:
        """Get one assessment per candidate on known-at, fresh OPEN/ADD/REVERSE cuts.

        follower_evidence is an optional as-of, separately computed (net R, LCB R)
        mapping. Caller must supply mature causal evidence, not outcome leaks.
        An uncalibrated engine *cannot* assign A/B.
        """
        cut = utc(decision_at)
        if utc(snapshot.roster_known_at) > cut:
            raise ValueError("FUTURE_ROSTER")
        if self.max_age_seconds <= 0:
            raise ValueError("INVALID_FRESHNESS_POLICY")
        if self.calibration is not None:
            if utc(self.calibration.calibrated_at) > cut:
                raise ValueError("FUTURE_CALIBRATION")
            if self.model_sha256 != self.calibration.model_sha256:
                raise ValueError("MODEL_CALIBRATION_MISMATCH")
            if self.policy_sha256 != self.calibration.policy_sha256:
                raise ValueError("POLICY_CALIBRATION_MISMATCH")

        roster = {w.alias: w for w in snapshot.wallets}
        unique = {e.event_id: e for e in snapshot.events}
        asof = sorted(
            (e for e in unique.values() if e.known_at <= cut and utc(e.event_at) <= cut),
            key=lambda e: (e.known_at, utc(e.event_at), e.event_id),
        )
        # Only events knowable by this cut participate in the input identity.
        # Append-only future observations must not alter older decision hashes.
        asof_sha256 = ObservationSnapshot(
            roster_id=snapshot.roster_id,
            roster_known_at=snapshot.roster_known_at,
            wallets=snapshot.wallets,
            events=tuple(asof),
            roster_origin=snapshot.roster_origin,
        ).sha256
        latest: dict[tuple[str, str], WalletEvent] = {}
        for e in asof:
            key = (e.wallet, e.instrument)
            old = latest.get(key)
            if old is not None and e.position_before is not None and old.position_after is not None:
                # Only compare a new transition when chronology establishes a continuous chain.
                if e.known_at >= old.known_at and decimal(e.position_before) != decimal(
                    old.position_after
                ):
                    # A gap cannot be silently used as an independent entry.
                    latest[key] = WalletEvent(
                        event_id=e.event_id,
                        wallet=e.wallet,
                        instrument=e.instrument,
                        event_at=e.event_at,
                        origin=e.origin,
                        first_known_at=e.first_known_at,
                        position_before=None,
                        position_after=e.position_after,
                        book_complete=e.book_complete,
                        source_equity_usd=e.source_equity_usd,
                        strategy_style=e.strategy_style,
                        book_id=e.book_id,
                        observed_price=e.observed_price,
                        source_sha256=e.source_sha256,
                        verified_position_transition=False,
                    )
                    continue
            latest[key] = e

        groups: dict[tuple[str, str], list[WalletEvent]] = {}
        # Both known source positions and latest position transitions inform book-style.
        all_positions: dict[str, list[WalletEvent]] = {}
        for e in latest.values():
            all_positions.setdefault(e.wallet, []).append(e)
            if e.direction is None or cut - e.known_at > timedelta(seconds=self.max_age_seconds):
                continue
            groups.setdefault((e.instrument, e.direction), []).append(e)

        result: list[OpportunityAssessment] = []
        for (instrument, direction), events in sorted(groups.items()):
            reasons: set[str] = set()
            statuses = {e.origin for e in events}
            # Mixed origin cannot masquerade as prospectively validated.
            origin = (
                "HISTORICAL_PROXY"
                if "HISTORICAL_PROXY" in statuses
                else "PROSPECTIVE_OBSERVED"
                if "PROSPECTIVE_OBSERVED" in statuses
                else "PROSPECTIVE_VALIDATED"
            )
            if snapshot.roster_origin == "HISTORICAL_PROXY":
                origin = "HISTORICAL_PROXY"
            valid: list[WalletEvent] = []
            for e in events:
                if e.book_complete is not True:
                    reasons.add("INCOMPLETE_OR_UNKNOWN_SOURCE_BOOK")
                    continue
                if e.strategy_style in ("FUNDING_CARRY", "MARKET_NEUTRAL", "HEDGED_BASKET"):
                    reasons.add(e.strategy_style)
                    continue
                if e.strategy_style != "DIRECTIONAL":
                    reasons.add("UNCLASSIFIED_TRADER_STRATEGY")
                    continue
                if e.source_equity_usd is None:
                    reasons.add("SOURCE_EQUITY_UNKNOWN")
                    continue
                if e.transition == "UNKNOWN":
                    reasons.add("UNVERIFIED_POSITION_CHAIN")
                    continue
                book = all_positions[e.wallet]
                # Conservative book-aware veto; do not strip the counter-leg and claim naked alpha.
                signs = {
                    1 if decimal(p.position_after) > 0 else -1
                    for p in book
                    if p.position_after is not None and decimal(p.position_after) != 0
                }
                if len(signs) > 1:
                    reasons.add("HEDGED_OR_MULTI_LEG_BOOK")
                    continue
                valid.append(e)
            cluster_ids = [
                roster[e.wallet].cluster
                or (f"parent:{roster[e.wallet].parent}" if roster[e.wallet].parent else None)
                for e in valid
            ]
            independence_unverified = any(cluster is None for cluster in cluster_ids)
            independent = {cluster for cluster in cluster_ids if cluster is not None}
            if independence_unverified:
                reasons.add("INDEPENDENCE_UNVERIFIED")
            if len(independent) < len([c for c in cluster_ids if c is not None]):
                reasons.add("DEPENDENT_SOURCE_WALLETS")
            if not valid:
                grade = (
                    "X"
                    if reasons.intersection(
                        {
                            "FUNDING_CARRY",
                            "MARKET_NEUTRAL",
                            "HEDGED_BASKET",
                            "HEDGED_OR_MULTI_LEG_BOOK",
                        }
                    )
                    else "C"
                )
                reasons.add("NO_ELIGIBLE_DIRECTIONAL_CONTRIBUTOR")
            else:
                grade = "C"
            economics = (follower_evidence or {}).get((instrument, direction))
            if economics is not None:
                decimal(economics[0])
                decimal(economics[1])
                # Never infer outcome-known time from an estimate: this is read-only input.
                if self.calibration is None or self.calibration.a_lower_bound_r is None:
                    reasons.add("UNCALIBRATED_FOLLOWER_ECONOMICS")
                else:
                    # Calibration metadata and caller-supplied floats are not
                    # evidence that the candidate's outcome was independently
                    # observed, matured and bound to this decision cut.
                    # Until signed outcome verification exists, C/X only.
                    reasons.add("UNATTESTED_FOLLOWER_ESTIMATE_NO_A_B")
            else:
                reasons.add("FOLLOWER_ECONOMICS_UNAVAILABLE")
            if not valid:
                reasons.add("WATCH_NOT_ACTIONABLE")
            if independence_unverified or not independent:
                reasons.add("INDEPENDENT_CLUSTER_COUNT_UNKNOWN")
            if grade in ("A", "B"):
                claim = (
                    "VALIDATED"
                    if (
                        origin == "PROSPECTIVE_VALIDATED"
                        and self.calibration is not None
                        and self.calibration.prospectively_validated
                    )
                    else "PROVISIONAL"
                )
            else:
                claim = "NOT_QUALIFIED"
            if origin == "HISTORICAL_PROXY":
                reasons.add("RETROSPECTIVE_SOURCE_TIME_PROXY")
            candidate_id = digest(
                {
                    "schema": SCHEMA,
                    "instrument": instrument,
                    "direction": direction,
                    "decision_at": norm_clock(decision_at),
                    "snapshot_sha256": asof_sha256,
                    "model_sha256": self.model_sha256,
                    "policy_sha256": self.policy_sha256,
                }
            )
            first_known = (
                norm_clock(
                    max(
                        (e.first_known_at for e in events if e.first_known_at is not None),
                        key=utc,
                    )
                )
                if origin != "HISTORICAL_PROXY"
                else None
            )
            result.append(
                OpportunityAssessment(
                    candidate_id=candidate_id,
                    instrument=instrument,
                    direction=direction,
                    decision_at=decision_at,
                    input_sha256=asof_sha256,
                    model_sha256=self.model_sha256,
                    policy_sha256=self.policy_sha256,
                    grade=grade,
                    research_r=GRADES[grade],
                    evidence_status=origin,
                    claim_status=claim,
                    reasons=tuple(sorted(reasons)),
                    independent_clusters=(
                        len(independent) if independent and not independence_unverified else None
                    ),
                    qualified_contributors=len(valid) if valid else None,
                    first_known_at=first_known,
                    latest_source_event_at=norm_clock(max((e.event_at for e in events), key=utc)),
                    follower_net_r=economics[0] if economics else None,
                    follower_lcb_r=economics[1] if economics else None,
                )
            )
        return tuple(result)


def assessment_document(
    assessments: tuple[OpportunityAssessment, ...],
    *,
    decision_at: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Canonical read-only assessment artifact, no transport or mutable state."""
    _sha(source_sha256)
    cut = norm_clock(decision_at)
    for a in assessments:
        if norm_clock(a.decision_at) != cut:
            raise ValueError("ASSESSMENT_CUT_MISMATCH")
    return {
        "schema": SCHEMA,
        "decision_at": cut,
        "source_sha256": source_sha256,
        "research_only": True,
        "order_authorized": False,
        "assessments": [
            a.as_wire() for a in sorted(assessments, key=lambda x: (x.instrument, x.direction))
        ],
    }


def assessment_document_for_board(
    assessments: tuple[OpportunityAssessment, ...],
    *,
    decision_at: str,
    four_hour_board: dict[str, Any],
    one_hour_board: dict[str, Any],
) -> dict[str, Any]:
    """Bind a grade artifact to both original descriptive board snapshots.

    This has the same canonical SHA formula as the optional ensemble consumer.
    It does not import the production publisher or grant order authority.
    """
    cut = norm_clock(decision_at)
    for board in (four_hour_board, one_hour_board):
        if (
            board.get("schema") != "copy-flow-board-v1"
            or board.get("status") != "DESCRIPTIVE_ONLY_INDEPENDENCE_NOT_QUALIFIED"
            or norm_clock(board["as_of"]) != cut
            or board.get("truncated") is not False
            or board.get("financial_execution") is not False
            or board.get("predictive_qualified") is not False
        ):
            raise ValueError("UNSUPPORTED_OR_STALE_SOURCE_FLOW_BOARD")
    return assessment_document(
        assessments,
        decision_at=decision_at,
        source_sha256=digest(
            {
                "four_hour": four_hour_board,
                "one_hour": one_hour_board,
            }
        ),
    )
