"""Five-wallet portfolio retrospective research: selection, leakage and safety tests."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("polars")

from scripts import phase7_best5_major4_screen as s  # noqa: E402


def member(alias: str, *, mix: dict | None = None) -> dict:
    return {
        "alias": alias,
        "gross_turnover_by_coin_fraction": mix
        or {"BTC": 0.27, "ETH": 0.22, "SOL": 0.18, "HYPE": 0.20, "DOGE": 0.13},
    }


def dummy_unit(pnl: float, turn: float, length: int) -> dict:
    return {
        "pnl_delta_per_budget_usd": np.full(length, pnl),
        "worst_bar_delta_per_budget_usd": np.full(length, pnl - 0.0001),
        "turnover_per_budget_usd": np.full(length, turn),
    }


def test_stage1_can_not_see_last30_performance() -> None:
    roster = {f"A{i}": member(f"A{i}") for i in range(5)}
    names = tuple(roster)
    daily20 = {a: np.ones(90) * 0.002 for a in names}
    daily30 = {a: np.ones(90) * 0.001 for a in names}
    first = s._stage1_record(names, roster, daily20, daily30)
    assert first is not None
    # The extra 30d contains adversarial future returns, but selection
    # ranks only days 1-60.
    for a in names:
        daily20[a][60:] = -100
        daily30[a][60:] = -150
    second = s._stage1_record(names, roster, daily20, daily30)
    assert first == second


def test_major_coin_coverage_excludes_no_SOL_or_HYPE() -> None:
    group = tuple(f"A{i}" for i in range(5))
    missing = {a: member(a, mix={"BTC": 0.4, "ETH": 0.4, "DOGE": 0.2}) for a in group}
    daily = {a: np.ones(90) for a in group}
    assert s._stage1_record(group, missing, daily, daily) is None


def test_stage1_reports_unqualified_daily_close_risk_only() -> None:
    group = tuple(f"A{i}" for i in range(5))
    roster = {a: member(a) for a in group}
    net = {a: np.zeros(90) for a in group}
    report = s._stage1_record(group, roster, net, net)
    assert report is not None
    assert report["risk_reference_scope"] == "FIRST_60_DAYS_DAILY_CLOSE_SCREEN_ONLY"


def test_fixed_total_gross_budget_when_expanding_three_to_five(monkeypatch) -> None:
    monkeypatch.setattr(s, "N", 3)
    models = {a: dummy_unit(0.01, 0.1, 3) for a in ("A", "B", "C", "D", "E")}
    three = s._combine(["A", "B", "C"], models, 5000)
    five = s._combine(["A", "B", "C", "D", "E"], models, 5000)
    assert three[0].sum() == pytest.approx(five[0].sum())
    assert three[2].sum() == pytest.approx(five[2].sum())


def test_discontinuous_intraday_breach_does_not_count_post_breach_profit_as_valid() -> None:
    metrics = {
        "earliest_model_reference_breach_at_utc": "2026-08-06T00:00:00+00:00",
        "illustrative_prop_loss_reference_breached": True,
    }
    status = s._strict_halt_evidence(metrics)
    assert status["no_post_breach_profit_can_be_credited_as_prop_account_return"]
    assert status["real_stop_execution_price"] is None
    status = s._strict_halt_evidence(
        {
            **metrics,
            "earliest_model_reference_breach_at_utc": None,
            "illustrative_prop_loss_reference_breached": False,
        }
    )
    assert not status["loss_reference_breached"]


def test_close_peak_to_trough_includes_initial_zero() -> None:
    assert s._close_max_drawdown(np.array([200, -300, -100, 50])) == pytest.approx(400)


def test_unbounded_pool_fails_closed() -> None:
    models = {f"A{i}": dummy_unit(0.001, 0.01, 90 * 1440) for i in range(3)}
    with pytest.raises(ValueError, match="FROZEN_POOL_SIZE_OR_MODEL_MISMATCH"):
        s.screen([member(x) for x in models], models)
