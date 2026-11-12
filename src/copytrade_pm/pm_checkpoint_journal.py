"""Explicit CWSA transitions stored inside the existing PaperJournal.

This module owns source continuity only. It cannot size, reserve or dispatch money.
"""

from __future__ import annotations

from typing import Annotated, Literal
import json
from pathlib import Path

from pydantic import Field

from .pm03_account import digest
from .pm_checkpoint_source import (
    GRID_MS,
    CheckpointSample,
    CheckpointScope,
    Milliseconds,
    SamplingLimits,
)
from .pm_source_contracts import Contract, Position, Sha

ZERO = "0" * 64
SCHEMA = """
CREATE TABLE IF NOT EXISTS cwsa_heads (
    stream TEXT PRIMARY KEY, scope TEXT NOT NULL, policy TEXT NOT NULL,
    state TEXT NOT NULL, head TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cwsa_transitions (
    stream TEXT NOT NULL REFERENCES cwsa_heads(stream), seq INTEGER NOT NULL,
    payload TEXT NOT NULL, sha TEXT NOT NULL, PRIMARY KEY(stream, seq)
);
CREATE TABLE IF NOT EXISTS cwsa_outcomes (
    stream TEXT NOT NULL REFERENCES cwsa_heads(stream), checkpoint_ms INTEGER NOT NULL,
    candidate_sha TEXT NOT NULL, outcome TEXT NOT NULL,
    PRIMARY KEY(stream, checkpoint_ms)
);
"""


class CwsaPolicy(Contract):
    name: Literal["cwsa_utc_5m_v3"] = "cwsa_utc_5m_v3"
    limits: SamplingLimits
    measurement_sha: Sha

    @property
    def epoch(self) -> str:
        return digest(self.model_dump(mode="json"))


class SourceState(Contract):
    phase: Literal["ABSENT", "UNANCHORED", "CONTINUOUS", "FENCED"]
    sequence: Annotated[int, Field(ge=0)]
    next_checkpoint_ms: Milliseconds
    economic_sha: Sha | None = None
    positions: tuple[Position, ...] = ()
    provider_clocks: tuple[tuple[str, int], ...] = ()


class CheckpointOutcome(Contract):
    schema_version: Literal[3] = 3
    source_id: str
    scope_generation: Sha
    policy_epoch: Sha
    checkpoint_ms: Milliseconds
    outcome_id: Sha
    kind: Literal[
        "BASELINE", "UNCHANGED", "CHANGED", "RECOVERY_BASELINE", "UNAVAILABLE", "QUARANTINE"
    ]
    economic_sha: Sha | None
    signal_id: Sha | None
    positions: tuple[Position, ...]
    sample: CheckpointSample | None
    published_ms: Milliseconds
    reasons: tuple[str, ...]
    financial_authority: Literal["NONE"] = "NONE"


class SourceTransition(Contract):
    schema_version: Literal[3] = 3
    source_id: str
    scope_generation: Sha
    policy_epoch: Sha
    sequence: Annotated[int, Field(gt=0)]
    prior_sha: Sha
    predecessor: SourceState
    event: Literal["REGISTER", "SAMPLE", "GAP", "CONFLICT", "LATE"]
    evidence_sha: Sha
    guard: Literal[
        "REGISTERED_SCOPE",
        "COMPLETE_BASELINE",
        "COMPLETE_CONTINUOUS",
        "COMPLETE_RECOVERY",
        "NATIVE_UNAVAILABLE",
        "PROOF_INVALID",
        "TIMING_EXPIRED",
        "POLICY_MISMATCH",
        "CLOCK_REGRESSION",
        "SCHEDULE_GAP",
        "EQUIVOCATION",
        "REORDERED",
    ]
    at_ms: Milliseconds
    actor: Literal["CWSA"] = "CWSA"
    successor: SourceState
    effect: CheckpointOutcome | None

    @property
    def sha(self) -> str:
        return digest(self.model_dump(mode="json"))


def stream_key(scope: CheckpointScope, epoch: str) -> str:
    return digest([scope.source_id, scope.account_sha, scope.generation, epoch])


def _json(value: Contract) -> str:
    return value.model_dump_json()


