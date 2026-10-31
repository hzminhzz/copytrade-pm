from decimal import Decimal as D

import pytest

from copytrade_pm.pm36_e1 import size


def call(source, opening_qty, opening_price, marks=None):
    return size(
        source,
        marks or {instrument: D("100") for instrument in source},
        shock={},
        cost_rate=D("0"),
        episode_open_qty=opening_qty,
        episode_open_price=opening_price,
    )


def test_concurrent_episodes_are_independently_normalized():
    assert call(
        {"BTC": D("2"), "ETH": D("-4")},
        {"BTC": D("2"), "ETH": D("-2")},
        {"BTC": D("100"), "ETH": D("50")},
    ) == {"BTC": D("2"), "ETH": D("-8")}


def test_later_source_quantity_transitions_keep_episode_scale_and_sign():
    target = call(
        {"BTC": D("3"), "ETH": D("-1")},
        {"BTC": D("2"), "ETH": D("-2")},
        {"BTC": D("100"), "ETH": D("50")},
    )
    assert target == {"BTC": D("3"), "ETH": D("-2")}


def test_flat_episode_quantity_produces_zero_target():
    assert call(
        {"BTC": D("0")},
        {"BTC": D("2")},
        {"BTC": D("100")},
    ) == {}


def test_missing_episode_anchor_blocks_all_targets():
    with pytest.raises(ValueError, match="MISSING_EPISODE_ANCHOR: ETH"):
        call(
            {"BTC": D("1"), "ETH": D("-1")},
            {"BTC": D("1")},
            {"BTC": D("100"), "ETH": D("50")},
        )


def test_source_sign_flip_is_not_treated_as_a_valid_episode():
    with pytest.raises(ValueError, match="EPISODE_SIGN_FLIP: BTC"):
        call(
            {"BTC": D("-1")},
            {"BTC": D("1")},
            {"BTC": D("100")},
        )
