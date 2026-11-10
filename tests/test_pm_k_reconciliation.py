"""Cross-check Track C reconciliation with the real PM03/PM04 in-memory wire.

The imported policy/account comes from the owning financial code. All tests
are offline, with no financial database or trading transport.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from copytrade_pm.pm03_account import Account, Instrument, Rulebook, digest
from copytrade_pm.pm_forward_observed_paper import _policy
from copytrade_pm.pm_k_finance import PM03FinanceFrame, assess_finance
from copytrade_pm.pm_k_recalibration import evaluate_k, make_candidate
from copytrade_pm.pm_k_release import (
    audit_pending_original_k,
    publish_k_candidate,
    verify_cutover,
)
from test_pm_k_recalibration import AFTER, KEY, NOW, P, U, _input

BEFORE = "2026-11-01T00:00:00+00:00"


def _base_state(*, pending=False, inventory=False, risk_halt=False):
    policy = _policy()
    inst = Instrument.parse(KEY)
    rule = Rulebook(
        program="test",
        stage="fixture",
        source="independent-fixture",
        observed_at=BEFORE,
        version="v1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=D("1000"),
        daily_loss=D("500"),
        static_loss=D("1000"),
        trailing_loss=None,
        confirmed=True,
        account_terms_confirmed=True,
        permitted=(inst,),
        max_gross_leverage=D("2"),
    )
    account = Account.start(rule, BEFORE)
    account.pm04_state = {
        "policy": policy,
        "paper_execution": {
            "schema": "pm04_single_shot_intents_v2",
            "history": {
                "old": {
                    "status": "PENDING_5M",
                    "first_known_at": "2026-11-10T00:57:00+00:00",
                    "due_at": "2026-11-10T01:02:00+00:00",
                }
            }
            if pending
            else {},
            "active": {"S035": "old"} if pending else {},
            "exits": {},
            "unresolved_exposures": {},
        },
    }
    if inventory:
        account.pm_quantities["S035"] = {inst: D("0.01")}
        account.quantities[inst] = D("0.01")
        account.marks[inst] = D("100")
        account.entries[inst] = D("100")
        account.cash -= D("1")
        account.pm_cash["S035"] = D("-1")
    if risk_halt:
        account.latch_halt("TEST_RISK")
    account.verify()
    return account, policy


def _finance_study(*, finance_overrides=None, account=None, policy=None, k="0.02"):
    if account is None or policy is None:
        account, policy = _base_state()
    snap = account.snapshot()
    frame = {
        "rulebook": account.rulebook.to_dict(),
        "account_snapshot": snap,
        "account_snapshot_sha256": digest(snap),
        "pm04_policy": policy,
        "pm04_policy_sha256": digest(policy),
        "source_known_at": NOW,
        "quote_known_at": NOW,
        "account_known_at": NOW,
        "lot_steps": {KEY: D("0.001")},
        "minimum_notionals": {KEY: D("1")},
        "funding_complete": True,
        "capacity_complete": True,
        "pending_unknown_orders": False,
        "unresolved_exposures": False,
        "correlation_stress_usd": D("0"),
        "liquidity_stress_usd": D("0"),
    }
    frame.update(finance_overrides or {})
    return _input(
        pod_id="S035",
        current=str(policy["fixed_k_by_pod"]["S035"]),
        k=k,
        finance_frame=PM03FinanceFrame.model_validate(frame),
    )


def test_actual_pm03_clone_reuses_pm04_risk_and_preserves_original_state():
    acct, policy = _base_state()
    before = digest(acct.snapshot())
    study = _finance_study(account=acct, policy=policy)
    check = assess_finance(study, study.finance_frame)
    assert check["ok"], check["blockers"]
    assert check["approved_for_trading"] is False
    assert check["order_route"] == "NONE"
    assert digest(acct.snapshot()) == before
    # A conservative research reduction may be proposed without rewriting live k.
    proposal = evaluate_k(study)
    assert proposal.decision == "DECREASE"
    assert proposal.finance_check["ok"]
    assert digest(acct.snapshot()) == before


@pytest.mark.parametrize(
    "alter,expected",
    [
        ({"funding_complete": False}, "FUNDING_UNVERIFIED"),
        ({"capacity_complete": False}, "CAPACITY_UNVERIFIED"),
        ({"pending_unknown_orders": True}, "UNRESOLVED_FINANCIAL_EFFECTS"),
        ({"unresolved_exposures": True}, "UNRESOLVED_FINANCIAL_EFFECTS"),
        ({"source_known_at": BEFORE}, "ACCOUNT_SOURCE_OR_QUOTE_STALE"),
        ({"minimum_notionals": {KEY: D("100")}}, "NATIVE_LOT_OR_MINIMUM_NOTIONAL"),
    ],
)
def test_real_finance_frame_missing_evidence_blocks(alter, expected):
    proposal = evaluate_k(_finance_study(finance_overrides=alter))
    assert expected in proposal.reasons
    assert proposal.finance_check["ok"] is False
    assert proposal.decision == "INSUFFICIENT_EVIDENCE"


def test_risk_halt_and_pending_entry_noninterference():
    for kwargs, expected in [
        ({"risk_halt": True}, "PM03_RISK_NOT_GREEN"),
        ({"pending": True}, "PENDING_T300_OR_UNRESOLVED"),
        ({"inventory": True}, "NATIVE_LOT_OR_MINIMUM_NOTIONAL"),
    ]:
        account, policy = _base_state(**kwargs)
        old_sha = digest(account.snapshot())
        proposal = evaluate_k(_finance_study(account=account, policy=policy))
        if kwargs.get("inventory"):
            assert proposal.finance_check is not None
            assert proposal.finance_check["order_route"] == "NONE"
        else:
            assert expected in proposal.reasons
        assert proposal.decision == "INSUFFICIENT_EVIDENCE"
        assert digest(account.snapshot()) == old_sha


def test_snapshot_and_policy_sha_tampering_refused():
    acct, pol = _base_state()
    study = _finance_study(account=acct, policy=pol)
    row = study.finance_frame.model_dump(mode="python")
    row["account_snapshot_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="PM03_ACCOUNT_SNAPSHOT_SHA_MISMATCH"):
        PM03FinanceFrame.model_validate(row)
    row = study.finance_frame.model_dump(mode="python")
    row["pm04_policy_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="PM04_POLICY_SNAPSHOT_SHA_MISMATCH"):
        PM03FinanceFrame.model_validate(row)


def _candidate():
    acct, policy = _base_state()
    p = evaluate_k(_input(pod_id="S035", k="0.01", current="0.01"))
    assert p.decision == "HOLD"
    candidate = make_candidate(
        portfolio_version=p.portfolio_version,
        portfolio_definition_sha256=P,
        pod_membership=("S035",),
        sizing_policy_version=p.sizing_policy_version,
        cost_policy_version=p.cost_policy_version,
        risk_policy_version=p.risk_policy_version,
        effective_at=AFTER,
        proposed_at=NOW,
        rollback_release_sha256=U,
        proposals=(p,),
        current_policy_sha256=digest(policy),
    )
    return candidate, acct, policy


def test_actual_paper_formats_pending_t180_and_inventory_block(tmp_path):
    candidate, _, policy = _candidate()
    for opts, expected in [
        ({"pending": True}, "PENDING_T300_ORIGINAL_K_NOT_PINNED"),
        ({"inventory": True}, "OPEN_INVENTORY_NEEDS_EXPLICIT_LEGACY_K"),
        ({"risk_halt": True}, "PERSISTENT_PM03_RISK_RESTRICTION"),
        ({}, "RUNTIME_RELEASE_CONSUMER_NOT_VERSION_AWARE"),
    ]:
        account, actual_policy = _base_state(**opts)
        assert actual_policy == policy
        snap = account.snapshot()
        original = digest(snap)
        receipt = verify_cutover(
            candidate,
            paper_snapshot=snap,
            paper_snapshot_sha256=original,
            current_policy=policy,
            checked_at="2026-11-10T02:00:00+00:00",
            observed_release_sha256=U,
        )
        assert receipt["status"] == "BLOCKED_NONACTIVATING"
        assert expected in receipt["blockers"]
        assert not receipt["shadow_deployed"] and receipt["order_route"] == "NONE"
        assert digest(snap) == original
    first = publish_k_candidate(candidate, tmp_path / "cache")
    second = publish_k_candidate(candidate, tmp_path / "cache")
    assert first["cache_status"] == "CACHE_CREATED"
    assert second["cache_status"] == "CACHE_HIT"
    assert first["package_sha256"] == second["package_sha256"]
    assert not second["signature_verified"] and not second["shadow_deployed"]


def _authentic_v2_pending(policy):
    known = "2026-11-10T00:57:00+00:00"
    source_sha = "f" * 64
    return {
        "intent_id": "e" * 64,
        "pod": "S035",
        "source_seq": 1,
        "source_sha": source_sha,
        "source_event_at": "2026-11-10T00:56:00+00:00",
        "first_known_at": known,
        "due_at": "2026-11-10T01:02:00+00:00",
        "deadline_at": "2026-11-10T01:02:30+00:00",
        "created_at": known,
        "updated_at": known,
        "status": "PENDING_5M",
        "positions": {KEY: "2"},
        "updates": [{"at": known, "source_seq": 1, "source_sha": source_sha}],
        "frozen_k": str(policy["fixed_k_by_pod"]["S035"]),
        "release_sha256": digest(policy),
    }


def test_version_pinned_t300_receipt_is_recognized_but_never_promoted():
    candidate, account, policy = _candidate()
    pending = _authentic_v2_pending(policy)
    execution = account.pm04_state["paper_execution"]
    execution["history"] = {pending["intent_id"]: pending}
    execution["active"] = {"S035": pending["intent_id"]}
    original = digest(account.snapshot())
    audit = audit_pending_original_k(
        history=execution["history"], active=execution["active"], current_policy=policy
    )
    assert audit["status"] == "BOUND_ORIGINAL_K_RESEARCH_ONLY"
    assert audit["pending"] == 1 and audit["pinned"] == 1 and audit["legacy"] == 0
    receipt = verify_cutover(
        candidate,
        paper_snapshot=account.snapshot(),
        paper_snapshot_sha256=original,
        current_policy=policy,
        checked_at="2026-11-10T02:00:00+00:00",
        observed_release_sha256=U,
    )
    assert receipt["pending_original_k_audit"] == audit
    assert "PENDING_T300_ORIGINAL_K_NOT_PINNED" not in receipt["blockers"]
    assert "INDEPENDENT_ORIGINAL_FINANCE_REPORT_PROOF_REQUIRED" in receipt["blockers"]
    assert "RUNTIME_RELEASE_CONSUMER_NOT_VERSION_AWARE" in receipt["blockers"]
    assert receipt["status"] == "BLOCKED_NONACTIVATING"
    assert not receipt["paper_journal_mutated"] and not receipt["active_policy_changed"]
    assert digest(account.snapshot()) == original


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ({"frozen_k": "0.08"}, "PENDING_T300_ORIGINAL_K_RELEASE_DRIFT"),
        ({"release_sha256": "0" * 64}, "PENDING_T300_ORIGINAL_K_RELEASE_DRIFT"),
        ({"frozen_k": None}, "PENDING_T300_ORIGINAL_K_NOT_PINNED"),
        ({"due_at": "2026-11-10T01:01:00+00:00"}, "PENDING_T300_ORIGINAL_K_INTEGRITY_INVALID"),
        ({"source_seq": 2}, "PENDING_T300_ORIGINAL_K_INTEGRITY_INVALID"),
        ({"intent_id": "c" * 64}, "PENDING_T300_ACTIVE_IDENTITY_MISMATCH"),
    ],
)
def test_pinned_t300_tampering_fails_without_mutating_finance(tamper, expected):
    account, policy = _base_state()
    pending = {**_authentic_v2_pending(policy), **tamper}
    execution = account.pm04_state["paper_execution"]
    original_id = "e" * 64
    execution["history"] = {original_id: pending}
    execution["active"] = {"S035": original_id}
    before = digest(account.snapshot())
    receipt = audit_pending_original_k(
        history=execution["history"], active=execution["active"], current_policy=policy
    )
    assert expected in receipt["blockers"]
    assert receipt["status"] == "BLOCKED"
    assert digest(account.snapshot()) == before


def test_malformed_active_pointer_or_non_dict_history_fail_closed():
    account, policy = _base_state()
    pending = _authentic_v2_pending(policy)
    row = {pending["intent_id"]: pending}
    for active in ({"S035": "0" * 64}, {"S035": pending["intent_id"], "OTHER": "f" * 64}):
        result = audit_pending_original_k(history=row, active=active, current_policy=policy)
        assert "PENDING_T300_ACTIVE_IDENTITY_MISMATCH" in result["blockers"]
    assert (
        "INVALID_PAPER_OPPORTUNITY_HISTORY"
        in audit_pending_original_k(history=[], active={}, current_policy=policy)["blockers"]
    )


def test_unmatched_policy_hash_and_wrong_release_are_blocked():
    candidate, acct, policy = _candidate()
    snap = acct.snapshot()
    for old, current, mismatch in [
        (U, {**policy, "max_gross_notional": "100000"}, "FROZEN_PM04_POLICY_HASH_MISMATCH"),
        ("f" * 64, policy, "ROLLBACK_RELEASE_IDENTITY_MISMATCH"),
    ]:
        result = verify_cutover(
            candidate,
            paper_snapshot=snap,
            paper_snapshot_sha256=digest(snap),
            current_policy=current,
            checked_at="2026-11-10T02:00:00+00:00",
            observed_release_sha256=old,
        )
        assert mismatch in result["blockers"]


def test_mutated_nested_proposal_and_release_cannot_be_published(tmp_path):
    candidate, acct, policy = _candidate()
    # Frozen Pydantic models do not deep-freeze nested dicts; force a mutation
    # and prove the publication boundary revalidates the original SHA.
    candidate.proposals[0].paired_economics["independent_blocks"] = 999
    with pytest.raises(ValidationError, match="K_PROPOSAL_SHA_MISMATCH"):
        publish_k_candidate(candidate, tmp_path)
    with pytest.raises(ValidationError, match="K_PROPOSAL_SHA_MISMATCH"):
        verify_cutover(
            candidate,
            paper_snapshot=acct.snapshot(),
            paper_snapshot_sha256=digest(acct.snapshot()),
            current_policy=policy,
            checked_at="2026-11-10T02:00:00+00:00",
            observed_release_sha256=U,
        )


def test_unauthenticated_prospective_label_cannot_increase_even_with_finance_frame():
    study = _finance_study(k="0.04")
    proposal = evaluate_k(study)
    assert proposal.decision == "INSUFFICIENT_EVIDENCE"
    assert "INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED" in proposal.reasons