def _state(previous: SourceState, **changes) -> SourceState:
    return SourceState(**{**previous.model_dump(), "sequence": previous.sequence + 1, **changes})


def _persist(db, key, transition):
    db.execute(
        "INSERT INTO cwsa_transitions VALUES (?,?,?,?)",
        (key, transition.sequence, _json(transition), transition.sha),
    )
    db.execute(
        "UPDATE cwsa_heads SET state=?,head=? WHERE stream=?",
        (_json(transition.successor), transition.sha, key),
    )


def register(db, scope: CheckpointScope, policy: CwsaPolicy, first: int, at_ms: int):
    if type(first) is not int or first % GRID_MS or not 0 <= at_ms <= first:
        raise ValueError("CWSA_REGISTRATION_CLOCK")
    key = stream_key(scope, policy.epoch)
    row = db.execute("SELECT scope,policy,state FROM cwsa_heads WHERE stream=?", (key,)).fetchone()
    if row:
        if json.loads(row[0]) != scope.model_dump(mode="json") or row[1] != _json(policy):
            raise ValueError("CWSA_REGISTRATION_CONFLICT")
        return SourceState.model_validate_json(row[2])
    before = SourceState(phase="ABSENT", sequence=0, next_checkpoint_ms=first)
    after = _state(before, phase="UNANCHORED")
    transition = SourceTransition(
        source_id=scope.source_id,
        scope_generation=scope.generation,
        policy_epoch=policy.epoch,
        sequence=1,
        prior_sha=ZERO,
        predecessor=before,
        event="REGISTER",
        evidence_sha=digest([scope.model_dump(mode="json"), policy.model_dump(mode="json"), first]),
        guard="REGISTERED_SCOPE",
        at_ms=at_ms,
        successor=after,
        effect=None,
    )
    db.execute(
        "INSERT INTO cwsa_heads VALUES (?,?,?,?,?)",
        (key, _json(scope), _json(policy), _json(before), ZERO),
    )
    _persist(db, key, transition)
    return after


def history(db, scope, epoch) -> tuple[SourceTransition, ...]:
    key = stream_key(scope, epoch)
    rows = db.execute(
        "SELECT payload,sha FROM cwsa_transitions WHERE stream=? ORDER BY seq", (key,)
    ).fetchall()
    result = []
    prior, state = ZERO, None
    for raw, sha in rows:
        item = SourceTransition.model_validate_json(raw)
        if item.sha != sha or item.prior_sha != prior or item.sequence != len(result) + 1:
            raise ValueError("CWSA_JOURNAL_CHAIN")
        if state is not None and item.predecessor != state:
            raise ValueError("CWSA_JOURNAL_PREDECESSOR")
        result.append(item)
        prior, state = sha, item.successor
    head = db.execute("SELECT state,head FROM cwsa_heads WHERE stream=?", (key,)).fetchone()
    if head and (SourceState.model_validate_json(head[0]) != state or head[1] != prior):
        raise ValueError("CWSA_JOURNAL_HEAD")
    return tuple(result)


