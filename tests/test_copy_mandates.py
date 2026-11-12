"""Immutable signed mandate and explicit lifecycle at the paper contract boundary."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from copytrade_pm.pm_copy_mandate import (
    CopyMandate,
    MandateState,
    transition_mandate,
    verify_mandate,
)
from copytrade_pm.production_manifest import sign
from test_checkpoint_source import BOUNDARY


def mandate(generation=1, start=BOUNDARY):
    return CopyMandate(
        mandate_id="fixture-copy",
        generation=generation,
        source_id="fixture-leader",
        source_scope_generation="a" * 64,
        source_account_sha="b" * 64,
        account_id="fixture-account",
        pod_id="pod-a",
        k="0.025",
        allowed_markets=("hyperliquid/mainnet:perp:default/BTC",),
        policy_epoch="c" * 64,
        risk_policy_sha="d" * 64,
        rulebook_sha="e" * 64,
        effective_from_ms=start,
        effective_until_ms=start + 3_600_000,
    )


def test_signed_generation_is_frozen_and_destination_activation_never_copies_current():
    m = mandate()
    key = Ed25519PrivateKey.generate()
    envelope = sign(m.model_dump(mode="json"), key, "copy-mandate-v1")
    verified = verify_mandate(envelope, key.public_key(), account_id="fixture-account")
    assert verified == m
    before = MandateState.initial(m)
    activated = transition_mandate(
        m, before, event="ACTIVATE", evidence_sha="1" * 64, at_ms=BOUNDARY - 1
    )
    assert activated.successor.phase == "AWAITING_BASELINE"
    baseline = transition_mandate(
        m,
        activated.successor,
        event="COMPLETE_BASELINE",
        evidence_sha="2" * 64,
        at_ms=BOUNDARY + 100,
        checkpoint_ms=BOUNDARY,
    )
    assert baseline.successor.phase == "ACTIVE"
    assert baseline.effect == "BASELINE_ONLY"
    pause = transition_mandate(
        m, baseline.successor, event="PAUSE", evidence_sha="3" * 64, at_ms=BOUNDARY + 101
    )
    assert pause.successor.phase == "PAUSED"
    assert pause.effect == "STOP_NEW_RISK_PRESERVE_OBLIGATIONS"
    resumed = transition_mandate(
        m, pause.successor, event="ACTIVATE", evidence_sha="4" * 64, at_ms=BOUNDARY + 102
    )
    assert resumed.effect == "REJECTED"
    assert resumed.successor.phase == "PAUSED"
    assert mandate(2, BOUNDARY + 300_000).sha != m.sha


def test_forged_in_place_and_wrong_destination_mandates_fail():
    key = Ed25519PrivateKey.generate()
    envelope = sign(mandate().model_dump(mode="json"), key, "copy-mandate-v1")
    with pytest.raises(ValueError):
        verify_mandate(
            envelope, Ed25519PrivateKey.generate().public_key(), account_id="fixture-account"
        )
    with pytest.raises(ValueError):
        verify_mandate(envelope, key.public_key(), account_id="other")
    envelope["payload"]["k"] = "0.05"
    with pytest.raises(ValueError):
        verify_mandate(envelope, key.public_key(), account_id="fixture-account")


def test_paper_journal_generations_pause_and_resume_preserve_shared_source(tmp_path):
    from copytrade_pm.pm_forward_journal import PaperJournal
    from copytrade_pm.production_manifest import digest
    from test_checkpoint_journal import register, sample
    from test_checkpoint_source import scope

    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    values = mandate().model_dump()
    values.update(source_account_sha=scope().account_sha, policy_epoch=policy.epoch)
    m = CopyMandate(**values)
    key = Ed25519PrivateKey.generate()
    envelope = sign(m.model_dump(mode="json"), key, "copy-mandate-v1")
    first = journal.activate_copy_mandate(
        envelope, key.public_key(), account_id=m.account_id, at_ms=BOUNDARY - 1
    )
    assert first.phase == "AWAITING_BASELINE"
    outcome = journal.append_checkpoint_sample(
        policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101
    )
    active = journal.baseline_copy_mandate(m.owner, outcome.outcome_id, at_ms=BOUNDARY + 102)
    assert active.phase == "ACTIVE"
    shared = journal.checkpoint_history(scope(), policy.epoch)
    revised = CopyMandate(
        **(
            m.model_dump()
            | {
                "generation": 2,
                "effective_from_ms": BOUNDARY + 300_000,
                "k": "0.03",
            }
        )
    )
    signed_new = sign(revised.model_dump(mode="json"), key, "copy-mandate-v1")
    with pytest.raises(ValueError, match="OVERLAP"):
        journal.activate_copy_mandate(
            signed_new, key.public_key(), account_id=m.account_id, at_ms=BOUNDARY + 102
        )
    command = sign(
        {
            "schema": "copy_mandate_control_v1",
            "owner": m.owner,
            "mandate_sha": m.sha,
            "predecessor_sha": active.sha,
            "event": "PAUSE",
            "issued_ms": BOUNDARY + 102,
            "expires_ms": BOUNDARY + 1000,
            "nonce": digest("pause"),
        },
        key,
        "copy-mandate-control-v1",
    )
    attacker = Ed25519PrivateKey.generate()
    forged = sign(command["payload"], attacker, "copy-mandate-control-v1")
    with pytest.raises(ValueError, match="AUTHORITY"):
        journal.control_copy_mandate(forged, attacker.public_key(), at_ms=BOUNDARY + 103)
    paused = journal.control_copy_mandate(command, key.public_key(), at_ms=BOUNDARY + 103)
    assert paused.phase == "PAUSED"
    assert journal.control_copy_mandate(command, key.public_key(), at_ms=BOUNDARY + 104) == paused
    next_generation = journal.activate_copy_mandate(
        signed_new, key.public_key(), account_id=m.account_id, at_ms=BOUNDARY + 105
    )
    assert next_generation.phase == "AWAITING_BASELINE"
    restarted = PaperJournal(journal.root)
    assert restarted.copy_mandate_state(m.owner) == paused
    assert restarted.checkpoint_history(scope(), policy.epoch) == shared
    altered = CopyMandate(**(m.model_dump() | {"k": "0.05"}))
    with pytest.raises(ValueError, match="GENERATION"):
        restarted.activate_copy_mandate(
            sign(altered.model_dump(mode="json"), key, "copy-mandate-v1"),
            key.public_key(),
            account_id=m.account_id,
            at_ms=BOUNDARY + 106,
        )
