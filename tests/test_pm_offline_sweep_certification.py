"""Exact PM-03 floor boundary and screening-only verdict regression."""

from decimal import Decimal as D
from random import Random

import pytest

from copytrade_pm.pm03_account import Account, Rulebook
from copytrade_pm.pm_offline_certification import (
    certify_account_fixture,
    exact_floor_state,
)


def rulebook(*, actual=True):
    return Rulebook(
        program="Synthetic prop fixture",
        stage="Evaluation",
        source="synthetic-only",
        observed_at="2026-10-20T12:00:00+00:00",
        version="test-v1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=D("1000"),
        daily_loss=D("500"),
        static_loss=D("1000"),
        trailing_loss=D("1000"),
        confirmed=True,
        account_terms_confirmed=actual,
    )


def account(*, actual=True):
    return Account.start(rulebook(actual=actual), "2026-10-20T12:00:00+00:00")


def kwargs():
    return dict(
        full_minute_coverage=True,
        complete_source_book=True,
        complete_equity=True,
        complete_funding=True,
        intrabar_order_known=True,
        right_censored=False,
    )


@pytest.mark.parametrize(
    ("equity", "breached"),
    [
        (D("9499.99"), True),
        (D("9500"), True),
        (D("9500.01"), False),
        (D("9500.00000000000001"), False),
    ],
)
def test_inclusive_daily_floor_exact_at_cent_boundary(equity, breached):
    report = exact_floor_state(
        rulebook(),
        observed_equity=equity,
        high_water=D("10000"),
        day_start_balance=D("10000"),
    )
    assert report["floor"] == "9500"
    assert report["breached"] is breached
    assert report["halt"] is breached


def test_trailing_highwater_equality_exact():
    above = exact_floor_state(
        rulebook(),
        observed_equity=D("10000.01"),
        high_water=D("11000"),
        day_start_balance=D("11000"),
    )
    at = exact_floor_state(
        rulebook(),
        observed_equity=D("10000"),
        high_water=D("11000"),
        day_start_balance=D("11000"),
    )
    assert above["floor"] == "10500"
    assert above["breached"] is True
    assert at["breached"] is True


def test_randomized_exact_cent_and_subcent_contract_floor_parity():
    rng = Random(20261104)
    r = rulebook()
    # Randomized exact cents and subcents cannot accidentally be classified
    # through binary float rounding near an inclusive daily/trailing floor.
    for floor, high, daily in (
        (D("9500"), D("10000"), D("10000")),
        (D("10000"), D("11000"), D("10500")),
    ):
        for _ in range(250):
            n = rng.randint(-5000, 5000)
            equity = floor + D(n).scaleb(-10)
            verdict = exact_floor_state(
                r,
                observed_equity=equity,
                high_water=high,
                day_start_balance=daily,
            )
            assert D(verdict["floor"]) == floor
            assert verdict["breached"] is (equity <= floor)
            assert verdict["halt"] is (equity <= floor)


def test_screen_never_authoritative_even_if_target_reached():
    a = account()
    a.stage_passed = True
    result = certify_account_fixture(a, mode="SCREEN_ONLY", **kwargs())
    assert result["verdict"] == "UNKNOWN"
    assert result["certified"] is False


def test_actual_rulebook_and_complete_fixture_can_certify_target():
    a = account()
    a.stage_passed = True
    result = certify_account_fixture(a, mode="CERTIFIED", **kwargs())
    assert result["verdict"] == "PASS"
    assert result["certified"] is True
    assert result["status"] == "SYNTHETIC_TARGET_REACHED"


def test_unconfirmed_rulebook_and_incomplete_evidence_never_pass():
    a = account(actual=False)
    a.stage_passed = True
    result = certify_account_fixture(a, mode="CERTIFIED", **kwargs())
    assert result["verdict"] == "UNKNOWN"
    assert result["certified"] is False
    a = account()
    a.stage_passed = True
    inputs = kwargs()
    inputs["complete_funding"] = False
    result = certify_account_fixture(a, mode="CERTIFIED", **inputs)
    assert result["verdict"] == "UNKNOWN"


def test_breach_with_unconfirmed_terms_is_not_contractual_verdict():
    a = account(actual=False)
    a.high_water = D("12000")
    a._check_breach()
    assert a.breached
    result = certify_account_fixture(a, mode="CERTIFIED", **kwargs())
    assert result["verdict"] == "UNKNOWN"
    assert result["certified"] is False


def test_simulated_breach_with_missing_source_cannot_be_contractually_certified():
    a = account()
    a.high_water = D("12000")
    a._check_breach()
    assert a.breached
    args = kwargs()
    args["complete_source_book"] = False
    result = certify_account_fixture(a, mode="CERTIFIED", **args)
    assert result["verdict"] == "UNKNOWN"
    assert result["certified"] is False


def test_breach_is_latched_even_after_price_recovery():
    a = account()
    a.mark({}, "2026-10-20T12:01:00+00:00")
    a.high_water = D("12000")
    a._check_breach()
    assert a.breached
    a.stage_passed = True
    result = certify_account_fixture(a, mode="CERTIFIED", **kwargs())
    assert result["verdict"] == "BREACH"


def test_intrabar_ambiguity_and_right_censor_are_not_passes():
    a = account()
    a.stage_passed = True
    args = kwargs()
    args["intrabar_order_known"] = False
    result = certify_account_fixture(a, mode="CERTIFIED", **args)
    assert result["verdict"] == "AMBIGUOUS"
    args = kwargs()
    args["right_censored"] = True
    result = certify_account_fixture(a, mode="CERTIFIED", **args)
    assert result["verdict"] == "UNKNOWN"