def record(db, epoch, candidate: CheckpointSample, published_ms: int, *, proof_valid: bool):
    key = stream_key(candidate.scope, epoch)
    row = db.execute(
        "SELECT scope,policy,state,head FROM cwsa_heads WHERE stream=?", (key,)
    ).fetchone()
    if row is None:
        raise ValueError("CWSA_SOURCE_NOT_REGISTERED")
    scope = CheckpointScope.model_validate_json(row[0])
    policy = CwsaPolicy.model_validate_json(row[1])
    before = SourceState.model_validate_json(row[2])
    if scope != candidate.scope:
        raise ValueError("CWSA_SOURCE_SCOPE_MISMATCH")
    if type(published_ms) is not int or published_ms < candidate.validated_ms:
        raise ValueError("CWSA_PUBLICATION_CLOCK")
    if candidate.checkpoint_ms % GRID_MS:
        raise ValueError("CWSA_BOUNDARY")
    candidate_sha = digest(candidate.model_dump(mode="json"))
    existing = db.execute(
        "SELECT candidate_sha,outcome FROM cwsa_outcomes WHERE stream=? AND checkpoint_ms=?",
        (key, candidate.checkpoint_ms),
    ).fetchone()
    if existing and existing[0] == candidate_sha:
        return CheckpointOutcome.model_validate_json(existing[1])
    previous_sha = row[3]
    if existing or candidate.checkpoint_ms < before.next_checkpoint_ms:
        transition = SourceTransition(
            source_id=scope.source_id,
            scope_generation=scope.generation,
            policy_epoch=epoch,
            sequence=before.sequence + 1,
            prior_sha=previous_sha,
            predecessor=before,
            event="CONFLICT" if existing else "LATE",
            evidence_sha=candidate_sha,
            guard="EQUIVOCATION" if existing else "REORDERED",
            at_ms=published_ms,
            successor=_state(before, phase="FENCED"),
            effect=None,
        )
        _persist(db, key, transition)
        return transition
    while before.next_checkpoint_ms < candidate.checkpoint_ms:
        missed = before.next_checkpoint_ms
        gap = CheckpointOutcome(
            source_id=scope.source_id,
            scope_generation=scope.generation,
            policy_epoch=epoch,
            checkpoint_ms=missed,
            outcome_id=digest(["cwsa_outcome_v3", key, missed]),
            kind="UNAVAILABLE",
            economic_sha=None,
            signal_id=None,
            positions=(),
            sample=None,
            published_ms=published_ms,
            reasons=("SCHEDULE_GAP",),
        )
        after_gap = _state(before, phase="FENCED", next_checkpoint_ms=missed + GRID_MS)
        transition = SourceTransition(
            source_id=scope.source_id,
            scope_generation=scope.generation,
            policy_epoch=epoch,
            sequence=after_gap.sequence,
            prior_sha=previous_sha,
            predecessor=before,
            event="GAP",
            evidence_sha=digest(["detected_gap", key, missed, candidate_sha]),
            guard="SCHEDULE_GAP",
            at_ms=published_ms,
            successor=after_gap,
            effect=gap,
        )
        db.execute(
            "INSERT INTO cwsa_outcomes VALUES (?,?,?,?)",
            (key, missed, transition.evidence_sha, _json(gap)),
        )
        _persist(db, key, transition)
        before, previous_sha = after_gap, transition.sha
    outcome_id = digest(["cwsa_outcome_v3", key, candidate.checkpoint_ms])
    valid = candidate.kind == "COMPLETE" and proof_valid and candidate.limits == policy.limits
    kind, guard = "QUARANTINE", "PROOF_INVALID"
    if candidate.kind == "UNAVAILABLE":
        kind, guard = "UNAVAILABLE", "NATIVE_UNAVAILABLE"
    elif candidate.limits != policy.limits:
        guard = "POLICY_MISMATCH"
    elif valid:
        if published_ms >= candidate.checkpoint_ms + policy.limits.publication_grace_ms:
            valid, guard = False, "TIMING_EXPIRED"
        elif any(
            r.state_ms < dict(before.provider_clocks).get(r.dex, 0)
            for r in candidate.receipts
            if r.state_ms is not None
        ):
            valid, guard = False, "CLOCK_REGRESSION"
    if valid:
        kind, guard = {
            "UNANCHORED": ("BASELINE", "COMPLETE_BASELINE"),
            "CONTINUOUS": (
                "UNCHANGED" if candidate.economic_sha == before.economic_sha else "CHANGED",
                "COMPLETE_CONTINUOUS",
            ),
            "FENCED": ("RECOVERY_BASELINE", "COMPLETE_RECOVERY"),
        }[before.phase]
    outcome = CheckpointOutcome(
        source_id=scope.source_id,
        scope_generation=scope.generation,
        policy_epoch=epoch,
        checkpoint_ms=candidate.checkpoint_ms,
        outcome_id=outcome_id,
        kind=kind,
        economic_sha=candidate.economic_sha if valid else None,
        signal_id=digest(["cwsa_target_v3", outcome_id, candidate.economic_sha])
        if kind == "CHANGED"
        else None,
        positions=candidate.positions if valid else (),
        sample=candidate,
        published_ms=published_ms,
        reasons=() if valid else (*candidate.reasons, guard),
    )
    after = _state(
        before,
        phase="CONTINUOUS" if valid else "FENCED",
        next_checkpoint_ms=candidate.checkpoint_ms + GRID_MS,
        economic_sha=candidate.economic_sha if valid else before.economic_sha,
        positions=candidate.positions if valid else before.positions,
        provider_clocks=tuple((r.dex, r.state_ms) for r in candidate.receipts)
        if valid
        else before.provider_clocks,
    )
    transition = SourceTransition(
        source_id=scope.source_id,
        scope_generation=scope.generation,
        policy_epoch=epoch,
        sequence=after.sequence,
        prior_sha=previous_sha,
        predecessor=before,
        event="SAMPLE",
        evidence_sha=candidate_sha,
        guard=guard,
        at_ms=published_ms,
        successor=after,
        effect=outcome,
    )
    db.execute(
        "INSERT INTO cwsa_outcomes VALUES (?,?,?,?)",
        (key, candidate.checkpoint_ms, candidate_sha, _json(outcome)),
    )
    _persist(db, key, transition)
    return outcome


