"""FP-01 public-seam contract: independent no-route virtual paper accounts."""

from dataclasses import replace
from decimal import Decimal

import pytest

from copytrade_pm.pm03_rules import propr_rulebook
from copytrade_pm.pm_forward_paper import PaperCampaign, PaperManifest


T = "2026-11-04T04:00:00+00:00"


def manifest(run: str, account: str) -> PaperManifest:
    return PaperManifest(
        run_id=run,
        account_id=account,
        portfolio_sha="a" * 64,
        market_manifest_sha="b" * 64,
        release_sha="c" * 64,
        selected_at=T,
        started_at=T,
        rulebook=propr_rulebook("classic_1step", "evaluation", Decimal("10000"), observed_at=T),
        policy_sha="d" * 64,
    )


def test_two_accounts_are_independent_sealed_and_blocked() -> None:
    campaign = PaperCampaign()
    first = campaign.register(manifest("run_1", "acct_1"))
    second = campaign.register(manifest("run_2", "acct_2"))
    assert first["manifest_sha"] != second["manifest_sha"]
    assert first["account"]["cash"] == second["account"]["cash"] == "10000"
    assert first["account"]["equity"] == second["account"]["equity"] == "10000"
    assert first["account"]["quantities"] == second["account"]["quantities"] == {}
    assert first["account"]["pm_quantities"] == second["account"]["pm_quantities"] == {}
    assert first["order_route"] == second["order_route"] == "NONE"
    assert first["worker_status"] == second["worker_status"] == "NOT_RUNNING"
    assert first["admission"] == second["admission"] == "BLOCKED"
    assert campaign.register(manifest("run_1", "acct_1")) == first
    assert not hasattr(campaign, "order")
    assert not hasattr(campaign, "cancel")
    assert not hasattr(campaign, "flatten")
    assert not hasattr(campaign, "set_leverage")
    assert not hasattr(campaign, "fill")


def test_conflict_and_future_known_are_rejected() -> None:
    campaign = PaperCampaign()
    original = manifest("run_1", "acct_1")
    campaign.register(original)
    for change in (
        {"portfolio_sha": "e" * 64},
        {"policy_sha": "f" * 64},
        {"started_at": "2026-11-04T05:00:00+00:00"},
    ):
        with pytest.raises(ValueError, match="CONFLICTING_PAPER_RUN_MANIFEST"):
            campaign.register(replace(original, **change))
    with pytest.raises(ValueError, match="PAPER_ACCOUNT_ALREADY_REGISTERED"):
        campaign.register(manifest("run_2", "acct_1"))
    with pytest.raises(ValueError, match="FUTURE_KNOWN_PORTFOLIO"):
        replace(original, selected_at="2026-11-04T05:00:00+00:00")
    with pytest.raises(ValueError, match="PAPER_STARTING_BALANCE"):
        replace(
            original,
            rulebook=propr_rulebook("classic_1step", "evaluation", Decimal("10001"), observed_at=T),
        )
    with pytest.raises(ValueError, match="UNSAFE_PAPER_IDENTIFIER"):
        replace(original, run_id="../bad")


def test_sha_is_deterministic_and_identity_bound() -> None:
    m = manifest("run_1", "acct_1")
    assert m.sha == manifest("run_1", "acct_1").sha
    assert m.sha != replace(m, account_id="acct_2").sha
    assert m.payload()["order_route"] == "NONE"
