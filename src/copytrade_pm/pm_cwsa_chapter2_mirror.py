"""Verified transport of CWSA source journal receipts into a paper consumer.

This is a read-only mirror of the *existing* canonical source, not another
position reducer or source authority. The paper Journal owns modeled finance;
independent signed mandate admission remains mandatory before calling consume.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import json
from datetime import UTC, datetime

from .pm03_account import digest
from .pm_checkpoint_journal import (
    CheckpointOutcome,
    CheckpointScope,
    CwsaPolicy,
    SourceState,
    SourceTransition,
    ZERO,
    stream_key,
)
from .pm_v4_evidence import publish_wire, read_wire


def mirror_source(source_db: Path, journal, stream: str) -> tuple[str, ...]:
    """Verify & mirror the immutable CWSA chain/originals, atomically.

    Crash before the mirror transaction: there is no visible new source row.
    Crash after it: exact replay compares hashes; no financial effect follows
    until a separately signed mandate is checked by PaperJournal.consume.
    """
    source_db = Path(source_db)
    if source_db.resolve() == journal.path.resolve():
        raise ValueError("CWSA_MIRROR_INDEPENDENT_SOURCE_REQUIRED")
    with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as consumer:
        previous = consumer.execute(
            "SELECT scope,policy,state,head FROM cwsa_heads WHERE stream=?", (stream,)
        ).fetchone()
        local_sequence = SourceState.model_validate_json(previous[2]).sequence if previous else 0
        local_outcomes = {
            row[0]: row[1:]
            for row in consumer.execute(
                "SELECT checkpoint_ms,candidate_sha,outcome FROM cwsa_outcomes WHERE stream=?",
                (stream,),
            )
        }

    with closing(sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        head = source.execute(
            "SELECT scope,policy,state,head FROM cwsa_heads WHERE stream=?", (stream,)
        ).fetchone()
        if head is None:
            raise ValueError("CWSA_MIRROR_SOURCE_UNKNOWN")
        scope = CheckpointScope.model_validate_json(head[0])
        policy = CwsaPolicy.model_validate_json(head[1])
        state = SourceState.model_validate_json(head[2])
        if stream_key(scope, policy.epoch) != stream:
            raise ValueError("CWSA_MIRROR_SCOPE_OR_POLICY")
        if previous is not None and (previous[0], previous[1]) != head[:2]:
            raise ValueError("CWSA_MIRROR_SCOPE_DRIFT")
        if local_sequence > state.sequence:
            raise ValueError("CWSA_MIRROR_REWIND")
        transitions = source.execute(
            "SELECT seq,payload,sha FROM cwsa_transitions WHERE stream=? AND seq>? ORDER BY seq",
            (stream, local_sequence),
        ).fetchall()
        outcomes = source.execute(
            "SELECT checkpoint_ms,candidate_sha,outcome FROM cwsa_outcomes "
            "WHERE stream=? ORDER BY checkpoint_ms",
            (stream,),
        ).fetchall()

        prior_sha = previous[3] if previous else ZERO
        prior_state = SourceState.model_validate_json(previous[2]) if previous else None
        observed_effects = {}
        for seq, raw, sha in transitions:
            item = SourceTransition.model_validate_json(raw)
            if (
                seq != local_sequence + 1
                or item.sequence != seq
                or item.sha != sha
                or item.prior_sha != prior_sha
                or (prior_state is not None and item.predecessor != prior_state)
            ):
                raise ValueError("CWSA_MIRROR_SOURCE_CHAIN")
            if item.effect is not None:
                observed_effects[item.effect.checkpoint_ms] = (item.effect, item.evidence_sha)
            prior_sha, prior_state, local_sequence = sha, item.successor, seq
        if local_sequence != state.sequence or prior_sha != head[3] or prior_state != state:
            raise ValueError("CWSA_MIRROR_SOURCE_HEAD")
        new_outcomes = []
        original_shas: set[str] = set()
        for checkpoint_ms, candidate_sha, raw in outcomes:
            item = CheckpointOutcome.model_validate_json(raw)
            if item.checkpoint_ms != checkpoint_ms or item.outcome_id != digest(
                ["cwsa_outcome_v3", stream, checkpoint_ms]
            ):
                raise ValueError("CWSA_MIRROR_OUTCOME_ID")
            if checkpoint_ms in local_outcomes:
                if local_outcomes[checkpoint_ms] != (candidate_sha, raw):
                    raise ValueError("CWSA_MIRROR_OUTCOME_DRIFT")
                continue
            effect = observed_effects.get(checkpoint_ms)
            if effect is None or effect[0] != item or effect[1] != candidate_sha:
                raise ValueError("CWSA_MIRROR_UNPROVEN_OUTCOME")
            if item.sample is not None:
                for receipt in (item.sample.catalog, *item.sample.receipts):
                    if receipt is not None:
                        original_shas.add(receipt.raw_sha)
            new_outcomes.append((checkpoint_ms, candidate_sha, raw))
        source.execute("COMMIT")

    # Publishing exact, verified originals before SQL ensures a crash cannot
    # leave an accepted source reference pointing at a missing paper sidecar.
    for sha in sorted(original_shas):
        publish_wire(journal.path, read_wire(source_db, sha), sha)

    with journal._writer() as consumer:
        consumer.execute("BEGIN IMMEDIATE")
        try:
            saved = consumer.execute(
                "SELECT scope,policy,state,head FROM cwsa_heads WHERE stream=?", (stream,)
            ).fetchone()
            if saved != previous:
                raise ValueError("CWSA_MIRROR_CONCURRENT_MODIFICATION")
            if saved is None:
                consumer.execute(
                    "INSERT INTO cwsa_heads VALUES (?,?,?,?,?)",
                    (stream, head[0], head[1], head[2], head[3]),
                )
            else:
                consumer.execute(
                    "UPDATE cwsa_heads SET state=?,head=? WHERE stream=?",
                    (head[2], head[3], stream),
                )
            for seq, raw, sha in transitions:
                consumer.execute(
                    "INSERT INTO cwsa_transitions VALUES (?,?,?,?)",
                    (stream, seq, raw, sha),
                )
            for checkpoint_ms, candidate_sha, raw in new_outcomes:
                consumer.execute(
                    "INSERT INTO cwsa_outcomes VALUES (?,?,?,?)",
                    (stream, checkpoint_ms, candidate_sha, raw),
                )
            consumer.execute("COMMIT")
        except BaseException:
            consumer.execute("ROLLBACK")
            raise
    return tuple(
        CheckpointOutcome.model_validate_json(raw).outcome_id for _, _, raw in new_outcomes
    )


def mirror_latest_quotes(
    source_db: Path, journal, instruments: tuple[str, ...], *, now_ms: int
) -> dict[str, str]:
    """Import only source-verified, already-known public L2 evidence.

    This retains the independent provider observation's actual event and
    known-at clocks. It never creates a market quote, assigns a future clock,
    or promotes a Vike mid-price into an executable book.
    """
    if source_db.resolve() == journal.path.resolve():
        raise ValueError("CWSA_QUOTE_INDEPENDENT_SOURCE_REQUIRED")
    selected = {}
    with closing(sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        for inst in sorted(set(instruments)):
            row = db.execute(
                "SELECT seq,payload,payload_sha,prior_sha,chain_sha,event_at,known_at "
                "FROM market_quote_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1",
                (inst,),
            ).fetchone()
            if row is None:
                continue
            seq, raw, sha, prior, chain, event_at, known_at = row
            head = db.execute(
                "SELECT cursor,event_at,known_at,chain_sha FROM market_quote_heads WHERE instrument=?",
                (inst,),
            ).fetchone()
            prev = (
                db.execute(
                    "SELECT chain_sha FROM market_quote_receipts WHERE instrument=? AND seq=?",
                    (inst, seq - 1),
                ).fetchone()
                if seq > 1
                else ("0" * 64,)
            )
            payload = json.loads(raw)
            if (
                head != (seq, event_at, known_at, chain)
                or prev is None
                or prior != prev[0]
                or chain != digest([inst, seq, sha, prior])
                or digest(payload) != sha
                or payload.get("instrument") != inst
                or payload.get("source_event_at") != event_at
                or payload.get("first_known_at") != known_at
                or int(datetime.fromisoformat(known_at).astimezone(UTC).timestamp() * 1000) > now_ms
            ):
                raise ValueError("CWSA_QUOTE_SOURCE_PROOF_INVALID")
            journal._validate_market_quote(payload)
            selected[inst] = payload
        db.execute("COMMIT")
    results = {}
    for inst, payload in selected.items():
        results[inst] = journal.append_market_quote(payload)["status"]
    return results


def consume_canonical_paper(
    *,
    journal,
    run_id: str,
    owner: str,
    outcome_id: str,
    source_db: Path,
    quote_db: Path,
    policy: dict,
    catalog: dict,
    at_ms: int,
) -> dict:
    """One verified source -> signed mandate -> modeled PM03 financial effect.

    The paper consumer performs its own signature, policy, source-head,
    opportunity, risk, quote and financial-journal validation. This adapter
    only mirrors immutable public inputs and never creates a mandate itself.
    """
    from .pm_copy_mandate import CopyMandate

    with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT mandate FROM copy_mandate_heads WHERE owner=?", (owner,)
        ).fetchall()
    if len(rows) != 1:
        raise ValueError("CHAPTER2_SIGNED_MANDATE_REQUIRED")
    mandate = CopyMandate.model_validate_json(rows[0][0])
    if digest(policy) != mandate.risk_policy_sha:
        raise ValueError("CHAPTER2_PAPER_POLICY_NOT_APPROVED")
    with closing(sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)) as db:
        items = db.execute(
            "SELECT stream,outcome FROM cwsa_outcomes WHERE json_extract(outcome,'$.outcome_id')=?",
            (outcome_id,),
        ).fetchall()
    if len(items) != 1:
        raise ValueError("CHAPTER2_CANONICAL_OUTCOME_UNKNOWN")
    stream, raw = items[0]
    outcome = CheckpointOutcome.model_validate_json(raw)
    if (
        outcome.source_id != mandate.source_id
        or outcome.scope_generation != mandate.source_scope_generation
        or outcome.policy_epoch != mandate.policy_epoch
        or outcome.published_ms > at_ms
    ):
        raise ValueError("CHAPTER2_CANONICAL_MANDATE_MISMATCH")
    mirror_source(source_db, journal, stream)
    mirror_latest_quotes(quote_db, journal, mandate.allowed_markets, now_ms=at_ms)
    return journal.consume_checkpoint(
        run_id, owner, outcome_id, at_ms=at_ms, policy=policy, catalog=catalog
    )
