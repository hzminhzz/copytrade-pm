"""ANOS-11: read-only native PM04 recovery interpretation (not broker authority)."""

from __future__ import annotations

import pytest

from copytrade_pm.pm_cwsa_chapter2_projection import explain_interrupted_paper
from copytrade_pm.pm_k_release import audit_pending_original_k
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_paper_contracts import PaperOpportunity


def opportunity(status="PENDING_5M") -> PaperOpportunity:
    data = {
        "intent_id": "a" * 64,
        "pod": "pod-A",
        "source_seq": 1,
        "source_sha": "b" * 64,
        "source_event_at": "2026-11-13T00:00:00+00:00",
        "first_known_at": "2026-11-13T00:00:00+00:00",
        "due_at": "2026-11-13T00:05:00+00:00",
        "deadline_at": "2026-11-13T00:05:30+00:00",
        "created_at": "2026-11-13T00:00:00+00:00",
        "updated_at": "2026-11-13T00:00:00+00:00",
        "status": "PENDING_5M",
        "positions": {"hyperliquid/mainnet:perp:default/BTC": "1"},
        "updates": [{"at": "2026-11-13T00:00:00+00:00", "source_seq": 1, "source_sha": "b" * 64}],
        "frozen_k": "0.025",
        "release_sha256": "c" * 64,
    }
    if status != "PENDING_5M":
        data.update(status=status, terminal_at="2026-11-13T00:05:00+00:00")
        if status in {"FILLED", "PARTIAL", "REJECTED"}:
            data["attempted_at"] = data["terminal_at"]
    return PaperOpportunity.model_validate(data)


def test_pending_is_owner_not_dispatched_only_for_virtual_paper():
    report = explain_interrupted_paper(opportunity(), observed_at="2026-11-13T00:04:00+00:00")
    assert report["dispatch_state"] == "NOT_DISPATCHED"
    assert report["intent_id"] == "a" * 64
    assert report["deadline_at"] == "2026-11-13T00:05:30+00:00"
    assert report["frozen_k"] == "0.025"
    assert report["mandate_generation"] is None
    assert report["guardian_authority"] == "UNKNOWN"
    assert report["order_route"] == "NONE"
    assert report["retry_authorized"] is False


def test_attempt_without_broker_proof_is_possible_dispatch_not_retry():
    for state in ("FILLED", "PARTIAL", "REJECTED"):
        report = explain_interrupted_paper(
            opportunity(state), observed_at="2026-11-13T00:06:00+00:00"
        )
        assert report["dispatch_state"] == "POSSIBLY_DISPATCHED"
        assert report["next_action"] == "RECONCILE_ORIGINAL_INTENT_WITH_GUARDIAN"
        assert report["retry_authorized"] is False
        assert report["original_obligation_preserved"] is True


def test_expired_and_cancelled_virtual_opportunity_never_reopen():
    for state in ("CANCELED", "CANCELED_SOURCE_GAP", "EXPIRED_NO_TRADE"):
        report = explain_interrupted_paper(
            opportunity(state), observed_at="2026-11-13T00:06:00+00:00"
        )
        assert report["dispatch_state"] == "NOT_DISPATCHED"
        assert report["next_action"] == "NO_NEW_EFFECT_ON_ORIGINAL_OPPORTUNITY"
        assert report["retry_authorized"] is False


def test_expired_pending_opportunity_cannot_gain_a_fresh_retry_window():
    original = opportunity()
    late = explain_interrupted_paper(original, observed_at="2026-11-13T00:06:00+00:00")
    assert late["dispatch_state"] == "NOT_DISPATCHED"
    assert late["next_action"] == "NO_NEW_EFFECT_ON_ORIGINAL_OPPORTUNITY"
    assert late["intent_id"] == original.intent_id
    assert late["retry_authorized"] is False


def test_invalid_or_tampered_original_evidence_fails_closed():
    forged = opportunity().model_dump()
    forged["source_sha"] = "9" * 64  # update chain still binds the original sha
    with pytest.raises(ValueError, match="PAPER_OPPORTUNITY_UPDATE_BINDING"):
        explain_interrupted_paper(forged, observed_at="2026-11-13T00:04:00+00:00")


def test_future_k_research_cannot_change_original_pending_intent_or_authorize_release():
    policy = {"fixed_k_by_pod": {"pod-A": "0.025"}}
    frozen = opportunity().model_dump(mode="json")
    frozen["release_sha256"] = digest(policy)
    history = {frozen["intent_id"]: frozen}
    active = {"pod-A": frozen["intent_id"]}
    original = (history.copy(), active.copy(), policy.copy())
    audit = audit_pending_original_k(history=history, active=active, current_policy=policy)
    assert audit["pending"] == 1
    assert audit["pinned"] == 1
    assert audit["release_eligible"] is False
    assert audit["order_route"] == "NONE"
    assert history == original[0]
    assert active == original[1]
    assert policy == original[2]
    explanation = explain_interrupted_paper(frozen, observed_at="2026-11-13T00:04:00+00:00")
    assert explanation["frozen_k"] == "0.025"
    assert explanation["mandate_generation"] is None
    assert explanation["retry_authorized"] is False


def test_missing_owner_evidence_blocks_and_unrelated_work_remains_allowed():
    report = explain_interrupted_paper(None, observed_at="2026-11-13T00:06:00+00:00")
    assert report["dispatch_state"] == "EVIDENCE_UNAVAILABLE"
    assert report["guardian_authority"] == "UNKNOWN"
    assert report["next_action"] == "READ_ORIGINAL_OWNER_EVIDENCE"
    assert report["unrelated_read_only_work_allowed"] is True
    assert report["retry_authorized"] is False
