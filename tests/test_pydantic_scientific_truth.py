"""Research truth cannot be promoted by a summary or a successful lifecycle."""

from datetime import timedelta

import pytest

from copytrade_pm.contract_actuary import Contract, simulate
from copytrade_pm.pm_fill_tape import build_wallet_tape
from copytrade_pm.pm_historical_combos import START, _source_episodes
from copytrade_pm.trader_intelligence_qualification import EvidenceReadiness
from test_pm_fill_replay import _entry
from test_pm_historical_combos import sample_event
from test_pm_prospective_audit import setup_receipt
from test_trader_intelligence_qualification import readiness


@pytest.mark.parametrize(
    "change",
    [
        {"status": "SCIENTIFICALLY_QUALIFIED"},
        {"receipt_count": True},
        {"eligible_whole_account_outcomes": -1},
    ],
)
def test_readiness_view_cannot_launder_positive_or_invalid_evidence(tmp_path, change):
    ledger, _, _, _ = setup_receipt(tmp_path)
    report = readiness(ledger).as_wire()
    with pytest.raises(ValueError):
        EvidenceReadiness(**{**report, **change})


def test_cf10_partial_episodes_and_past_payout_do_not_mean_current_funded():
    np = pytest.importorskip("numpy")
    t = START + timedelta(minutes=1)
    rows = [
        sample_event(t, "BTC", "5", "0", 1),
        sample_event(t + timedelta(minutes=1), "BTC", "0", "2", 2),
        sample_event(t + timedelta(minutes=2), "BTC", "2", "0", 3),
        sample_event(t + timedelta(minutes=3), "ETH", "0", "2", 4),
        sample_event(t + timedelta(minutes=4), "ETH", "9", "0", 5),
    ]
    episodes, counts = _source_episodes("W001", rows)
    assert len(episodes) == 1 and counts["source_chain_breaks"] == 1
    assert episodes[0].evidence_scope.kind == "RETROSPECTIVE_ESTIMATE"
    assert not episodes[0].evidence_scope.prospective_source_book
    book = build_wallet_tape(_entry(), ["BTC", "ETH"], rows, ["ETH:POSITION_DISCONTINUITY"])
    assert book["evidence_scope"]["source_gaps"] == ("ETH:POSITION_DISCONTINUITY",)
    assert book["source_first_known_at"] is None
    assert book["causal_follower_actions_allowed"] is False
    contract = Contract("synthetic", 1, (10,), 100, 100, 50, None, False, payout_every_days=1)
    result = simulate(
        contract,
        paths=1,
        evaluation_days=2,
        funded_days=4,
        steps_per_day=1,
        daily_sigma=1,
        payout_safety_buffer=1,
        innovations=lambda day, step: np.array(
            [10.0 if day == 0 else 20.0 if day == 1 else -100.0]
        ),
    )
    assert result["funded_probability"] == 1
    assert result["first_payout_probability"] == 1
    assert result["mean_payout"] > 0
    assert result["lifecycle"]["ever_funded_count"] == 1
    assert result["lifecycle"]["currently_funded_count"] == 0
    assert result["lifecycle"]["currently_active_count"] == 0
    assert result["lifecycle"]["forward_observed"] is False
    assert result["lifecycle"]["trading_authorized"] is False


def test_receipt_audit_signature_maturity_and_economics_remain_independent(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from test_pm02_whole_account_outcomes import whole
    from test_pm_prospective_audit import signature
    from test_pm_prospective_ledger import IMPORTED

    journal, signer, audit, now = setup_receipt(tmp_path)
    now[0] = IMPORTED + timedelta(minutes=6)
    unaudited = whole(journal, "0" * 64)
    with pytest.raises(ValueError, match="NO_INDEPENDENT_AUDITED_RECEIPT"):
        journal.record_matched_outcome(unaudited, signature(signer, unaudited))
    head = journal.audit_receipt(audit, signature(signer, audit))
    good = whole(journal, head)
    immature = {**good, "outcome_known_at": (IMPORTED + timedelta(minutes=1)).isoformat()}
    with pytest.raises(ValueError, match="HORIZON_NOT_MATURE"):
        journal.record_matched_outcome(immature, signature(signer, immature))
    with pytest.raises(ValueError, match="INVALID_OUTCOME_SIGNATURE"):
        journal.record_matched_outcome(good, signature(Ed25519PrivateKey.generate(), good))
    for field in (
        "execution_costs_verified",
        "funding_verified",
        "capacity_verified",
        "complete_episode_census",
        "selection_plan_independently_reviewed",
    ):
        bad = {**good, field: False}
        with pytest.raises(ValueError, match="UNVERIFIED_WHOLE_ACCOUNT"):
            journal.record_matched_outcome(bad, signature(signer, bad))
    assert readiness(journal).eligible_whole_account_outcomes == 0
    journal.record_matched_outcome(good, signature(signer, good))
    proof = readiness(journal)
    assert proof.eligible_whole_account_outcomes == 1
    assert proof.status == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert "OOS_SKILL_AND_CALIBRATION_NOT_TESTED" in proof.reasons
    assert "INDEPENDENT_ECONOMIC_TRUTH_NOT_ESTABLISHED_BY_SIGNATURE" in proof.reasons
    assert "PREDECLARED_INDEPENDENT_HOLDOUT_NOT_ESTABLISHED" in proof.reasons
