"""Vike fill-subscription preflight must not silently inherit $1,000 floor."""

import pytest

from copytrade_pm.pm_vike_contract import verify_fill_subscription


WALLET = "0x" + "a" * 40


def response(filter_):
    return {
        "valid": True,
        "subscribe": {
            "action": "subscribe",
            "channel": "hl.fills",
            "filter": {"wallet": [WALLET], **filter_},
        },
    }


def test_explicit_zero_echo_is_only_preflight_not_production():
    verdict = verify_fill_subscription(response({"min_usd": 0}), [WALLET])
    assert verdict["status"] == "PREFLIGHT_ONLY"
    assert verdict["production_admitted"] is False
    assert verdict["rest_ws_parity"] == "UNVERIFIED"


@pytest.mark.parametrize("filters", [{}, {"min_usd": 1000}, {"min_usd": True}, {"min_usd": "0"}])
def test_missing_or_ambiguous_small_fill_floor_fails_closed(filters):
    with pytest.raises(ValueError, match="VIKE_SMALL_FILL_INCLUSION_UNVERIFIED"):
        verify_fill_subscription(response(filters), [WALLET])


def test_valid_but_wrong_wallet_fails():
    with pytest.raises(ValueError, match="VIKE_SUBSCRIPTION_WALLETS_MISMATCH"):
        verify_fill_subscription(
            {"valid": True, "subscribe": {
                "action": "subscribe", "channel": "hl.fills",
                "filter": {"wallet": ["0x" + "b" * 40], "min_usd": 0},
            }},
            [WALLET],
        )


def test_invalid_subscription_refused():
    with pytest.raises(ValueError, match="VIKE_SUBSCRIPTION_NOT_VALIDATED"):
        verify_fill_subscription({"valid": False}, [WALLET])


def test_empty_or_duplicate_wallets_refused():
    for wallets in [[], [WALLET, WALLET]]:
        with pytest.raises(ValueError, match="VIKE_WALLET_SET_EMPTY_OR_DUPLICATED"):
            verify_fill_subscription(response({"min_usd": 0}), wallets)
