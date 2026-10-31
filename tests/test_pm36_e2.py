from decimal import Decimal as D

import pytest

from copytrade_pm.pm36_e2 import STRESS_CAP_USD, risk_charge, risk_utilization, size


def test_common_multiplier_caps_aggregate_stress_and_cost_once():
    source = {"A": D("2"), "B": D("-3")}
    marks = {"A": D("100"), "B": D("50")}
    shock = {"A": D("0.10"), "B": D("0.20")}
    cost_rate = D("0.03")

    # Aggregate risk is 60.5 USD before scaling, not a $60 allowance per leg.
    assert risk_charge(source, marks, shock=shock, cost_rate=cost_rate) == D("60.50")
    targets = size(source, marks, shock=shock, cost_rate=cost_rate)

    assert abs(targets["A"] / source["A"] - targets["B"] / source["B"]) < D("1e-25")
    assert targets["A"] > 0 and targets["B"] < 0
    assert abs(targets["A"]) < abs(source["A"])
    assert risk_charge(targets, marks, shock=shock, cost_rate=cost_rate) <= STRESS_CAP_USD
    assert risk_utilization(targets, marks, shock=shock, cost_rate=cost_rate) <= D("1")


def test_rounding_cannot_push_aggregate_risk_over_budget():
    source = {"A": D("435"), "B": D("61"), "C": D("847")}
    marks = {"A": D("580"), "B": D("127"), "C": D("971")}
    shock = dict.fromkeys(source, D("0.1"))
    result = size(source, marks, shock=shock, cost_rate=D("0.001"))
    assert risk_charge(result, marks, shock=shock, cost_rate=D("0.001")) <= STRESS_CAP_USD


def test_under_cap_positions_are_unchanged_and_utilization_is_exposed():
    source = {"A": D("1")}
    marks = {"A": D("10")}
    shock = {"A": D("0.10")}

    assert size(source, marks, shock=shock, cost_rate=D("0")) == source
    assert risk_charge(source, marks, shock=shock, cost_rate=D("0")) == D("1.0")
    assert risk_utilization(source, marks, shock=shock, cost_rate=D("0")) == D("1.0") / D("60")


def test_missing_inputs_do_not_treat_unpriced_legs_as_flat():
    with pytest.raises(ValueError, match="INCOMPLETE_OR_EXTRA_RISK_INPUTS"):
        size({"A": D("1"), "B": D("1")}, {"A": D("10")}, shock={"A": D("0.1")}, cost_rate=D("0"))


@pytest.mark.parametrize(
    ("marks", "shock", "cost_rate", "error"),
    [
        ({"A": D("0")}, {"A": D("0.1")}, D("0"), "INVALID_MARK"),
        ({"A": D("10")}, {"A": D("-0.1")}, D("0"), "INVALID_SHOCK"),
        ({"A": D("10")}, {"A": D("NaN")}, D("0"), "INVALID_SHOCK"),
        ({"A": D("10")}, {"A": D("0.1")}, D("-0.01"), "INVALID_COST_RATE"),
    ],
)
def test_invalid_risk_inputs_rejected(marks, shock, cost_rate, error):
    with pytest.raises(ValueError, match=error):
        size({"A": D("1")}, marks, shock=shock, cost_rate=cost_rate)
