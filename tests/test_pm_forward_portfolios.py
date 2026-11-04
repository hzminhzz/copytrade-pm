"""FP-09 blocked-yet-independent P1 and P14 portfolio admission."""

from dataclasses import replace

import pytest

from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_paper import PaperCampaign
from copytrade_pm.pm_forward_portfolios import P1, P14, PaperPortfolioView
from test_pm_forward_admission import _alter
from test_pm_forward_fill import _source_book
from test_pm_forward_journal import T, manifest


def test_two_frozen_10k_accounts_and_shared_source_fanout() -> None:
    assert P1.members == ("S035", "S051", "S053")
    assert len(P14.members) == 5 and "S064" in P14.members
    assert "Whale_0x5f94" in P14.members
    assert P1.nominal_risk_per_member == "200"
    assert P14.nominal_risk_per_member == "120"
    coordinator = PaperPortfolioView(PaperCampaign())
    coordinator.register(P1, replace(manifest("p1", "p1_account"), portfolio_sha=P1.sha))
    coordinator.register(P14, replace(manifest("p14", "p14_account"), portfolio_sha=P14.sha))
    for name in ("P1", "P14"):
        state = coordinator.status(name)
        assert state["account"]["cash"] == "10000"
        assert state["account"]["quantities"] == {}
        assert state["source_admission"] == "BLOCKED"
        assert state["order_route"] == "NONE"
    shared = admit_source_book(_source_book(), decision_at=T, fill_at=T)
    result = coordinator.observe("S035", shared)
    assert result == {"P1": "BLOCKED", "P14": "BLOCKED"}
    assert "S064" in coordinator.status("P14")["missing_members"]
    assert "S064" not in coordinator.status("P1")["missing_members"]
    broken = admit_source_book(_alter(_source_book(), source_equity=None), decision_at=T, fill_at=T)
    coordinator.observe("S064", broken)
    assert "S064" in coordinator.status("P14")["rejected_members"]
    assert coordinator.status("P1")["rejected_members"] == {}
    assert coordinator.status("P1")["account"] == coordinator.campaign.status("p1")["account"]


def test_resealing_or_cross_portfolio_manifest_fails() -> None:
    view = PaperPortfolioView(PaperCampaign())
    with pytest.raises(ValueError, match="PORTFOLIO_MANIFEST_SHA_MISMATCH"):
        view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P14.sha))
    view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P1.sha))
    with pytest.raises(ValueError, match="DUPLICATE_PORTFOLIO_RUN_ID"):
        view.register(P14, replace(manifest("p1", "other"), portfolio_sha=P14.sha))
