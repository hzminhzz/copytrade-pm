"""Track C public read-only proposal and release preflight behavioral acceptance."""

from __future__ import annotations

from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_k_recalibration import (
    FinanceWindow,
    KProposal,
    KReleaseCandidate,
    KResearchInput,
    Trial,
    bind_opportunity_k,
    evaluate_k,
    make_candidate,
    offline_preflight,
)

S = "a" * 64
T = "b" * 64
U = "c" * 64
P = "d" * 64
NOW = "2026-11-10T01:00:00+00:00"
BEFORE = "2026-11-01T00:00:00+00:00"
AFTER = "2026-11-11T00:00:00+00:00"
KEY = "hyperliquid/mainnet:perp:main/BTC"


def _trial():
    return Trial(
        trial_id="variant-1",
        candidate_id="wallet-A",
        selection_as_of=BEFORE,
        status="ACCEPTED",
        evidence_sha256=S,
        variant_k=D(".01"),
    )


def _window(
    label="OOS", kind="PM03_HISTORICAL_PROXY", episodes=50, funding="0", lower="10", known=BEFORE
):
    return FinanceWindow(
        label=label,
        class_of_evidence=kind,
        report_sha256=T,
        known_at=known,
        period_end="2026-10-31T00:00:00+00:00",
        independent_episodes=episodes,
        follower_realized_net_usd=D("100"),
        follower_mtm_net_usd=D("100"),
        fees_usd=D("5"),
        slippage_usd=D("3"),
        funding_usd=D(funding) if funding is not None else None,
        financing_complete=funding is not None,
        capacity_verified=True,
        quote_coverage_complete=True,
        selection_frozen_before_window=True,
        cash_control_net_usd=D("0"),
        matched_control_net_usd=D("10"),
        market_control_net_usd=D("10"),
        max_drawdown_usd=D("20"),
        concentration_fraction=D(".1"),
        max_pair_correlation=D(".1"),
        uncertainty_lower_incremental_net_usd=D(lower) if lower is not None else None,
    )


def _input(*, k="0.02", current="0.01", windows=None, **kwargs):
    trial = _trial()
    data = dict(
        portfolio_version="sealed-P1@v1",
        portfolio_definition_sha256=P,
        pod_id="wallet-A",
        selected_account_sha256=S,
        sizing_policy_version="fixed-k-v1",
        as_of=NOW,
        current_frozen_k=D(current),
        candidate_k=D(k),
        cost_policy_version="v4-paper-5bps-2bps",
        risk_policy_version="pm03-v1",
        source_sha256=U,
        trial_roster_sha256=digest([trial.model_dump(mode="json")]),
        trials=(trial,),
        windows=windows
        if windows is not None
        else (
            _window("TRAIN"),
            _window("OOS"),
            _window("FORWARD", "PM03_PROSPECTIVE_SHADOW"),
        ),
        pod_loss_budget_usd=D("200"),
        follower_equity_usd=D("10000"),
        max_gross_notional_usd=D("1000"),
        max_market_notional_usd=D("1000"),
        daily_headroom_usd=D("500"),
        trailing_headroom_usd=D("1000"),
        source_quantities={KEY: D("1")},
        source_marks={KEY: D("100")},
        follower_marks={KEY: D("101")},
        stress_shocks=({KEY: D("-.1")},),
        adverse_price_extra_loss_usd=D("2"),
        latency_extra_loss_usd=D("2"),
        lot_notional_valid=True,
        unresolved_financial_effects=False,
        portfolio_correlation_checked=True,
        evidence_expired=False,
    )
    data.update(kwargs)
    return KResearchInput.model_validate(data)


def test_positive_incremental_candidate_research_only_and_deterministic():
    result = evaluate_k(_input())
    assert result.decision == "INCREASE"
    assert result.research_only and result.authorized_for_trading is False
    assert result.order_route == "NONE" and result.release_activated is False
    assert result.identity_sha256 == evaluate_k(_input()).identity_sha256
    assert result.tested_trials == 1 and result.effective_independent_episodes == 100
    assert KProposal.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "changes,reason",
    [
        (dict(windows=(_window("TRAIN"), _window("OOS"))), "NO_AUTHENTIC_PROSPECTIVE_FINANCE"),
        (
            dict(
                windows=(
                    _window("TRAIN"),
                    _window("OOS", episodes=3),
                    _window("FORWARD", "PM03_PROSPECTIVE_SHADOW", episodes=3),
                )
            ),
            "INSUFFICIENT_INDEPENDENT_OOS_EPISODES",
        ),
        (
            dict(
                windows=(
                    _window("TRAIN"),
                    _window("OOS", lower=None),
                    _window("FORWARD", "PM03_PROSPECTIVE_SHADOW"),
                )
            ),
            "NO_POSITIVE_LOWER_INCREMENTAL_BOUND",
        ),
        (
            dict(
                windows=(
                    _window("TRAIN"),
                    _window("OOS", funding=None),
                    _window("FORWARD", "PM03_PROSPECTIVE_SHADOW"),
                )
            ),
            "FUNDING_UNAVAILABLE",
        ),
        (dict(unresolved_financial_effects=True), "UNRESOLVED_EXECUTIONS_OR_INVENTORY"),
        (dict(evidence_expired=True), "EXPIRED_EVIDENCE"),
        (dict(lot_notional_valid=False), "LOT_OR_MINIMUM_NOTIONAL_INVALID"),
        (dict(portfolio_correlation_checked=False), "CORRELATION_NOT_VALIDATED"),
        (dict(pod_loss_budget_usd=D("1")), "PM03_STRESS_HEADROOM_EXCEEDED"),
        (dict(trial_roster_sha256=S), "TRIAL_ROSTER_SHA_MISMATCH"),
    ],
)
def test_increase_abstains_on_missing_or_risky_evidence(changes, reason):
    proposal = evaluate_k(_input(**changes))
    assert proposal.decision == "INSUFFICIENT_EVIDENCE"
    assert reason in proposal.reasons


