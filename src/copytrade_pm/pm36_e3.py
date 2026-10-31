"""PM-36 E3: trailing realized-volatility sizing, research-only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from typing import Sequence

HOUR = timedelta(hours=1)
RECENT_HOURS = 7 * 24
REFERENCE_HOURS = 28 * 24
ZERO = D("0")
ONE = D("1")


def _returns(history: Sequence[tuple[datetime, D]], decision_time: datetime) -> dict[datetime, D]:
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("DECISION_TIME_MUST_BE_TIMEZONE_AWARE")
    decision_time = decision_time.astimezone(UTC)
    prices: dict[datetime, D] = {}
    for timestamp, price in history:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("PRICE_TIME_MUST_BE_TIMEZONE_AWARE")
        timestamp = timestamp.astimezone(UTC)
        if not price.is_finite() or price <= ZERO:
            raise ValueError("PRICE_MUST_BE_POSITIVE_AND_FINITE")
        if timestamp >= decision_time:
            continue
        if timestamp in prices:
            raise ValueError("DUPLICATE_PRICE_TIMESTAMP")
        prices[timestamp] = price
    returns: dict[datetime, D] = {}
    for end, price in prices.items():
        previous = prices.get(end - HOUR)
        if previous is not None:
            returns[end] = (price / previous).ln()
    return returns


def _volatility(returns: list[D]) -> D | None:
    if len(returns) < 2:
        return None
    mean = sum(returns, ZERO) / D(len(returns))
    variance = sum(((value - mean) ** 2 for value in returns), ZERO) / D(len(returns))
    return variance.sqrt()


def _multiplier(history: Sequence[tuple[datetime, D]], decision_time: datetime) -> D | None:
    hourly_returns = _returns(history, decision_time)
    decision_utc = decision_time.astimezone(UTC)
    anchor = decision_utc.replace(minute=0, second=0, microsecond=0)
    if anchor == decision_utc:
        anchor -= HOUR
    recent = [hourly_returns.get(anchor - HOUR * offset) for offset in range(RECENT_HOURS)]
    reference = [
        hourly_returns.get(anchor - HOUR * offset)
        for offset in range(RECENT_HOURS, RECENT_HOURS + REFERENCE_HOURS)
    ]
    recent_values = [value for value in recent if value is not None]
    reference_values = [value for value in reference if value is not None]
    if len(recent_values) != RECENT_HOURS or len(reference_values) != REFERENCE_HOURS:
        return None
    recent_vol = _volatility(recent_values)
    reference_vol = _volatility(reference_values)
    if recent_vol is None or reference_vol is None or reference_vol <= ZERO:
        return None
    return min(ONE, reference_vol / recent_vol) if recent_vol > ZERO else ONE


def session_multiplier(history: Sequence[tuple[datetime, D]], decision_time: datetime) -> D | None:
    """PIT 7d/previous-28d volatility ratio; gaps are unknown, never zero.

    Require >=48 actual adjacent hourly returns in 7d and >=192 in the
    preceding 28d. This allows closed HIP-3 sessions without manufacturing
    across-session returns or using any price at/after the decision.
    The multiplier cannot exceed one, and a flat/stale window blocks entry.
    """
    hourly = _returns(history, decision_time)
    anchor = decision_time.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if anchor == decision_time.astimezone(UTC):
        anchor -= HOUR
    recent = [hourly[t] for i in range(RECENT_HOURS) if (t := anchor - HOUR * i) in hourly]
    prior = [
        hourly[t]
        for i in range(RECENT_HOURS, RECENT_HOURS + REFERENCE_HOURS)
        if (t := anchor - HOUR * i) in hourly
    ]
    if len(recent) < 48 or len(prior) < 192:
        return None
    recent_vol = _volatility(recent)
    prior_vol = _volatility(prior)
    if recent_vol is None or prior_vol is None or recent_vol <= ZERO or prior_vol <= ZERO:
        return None
    return min(ONE, prior_vol / recent_vol)


def _reduce_only(current: D, target: D) -> D:
    """Honor same-side/flat reductions only; do not open or reverse without evidence."""
    if current == ZERO:
        return ZERO
    if target == ZERO or current * target < ZERO:
        return ZERO
    return target if abs(target) < abs(current) else current


def size(
    permitted_targets: dict[str, D],
    current: dict[str, D],
    histories: dict[str, Sequence[tuple[datetime, D]]],
    decision_time: datetime,
) -> dict[str, D]:
    """Apply vol scaling to E2 targets; missing evidence blocks increases.

    Histories contain hourly (timestamp, positive price) observations. The 168
    recent returns end at [decision-168h, decision-1h]; the 672 reference
    returns end at [decision-840h, decision-169h], strictly before the recent
    window. On insufficient history, keep current exposure or honor only an
    E2 same-side reduction/flattening.
    """
    if set(permitted_targets) != set(current):
        raise ValueError("CURRENT_AND_PERMITTED_TARGET_UNIVERSES_MUST_MATCH")
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("DECISION_TIME_MUST_BE_TIMEZONE_AWARE")
    result: dict[str, D] = {}
    for instrument, target in permitted_targets.items():
        if not target.is_finite() or not current[instrument].is_finite():
            raise ValueError("TARGETS_MUST_BE_FINITE")
        multiplier = _multiplier(histories.get(instrument, ()), decision_time)
        result[instrument] = (
            _reduce_only(current[instrument], target) if multiplier is None else target * multiplier
        )
    return result
