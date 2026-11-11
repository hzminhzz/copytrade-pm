"""Copy Mandate storage within PaperJournal, without a financial effect."""

import re

from .pm03_account import digest
from .pm_copy_mandate import CopyMandate, MandateState, MandateTransition, transition_mandate
from .pm_checkpoint_journal import CheckpointOutcome

ZERO = "0" * 64
SCHEMA = """
CREATE TABLE IF NOT EXISTS copy_mandate_heads (
    owner TEXT PRIMARY KEY, account_id TEXT NOT NULL, pod_id TEXT NOT NULL,
    mandate_id TEXT NOT NULL, generation INTEGER NOT NULL,
    mandate TEXT NOT NULL, state TEXT NOT NULL, head TEXT NOT NULL, approval TEXT NOT NULL,
    authority_public TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS copy_mandate_events (
    owner TEXT NOT NULL REFERENCES copy_mandate_heads(owner), seq INTEGER NOT NULL,
    payload TEXT NOT NULL, prior_sha TEXT NOT NULL, sha TEXT NOT NULL,
    PRIMARY KEY(owner, seq)
);
CREATE TABLE IF NOT EXISTS copy_mandate_commands (
    nonce TEXT PRIMARY KEY, owner TEXT NOT NULL, command_sha TEXT NOT NULL, state TEXT NOT NULL,
    approval TEXT NOT NULL
);
"""


def state(db, owner):
    row = db.execute("SELECT state FROM copy_mandate_heads WHERE owner=?", (owner,)).fetchone()
    if row is None:
        raise ValueError("MANDATE_UNKNOWN")
    return MandateState.model_validate_json(row[0])


def _append(db, owner, transition):
    row = db.execute("SELECT state,head FROM copy_mandate_heads WHERE owner=?", (owner,)).fetchone()
    if row is None or MandateState.model_validate_json(row[0]) != transition.predecessor:
        raise ValueError("MANDATE_PREDECESSOR_DRIFT")
    head = digest([row[1], transition.model_dump(mode="json")])
    db.execute(
        "INSERT INTO copy_mandate_events VALUES (?,?,?,?,?)",
        (
            owner,
            transition.successor.sequence,
            transition.model_dump_json(),
            row[1],
            head,
        ),
    )
    db.execute(
        "UPDATE copy_mandate_heads SET state=?,head=? WHERE owner=?",
        (
            transition.successor.model_dump_json(),
            head,
            owner,
        ),
    )
    return transition.successor


def activate(
    db,
    mandate: CopyMandate,
    *,
    at_ms: int,
    evidence_sha: str,
    approval: dict,
    authority_public: str,
):
    existing = db.execute(
        "SELECT mandate,state FROM copy_mandate_heads WHERE owner=?", (mandate.owner,)
    ).fetchone()
    if existing:
        if CopyMandate.model_validate_json(existing[0]) != mandate:
            raise ValueError("MANDATE_GENERATION_EQUIVOCATION")
        return MandateState.model_validate_json(existing[1])
    for raw, old_state in db.execute(
        "SELECT mandate,state FROM copy_mandate_heads WHERE account_id=?",
        (mandate.account_id,),
    ):
        old = CopyMandate.model_validate_json(raw)
        previous = MandateState.model_validate_json(old_state)
        if old.mandate_id == mandate.mandate_id and old.generation >= mandate.generation:
            raise ValueError("MANDATE_GENERATION_ROLLBACK")
        if (
            old.pod_id == mandate.pod_id
            and previous.phase in ("ACTIVE", "AWAITING_BASELINE")
            and max(old.effective_from_ms, mandate.effective_from_ms)
            < min(old.effective_until_ms, mandate.effective_until_ms)
        ):
            raise ValueError("MANDATE_OPENING_INTERVAL_OVERLAP")
    before = MandateState.initial(mandate)
    transition = transition_mandate(
        mandate, before, event="ACTIVATE", evidence_sha=evidence_sha, at_ms=at_ms
    )
    if transition.effect == "REJECTED":
        raise ValueError("MANDATE_ACTIVATION_NOT_PROSPECTIVE")
    from .production_manifest import canonical

    db.execute(
        "INSERT INTO copy_mandate_heads VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            mandate.owner,
            mandate.account_id,
            mandate.pod_id,
            mandate.mandate_id,
            mandate.generation,
            mandate.model_dump_json(),
            before.model_dump_json(),
            ZERO,
            canonical(approval).decode(),
            authority_public,
        ),
    )
    return _append(db, mandate.owner, transition)


