"""PM03 consumes the shared kernel decision, including Q15 opening memory.

Forward reviews carry ``checkpoint_decision_q15_v1``.  Each new review hands the
kernel real normalized ``DecisionInputs`` and consumes its risk decision, native
targets and net order intents; the paper shell only simulates the fills and signs
the event.  Pre-cutover rows keep replaying through the frozen body.
"""

from decimal import Decimal as D
import json

from copytrade_kernel import Q15_REJECTION

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_checkpoint_decision import DECISION_VERSION, SEMANTICS_FIELD
from copytrade_pm.pm_checkpoint_journal import CheckpointOutcome
from copytrade_pm.pm_copy_mandate_journal import baseline
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_mandate import SignedMandate, state_parse
from copytrade_pm.pm_wire_evidence import read_wire
from test_checkpoint_paper import (
    BTC,
    GRID,
    checkpoint,
    consume,
    quote,
    setup_paper,
)
from test_checkpoint_source import BOUNDARY
from test_pm_forward_ccxt_market import ccxt_market

LEGACY_EFFECT = "checkpoint_paper_effect_v3"

#: seq, event_id, input_sha, prior_sha, post_sha, chain_sha of two pre-cutover
#: reviews, captured by replaying the same deterministic scenario on ``HEAD``.
LEGACY_GOLDEN = [
    [
        1,
        "e9ffedea69be2b9aeecd6d59b2f2945c766c1156cd7ec0cf6935c86eec8a974f",
        "9b524994bae527d885befe17e41a5947d28f573c1f177b29cd31dc46de84df0d",
        "3e6f10fa5b8df3264e32f11796f11c629d299e8dfc2c8bc8e54a7e99e3bb3b87",
        "8034c4df1d6bf4a0886f37fb974a8325c5390719a4359e45cb120914158cc03c",
        "143cf5e2a0c662c117b15a6d639b4df836c8c5afec87276c05377162f4cb6277",
    ],
    [
        2,
        "895dbca1ae5dd280bc68df214be6c5c73686a54a36278e65904343e09e523a38",
        "e19b3ebdd4d778094fcb9c8f419242ea168b6820c23edab7221eaa02b7da7743",
        "8034c4df1d6bf4a0886f37fb974a8325c5390719a4359e45cb120914158cc03c",
        "4ae4672fe4d76938dddab87b7a3457ee446749fbec46abb3a4143bbf3fde4934",
        "f19ac8f3e9f52898e3158326d2ca351bca61b041bbf2535d7410c4adaac35703",
    ],
]


def state_of(journal, run="p1"):
    return journal.restore(run)["account"]["pm04"]["checkpoint_v3"]


def entry_memory(journal, run="p1"):
    return state_of(journal, run).get("entry_memory", {})


def missed_opening(journal, source_policy, m, p):
    """Baseline, then a changed checkpoint whose opening opportunity expires."""
    assert (
        consume(journal, m, checkpoint(journal, source_policy, 0), p, BOUNDARY + 102)["status"]
        == "BASELINE"
    )
    changed = checkpoint(journal, source_policy, 1, "3")
    now = BOUNDARY + GRID + 102
    blocked = consume(journal, m, changed, p, now)
    assert blocked["status"] == "PRE_DISPATCH_BLOCKED"
    missed = consume(journal, m, changed, p, blocked["opportunity"]["deadline_ms"])
    assert missed["status"] == "MISSED"
    return changed, missed


