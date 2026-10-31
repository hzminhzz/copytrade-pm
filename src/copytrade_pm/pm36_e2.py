"""PM36 E2: aggregate conservative stress-cap sizing (historical research only)."""

from __future__ import annotations

from decimal import Decimal

STRESS_CAP_USD = Decimal("60")
_ZERO = Decimal(0)
_ONE = Decimal(1)


def _validate(
    quantities: dict[str, Decimal],
    marks: dict[str, Decimal],
    shock: dict[str, Decimal],
    cost_rate: Decimal,
) -> None:
    instruments = set(quantities)
    if set(marks) != instruments or set(shock) != instruments:
        raise ValueError("INCOMPLETE_OR_EXTRA_RISK_INPUTS")
    for instrument, quantity in quantities.items():
        if not isinstance(instrument, str) or not instrument:
            raise ValueError("INVALID_INSTRUMENT")
        if not isinstance(quantity, Decimal) or not quantity.is_finite():
            raise ValueError("INVALID_SOURCE_QUANTITY")
        mark = marks[instrument]
        move = shock[instrument]
        if not isinstance(mark, Decimal) or not mark.is_finite() or mark <= 0:
            raise ValueError("INVALID_MARK")
        if not isinstance(move, Decimal) or not move.is_finite() or move < 0:
            raise ValueError("INVALID_SHOCK")
    if not isinstance(cost_rate, Decimal) or not cost_rate.is_finite() or cost_rate < 0:
        raise ValueError("INVALID_COST_RATE")


def risk_charge(
    quantities: dict[str, Decimal],
    marks: dict[str, Decimal],
    *,
    shock: dict[str, Decimal],
    cost_rate: Decimal,
) -> Decimal:
    """Aggregate legwise adverse stress plus costs on target notional."""
    _validate(quantities, marks, shock, cost_rate)
    return sum(
        (
            abs(quantity) * marks[instrument] * (abs(shock[instrument]) + cost_rate)
            for instrument, quantity in quantities.items()
        ),
        _ZERO,
    )


def risk_utilization(
    quantities: dict[str, Decimal],
    marks: dict[str, Decimal],
    *,
    shock: dict[str, Decimal],
    cost_rate: Decimal,
) -> Decimal:
    """Return aggregate stress-plus-cost usage as a fraction of the $60 cap."""
    return risk_charge(quantities, marks, shock=shock, cost_rate=cost_rate) / STRESS_CAP_USD


def size(
    source: dict[str, Decimal],
    marks: dict[str, Decimal],
    *,
    shock: dict[str, Decimal],
    cost_rate: Decimal,
) -> dict[str, Decimal]:
    """Scale signed source positions together to fit the single aggregate cap."""
    charge = risk_charge(source, marks, shock=shock, cost_rate=cost_rate)
    multiplier = min(_ONE, STRESS_CAP_USD / charge) if charge else _ONE
    targets = {instrument: quantity * multiplier for instrument, quantity in source.items()}
    while risk_charge(targets, marks, shock=shock, cost_rate=cost_rate) > STRESS_CAP_USD:
        multiplier = multiplier.next_minus()
        targets = {instrument: quantity * multiplier for instrument, quantity in source.items()}
    return targets