def test_candidate_k_is_portfolio_scoped_not_wallet_global():
    a = evaluate_k(_input())
    b = evaluate_k(_input(portfolio_version="sealed-P2@v3", current_frozen_k=D(".005")))
    assert a.identity_sha256 != b.identity_sha256
    assert a.current_frozen_k != b.current_frozen_k


def test_no_future_finance_or_trial_inputs():
    with pytest.raises(ValidationError, match="FINANCE_REPORT_FROM_FUTURE"):
        _input(windows=(_window(known=AFTER),))
    with pytest.raises(ValidationError, match="TRIAL_FROM_FUTURE"):
        _input(
            trials=(
                Trial(
                    trial_id="later",
                    candidate_id="wallet-A",
                    selection_as_of=AFTER,
                    status="REJECTED",
                    evidence_sha256=S,
                    variant_k=D(".01"),
                ),
            )
        )


def test_no_research_model_can_claim_order_or_release_authority():
    good = evaluate_k(_input())
    with pytest.raises(ValidationError):
        KProposal.model_validate({**good.model_dump(), "authorized_for_trading": True})
    with pytest.raises(ValidationError):
        KProposal.model_validate({**good.model_dump(), "release_activated": True})
    with pytest.raises(ValidationError):
        KProposal.model_validate({**good.model_dump(), "order_route": "BROKER"})


def test_releases_are_nonactivating_and_future_only():
    p = evaluate_k(_input())
    release = make_candidate(
        portfolio_version=p.portfolio_version,
        portfolio_definition_sha256=P,
        pod_membership=("wallet-A",),
        sizing_policy_version="fixed-k-v1",
        cost_policy_version="v4-paper-5bps-2bps",
        risk_policy_version="pm03-v1",
        effective_at=AFTER,
        proposed_at=NOW,
        rollback_release_sha256=U,
        proposals=(p,),
    )
    assert KReleaseCandidate.model_validate_json(release.model_dump_json()) == release
    receipt = offline_preflight(
        release,
        sealed_definition_sha256=P,
        observed_current_release_sha256=U,
        pending_opportunity_count=1,
        open_inventory_count=2,
    )
    assert receipt["status"] == "BLOCKED"
    assert "SQLITE_INDEPENDENT_SEAL_NOT_CHECKED" in receipt["blockers"]
    assert receipt["release_eligible"] is False
    assert not receipt["activated"] and receipt["order_route"] == "NONE"
    old = bind_opportunity_k(
        first_known_at="2026-11-10T01:03:00+00:00",
        pending_k=D(".01"),
        pending_release_sha256=U,
        candidate=release,
        opportunity_already_exists=True,
    )
    assert old["k"] == "0.01" and old["release_sha256"] == U
    new = bind_opportunity_k(
        first_known_at="2026-11-12T00:00:00+00:00",
        pending_k=D(".01"),
        pending_release_sha256=U,
        candidate=release,
        opportunity_already_exists=False,
    )
    assert new["action"] == "NO_ACTIVE_RELEASE_CHANGE"
    assert new["k"] == "0.01"  # a verified candidate cannot change active k
    with pytest.raises(ValidationError):
        KReleaseCandidate.model_validate({**release.model_dump(), "activated": True})
    assert (
        offline_preflight(
            release,
            sealed_definition_sha256=S,
            observed_current_release_sha256=U,
            pending_opportunity_count=1,
            open_inventory_count=2,
        )["status"]
        == "BLOCKED"
    )
    with pytest.raises(ValueError, match="RELEASE_EFFECTIVE_TIME_NOT_FUTURE"):
        make_candidate(
            portfolio_version=p.portfolio_version,
            portfolio_definition_sha256=P,
            pod_membership=("wallet-A",),
            sizing_policy_version="fixed-k-v1",
            cost_policy_version="v4-paper-5bps-2bps",
            risk_policy_version="pm03-v1",
            effective_at=NOW,
            proposed_at=NOW,
            rollback_release_sha256=U,
            proposals=(p,),
        )


def test_funding_cost_model_identity_not_reused_as_historical_screen():
    candidate = evaluate_k(_input(cost_policy_version="v4-paper-cost-v1"))
    screen = evaluate_k(_input(cost_policy_version="v4-screen-1m-v2"))
    assert candidate.identity_sha256 != screen.identity_sha256


def test_no_increase_in_historical_only_and_no_automatic_inventory_change():
    p = evaluate_k(_input(windows=(_window("TRAIN"), _window("OOS"))))
    assert p.decision == "INSUFFICIENT_EVIDENCE"
    assert p.evidence_class == "HISTORICAL_ONLY"
    assert evaluate_k(_input(k="0.005")).decision == "DECREASE"