def verify_candidate(candidate: CheckpointSample, evidence_root: Path) -> bool:
    """Replay original native bytes before entering the journal transaction."""
    if candidate.kind != "COMPLETE":
        return False
    from .pm_e4_prospective import _dex_universe
    from .pm_source_contracts import exact_decimal
    from .pm_v4_evidence import read_wire

    try:
        if candidate.reasons or candidate.catalog is None or candidate.limits is None:
            return False
        if tuple(r.dex for r in candidate.receipts) != candidate.scope.dexes:
            return False
        limits = candidate.limits
        receipts = (candidate.catalog, *candidate.receipts)
        if (
            not candidate.checkpoint_ms
            <= candidate.started_ms
            <= candidate.received_ms
            <= candidate.validated_ms
        ):
            return False
        if candidate.validated_ms >= candidate.checkpoint_ms + limits.publication_grace_ms:
            return False
        if candidate.validated_ms - candidate.started_ms > limits.max_acquisition_ms:
            return False
        if candidate.received_ms != max(r.received_ms for r in receipts):
            return False
        if any(
            not candidate.started_ms <= r.requested_ms <= r.received_ms <= candidate.validated_ms
            for r in receipts
        ):
            return False
        if any(
            r.state_ms is None or not 0 < r.state_ms <= r.received_ms for r in candidate.receipts
        ):
            return False
        stamps = [r.state_ms for r in candidate.receipts]
        if candidate.validated_ms - min(stamps) > limits.max_state_age_ms:
            return False
        if max(stamps) - min(stamps) > limits.max_dex_skew_ms:
            return False
        if candidate.catalog.request_sha != digest({"type": "perpDexs"}):
            return False
        from hashlib import sha256

        for receipt in receipts:
            if receipt.request is None:
                return False
            request = receipt.request.model_dump(exclude_none=True)
            if digest(request) != receipt.request_sha:
                return False
            if receipt.dex == "catalog":
                if request != {"type": "perpDexs"}:
                    return False
            elif (
                request.get("type") != "clearinghouseState"
                or sha256(request.get("user", "").encode()).hexdigest()
                != candidate.scope.account_sha
                or request.get("dex", "default") != receipt.dex
            ):
                return False
        path = evidence_root / "paper-events.sqlite3"
        catalog = json.loads(read_wire(path, candidate.catalog.raw_sha))
        if tuple(sorted(_dex_universe(catalog))) != candidate.scope.dexes:
            return False
        positions = {}
        for receipt in candidate.receipts:
            body = json.loads(read_wire(path, receipt.raw_sha))
            if type(body["time"]) is not int or body["time"] != receipt.state_ms:
                return False
            seen = set()
            count = 0
            for row in body["assetPositions"]:
                position = row["position"]
                coin = position["coin"]
                dex = receipt.dex
                if dex != "default":
                    if not coin.startswith(dex + ":"):
                        return False
                    coin = coin[len(dex) + 1 :]
                key = f"hyperliquid/mainnet:perp:{dex}/{coin}"
                qty = exact_decimal(position["szi"])
                p = Position(instrument=key, quantity=qty)
                if key in seen:
                    return False
                seen.add(key)
                if qty:
                    positions[key] = p
                    count += 1
            if count != receipt.position_count:
                return False
        return tuple(positions[k] for k in sorted(positions)) == candidate.positions
    except ValueError, TypeError, KeyError, OSError:
        return False
