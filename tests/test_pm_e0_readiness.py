from dataclasses import replace

import pytest

from copytrade_pm.pm_e0_readiness import (
    CONTRACT, HISTORICAL, SCIENTIFIC, PortfolioEvidence, assess_readiness,
)
from copytrade_pm.pm_portfolio_e0 import PORTFOLIOS


@pytest.mark.parametrize("name", ("A", "B", "C"))
def test_missing_prospective_and_contract_evidence_fail_closed(name):
    evidence = {pod: PortfolioEvidence(wallet=pod) for pod in PORTFOLIOS[name]}
    result = assess_readiness(name, evidence)
    assert result["historical_replay"] == "BLOCKED_EVIDENCE"
    assert result["scientific_qualification"] == "UNQUALIFIED"
    assert result["contract_readiness"] == "NOT_AUTHORIZED"
    assert result["live_orders_enabled"] is False
    for pod in PORTFOLIOS[name]:
        assert result["missing"]["historical_replay"][pod] == list(HISTORICAL)
        assert result["missing"]["scientific_qualification"][pod] == list(SCIENTIFIC)
        assert result["missing"]["contract_readiness"][pod] == list(CONTRACT)


@pytest.mark.parametrize("name", ("A", "B", "C"))
def test_one_incomplete_wallet_blocks_whole_portfolio(name):
    evidence = {
        pod: PortfolioEvidence(wallet=pod, **{k: True for k in HISTORICAL})
        for pod in PORTFOLIOS[name]
    }
    missing_pod = PORTFOLIOS[name][-1]
    evidence[missing_pod] = replace(
        evidence[missing_pod], historical_equity_reconciled=False
    )
    result = assess_readiness(name, evidence)
    assert result["historical_replay"] == "BLOCKED_EVIDENCE"
    assert result["missing"]["historical_replay"] == {
        missing_pod: ["historical_equity_reconciled"]
    }


def test_even_all_claims_true_never_authorize_live_orders():
    evidence = {
        pod: PortfolioEvidence(
            wallet=pod, **{k: True for k in HISTORICAL + SCIENTIFIC + CONTRACT}
        )
        for pod in PORTFOLIOS["A"]
    }
    result = assess_readiness("A", evidence)
    assert result["historical_replay"] == "EVIDENCE_READY_FOR_RESEARCH_ONLY"
    assert result["scientific_qualification"] == "REQUIRES_INDEPENDENT_REVIEW"
    assert result["contract_readiness"] == "REQUIRES_HUMAN_AUTHORIZATION"
    assert result["live_orders_enabled"] is False


def test_wrong_cohort_rejected():
    with pytest.raises(ValueError, match="ALL_THREE_PODS"):
        assess_readiness("B", {"W044": PortfolioEvidence(wallet="W044")})
