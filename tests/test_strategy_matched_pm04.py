"""Matched candidate common-account orchestration uses original PM03/PM04."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.strategy_matched_pm04 import compare_candidate, attach_to_strategy
from copytrade_pm.strategy_health import FollowerEconomics, StrategyAssessment, seal
from test_strategy_health_v2 import assessment
from test_pm04_compare import _spec


def _input():
    base = _spec()
    base["schema"] = "strategy_matched_comparison_input_v1"
    base["candidate"] = "W028"
    base["portfolio_id"] = "P1"
    return base


def test_matched_common_account_not_independent_pnl_subtraction(tmp_path):
    report = compare_candidate(_input(), tmp_path)
    assert report["schema"] == "strategy_matched_comparison_v1"
    assert report["report_sha256"] == digest(
        {k: v for k, v in report.items() if k != "report_sha256"}
    )
    assert report["same_account_initial_balance_usd"] == "10000"
    assert report["evidence_class"] == "RESEARCH_SYNTHETIC"
    assert not report["authentic_prospective_marginal_value"]
    assert not report["trading_authorized"]
    assert D(report["marginal_pnl_usd"]) == (
        D(report["comparison"]["with"]["account_pnl_usd"])
        - D(report["comparison"]["without"]["account_pnl_usd"])
    )
    assert (
        report["comparison"]["with"]["ledger_head"]
        != report["comparison"]["without"]["ledger_head"]
    )
    assert (
        report["comparison"]["without"]["pm04"]["pod_stats"]
        != report["comparison"]["with"]["pm04"]["pod_stats"]
    )


def test_matched_rejects_unqualified_real_source_and_invalid_context(tmp_path):
    input_data = _input()
    input_data["mode"] = "PROSPECTIVE_OBSERVED"
    with pytest.raises(ValueError, match="NOT_AUTHENTICATED"):
        compare_candidate(input_data, tmp_path)
    input_data["mode"] = "RESEARCH_SYNTHETIC"
    input_data["events"][0]["kind"] = "REAL_BROKER"
    with pytest.raises(ValueError, match="EVENT_KIND"):
        compare_candidate(input_data, tmp_path / "invalid")


def test_attach_synthetic_shared_account_without_prospective_promotion(tmp_path):
    result = compare_candidate(_input(), tmp_path)
    report = assessment(follower_economics=FollowerEconomics(evidence_class="RESEARCH_SYNTHETIC"))
    report = seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "strategy": report.strategy.model_copy(update={"source_alias": "W028"}),
            }
        )
    )
    updated = attach_to_strategy(report, result)
    assert updated.portfolio_contribution.status == "SYNTHETIC_COMPARISON"
    assert updated.portfolio_contribution.marginal_pnl_usd == D(result["marginal_pnl_usd"])
    assert updated.portfolio_contribution.with_pm03_head_sha256
    assert updated.portfolio_contribution.without_pm03_head_sha256
    assert updated.scientifically_qualified is False
    assert updated.source_finance_authenticated is False
    assert updated.trading_authorized is False
    with pytest.raises(ValueError, match="CANDIDATE_SCOPE"):
        attach_to_strategy(assessment(), result)
    forged = {**result, "marginal_pnl_usd": "999999"}
    with pytest.raises(ValueError, match="HASH"):
        attach_to_strategy(report, forged)
