"""E1 episode-normalized sizing for historical-oracle research only."""

from __future__ import annotations

from decimal import Decimal

EPISODE_NOTIONAL_USD = Decimal("200")
ZERO = Decimal("0")


def size(
    source: dict[str, Decimal],
    marks: dict[str, Decimal],
    *,
    shock: dict[str, Decimal],
    cost_rate: Decimal,
    episode_open_qty: dict[str, Decimal],
    episode_open_price: dict[str, Decimal],
) -> dict[str, Decimal]:
    """Scale each eligible episode to $200 at entry, preserving signed quantity changes.

    Source and anchor mappings are keyed by instrument; source contains only
    explicitly reconstructed eligible episodes. Missing anchors block the
    entire sizing result rather than treating an unknown episode as flat.
    """
    targets: dict[str, Decimal] = {}
    for instrument, quantity in source.items():
        if instrument not in episode_open_qty or instrument not in episode_open_price:
            raise ValueError(f"MISSING_EPISODE_ANCHOR: {instrument}")
        opening_quantity = episode_open_qty[instrument]
        opening_price = episode_open_price[instrument]
        mark = marks.get(instrument)
        if (
            not quantity.is_finite()
            or not opening_quantity.is_finite()
            or not opening_price.is_finite()
            or opening_quantity == ZERO
            or opening_price <= ZERO
            or mark is None
            or not mark.is_finite()
            or mark <= ZERO
        ):
            raise ValueError(f"INVALID_EPISODE_INPUT: {instrument}")
        if quantity != ZERO and (quantity > ZERO) != (opening_quantity > ZERO):
            raise ValueError(f"EPISODE_SIGN_FLIP: {instrument}")
        target = quantity * EPISODE_NOTIONAL_USD / (abs(opening_quantity) * opening_price)
        if target != ZERO:
            targets[instrument] = target
    return targets