def test_q15_miss_is_retained_through_reduction_and_rebound(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    missed_outcome, missed = missed_opening(j, sp, m, p)
    assert missed["reasons"] == ["EXPIRED"]
    assert entry_memory(j) == {
        m.owner: {BTC.key: {"missed_at": missed_outcome.checkpoint_ms, "qty_at_miss": "3"}}
    }
    assert not j.restore("p1")["account"]["quantities"]

    # A same-sign decrease, a rebound below the miss and the unchanged quantity
    # are all refused by the kernel's owner-local opening memory.
    for index, quantity in ((2, "1"), (3, "2"), (4, "3")):
        now = BOUNDARY + index * GRID + 102
        quote(j, now)
        result = consume(j, m, checkpoint(j, sp, index, quantity), p, now + 2)
        assert result["status"] == "MISSED", (quantity, result["reasons"])
        assert result["reasons"] == [Q15_REJECTION]
        assert "net_intents" not in result and "kernel_decision" not in result
        assert not j.restore("p1")["account"]["quantities"]
    # ``qty_at_miss`` is retained, never rewritten by the smaller retries.
    assert entry_memory(j) == {
        m.owner: {BTC.key: {"missed_at": missed_outcome.checkpoint_ms, "qty_at_miss": "3"}}
    }

    # A genuine increase unlocks exactly one attempt, sized by the kernel.
    now = BOUNDARY + 5 * GRID + 102
    quote(j, now)
    result = consume(j, m, checkpoint(j, sp, 5, "4"), p, now + 2)
    assert result["status"] == "COMMITTED_ONCE"
    assert D(j.restore("p1")["account"]["quantities"][BTC.key]) == D("0.09999")
    assert result["net_intents"] == [
        {
            "market": BTC.key,
            "net_delta_qty": "0.09999",
            "reduce_only": False,
            "owner_allocations": [[m.owner, "0.09999"]],
        }
    ]
    # The proven entry clears the owner's opening memory.
    assert entry_memory(j) == {}


def test_q15_miss_does_not_block_a_flip(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    missed_outcome, _ = missed_opening(j, sp, m, p)
    now = BOUNDARY + 2 * GRID + 102
    quote(j, now)
    result = consume(j, m, checkpoint(j, sp, 2, "-3"), p, now + 2)
    assert result["status"] == "COMMITTED_ONCE"
    quantity = D(j.restore("p1")["account"]["quantities"][BTC.key])
    assert quantity < 0 and abs(quantity) == D("0.075")
    assert result["net_intents"][0]["reduce_only"] is False
    assert D(result["net_intents"][0]["net_delta_qty"]) == quantity
    assert entry_memory(j) == {}
    assert DECISION_VERSION == state_of(j)[SEMANTICS_FIELD]


def test_pm03_consumes_the_kernel_reduction_scale(tmp_path):
    # A pod budget only the half-size book satisfies: the kernel, not PM03,
    # chooses 0.5 and PM03 reports the label that scale implies.
    j, sp, m, p = setup_paper(tmp_path, overrides={"pod_loss_limit": "45"})
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    now = BOUNDARY + GRID + 102
    quote(j, now)
    result = consume(j, m, checkpoint(j, sp, 1, "3"), p, now + 2)
    assert result["status"] == "COMMITTED_ONCE"
    assert result["kernel_decision"]["scale"] == "0.5"
    assert result["risk"]["state"] == "ORANGE"
    assert D(result["requested_targets"][m.owner][BTC.key]) == D("0.07499")
    assert D(result["approved_targets"][m.owner][BTC.key]) == D("0.03749")
    assert D(j.restore("p1")["account"]["quantities"][BTC.key]) == D("0.03749")
    assert result["net_intents"][0]["net_delta_qty"] == "0.03749"


def test_kernel_risk_veto_keeps_the_paper_account_flat(tmp_path):
    j, sp, m, p = setup_paper(tmp_path, overrides={"max_gross_notional": "100"})
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    now = BOUNDARY + GRID + 102
    quote(j, now)
    result = consume(j, m, checkpoint(j, sp, 1, "3"), p, now + 2)
    assert result["status"] == "MISSED"
    assert result["kernel_risk"] == {"status": "NO_TRADE"}
    assert any(reason.startswith("KERNEL_RISK:") for reason in result["reasons"])
    assert not j.restore("p1")["account"]["quantities"]
    assert result["order_route"] == "NONE"


def test_replay_after_reopen_keeps_q15_memory_and_the_same_decision(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    missed_opening(j, sp, m, p)
    now = BOUNDARY + 2 * GRID + 102
    quote(j, now)
    suppressed = checkpoint(j, sp, 2, "1")
    first = consume(j, m, suppressed, p, now + 2)
    assert first["reasons"] == [Q15_REJECTION]
    before = j.restore("p1")
    assert state_of(j)["entry_memory"][m.owner][BTC.key]["qty_at_miss"] == "3"

    reopened = PaperJournal(j.root)
    assert reopened.restore("p1") == before
    # Re-open replays every event through the same apply path: the terminal
    # decision is byte-identical and the retained miss is still there.
    assert consume(reopened, m, suppressed, p, now + 3) == first
    assert reopened.restore("p1") == before


def legacy_event(journal, run_id, owner, outcome_id, *, at_ms, paper_policy, catalog):
    """Build the exact pre-cutover v3 row shape from the journal's own evidence."""
    with journal.writer() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT mandate,state,approval,authority_public FROM copy_mandate_heads WHERE owner=?",
            (owner,),
        ).fetchone()
        m = SignedMandate.from_json(row[0])
        current = state_parse(row[1])
        stream, raw_outcome = db.execute(
            "SELECT stream,outcome FROM cwsa_outcomes WHERE json_extract(outcome,'$.outcome_id')=?",
            (outcome_id,),
        ).fetchone()
        outcome = CheckpointOutcome.model_validate_json(raw_outcome)
        if (
            current.phase == "AWAITING_BASELINE"
            and outcome.sample is not None
            and outcome.sample.kind == "COMPLETE"
        ):
            current = baseline(db, owner, outcome_id, at_ms=at_ms)
        raw_head, head_sha = db.execute(
            "SELECT state,head FROM cwsa_heads WHERE stream=?", (stream,)
        ).fetchone()
        assert outcome.sample is not None
        originals = {
            receipt.raw_sha: read_wire(journal.path, receipt.raw_sha)
            for receipt in outcome.sample.receipts
        }
        snapshot = journal.verify(db, run_id)["account"]
        keys = set(m.allowed_markets) | {
            key for book in snapshot.get("pm_quantities", {}).values() for key in book
        }
        from copytrade_pm.pm_forward_observed_paper import read_quote

        quotes = {key: value for key in sorted(keys) if (value := read_quote(db, key)) is not None}
        event = {
            "kind": "CWSA_PAPER_REVIEW",
            "run_id": run_id,
            "event_at": __import__("copytrade_pm.pm_checkpoint_paper", fromlist=["at"]).at(at_ms),
            "at_ms": at_ms,
            "mandate": m.data,
            "mandate_state": current.data,
            "approval": json.loads(row[2]),
            "authority_public": row[3],
            "outcome": outcome.model_dump(mode="json"),
            "source_head_sequence": json.loads(raw_head)["sequence"],
            "source_head_sha": head_sha,
            "source_phase": json.loads(raw_head)["phase"],
            "originals": originals,
            "policy": paper_policy,
            "quotes": quotes,
            "catalog": catalog,
            "expected_sources": sorted(
                {
                    SignedMandate.from_json(item[0]).source_id
                    for item in db.execute(
                        "SELECT mandate FROM copy_mandate_heads WHERE account_id=?",
                        (m.account_id,),
                    )
                }
            ),
            "order_route": "NONE",
            "evidence_class": "CWSA_MODELED_FOLLOWER_V3",
        }
        journal.append_locked(db, run_id, digest([LEGACY_EFFECT, event]), event)
        db.execute("COMMIT")
    return event, journal.restore(run_id)


def test_pre_cutover_rows_are_byte_identical_to_the_pre_cutover_golden_vector(
    tmp_path, monkeypatch
):
    """Frozen hashes captured from the pre-cutover tree must still reproduce.

    ``LEGACY_GOLDEN`` was produced by running the same deterministic scenario
    (fixed authority key, signed mandate, CWSA samples, quote, policy) against
    ``HEAD`` of this repository, i.e. before the kernel decision cutover.  A
    changed event id, input hash, post-state hash or chain hash would make an
    existing journal fail ``verify`` after the upgrade.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    monkeypatch.setattr(
        Ed25519PrivateKey,
        "generate",
        classmethod(lambda cls: Ed25519PrivateKey.from_private_bytes(bytes([7]) * 32)),
    )
    j, sp, m, p = setup_paper(tmp_path)
    baseline_outcome = checkpoint(j, sp, 0)
    assert isinstance(baseline_outcome, CheckpointOutcome)
    first, _ = legacy_event(
        j,
        "p1",
        m.owner,
        baseline_outcome.outcome_id,
        at_ms=BOUNDARY + 102,
        paper_policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    changed = checkpoint(j, sp, 1, "3")
    assert isinstance(changed, CheckpointOutcome)
    now = BOUNDARY + GRID + 102
    quote(j, now)
    second, restored = legacy_event(
        j,
        "p1",
        m.owner,
        changed.outcome_id,
        at_ms=now + 2,
        paper_policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    assert "decision_version" not in first and "decision_version" not in second
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(j.path)) as db:
        rows = [
            list(row)
            for row in db.execute(
                "SELECT seq,event_id,input_sha,prior_sha,post_sha,chain_sha FROM events ORDER BY seq"
            )
        ]
    assert rows == LEGACY_GOLDEN
    assert restored["cursor"] == 2
    assert D(restored["account"]["quantities"][BTC.key]) == D("0.05624")
    assert PaperJournal(j.root).restore("p1") == restored


def test_pre_cutover_row_still_replays_through_the_frozen_body(tmp_path):
    """A v3 row keeps its old paper-tier decision, untouched by the kernel path."""
    j, sp, m, p = setup_paper(tmp_path)
    baseline_outcome = checkpoint(j, sp, 0)
    assert isinstance(baseline_outcome, CheckpointOutcome)
    legacy_event(
        j,
        "p1",
        m.owner,
        baseline_outcome.outcome_id,
        at_ms=BOUNDARY + 102,
        paper_policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    changed = checkpoint(j, sp, 1, "3")
    assert isinstance(changed, CheckpointOutcome)
    now = BOUNDARY + GRID + 102
    quote(j, now)
    event, restored = legacy_event(
        j,
        "p1",
        m.owner,
        changed.outcome_id,
        at_ms=now + 2,
        paper_policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    assert "decision_version" not in event
    result = restored["account"]["pm04"]["checkpoint_v3"]["outcomes"][
        digest(["p1", m.owner, changed.outcome_id])
    ]
    # Frozen pre-cutover semantics: the paper tier scales 0.75 and the kernel was
    # only asked for the fixed-k request (no DecisionInputs).
    assert result["status"] == "COMMITTED_ONCE"
    assert result["risk"]["state"] == "YELLOW"
    assert D(result["requested_targets"][m.owner][BTC.key]) == D("0.07499")
    assert D(restored["account"]["quantities"][BTC.key]) == D("0.05624")
    assert "net_intents" not in result and "approved_targets" not in result
    assert SEMANTICS_FIELD not in restored["account"]["pm04"]["checkpoint_v3"]
    assert "entry_memory" not in restored["account"]["pm04"]["checkpoint_v3"]

    # Reopen replays the legacy row with identical state and chain integrity.
    reopened = PaperJournal(j.root)
    assert reopened.restore("p1") == restored
    assert (
        reopened.consume_checkpoint(
            "p1",
            m.owner,
            changed.outcome_id,
            at_ms=now + 3,
            policy=p,
            catalog={"BTC/USDC:USDC": ccxt_market()},
        )
        == result
    )

    # A legacy miss keeps the frozen behaviour too: no Q15 memory is invented
    # for a journal that never recorded a forward decision.
    later = checkpoint(j, sp, 2, "4")
    assert isinstance(later, CheckpointOutcome)
    quote(j, BOUNDARY + 2 * GRID + 200)
    _, after = legacy_event(
        j,
        "p1",
        m.owner,
        later.outcome_id,
        at_ms=BOUNDARY + 3 * GRID,
        paper_policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    missed = after["account"]["pm04"]["checkpoint_v3"]["outcomes"][
        digest(["p1", m.owner, later.outcome_id])
    ]
    assert missed["status"] == "MISSED"
    assert "entry_memory" not in after["account"]["pm04"]["checkpoint_v3"]
    assert SEMANTICS_FIELD not in after["account"]["pm04"]["checkpoint_v3"]
    assert D(after["account"]["quantities"][BTC.key]) == D("0.05624")
    assert PaperJournal(j.root).restore("p1") == after


def test_forward_row_cannot_be_followed_by_a_legacy_row(tmp_path):
    import pytest

    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    changed = checkpoint(j, sp, 1, "3")
    assert isinstance(changed, CheckpointOutcome)
    now = BOUNDARY + GRID + 102
    quote(j, now)
    consume(j, m, changed, p, now + 2)
    assert SEMANTICS_FIELD in state_of(j)
    with pytest.raises(ValueError, match="CHECKPOINT_DECISION_SEMANTICS_DOWNGRADE"):
        legacy_event(
            j,
            "p1",
            m.owner,
            changed.outcome_id,
            at_ms=now + 4,
            paper_policy=p,
            catalog={"BTC/USDC:USDC": ccxt_market()},
        )


def test_kernel_inputs_carry_the_owner_book_and_net_intents(tmp_path):
    """Second checkpoint: the kernel sees real inventory and emits a reduction."""
    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    now = BOUNDARY + GRID + 102
    quote(j, now)
    first = consume(j, m, checkpoint(j, sp, 1, "3"), p, now + 2)
    assert first["status"] == "COMMITTED_ONCE"
    now = BOUNDARY + 2 * GRID + 102
    quote(j, now)
    reduced = consume(j, m, checkpoint(j, sp, 2, "1"), p, now + 2)
    assert reduced["status"] == "COMMITTED_ONCE"
    assert reduced["approved_targets"][m.owner][BTC.key] == "0.02499"
    assert reduced["net_intents"] == [
        {
            "market": BTC.key,
            "net_delta_qty": "-0.05",
            "reduce_only": True,
            "owner_allocations": [[m.owner, "-0.05"]],
        }
    ]
    assert D(j.restore("p1")["account"]["quantities"][BTC.key]) == D("0.02499")