def control(db, command, *, at_ms: int, approval: dict, authority_public: str):
    from .production_manifest import canonical

    authority = db.execute(
        "SELECT authority_public FROM copy_mandate_heads WHERE owner=?", (command.get("owner"),)
    ).fetchone()
    if authority != (authority_public,):
        raise ValueError("MANDATE_CONTROL_AUTHORITY")
    required = {
        "schema",
        "owner",
        "mandate_sha",
        "predecessor_sha",
        "event",
        "issued_ms",
        "expires_ms",
        "nonce",
    }
    if (
        type(at_ms) is not int
        or set(command) != required
        or command["schema"] != "copy_mandate_control_v1"
        or command["event"] not in ("PAUSE", "RETIRE")
        or any(type(command[k]) is not int for k in ("issued_ms", "expires_ms"))
        or not 0 <= command["issued_ms"] <= at_ms < command["expires_ms"]
    ):
        raise ValueError("MANDATE_CONTROL_SCHEMA_OR_CLOCK")
    if any(
        not isinstance(command[k], str) or re.fullmatch(r"[0-9a-f]{64}", command[k]) is None
        for k in ("owner", "mandate_sha", "predecessor_sha", "nonce")
    ):
        raise ValueError("MANDATE_CONTROL_DIGEST")
    command_sha = digest(command)
    replay = db.execute(
        "SELECT owner,command_sha,state FROM copy_mandate_commands WHERE nonce=?",
        (command["nonce"],),
    ).fetchone()
    if replay:
        if replay[:2] != (command["owner"], command_sha):
            raise ValueError("MANDATE_CONTROL_NONCE_CONFLICT")
        return MandateState.model_validate_json(replay[2])
    row = db.execute(
        "SELECT mandate,state FROM copy_mandate_heads WHERE owner=?", (command["owner"],)
    ).fetchone()
    if row is None:
        raise ValueError("MANDATE_UNKNOWN")
    mandate, before = (
        CopyMandate.model_validate_json(row[0]),
        MandateState.model_validate_json(row[1]),
    )
    if command["mandate_sha"] != mandate.sha or command["predecessor_sha"] != before.sha:
        raise ValueError("MANDATE_CONTROL_PREDECESSOR")
    transition = transition_mandate(
        mandate, before, event=command["event"], evidence_sha=command_sha, at_ms=at_ms
    )
    after = _append(db, mandate.owner, transition)
    db.execute(
        "INSERT INTO copy_mandate_commands VALUES (?,?,?,?,?)",
        (
            command["nonce"],
            mandate.owner,
            command_sha,
            after.model_dump_json(),
            canonical(approval).decode(),
        ),
    )
    return after


def baseline(db, owner, outcome_id, *, at_ms):
    row = db.execute(
        "SELECT mandate,state FROM copy_mandate_heads WHERE owner=?", (owner,)
    ).fetchone()
    if row is None:
        raise ValueError("MANDATE_UNKNOWN")
    mandate, before = (
        CopyMandate.model_validate_json(row[0]),
        MandateState.model_validate_json(row[1]),
    )
    if before.phase != "AWAITING_BASELINE":
        return before
    rows = db.execute(
        "SELECT outcome FROM cwsa_outcomes WHERE json_extract(outcome,'$.outcome_id')=?",
        (outcome_id,),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("MANDATE_BASELINE_SOURCE_UNKNOWN")
    outcome = CheckpointOutcome.model_validate_json(rows[0][0])
    if (
        outcome.kind not in ("BASELINE", "UNCHANGED", "CHANGED", "RECOVERY_BASELINE")
        or outcome.sample is None
        or outcome.source_id != mandate.source_id
        or outcome.scope_generation != mandate.source_scope_generation
        or outcome.policy_epoch != mandate.policy_epoch
        or outcome.sample.scope.account_sha != mandate.source_account_sha
    ):
        raise ValueError("MANDATE_BASELINE_SOURCE_MISMATCH")
    if type(at_ms) is not int or at_ms < outcome.published_ms:
        raise ValueError("MANDATE_BASELINE_RECEIPT_CLOCK")
    transition = transition_mandate(
        mandate,
        before,
        event="COMPLETE_BASELINE",
        evidence_sha=outcome.outcome_id,
        at_ms=at_ms,
        checkpoint_ms=outcome.checkpoint_ms,
    )
    return _append(db, owner, transition)


def history(db, owner):
    before_head, before_state = ZERO, None
    result = []
    saved = db.execute(
        "SELECT mandate,approval,authority_public FROM copy_mandate_heads WHERE owner=?", (owner,)
    ).fetchone()
    if saved is None:
        raise ValueError("MANDATE_UNKNOWN")
    import json
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from .pm_copy_mandate import verify_mandate
    from .production_manifest import verify

    mandate = CopyMandate.model_validate_json(saved[0])
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(saved[2]))
    if verify_mandate(json.loads(saved[1]), key, account_id=mandate.account_id) != mandate:
        raise ValueError("MANDATE_APPROVAL_REPLAY")
    commands = {}
    for (raw_command,) in db.execute(
        "SELECT approval FROM copy_mandate_commands WHERE owner=?", (owner,)
    ):
        command = verify(json.loads(raw_command), key, "copy-mandate-control-v1")
        commands[digest(command)] = command
    for seq, raw, prior, current in db.execute(
        "SELECT seq,payload,prior_sha,sha FROM copy_mandate_events WHERE owner=? ORDER BY seq",
        (owner,),
    ):
        transition = MandateTransition.model_validate_json(raw)
        if (
            prior != before_head
            or current != digest([prior, transition.model_dump(mode="json")])
            or seq != len(result) + 1
            or (before_state is not None and before_state != transition.predecessor)
        ):
            raise ValueError("MANDATE_JOURNAL_CHAIN")
        if transition.event in ("PAUSE", "RETIRE"):
            command = commands.get(transition.evidence_sha)
            if (
                command is None
                or command["predecessor_sha"] != transition.predecessor.sha
                or command["event"] != transition.event
            ):
                raise ValueError("MANDATE_CONTROL_REPLAY")
        expected = transition_mandate(
            mandate,
            transition.predecessor,
            event=transition.event,
            evidence_sha=transition.evidence_sha,
            at_ms=transition.at_ms,
            checkpoint_ms=transition.checkpoint_ms,
        )
        if transition != expected:
            raise ValueError("MANDATE_SEMANTIC_REPLAY")
        result.append(transition)
        before_head, before_state = current, transition.successor
    row = db.execute("SELECT state,head FROM copy_mandate_heads WHERE owner=?", (owner,)).fetchone()
    if row and (MandateState.model_validate_json(row[0]) != before_state or row[1] != before_head):
        raise ValueError("MANDATE_JOURNAL_HEAD")
    return tuple(result)
