"""CWSA consumption within PaperJournal and the existing PM03 account engine.

No scheduler, broker transport, standalone financial store or T0+300 path.
All costs and timing limits are explicit inputs pinned by the signed mandate.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import ROUND_DOWN
from hashlib import sha256
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .pm03_account import Account, Instrument, Rulebook, ZERO, clock, digest, number
from .pm03_execution import CostModel, MarketObservation, execute_targets
from .pm03_risk import RiskEvidence, RiskPolicy, classify, loss_under_shock
from .pm_checkpoint_journal import CheckpointOutcome, history as source_history
from .pm_checkpoint_opportunity import OpportunityState, advance
from .pm_checkpoint_source import GRID_MS
from .pm_copy_mandate import CopyMandate, MandateState, verify_mandate
from .pm_copy_mandate_journal import baseline, history as mandate_history
from .pm_forward_observed_paper import _candidate_market, _read_quote
from .pm_v4_evidence import read_wire
from .v4_source_export import _source_marks

KIND = "CWSA_PAPER_REVIEW"
TERMINAL = {
    "COMMITTED_ONCE",
    "MISSED",
    "BASELINE",
    "UNCHANGED",
    "RECOVERY_BASELINE",
    "COVERAGE_GAP",
}


def at(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def _marks(outcome, originals):
    if outcome.sample is None:
        return {}
    states = []
    for receipt in outcome.sample.receipts:
        raw = originals[receipt.raw_sha]
        if sha256(raw.encode()).hexdigest() != receipt.raw_sha:
            raise ValueError("CHECKPOINT_ORIGINAL_HASH")
        native = json.loads(raw)
        if native["time"] != receipt.state_ms:
            raise ValueError("CHECKPOINT_SOURCE_MARK_CLOCK")
        states.append([receipt.dex, native])
    return _source_marks(
        {"data": {"clearinghouseStates": states}},
        {p.instrument: str(p.quantity) for p in outcome.positions},
    )


def _policy(value):
    if (
        set(value)
        != {
            "schema",
            "max_quote_age_ms",
            "pod_loss_limit",
            "max_gross_notional",
            "risk",
            "shocks",
            "costs",
        }
        or value["schema"] != "checkpoint_paper_policy_v3"
    ):
        raise ValueError("CHECKPOINT_PAPER_POLICY")
    if type(value["max_quote_age_ms"]) is not int or value["max_quote_age_ms"] <= 0:
        raise ValueError("CHECKPOINT_QUOTE_AGE_POLICY")
    if number(value["pod_loss_limit"]) <= 0 or number(value["max_gross_notional"]) <= 0:
        raise ValueError("CHECKPOINT_RISK_LIMIT_POLICY")
    if set(value["risk"]) != set(RiskPolicy.__dataclass_fields__):
        raise ValueError("CHECKPOINT_EXPLICIT_RISK_POLICY")
    risk = RiskPolicy(**{k: number(v) for k, v in value["risk"].items()})
    costs = CostModel(
        **{
            k: (v if k in ("max_age_seconds", "latency_seconds") else number(v))
            for k, v in value["costs"].items()
        }
    )
    if costs.latency_seconds != 0:
        raise ValueError("CHECKPOINT_DELAYED_MODEL_REQUIRES_LATER_QUOTE")
    return risk, costs


def validate_binding(db, run_id, event):
    """Replay source/mandate causality against their independently owned histories."""
    m = CopyMandate.model_validate_json(json.dumps(event["mandate"]))
    outcome = CheckpointOutcome.model_validate_json(json.dumps(event["outcome"]))
    saved = db.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
    manifest = json.loads(saved[0])
    if (
        m.account_id != manifest["account_id"]
        or m.risk_policy_sha != manifest["policy_sha"]
        or digest(event["policy"]) != manifest["policy_sha"]
        or m.rulebook_sha != Rulebook.from_dict(manifest["rulebook"]).sha
    ):
        raise ValueError("CHECKPOINT_MANIFEST_POLICY_BINDING")
    transitions = mandate_history(db, m.owner)
    if event["mandate_state"] not in [t.successor.model_dump(mode="json") for t in transitions]:
        raise ValueError("CHECKPOINT_MANDATE_STATE_PROOF")
    rows = db.execute(
        "SELECT outcome FROM cwsa_outcomes WHERE json_extract(outcome,'$.outcome_id')=?",
        (outcome.outcome_id,),
    ).fetchall()
    if len(rows) != 1 or CheckpointOutcome.model_validate_json(rows[0][0]) != outcome:
        raise ValueError("CHECKPOINT_SOURCE_CAUSAL_BINDING")
    if outcome.sample is not None:
        chain = source_history(db, outcome.sample.scope, outcome.policy_epoch)
        if not any(
            t.sequence == event["source_head_sequence"]
            and digest(t.model_dump(mode="json")) == event["source_head_sha"]
            and t.successor.phase == event["source_phase"]
            and t.at_ms <= event["at_ms"]
            for t in chain
        ):
            raise ValueError("CHECKPOINT_SOURCE_HEAD_PROOF")
    if (
        outcome.source_id != m.source_id
        or outcome.scope_generation != m.source_scope_generation
        or outcome.policy_epoch != m.policy_epoch
        or event["at_ms"] < outcome.published_ms
        or at(event["at_ms"]) != event["event_at"]
    ):
        raise ValueError("CHECKPOINT_SOURCE_MANDATE_BINDING")


def consume(journal, run_id, owner, outcome_id, *, at_ms, policy, catalog):
    """Caller explicitly chooses a checkpoint policy; no timer or automatic activation."""

    if type(at_ms) is not int or at_ms < 0:
        raise ValueError("CHECKPOINT_CONSUMER_CLOCK")
    _policy(policy)
    with journal._writer() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            previous = journal._verify(db, run_id)
            row = db.execute(
                "SELECT mandate,state,approval,authority_public FROM copy_mandate_heads WHERE owner=?",
                (owner,),
            ).fetchone()
            if row is None:
                raise ValueError("MANDATE_UNKNOWN")
            m = CopyMandate.model_validate_json(row[0])
            if digest(policy) != m.risk_policy_sha:
                raise ValueError("CHECKPOINT_POLICY_PIN")
            key = digest([run_id, owner, outcome_id])
            prior = (
                previous["account"]
                .get("pm04", {})
                .get("checkpoint_v3", {})
                .get("outcomes", {})
                .get(key)
            )
            if prior and prior["status"] in TERMINAL:
                db.execute("COMMIT")
                return prior
            rows = db.execute(
                "SELECT stream,outcome FROM cwsa_outcomes WHERE json_extract(outcome,'$.outcome_id')=?",
                (outcome_id,),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("CHECKPOINT_OUTCOME_UNKNOWN")
            stream, raw_outcome = rows[0]
            outcome = CheckpointOutcome.model_validate_json(raw_outcome)
            current = MandateState.model_validate_json(row[1])
            if (
                current.phase == "AWAITING_BASELINE"
                and outcome.sample is not None
                and outcome.sample.kind == "COMPLETE"
            ):
                current = baseline(db, owner, outcome_id, at_ms=at_ms)
            raw_head, head_sha = db.execute(
                "SELECT state,head FROM cwsa_heads WHERE stream=?", (stream,)
            ).fetchone()
            source_head = json.loads(raw_head)
            originals = {}
            if outcome.sample is not None:
                for receipt in outcome.sample.receipts:
                    originals[receipt.raw_sha] = read_wire(journal.path, receipt.raw_sha)
            keys = set(m.allowed_markets)
            for book in previous["account"].get("pm_quantities", {}).values():
                keys.update(book)
            quotes = {k: value for k in sorted(keys) if (value := _read_quote(db, k)) is not None}
            event = {
                "kind": KIND,
                "run_id": run_id,
                "event_at": at(at_ms),
                "at_ms": at_ms,
                "mandate": m.model_dump(mode="json"),
                "mandate_state": current.model_dump(mode="json"),
                "approval": json.loads(row[2]),
                "authority_public": row[3],
                "outcome": outcome.model_dump(mode="json"),
                "source_head_sequence": source_head["sequence"],
                "source_head_sha": head_sha,
                "source_phase": source_head["phase"],
                "originals": originals,
                "policy": policy,
                "quotes": quotes,
                "catalog": catalog,
                "expected_sources": sorted(
                    {
                        CopyMandate.model_validate_json(r[0]).source_id
                        for r in db.execute(
                            "SELECT mandate FROM copy_mandate_heads WHERE account_id=?",
                            (m.account_id,),
                        )
                    }
                ),
                "order_route": "NONE",
                "evidence_class": "CWSA_MODELED_FOLLOWER_V3",
            }
            validate_binding(db, run_id, event)
            event_id = digest(["checkpoint_paper_effect_v3", event])
            journal._append_locked(db, run_id, event_id, event)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    restored = journal.restore(run_id)
    return restored["account"]["pm04"]["checkpoint_v3"]["outcomes"][key]


def apply(account: Account, event: dict) -> dict:
    """Deterministic replay: protocol metadata and PM03 effects commit together."""
    if event["order_route"] != "NONE" or event["evidence_class"] != "CWSA_MODELED_FOLLOWER_V3":
        raise ValueError("CHECKPOINT_PAPER_AUTHORITY")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(event["authority_public"]))
    m = verify_mandate(event["approval"], key, account_id=event["mandate"]["account_id"])
    if (
        m.model_dump(mode="json") != event["mandate"]
        or m.rulebook_sha != account.rulebook.sha
        or m.risk_policy_sha != digest(event["policy"])
    ):
        raise ValueError("CHECKPOINT_MANDATE_POLICY")
    lifecycle = MandateState.model_validate_json(json.dumps(event["mandate_state"]))
    outcome = CheckpointOutcome.model_validate_json(json.dumps(event["outcome"]))
    now = event["at_ms"]
    risk_policy, costs = _policy(event["policy"])
    state = account.pm04_state.setdefault(
        "checkpoint_v3",
        {
            "schema": "checkpoint_paper_consumer_v3",
            "outcomes": {},
            "opportunities": {},
            "last_checkpoint": {},
            "coverage": {},
            "consumed_quotes": {},
        },
    )
    effect_key = digest([event["run_id"], m.owner, outcome.outcome_id])
    if effect_key in state["outcomes"] and state["outcomes"][effect_key]["status"] in TERMINAL:
        return state["outcomes"][effect_key]
    if outcome.checkpoint_ms < state["last_checkpoint"].get(m.owner, 0):
        raise ValueError("CHECKPOINT_CONSUMER_REORDER")
    state["last_checkpoint"][m.owner] = outcome.checkpoint_ms
    for source in event["expected_sources"]:
        state["coverage"].setdefault(source, False)
    state["coverage"][m.source_id] = outcome.kind not in ("UNAVAILABLE", "QUARANTINE")
    evidence_sha = digest(event)
    for record in state["opportunities"].values():
        previous = OpportunityState.model_validate_json(json.dumps(record["state"]))
        if (
            previous.owner == m.owner
            and previous.phase not in ("COMMITTED_ONCE", "MISSED")
            and now >= previous.deadline_ms
        ):
            transition = advance(
                previous,
                event="MISS",
                evidence_sha=evidence_sha,
                at_ms=now,
                actor="PAPER",
                guard="IMMUTABLE_DEADLINE_EXPIRED",
            )
            record["state"] = transition.successor.model_dump(mode="json")
            record["history"].append(transition.model_dump(mode="json"))
            old_result = state["outcomes"].get(record["effect_key"])
            if old_result:
                old_result.update(status="MISSED", opportunity=record["state"], reasons=["EXPIRED"])
    result = {
        "status": "MISSED",
        "source_id": outcome.source_id,
        "outcome_id": outcome.outcome_id,
        "signal_id": outcome.signal_id,
        "coverage_complete": all(state["coverage"].values()),
        "opportunity": None,
        "reasons": [],
        "execution": None,
        "order_route": "NONE",
        "modeled_only": True,
    }
    if outcome.kind in ("UNAVAILABLE", "QUARANTINE"):
        result.update(status="COVERAGE_GAP", reasons=list(outcome.reasons))
    elif lifecycle.baseline_outcome_id == outcome.outcome_id or outcome.kind == "BASELINE":
        result["status"] = "BASELINE"
    elif outcome.kind in ("UNCHANGED", "RECOVERY_BASELINE"):
        result["status"] = outcome.kind
    else:
        deadline = min(
            outcome.checkpoint_ms + GRID_MS,
            m.effective_until_ms,
            min(r.state_ms for r in outcome.sample.receipts)
            + outcome.sample.limits.max_state_age_ms,
        )
        opportunity_id = digest(["checkpoint_opportunity_v3", m.owner, outcome.signal_id])
        record = state["opportunities"].setdefault(
            opportunity_id,
            {
                "state": OpportunityState(
                    opportunity_id=opportunity_id,
                    owner=m.owner,
                    signal_id=outcome.signal_id,
                    deadline_ms=deadline,
                ).model_dump(mode="json"),
                "history": [],
                "effect_key": effect_key,
            },
        )

        def move(action, guard, *, no_side_effect=False):
            before = OpportunityState.model_validate_json(json.dumps(record["state"]))
            transition = advance(
                before,
                event=action,
                evidence_sha=evidence_sha,
                at_ms=now,
                actor="PAPER",
                guard=guard,
                no_side_effect=no_side_effect,
            )
            record["state"] = transition.successor.model_dump(mode="json")
            record["history"].append(transition.model_dump(mode="json"))
            result.update(status=transition.successor.phase, opportunity=record["state"])
            if guard not in ("COMPLETE_PROOF", "MODELED_ATTEMPT"):
                result["reasons"].append(guard)

        if record["state"]["phase"] == "MISSED":
            result.update(status="MISSED", opportunity=record["state"], reasons=["EXPIRED"])
        elif (
            now >= deadline or lifecycle.phase != "ACTIVE" or event["source_phase"] != "CONTINUOUS"
        ):
            move("MISS", "EXPIRED_OR_INACTIVE_OR_SOURCE_FENCED")
        else:
            move("REVIEW", "COMPLETE_PROOF", no_side_effect=True)
            try:
                marks = _marks(outcome, event["originals"])
                if set(marks) != {p.instrument for p in outcome.positions}:
                    raise ValueError("NATIVE_SOURCE_MARK_UNAVAILABLE")
                proposed, observations = _proposal(account, m, outcome, marks, event)
            except (KeyError, ValueError) as exc:
                move("BLOCK", str(exc), no_side_effect=True)
            else:
                quotes = {k: q.mark for k, q in observations.items()}
                account.mark(quotes, event["event_at"])
                shocks = tuple(
                    {Instrument.parse(k): number(v) for k, v in row.items()}
                    for row in event["policy"]["shocks"]
                )
                own = proposed.get(m.owner, {})
                used = max(ZERO, -account.pm_equity_pnl().get(m.owner, ZERO))
                stress = max((loss_under_shock(own, quotes, row) for row in shocks), default=ZERO)
                gross = sum(
                    (abs(q * quotes[k]) for book in proposed.values() for k, q in book.items()),
                    ZERO,
                )
                if used + stress > number(event["policy"]["pod_loss_limit"]) or gross > number(
                    event["policy"]["max_gross_notional"]
                ):
                    move("MISS", "POD_OR_GROSS_RISK_LIMIT")
                else:
                    evidence = RiskEvidence(
                        True, True, True, True, False, "FORWARD_PAPER_SIMULATED_v1", False
                    )
                    decision = classify(account, proposed, quotes, shocks, evidence, risk_policy)
                    result["requested_targets"] = {
                        owner: {k.key: str(q) for k, q in book.items()}
                        for owner, book in proposed.items()
                    }
                    result["risk"] = {
                        "state": decision["state"],
                        "reasons": decision["reason_codes"],
                        "worst_stress_loss": decision["worst_stress_loss"],
                        "headroom": decision["headroom"],
                    }
                    # Existing generations and unavailable leaders retain their exact inventory.
                    unchanged = all(
                        decision["approved"].get(owner, {}) == book
                        for owner, book in account.pm_quantities.items()
                        if owner != m.owner
                    )
                    if not decision["approved_new_risk"] or not unchanged:
                        move("MISS", "ACCOUNT_RISK_OR_RESIDUAL_PROTECTION")
                    else:
                        claims = []
                        target = account.external_targets(decision["approved"])
                        for inst in set(target) | set(account.quantities):
                            delta = target.get(inst, ZERO) - account.quantities.get(inst, ZERO)
                            if delta:
                                claim = digest(
                                    [
                                        inst.key,
                                        "BUY" if delta > 0 else "SELL",
                                        digest(event["quotes"][inst.key]),
                                    ]
                                )
                                if claim in state["consumed_quotes"]:
                                    break
                                claims.append(claim)
                        else:
                            move("COMMIT", "MODELED_ATTEMPT")
                            result["execution"] = execute_targets(
                                account,
                                decision["approved"],
                                observations,
                                costs,
                                decision_at=event["event_at"],
                                hypothetical_fill_at=event["event_at"],
                                permitted=True,
                            )
                            for claim in claims:
                                state["consumed_quotes"][claim] = opportunity_id
                        if result["status"] == "REVIEWABLE":
                            move("BLOCK", "QUOTE_ALREADY_CONSUMED", no_side_effect=True)
    state["outcomes"][effect_key] = result
    account.verify()
    return result


def _proposal(account, mandate, outcome, marks, event):
    proposed = deepcopy(account.pm_quantities)
    keys = {p.instrument for p in outcome.positions}
    if keys - set(mandate.allowed_markets):
        raise ValueError("CHECKPOINT_UNSUPPORTED_MARKET")
    keys |= {k.key for book in proposed.values() for k, q in book.items() if q}
    observations, native = {}, {}
    from .pm_forward_journal import PaperJournal

    for key in sorted(keys):
        raw = event["quotes"].get(key)
        if raw is None:
            raise ValueError("INDEPENDENT_FOLLOWER_QUOTE_MISSING")
        PaperJournal._validate_market_quote(raw)
        age = event["at_ms"] - int(clock(raw["source_event_at"]).timestamp() * 1000)
        if not 0 <= age <= event["policy"]["max_quote_age_ms"] or clock(
            raw["first_known_at"]
        ) > clock(event["event_at"]):
            raise ValueError("INDEPENDENT_FOLLOWER_QUOTE_STALE_OR_FUTURE")
        inst = Instrument.parse(key)
        market = _candidate_market(inst, event["catalog"], raw)
        native[key] = market
        observations[inst] = MarketObservation(
            instrument=inst,
            event_at=raw["source_event_at"],
            first_known_at=raw["first_known_at"],
            mark=number(raw["mid_quote"]),
            volume_base=None,
            quality="VERIFIED_QUOTE",
            supported=market.session_eligible,
            capacity_basis="DISPLAYED_L2_TOP_LEVEL",
            best_bid=number(raw["best_bid"]),
            best_ask=number(raw["best_ask"]),
            bid_size=number(raw["bid_size"]),
            ask_size=number(raw["ask_size"]),
            quantity_step=market.amount_step,
            minimum_notional=market.minimum_notional,
        )
    own = {}
    for position in outcome.positions:
        inst = Instrument.parse(position.instrument)
        market = native[position.instrument]
        raw = event["quotes"][position.instrument]
        executable = number(raw["best_ask"] if position.quantity > 0 else raw["best_bid"])
        value = position.quantity * number(marks[position.instrument]) * mandate.k / executable
        value = (
            (abs(value) / market.amount_step).to_integral_value(rounding=ROUND_DOWN)
            * market.amount_step
            * (1 if value > 0 else -1)
        )
        if value and abs(value) * executable >= market.minimum_notional:
            own[inst] = value
    proposed[mandate.owner] = own
    return proposed, observations
