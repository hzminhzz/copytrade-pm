"""Risk budgets are independently reserved against a shared synthetic account."""

from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_run import ShadowRun
from test_pm03_extended import T, book
from test_pm04_shadow import SHA, event, policy


def configure(tmp_path, p):
    run = ShadowRun(
        tmp_path,
        run_id="pm04-run",
        rulebook=book(),
        started_at=T,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SHA,
        pm02_sha=SHA,
        market_manifest_sha=SHA,
    )
    run.record(event("config", "PM04_CONFIG", {"policy": p}, 0))
    return run


def test_unfunded_daily_loss_allowances_rejected_before_any_shadow_book(tmp_path):
    p = policy()
    for pod in p["pods"].values():
        pod["daily_loss"] = "200"
    with pytest.raises(ValueError, match="UNFUNDED_POD_DAILY"):
        configure(tmp_path, p)


def test_unfunded_max_drawdown_budgets_rejected(tmp_path):
    p = policy()
    for pod in p["pods"].values():
        pod["max_drawdown"] = "500"
    with pytest.raises(ValueError, match="UNFUNDED_POD_DRAWDOWN"):
        configure(tmp_path, p)


def test_unfunded_independent_stress_allowances_rejected(tmp_path):
    p = policy()
    for pod in p["pods"].values():
        pod["stress_loss"] = "500"
    with pytest.raises(ValueError, match="UNFUNDED_POD_STRESS"):
        configure(tmp_path, p)


def test_duplicate_pod_budget_identity_rejected(tmp_path):
    p = policy()
    p["pods"]["W042"]["budget_ref"] = p["pods"]["W028"]["budget_ref"]
    with pytest.raises(ValueError, match="DUPLICATE_POD_BUDGET_REF"):
        configure(tmp_path, p)


def test_funded_synthetic_budgets_have_versioned_account_funding_receipt(tmp_path):
    r = configure(tmp_path, policy())
    receipt = r.account.pm04_state["budget_funding"]
    assert receipt["source"] == "PM03_RULEBOOK_SYNTHETIC"
    assert D(receipt["daily_reserved"]) <= D(receipt["daily_available"])
    assert D(receipt["drawdown_reserved"]) <= D(receipt["drawdown_available"])
    assert D(receipt["stress_reserved"]) <= D(receipt["stress_available"])
