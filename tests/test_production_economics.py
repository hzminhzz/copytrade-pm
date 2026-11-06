import pytest

np = pytest.importorskip("numpy")


def test_20day_competing_risks_and_conditional_pass_time_use_native_engine():
    from copytrade_pm.contract_actuary import Contract, simulate

    contract = Contract("provisional 10k", 100, (1000,), 1000, 500, 1000, 500, False)
    increments = np.zeros((40, 4, 3))
    increments[0, 0] = [1100, -600, 0]
    result = simulate(
        contract,
        paths=3,
        evaluation_days=20,
        funded_days=20,
        steps_per_day=4,
        daily_sigma=2,
        innovations=increments,
    )
    assert result["evaluation_pass_probability"] == pytest.approx(1 / 3)
    assert result["evaluation_breach_before_pass_probability"] == pytest.approx(1 / 3)
    assert result["evaluation_timeout_probability"] == pytest.approx(1 / 3)
    assert result["conditional_pass_time_days"] == 0.25
    assert result["maximum_daily_adverse_excursion"] == 600


def test_missing_policies_or_unattested_tapes_block_economics(tmp_path):
    from copytrade_pm.production_economics import evaluate

    result = evaluate({}, predeclaration=None)
    assert result["verdict"] == "BLOCKED_ECONOMICS"
    assert result["no_buy"]["net_ev"] == 0
    assert result["trading_authorized"] is False
    assert {"FIXED", "VOLATILITY_THROTTLED", "BARRIER_AWARE"} == set(result["missing_policies"])


def test_matched_synthetic_policy_tapes_report_metrics_without_qualifying(tmp_path):
    from test_pm_contract_selector import _fixture
    from copytrade_pm.production_economics import evaluate

    files = {}
    for policy in ("FIXED", "VOLATILITY_THROTTLED", "BARRIER_AWARE"):
        path = tmp_path / (policy + ".json")
        _fixture(path, pnl_a=90, pnl_b=-10)
        files[policy] = path
    result = evaluate(files, predeclaration=None, paths=32, seed=7, assumed_fee=100)
    assert len(result["policies"]) == 3
    assert result["policies"]["FIXED"]["pass_within_20_days"]["estimate"] == 1
    assert result["verdict"] == "BLOCKED_ECONOMICS"
    assert "SYNTHETIC_OR_UNATTESTED_FOLLOWER_TAPE" in result["blockers"]
    assert result["selection"] == "NO_POST_HOC_WINNER"
    assert result["sensitivity"]["batch_2m_vs_5m"] == "UNKNOWN_MATCHED_TAPES_REQUIRED"
