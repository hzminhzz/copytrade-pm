"""PM-03 exact partial allocation across awkward Decimal k-scaled targets.

No new simulator: tests exercise the existing sequential account allocation.
"""

from decimal import Decimal as D
from random import Random

import pytest

from copytrade_pm.pm03_execution import _allocate


@pytest.mark.parametrize("sign", [D("1"), D("-1")])
def test_complete_five_pod_fill_preserves_all_high_precision_requests(sign):
    pending = {f"W{i:03d}": sign * D("0.09990009990009990009990009990") for i in range(1, 6)}
    total = sum(pending.values(), D("0"))
    result = _allocate(total, pending)
    assert result == dict(sorted(pending.items()))
    assert sum(result.values(), D("0")) == total


@pytest.mark.parametrize("sign", [D("1"), D("-1")])
def test_partial_fill_is_bounded_exact_and_deterministic(sign):
    pending = {
        "A": sign * D("0.3333333333333333333333333333"),
        "B": sign * D("0.1666666666666666666666666667"),
        "C": sign * D("0.1234567891234567891234567891"),
    }
    quantity = sign * D("0.40")
    allocation = _allocate(quantity, pending)
    assert allocation == _allocate(quantity, dict(reversed(list(pending.items()))))
    assert sum(allocation.values(), D("0")) == quantity
    assert all(
        allocation[pm] * sign >= 0 and abs(allocation[pm]) <= abs(pending[pm]) for pm in pending
    )


def test_odd_lots_randomized_deterministic_pro_rata_preserves_contract():
    rng = Random(20261104)
    for _ in range(250):
        n = rng.randint(2, 12)
        scale = rng.choice([6, 12, 18, 24])
        sign = D(rng.choice([-1, 1]))
        pending = {
            f"P{i:03d}": sign * D(rng.randint(1, 999999999)).scaleb(-scale) for i in range(n)
        }
        total = sum(pending.values(), D("0"))
        # Include exactly full fill, just smaller than full, and small partial.
        shrink = D(rng.choice(["1", "0.999999", "0.67", "0.01"]))
        quantity = total * shrink
        allocation = _allocate(quantity, pending)
        assert sum(allocation.values(), D("0")) == quantity
        assert all(
            allocation[pm] * sign >= 0 and abs(allocation[pm]) <= abs(pending[pm]) for pm in pending
        )


@pytest.mark.parametrize(
    "quantity,pending,error",
    [
        (D("2"), {"A": D("1")}, "OVERSIZED_PARTIAL_ALLOCATION"),
        (D("1"), {"A": D("-1")}, "INCOMPATIBLE_ALLOCATION_SIDE"),
        (D("1"), {"A": D("1"), "B": D("-1")}, "INCOMPATIBLE_ALLOCATION_SIDE"),
    ],
)
def test_invalid_cross_sign_or_overfilled_allocation_fails(quantity, pending, error):
    with pytest.raises(ValueError, match=error):
        _allocate(quantity, pending)
